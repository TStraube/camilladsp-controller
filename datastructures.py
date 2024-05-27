from enum import Enum, auto
from dataclasses import dataclass

class DeviceEvent(Enum):
    """
    Enum represending the events a device listener can send.
    """
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
        """
        Getter for the data property
        """
        return self._data


@dataclass
class WaveFormat:
    """
    A class representing a wave format, that consists of the sample rate,
    sample format and number of channels.
    """
    sample_rate: int | None
    sample_format: str | None
    channels: int | None