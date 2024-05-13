import sys
import time
import select
import threading

from dataclasses import dataclass
from enum import Enum, auto

from pyalsa import alsahcontrol

LOOPBACK_ACTIVE = "PCM Slave Active"
LOOPBACK_CHANNELS = "PCM Slave Channels"
LOOPBACK_FORMAT = "PCM Slave Format"
LOOPBACK_RATE = "PCM Slave Rate"
#LOOPBACK_VOLUME = "PCM Playback Volume"
GADGET_PB_RATE = "Playback Rate"
GADGET_CAP_RATE = "Capture Rate"

INTERFACE_PCM = alsahcontrol.interface_id["PCM"]
INTERFACE_MIXER = alsahcontrol.interface_id['MIXER']
EVENT_VALUE = alsahcontrol.event_mask["VALUE"]
EVENT_INFO = alsahcontrol.event_mask["INFO"]
EVENT_REMOVE = alsahcontrol.event_mask_remove

class SampleFormat(Enum):
    S8 = 0
    U8 = 1
    S16_LE = 2
    S16_BE = 3
    U16_LE = 4
    U16_BE = 5
    S24_LE = 6
    S24_BE = 7
    U24_LE = 8
    U24_BE = 9
    S32_LE = 10
    S32_BE = 11
    U32_LE = 12
    U32_BE = 13
    FLOAT_LE = 14
    FLOAT_BE = 15
    FLOAT64_LE = 16
    FLOAT64_BE = 17
    IEC958_SUBFRAME_LE = 18
    IEC958_SUBFRAME_BE = 19
    MU_LAW = 20
    A_LAW = 21
    IMA_ADPCM = 22
    MPEG = 23
    GSM = 24
    S20_LE = 25
    S20_BE = 26
    U20_LE = 27
    U20_BE = 28
    SPECIAL = 31
    S24_3LE = 32
    S24_3BE = 33
    U24_3LE = 34
    U24_3BE = 35
    S20_3LE = 36
    S20_3BE = 37
    U20_3LE = 38
    U20_3BE = 39
    S18_3LE = 40
    S18_3BE = 41
    U18_3LE = 42
    U18_3BE = 43
    G723_24 = 44
    G723_24_1B = 45
    G723_40 = 46
    G723_40_1B = 47
    DSD_U8 = 48
    DSD_U16_LE = 49
    DSD_U32_LE = 50
    DSD_U16_BE = 51
    DSD_U32_BE = 52

def alsa_format_to_cdsp(fmt):
    if fmt == SampleFormat.S16_LE:
        return "S16LE"
    if fmt == SampleFormat.S24_3LE:
        return "S24LE3"
    if fmt == SampleFormat.S24_LE:
        return "S24LE"
    if fmt == SampleFormat.S32_LE:
        return "S32LE"
    if fmt == SampleFormat.FLOAT_LE:
        return "FLOAT32LE"
    if fmt == SampleFormat.FLOAT64_LE:
        return "FLOAT64LE"


class DeviceEvent(Enum):

    STOPPED = auto()
    STARTED = auto()

    def __new__(cls, value):
        obj = object.__new__(cls)
        obj._value_ = value
        obj._data = None
        return obj

    def set_data(self, value):
        """
        Set the custom data property of the enum.
        """
        self._data = value

    @property
    def data(self):
        """Getter for the data property"""
        return self._data

@dataclass
class WaveFormat:
    sample_rate: int | None
    sample_format: str | None
    channels: int | None


