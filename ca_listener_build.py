from cffi import FFI

ffibuilder = FFI()

# Build a native binding to selected parts of the CoreAudio API.
# This is inspired by the CoreAudio bindings in the [SoundCard library](https://github.com/bastibe/SoundCard) by Bastian Bechtold.

ffibuilder.set_source(
    "_ca_listener",
    r"""
    #include <CoreAudio/CoreAudio.h>
    """,
    libraries=[],
    extra_link_args=["-framework", "CoreAudio"],
)

ffibuilder.cdef(
    """
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
                                                    const AudioObjectPropertyAddress *inAddresses,
                                                    void *inClientData);
extern "Python" OSStatus property_listener(AudioObjectID, UInt32, const AudioObjectPropertyAddress *, void *);

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
)


def run_build():
    ffibuilder.compile(verbose=True)


if __name__ == "__main__":
    run_build()
