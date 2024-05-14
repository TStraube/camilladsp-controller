# camilladsp-controller

## Example on Mac
```
python controller.py -p 1234 -s "/path_to/config_{samplerate}.yml" -a "/path/to/config_with_resampler.yml" -r 44100
```

Three config files:

config_44100.yml
```
devices:
  samplerate: 44100
  chunksize: 1024
  enable_rate_adjust: true
  capture:
    type: CoreAudio
    channels: 2
    device: "BlackHole 2ch"
  playback:
    type: CoreAudio
    channels: 2
    device: "MacBook Air Speakers"
```

config_48000.yml
```
devices:
  samplerate: 48000
  chunksize: 1024
  enable_rate_adjust: true
  capture:
    type: CoreAudio
    channels: 2
    device: "BlackHole 2ch"
  playback:
    type: CoreAudio
    channels: 2
    device: "MacBook Air Speakers"
```

config_with_resampler.yml
```
devices:
  samplerate: 44100
  capture_samplerate: 44100
  chunksize: 1024
  enable_rate_adjust: true
  resampler:
    type: Synchronous
  capture:
    type: CoreAudio
    channels: 2
    device: "BlackHole 2ch"
  playback:
    type: CoreAudio
    channels: 2
    device: "MacBook Air Speakers"
```

Open Audio and Midi settings and switch the Blackhole sample rate to different values.

## Example on Linux:
config_44100.yml
```
devices:
  samplerate: 44100
  chunksize: 1024
  enable_rate_adjust: true
  capture:
    type: Alsa
    channels: 4
    device: "hw:Loopback,0"
    stop_on_inactive: true
    format: S32LE
  playback:
    type: Alsa
    channels: 4
    device: "hw:M4"
```

config_48000.yml
```
devices:
  samplerate: 48000
  chunksize: 1024
  enable_rate_adjust: true
  capture:
    type: Alsa
    channels: 4
    device: "hw:Loopback,0"
    stop_on_inactive: true
    format: S32LE
  playback:
    type: Alsa
    channels: 4
    device: "hw:M4"
```

Start the controller:
```
python controller.py -p 1234 -s "/home/henrik/repos/camilladsp-controller/kladd/loopback_m4_{samplerate}.yml"  -r 44100 -d hw:Loopback,0
```

Play two files with different rates (random.raw is a short raw file):
```
aplay -D hw:Loopback,1 random.raw -r 44100 -f S32_LE -c 4 && aplay -D hw:Loopback,1 random.raw -r 48000 -f S32_LE -c 4
```