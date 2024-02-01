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

        self._ctl_active = self.find_element(LOOPBACK_ACTIVE, INTERFACE_PCM)
        self._ctl_channels = self.find_element(LOOPBACK_CHANNELS, INTERFACE_PCM)
        self._ctl_format = self.find_element(LOOPBACK_FORMAT, INTERFACE_PCM)
        self._ctl_rate = self.find_element(LOOPBACK_RATE, INTERFACE_PCM)
        if self._ctl_rate is None:
            self._ctl_rate = self.find_element(GADGET_CAP_RATE, INTERFACE_PCM)
        self._ctl_volume = self.find_element(LOOPBACK_VOLUME, INTERFACE_MIXER, device=0, subdevice=0)

        self._elem_active = None
        self._elem_channels = None
        self._elem_format = None
        self._elem_rate = None
        self._elem_volume = None

        if self._ctl_active is not None:
            self._elem_active = alsahcontrol.Element(self.hctl, self._ctl_active)
            self._elem_active.set_callback(self)
        if self._ctl_channels is not None:
            self._elem_channels = alsahcontrol.Element(self.hctl, self._ctl_channels)
            self._elem_channels.set_callback(self)
        if self._ctl_format is not None:
            self._elem_format = alsahcontrol.Element(self.hctl, self._ctl_format)
            self._elem_format.set_callback(self)
        if self._ctl_rate is not None:
            self._elem_rate = alsahcontrol.Element(self.hctl, self._ctl_rate)
            self._elem_rate.set_callback(self)
        if self._ctl_volume is not None:
            self._elem_volume = alsahcontrol.Element(self.hctl, self._ctl_volume)
            self._elem_volume.set_callback(self)

        self._active_events = []
        self._channels_events = []
        self._format_events = []
        self._rate_events = []
        self._volume_events = []
        self._new_events = False
        self._is_active = True

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
            #print("search", idx, dev, subdev, name)
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
            self._is_active = False
        elif mask & EVENT_INFO:
            info = alsahcontrol.Info(el)
            if info.is_inactive:
                self._is_active = False
        elif mask & EVENT_VALUE:
            val = self.read_value(el)
            self._new_events = True
            if el.numid == self._ctl_active:
                self._active_events.append(val)
            elif el.numid == self._ctl_channels:
                self._channels_events.append(val)
            elif el.numid == self._ctl_format:
                self._format_events.append(val)
            elif el.numid == self._ctl_rate:
                self._rate_events.append(val)
            elif el.numid == self._ctl_volume:
                self._volume_events.append(val)


    def read_all(self):
        active =  self.read_value(self._elem_active)
        rate =  self.read_value(self._elem_rate)
        channels = self.read_value(self._elem_channels)
        sample_format = SampleFormat(self.read_value(self._elem_format))
        volume = self.read_value(self._elem_volume)
        return DeviceParameters(active=active, sample_rate=rate, sample_format=sample_format, channels=channels, volume=volume)


    def pollingloop(self):
        while True:
            time.sleep(0.001)
            pollres = self.poller.poll()
            #print("poll result:", pollres)
            if pollres:
                #print("handling events")
                self.hctl.handle_events()

    def run(self):
        th = threading.Thread(target=self.pollingloop, daemon=True)
        th.start()
        while True:
            time.sleep(0.1)
            if self._new_events:
                time.sleep(self.debounce_time)
                #self.print_all()
                while self._active_events:
                    value = self._active_events.pop(0)
                    print("Active changed to", value)
                while self._channels_events:
                    value = self._channels_events.pop(0)
                    print("Channels changed to", value)
                while self._format_events:
                    value = self._format_events.pop(0)
                    print("Format changed to", SampleFormat(value))
                while self._rate_events:
                    value = self._rate_events.pop(0)
                    print("Rate changed to", value)
                while self._volume_events:
                    value = self._volume_events.pop(0)
                    print("Volume changed to", value)

                if self.on_change is not None:
                    params = self.read_all()
                    self.on_change(params)

                self._new_events = False
                # print("loop", self._active_events, self._rate_events, self._format_events, self._channels_events)

    def set_on_change(self, function):
        self.on_change = function


def print_params(params):
    print("--- Current values ---")
    print("Active:", params.active)
    print("Rate:", params.sample_rate)
    print("Channels:", params.channels)
    print("Format:", params.sample_format)
    print("Volume:", params.volume)
    print()

if __name__ == "__main__":
    listener = ControlListener("hw:Loopback,1,0")
    def notifier(params):
        print_params(params)
    listener.set_on_change(notifier)
    listener.run()
