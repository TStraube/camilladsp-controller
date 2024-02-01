import sys
import time
import select
import threading

from dataclasses import dataclass
from enum import Enum

from pyalsa import alsahcontrol

LOOPBACK_ACTIVE = "PCM Slave Active"
LOOPBACK_CHANNELS = "PCM Slave Channels"
LOOPBACK_FORMAT = "PCM Slave Format"
LOOPBACK_RATE = "PCM Slave Rate"
LOOPBACK_VOLUME = "PCM Playback Volume"
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


@dataclass
class DeviceParameters:
    active: bool | None
    sample_rate: int | None
    sample_format: SampleFormat | None
    channels: int | None
    volume: float | None

class ControlListener:
    def __init__(self, device):
        self.get_card_device_subdevice(device)
        self.hctl = alsahcontrol.HControl(
            self._card, mode=alsahcontrol.open_mode["NONBLOCK"]
        )

        self.all_device_controls = self.hctl.list()

        self._controls = {}
        self._controls["Active"] = self.find_element(LOOPBACK_ACTIVE, INTERFACE_PCM)
        self._controls["Channels"] = self.find_element(LOOPBACK_CHANNELS, INTERFACE_PCM)
        self._controls["Format"] = self.find_element(LOOPBACK_FORMAT, INTERFACE_PCM)
        self._controls["Rate"] = self.find_element(LOOPBACK_RATE, INTERFACE_PCM)
        if self._controls["Rate"] is None:
            self._controls["Rate"] = self.find_element(GADGET_CAP_RATE, INTERFACE_PCM)
        self._controls["Volume"] = self.find_element(LOOPBACK_VOLUME, INTERFACE_MIXER, device=0, subdevice=0)

        self._control_elements = {}
        for desc, control in self._controls.items():
            if control is not None:
                element = alsahcontrol.Element(self.hctl, control)
                element.set_callback(self)
                self._control_elements[control] = {"element": element, "events": []}

        self._new_events = False
        self._is_removed = False
        self._is_inactive = False

        self.poller = select.poll()
        for fd in self.hctl.poll_fds:
            self.poller.register(fd[0], fd[1])

        self.on_change = None

        self.debounce_time = 0.01

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
        if mask == EVENT_REMOVE:
            #TODO check if this is relevant for loopback and gadget
            self._is_removed = True
        elif mask & EVENT_INFO:
            #TODO check if this is relevant for loopback and gadget
            info = alsahcontrol.Info(el)
            if info.is_inactive:
                self._is_inactive = True
        elif mask & EVENT_VALUE:
            val = self.read_value(el)
            self._new_events = True
            if el.numid in self._control_elements:
                self._control_elements[el.numid]["events"].append(val)

    def read_control_value(self, name):
        control = self._controls[name]
        if control is None:
            return None
        value = self.read_value(self._control_elements[control]["element"])
        if name == "Format":
            return SampleFormat(value)
        return value

    def read_all(self):
        active =  self.read_control_value("Active")
        rate =  self.read_control_value("Rate")
        channels =  self.read_control_value("Channels")
        sample_format = self.read_control_value("Format")
        volume = self.read_control_value("Volume")
        #TODO check if these are relevant for loopback and gadget
        #print(f"Removed: {self._is_removed}, inactive: {self._is_inactive}")
        return DeviceParameters(active=active, sample_rate=rate, sample_format=sample_format, channels=channels, volume=volume)


    def pollingloop(self):
        while True:
            print("loop")
            #time.sleep(0.001)
            pollres = self.poller.poll()
            if pollres:
                self.hctl.handle_events()

    def run(self):
        th = threading.Thread(target=self.pollingloop, daemon=True)
        th.start()
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
                    params = self.read_all()
                    self.on_change(params)

                self._new_events = False


    def set_on_change(self, function):
        self.on_change = function


if __name__ == "__main__":
    listener = ControlListener("hw:Loopback,1,0")
    def notifier(params):
        print(params)
    listener.set_on_change(notifier)
    listener.run()
