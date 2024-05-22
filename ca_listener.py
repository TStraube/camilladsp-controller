import cffi

from datastructures import WaveFormat, DeviceEvent
from device_listener import DeviceListener

HEADERS = """

// from /System/Library/Frameworks/CoreFoundation/CFBase.h:
typedef unsigned char           Boolean;
typedef signed short            SInt16;
typedef unsigned int            UInt32;
typedef signed int              SInt32;
typedef SInt32                  OSStatus;
typedef double                  Float64;

typedef signed long long CFIndex;
typedef const void * CFStringRef;


// from /System/Library/Frameworks/CoreFoundation/CFString.h
typedef UInt32 CFStringEncoding;

CFIndex CFStringGetLength(CFStringRef theString);
Boolean CFStringGetCString(CFStringRef theString, char *buffer, CFIndex bufferSize, CFStringEncoding encoding);


// from /System/Library/Frameworks/CoreAudio/AudioHardwareBase.h
typedef UInt32  AudioObjectID;
typedef UInt32  AudioObjectPropertySelector;
typedef UInt32  AudioObjectPropertyScope;
typedef UInt32  AudioObjectPropertyElement;

struct  AudioObjectPropertyAddress
{
    AudioObjectPropertySelector mSelector;
    AudioObjectPropertyScope    mScope;
    AudioObjectPropertyElement  mElement;
};
typedef struct AudioObjectPropertyAddress AudioObjectPropertyAddress;


// from /System/Library/Frameworks/CoreAudio/AudioHardware.h
OSStatus AudioObjectGetPropertyDataSize(AudioObjectID inObjectID,
                                        const AudioObjectPropertyAddress* inAddress,
                                        UInt32 inQualifierDataSize,
                                        const void* inQualifierData,
                                        UInt32* outDataSize);
OSStatus AudioObjectGetPropertyData(AudioObjectID inObjectID,
                                    const AudioObjectPropertyAddress* inAddress,
                                    UInt32 inQualifierDataSize,
                                    const void* inQualifierData,
                                    UInt32* ioDataSize,
                                    void* outData);

typedef OSStatus (*AudioObjectPropertyListenerProc)(AudioObjectID inObjectID,
                                                    UInt32 inNumberAddresses,
                                                    void *inAddresses,
                                                    void *inClientData);

OSStatus AudioObjectAddPropertyListener(AudioObjectID inObjectID,
                                        const AudioObjectPropertyAddress *inAddress,
                                        AudioObjectPropertyListenerProc inListener,
                                        void *inClientData);

OSStatus AudioObjectRemovePropertyListener(AudioObjectID inObjectID,
                                        const AudioObjectPropertyAddress *inAddress,
                                        AudioObjectPropertyListenerProc inListener,
                                        void *inClientData);

                                        
// from /System/Library/Frameworks/CoreAudioTypes.h
typedef UInt32	AudioFormatID;
typedef UInt32	AudioFormatFlags;
struct AudioStreamBasicDescription
{
    Float64             mSampleRate;
    AudioFormatID       mFormatID;
    AudioFormatFlags    mFormatFlags;
    UInt32              mBytesPerPacket;
    UInt32              mFramesPerPacket;
    UInt32              mBytesPerFrame;
    UInt32              mChannelsPerFrame;
    UInt32              mBitsPerChannel;
    UInt32              mReserved;
};
typedef struct AudioStreamBasicDescription  AudioStreamBasicDescription;
"""

def to_int(bytes):
    return int.from_bytes(bytes, byteorder='big')

kAudioObjectPropertyElementMaster     = 0
kAudioObjectPropertyScopeGlobal       = to_int(b'glob')
kAudioObjectPropertyName              = to_int(b'lnam')
kAudioObjectSystemObject              = 1
kAudioDevicePropertyNominalSampleRate = to_int(b'nsrt')
kAudioHardwarePropertyDevices         = to_int(b'dev#')
kAudioStreamPropertyPhysicalFormat    = to_int(b'pft ')
kCFStringEncodingUTF8                 = 0x08000100

