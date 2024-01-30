from pyalsa import alsahcontrol
import sys
import time
import select
import threading

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

SAMPLE_FORMATS_BY_NAME = {
    "S8": 0,
    "U8": 1,
    "S16_LE": 2,
    "S16_BE": 3,
    "U16_LE": 4,
    "U16_BE": 5,
    "S24_LE": 6,
    "S24_BE": 7,
    "U24_LE": 8,
    "U24_BE": 9,
    "S32_LE": 10,
    "S32_BE": 11,
    "U32_LE": 12,
    "U32_BE": 13,
    "FLOAT_LE": 14,
    "FLOAT_BE": 15,
    "FLOAT64_LE": 16,
    "FLOAT64_BE": 17,
    "IEC958_SUBFRAME_LE": 18,
    "IEC958_SUBFRAME_BE": 19,
    "MU_LAW": 20,
    "A_LAW": 21,
    "IMA_ADPCM": 22,
    "MPEG": 23,
    "GSM": 24,
    "S20_LE": 25,
    "S20_BE": 26,
    "U20_LE": 27,
    "U20_BE": 28,
    "SPECIAL": 31,
    "S24_3LE": 32,
    "S24_3BE": 33,
    "U24_3LE": 34,
    "U24_3BE": 35,
    "S20_3LE": 36,
    "S20_3BE": 37,
    "U20_3LE": 38,
    "U20_3BE": 39,
    "S18_3LE": 40,
    "S18_3BE": 41,
    "U18_3LE": 42,
    "U18_3BE": 43,
    "G723_24": 44,
    "G723_24_1B": 45,
    "G723_40": 46,
    "G723_40_1B": 47,
    "DSD_U8": 48,
    "DSD_U16_LE": 49,
    "DSD_U32_LE": 50,
    "DSD_U16_BE": 51,
    "DSD_U32_BE": 52,
}

SAMPLE_FORMATS_BY_NUMBER = {nbr: desc for desc, nbr in SAMPLE_FORMATS_BY_NAME.items()}


class ControlListener:
    def __init__(self, device):
        self.get_card_device_subdevice(device)
        self.hctl = alsahcontrol.HControl(
            self._card, mode=alsahcontrol.open_mode["NONBLOCK"]
        )

        self.elements = self.hctl.list()

        self._active = self.find_element(LOOPBACK_ACTIVE, INTERFACE_PCM)
        self._channels = self.find_element(LOOPBACK_CHANNELS, INTERFACE_PCM)
        self._format = self.find_element(LOOPBACK_FORMAT, INTERFACE_PCM)
        self._rate = self.find_element(LOOPBACK_RATE, INTERFACE_PCM)
        if self._rate is None:
            self._rate = self.find_element(GADGET_CAP_RATE, INTERFACE_PCM)

        self._volume = self.find_element(LOOPBACK_VOLUME, INTERFACE_MIXER, device=0, subdevice=0)

        self._active_elem = None
        self._channels_elem = None
        self._format_elem = None
        self._rate_elem = None
        self._volume_elem = None

        if self._active is not None:
            self._active_elem = alsahcontrol.Element(self.hctl, self._active)
            self._active_elem.set_callback(self)
        if self._channels is not None:
            self._channels_elem = alsahcontrol.Element(self.hctl, self._channels)
            self._channels_elem.set_callback(self)
        if self._format is not None:
            self._format_elem = alsahcontrol.Element(self.hctl, self._format)
            self._format_elem.set_callback(self)
        if self._rate is not None:
            self._rate_elem = alsahcontrol.Element(self.hctl, self._rate)
            self._rate_elem.set_callback(self)
        if self._volume is not None:
            self._volume_elem = alsahcontrol.Element(self.hctl, self._volume)
            self._volume_elem.set_callback(self)

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
        for idx, iface, dev, subdev, name, _ in self.elements:
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
            if el.numid == self._active:
                self._active_events.append(val)
            elif el.numid == self._channels:
                self._channels_events.append(val)
            elif el.numid == self._format:
                self._format_events.append(val)
            elif el.numid == self._rate:
                self._rate_events.append(val)


    def read_all(self):
        active =  self.read_value(self._active_elem)
        rate =  self.read_value(self._rate_elem)
        channels = self.read_value(self._channels_elem)
        sample_format = SAMPLE_FORMATS_BY_NUMBER.get(self.read_value(self._format_elem))
        volume = self.read_value(self._volume_elem)
        return (active, rate, channels, sample_format, volume)

    def print_all(self):
        (active, rate, channels, sample_format, volume) = self.read_all()
        print("--- Current values ---")
        print("Active:", active)
        print("Rate:", rate)
        print("Channels:", channels)
        print("Format:", sample_format)
        print("Volume:", volume)
        print()

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
                #self.print_all()
                while self._active_events:
                    value = self._active_events.pop()
                    print("Active changed to", value)
                while self._channels_events:
                    value = self._channels_events.pop()
                    print("Channels changed to", value)
                while self._format_events:
                    value = self._format_events.pop()
                    print("Format changed to", SAMPLE_FORMATS_BY_NUMBER.get(value))
                while self._rate_events:
                    value = self._rate_events.pop()
                    print("Rate changed to", value)
                while self._volume_events:
                    value = self._volume_events.pop()
                    print("Volume changed to", value)


                self._new_events = False
                # print("loop", self._active_events, self._rate_events, self._format_events, self._channels_events)


if __name__ == "__main__":
    listener = ControlListener("hw:Loopback,1,0")
    listener.run()
