import soundcard as sc
from  soundcard import coreaudio as ca

from datastructures import WaveFormat
from device_listener import DeviceListener

kAudioStreamPropertyPhysicalFormat= int.from_bytes(b'pft ', byteorder='big')

class CAListener(DeviceListener):
    def __init__(self, device):
        self.device_id = sc.get_microphone(device).id

    def read_wave_format(self):
        asbd = ca._CoreAudio.get_property(
            self.device_id,
            kAudioStreamPropertyPhysicalFormat,
            "AudioStreamBasicDescription", scope=ca._cac.kAudioObjectPropertyScopeGlobal)
        return WaveFormat(channels=asbd[0].mChannelsPerFrame, sample_rate=int(asbd[0].mSampleRate), sample_format=None)