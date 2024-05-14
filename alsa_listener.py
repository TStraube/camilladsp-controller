import sys
import time
import select
import threading
from copy import deepcopy
from typing import Callable

from dataclasses import dataclass
from enum import Enum

from pyalsa import alsahcontrol

from datastructures import WaveFormat, DeviceEvent

LOOPBACK_ACTIVE = "PCM Slave Active"
LOOPBACK_CHANNELS = "PCM Slave Channels"
LOOPBACK_FORMAT = "PCM Slave Format"
LOOPBACK_RATE = "PCM Slave Rate"
GADGET_CAP_RATE = "Capture Rate"

INTERFACE_PCM = alsahcontrol.interface_id["PCM"]
INTERFACE_MIXER = alsahcontrol.interface_id["MIXER"]


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





@dataclass
class Control:
    index: int | None
    element: alsahcontrol.Element | None
    value_transform_func: Callable | None


class ControlListener:
    def __init__(self, device, debounce_time=0.05):

        self.on_change = None

        self.debounce_time = debounce_time
        self.get_card_device_subdevice(device)

        self.hctl = alsahcontrol.HControl(
            self._card, mode=alsahcontrol.open_mode["NONBLOCK"]
        )

        self.all_device_controls = self.hctl.list()

        self.ctl_loopback_active = self.find_control(LOOPBACK_ACTIVE, INTERFACE_PCM)
        self.ctl_loopback_channels = self.find_control(LOOPBACK_CHANNELS, INTERFACE_PCM)
        self.ctl_loopback_format = self.find_control(
            LOOPBACK_FORMAT, INTERFACE_PCM, value_transform_func=SampleFormat
        )
        self.ctl_loopback_rate = self.find_control(LOOPBACK_RATE, INTERFACE_PCM)
        self.ctl_gadget_rate = self.find_control(GADGET_CAP_RATE, INTERFACE_PCM)

        self.poller = select.poll()
        self.hctl.register_poll(self.poller)

        self.poll_thread = None
        self.wave_format = self.read_wave_format()
        self.is_active = self.check_if_active()

    def find_control(self, name, interface, value_transform_func=None):
        index = self.find_element(name, interface)
        if index is None:
            return None
        element = alsahcontrol.Element(self.hctl, index)
        if element is None:
            return None
        return Control(
            index=index, element=element, value_transform_func=value_transform_func
        )

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
            device = self.device_nbr
        if subdevice is None:
            subdevice = self.subdev_nbr
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

    def read_element_value(self, elem):
        if elem is None:
            return None
        info = alsahcontrol.Info(elem)
        val = alsahcontrol.Value(elem)
        values = val.get_tuple(info.type, info.count)
        val.set_tuple(info.type, values)
        val.read()
        return values[0]

    def read_control_value(self, ctl: Control | None):
        if ctl is None:
            return None
        value = self.read_element_value(ctl.element)
        if ctl.value_transform_func is not None:
            return ctl.value_transform_func(value)
        return value

    def check_if_active(self):
        gadget_rate = self.read_control_value(self.ctl_gadget_rate)
        if gadget_rate is not None:
            return gadget_rate > 0
        return self.read_control_value(self.ctl_loopback_active)

    def read_wave_format(self):
        loopback_rate = self.read_control_value(self.ctl_loopback_rate)
        loopback_channels = self.read_control_value(self.ctl_loopback_channels)
        loopback_format = self.read_control_value(self.ctl_loopback_format)
        gadget_rate = self.read_control_value(self.ctl_gadget_rate)
        if gadget_rate is not None:
            return WaveFormat(
                sample_format=None, channels=None, sample_rate=gadget_rate
            )
        return WaveFormat(
            sample_format=alsa_format_to_cdsp(loopback_format),
            channels=loopback_channels,
            sample_rate=loopback_rate,
        )

    def determine_action(self):
        new_wave_format = self.read_wave_format()
        new_active = self.check_if_active()
        if not self.is_active and new_active:
            self.is_active = True
            event = DeviceEvent.STARTED
            event.set_data(deepcopy(new_wave_format))
            self.emit_event(event)
        elif self.is_active and not new_active:
            self.is_active = False
            event = DeviceEvent.STOPPED
            self.emit_event(event)
        elif self.is_active and new_active and self.wave_format != new_wave_format:
            stop_event = DeviceEvent.STOPPED
            self.emit_event(stop_event)
            start_event = DeviceEvent.STARTED
            start_event.set_data(deepcopy(new_wave_format))
            self.emit_event(start_event)
        self.wave_format = new_wave_format

    def emit_event(self, event):
        if self.on_change is not None:
            self.on_change(event)

    def pollingloop(self):
        while True:
            pollres = self.poller.poll()
            if pollres:
                time.sleep(self.debounce_time)
                self.hctl.handle_events()
                self.determine_action()

    def run(self):
        self.poll_thread = threading.Thread(target=self.pollingloop, daemon=True)
        self.poll_thread.start()

    def set_on_change(self, function):
        self.on_change = function


if __name__ == "__main__":
    device = sys.argv[1]
    listener = ControlListener(device, debounce_time=0.05)

    def notifier(params):
        print(params, params.data)

    listener.set_on_change(notifier)
    listener.run()
    while True:
        time.sleep(10)