class CAListener(DeviceListener):
    def __init__(self, device):
        self.ffi = cffi.FFI()
        self.ffi.cdef(HEADERS)
        self.ca = self.ffi.dlopen('CoreAudio')

        self.device_name = device
        self.device_id = self._get_capture_device_id(device)

        self.sr_prop = self._property_address(kAudioDevicePropertyNominalSampleRate)
        self.asbd_prop = self._property_address(kAudioStreamPropertyPhysicalFormat)

        self.on_change = None
        self.listening = False
        self.rate_callback = None

    def _property_address(self, selector, scope=kAudioObjectPropertyScopeGlobal, element=kAudioObjectPropertyElementMaster):
        prop = self.ffi.new("AudioObjectPropertyAddress*",
            {'mSelector': selector,
            'mScope': scope,
            'mElement': element})
        return prop

    def _read_property(self, id, prop_address, ctype):
        size = self.ffi.new("UInt32*")
        res = self.ca.AudioObjectGetPropertyDataSize(id, prop_address, 0, self.ffi.NULL, size)
        if res != 0:
            return None

        num_values = int(size[0]//self.ffi.sizeof(ctype))

        prop_data = self.ffi.new(ctype+'[]', num_values)
        res = self.ca.AudioObjectGetPropertyData(id, prop_address, 0, self.ffi.NULL, size, prop_data)
        if res != 0:
            return None
        return prop_data

    def _CFString_to_str(self, cfstr_ptr):
        str_length = self.ca.CFStringGetLength(cfstr_ptr[0])
        str_buffer = self.ffi.new('char[]', 4*str_length+1)
        success = self.ca.CFStringGetCString(cfstr_ptr[0], str_buffer, str_length+1, kCFStringEncodingUTF8)
        if not success:
            return None
        return self.ffi.string(str_buffer).decode()

    def _get_capture_device_id(self, wanted_name):
        id_prop = self._property_address(kAudioHardwarePropertyDevices)
        device_ids = self._read_property(
            kAudioObjectSystemObject,
            id_prop,
            "AudioObjectID")
        name_prop = self._property_address(kAudioObjectPropertyName)
        for id in device_ids:
            name_ptr = self._read_property(id, name_prop, 'CFStringRef')
            name = self._CFString_to_str(name_ptr)
            print(name)
            if name == wanted_name:
                print("found it!", id)
                return id
        raise ValueError(f"Cannot find device with name {wanted_name}")

    def run(self):
        if self.listening:
            raise RuntimeError("Already listening to events")
        
        @self.ffi.callback("AudioObjectPropertyListenerProc")
        def rate_callback(inObjectID, _inNumberAddresses, _inAddresses, _inClientData):
            print("yo!")
            wave_format = self.read_wave_format()
            stop_event = DeviceEvent.STOPPED
            self.emit_event(stop_event)
            start_event = DeviceEvent.STARTED
            start_event.set_data(wave_format)
            self.emit_event(start_event)
            return 0

        res = self.ca.AudioObjectAddPropertyListener(self.device_id, self.sr_prop, rate_callback, self.ffi.NULL)
        if res != 0:
            raise RuntimeError(f"Unable to register listener, code: {res}")
        self.rate_callback = rate_callback
        self.listening = True

    def emit_event(self, event):
        if self.on_change is not None:
            self.on_change(event)

    def stop(self):
        if not self.listening:
            raise RuntimeError("Not listening to events")
        res = self.ca.AudioObjectRemovePropertyListener(self.device_id, self.sr_prop, self.rate_callback, self.ffi.NULL)
        if res != 0:
            raise RuntimeError(f"Unable to remove listener, code: {res}")
        self.rate_callback = None
        self.listening = False

    def set_on_change(self, function):
        self.on_change = function

    def read_wave_format(self):
        asbd = self._read_property(self.device_id, self.asbd_prop, "AudioStreamBasicDescription")
        return WaveFormat(channels=asbd[0].mChannelsPerFrame, sample_rate=int(asbd[0].mSampleRate), sample_format=None)
    

if __name__ == "__main__":
    import sys
    import time
    device = sys.argv[1]
    listener = CAListener(device)

    def notifier(params):
        print(params, params.data)

    listener.set_on_change(notifier)
    listener.run()
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        pass
    listener.stop()