class ControlListener:
    def __init__(self, device):
        self.get_card_device_subdevice(device)
        self.hctl = alsahcontrol.HControl(
            self._card, mode=alsahcontrol.open_mode["NONBLOCK"]
        )

        self.all_device_controls = self.hctl.list()

        self._controls = {}
        self._controls["Loopback Active"] = {"index": self.find_element(LOOPBACK_ACTIVE, INTERFACE_PCM), "element": None}
        self._controls["Loopback Channels"] = {"index": self.find_element(LOOPBACK_CHANNELS, INTERFACE_PCM), "element": None}
        self._controls["Loopback Format"] = {"index": self.find_element(LOOPBACK_FORMAT, INTERFACE_PCM), "element": None}
        self._controls["Loopback Rate"] = {"index": self.find_element(LOOPBACK_RATE, INTERFACE_PCM), "element": None}
        self._controls["Gadget Rate"] = {"index": self.find_element(GADGET_CAP_RATE, INTERFACE_PCM), "element": None}
        #self._controls["Volume"] = self.find_element(LOOPBACK_VOLUME, INTERFACE_MIXER, device=0, subdevice=0)

        for desc, control in self._controls.items():
            if control["index"] is not None:
                element = alsahcontrol.Element(self.hctl, control["index"])
                element.set_callback(self)
                control["element"] = element
                print(desc, control)

        self._new_events = False
        self._is_removed = False
        self._is_inactive = False

        self.poller = select.poll()
        for fd in self.hctl.poll_fds:
            self.poller.register(fd[0], fd[1])

        self.on_change = None

        self.debounce_time = 0.01

        self.poll_thread = None
        self.handler_thread = None
        self.wave_format = self.read_wave_format()
        print(self.wave_format)

    def get_card_device_subdevice(self, dev):
        parts = dev.split(",")
        if len(parts) >= 3:
            self.subdev_nbr = int(parts[2])
        else:
            self.subdev_nbr = 0
        if len(parts) >= 2:
            self.device_nbr = int(parts[1])
        else:
            self.device_nbr = 0
        self._card = parts[0]

    def find_element(self, wanted_name, interface, device=None, subdevice=None):
        if device is None:
            device=self.device_nbr
        if subdevice is None:
            subdevice=self.subdev_nbr
        found = None
        for idx, iface, dev, subdev, name, _ in self.all_device_controls:
            if (
                name == wanted_name
                and dev == device
                and subdev == subdevice
                and iface == interface
            ):
                found = idx
                print(f"Found control '{wanted_name}' with index {idx}")
                break
        return found

    def read_value(self, elem):
        if elem is None:
            return None
        info = alsahcontrol.Info(elem)
        val = alsahcontrol.Value(elem)
        values = val.get_tuple(info.type, info.count)
        val.set_tuple(info.type, values)
        val.read()
        return values[0]

    def callback(self, el, mask):
        print("hctl callback")
        if mask == EVENT_REMOVE:
            #TODO check if this is relevant for loopback and gadget
            self._is_removed = True
        elif mask & EVENT_INFO:
            #TODO check if this is relevant for loopback and gadget
            info = alsahcontrol.Info(el)
            if info.is_inactive:
                self._is_inactive = True
        elif mask & EVENT_VALUE:
            self.determine_action(el)


    def determine_action(self, element):
        value = self.read_value(element)
        if self._controls["Loopback Format"]["element"] is not None and self._controls["Loopback Format"]["element"].numid == el.numid:
            self.wave_format.sample_format = alsa_format_to_cdsp(SampleFormat(value))
            print("Changed Loopback format")
        elif self._controls["Loopback Rate"]["element"] is not None and self._controls["Loopback Rate"]["element"].numid == el.numid:
            self.wave_format.sample_rate = value
            print("Changed Loopback rate")
        elif self._controls["Loopback Channels"]["element"] is not None and self._controls["Loopback Channels"]["element"].numid == el.numid:
            self.wave_format.channels = value
            print("Changed Loopback channels")
        elif self._controls["Loopback Active"]["element"] is not None and self._controls["Loopback Active"]["element"].numid == el.numid:
            if value:
                self.emit_event(DeviceEvent.STARTED(self.wave_format))
                print("Loopback active", self.wave_format)
            else:
                self.emit_event(DeviceEvent.STOPPED)
                print("Loopback inactive")
        elif self._controls["Gadget Rate"]["element"] is not None and self._controls["Gadget Rate"]["element"].numid == el.numid:
            self.wave_format.sample_rate = value
            if value > 0:
                self.emit_event(DeviceEvent.STARTED(self.wave_format))
                print("Gadget active", self.wave_format)
            else:
                self.emit_event(DeviceEvent.STOPPED)
                print("Gadget inactive")

    def emit_event(self, event):
        if self.on_change is not None:
            self.on_change(event)

    def read_control_value(self, name):
        element = self._controls[name]["element"]
        if element is None:
            return None
        value = self.read_value(element)
        if name.endswith("Format"):
            return SampleFormat(value)
        return value

    def read_wave_format(self):
        loopback_rate =  self.read_control_value("Loopback Rate")
        loopback_channels =  self.read_control_value("Loopback Channels")
        loopback_format = self.read_control_value("Loopback Format")
        gadget_rate =  self.read_control_value("Gadget Rate")
        if gadget_rate is not None:
            return WaveFormat(sample_format=None, channels=None, sample_rate=gadget_rate)
        return WaveFormat(sample_format=alsa_format_to_cdsp(loopback_format), channels=loopback_channels, sample_rate=loopback_rate) 

    def pollingloop(self):
        while True:
            print("got some event(s)")
            #time.sleep(0.001)
            pollres = self.poller.poll()
            if pollres:
                self.hctl.handle_events()

    def run(self):
        self.poll_thread = threading.Thread(target=self.pollingloop, daemon=True)
        self.poll_thread.start()
        #self.handler_thread = threading.Thread(target=self.event_handler, daemon=True)
        #self.handler_thread.start()

    def event_handler(self):
        device_params = self.read_all()
        while True:
            time.sleep(0.1)
            if self._new_events:
                time.sleep(self.debounce_time)
                for desc, control in self._controls.items():
                    if control is None:
                        continue
                    data = self._control_elements[control]
                    while data["events"]:
                        value = data["events"].pop(0)
                        print(f"{desc} changed to", value)

                if self.on_change is not None:
                    print("callback..")
                    params = self.read_all()
                    self.set_device_event(params, device_params)
                    device_params = params
                    self.on_change(params)

                self._new_events = False

    def set_on_change(self, function):
        self.on_change = function


if __name__ == "__main__":
    device = sys.argv[1]
    listener = ControlListener(device)
    def notifier(params):
        print(params)
    listener.set_on_change(notifier)
    listener.run()
    input("press enter to exit")
