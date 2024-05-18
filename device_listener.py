from datastructures import WaveFormat

class DeviceListener:
    def __init__(self, device):
        pass

    def run(self):
        pass

    def set_on_change(self, function):
        pass

    def read_wave_format(self):
        return WaveFormat(channels=None, sample_format=None, sample_rate=None)


