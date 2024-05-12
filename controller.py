import sys
import time
from copy import deepcopy
import yaml
import argparse

from camilladsp import CamillaClient, ProcessingState, StopReason


try:
    # TODO linux only
    from pyalsa_class import ControlListener
except ModuleNotFoundError:
    from dummy_listener import ControlListener

class CamillaController():

    def __init__(self, host, port, config_providers, listener):
        self.listener = listener
        self.host = host
        self.port = port
        self.config_providers = config_providers
        self.config = None
        self.events = []
        self.cdsp = CamillaClient(self.host, self.port)
        self.cdsp.connect()
        if self.listener is not None:
            self.listener.set_on_change(self.queue_event)
            self.listener.run()

    def queue_event(self, params):
        self.events.append(params)
    
    def main_loop(self):
        while True:
            time.sleep(0.1)
            state = self.cdsp.general.state()
            if state == ProcessingState.INACTIVE:
                print("CamillaDSP is inactive")
                stop_reason = self.cdsp.general.stop_reason()
                if stop_reason == StopReason.CAPTUREFORMATCHANGE:
                    print("CamillaDSP stopped because the capture format changed")
                    new_rate = stop_reason.data
                    if new_rate > 0:
                        self.get_config_for_new_wave_format(sample_rate=new_rate)
                        self.stop_cdsp()
                        self.start_cdsp()
                    else:
                        print("Sample rate changed, new value is unknown. Unable to continue")
                        sys.exit()
                elif stop_reason == StopReason.DONE:
                    print("Capture is done, no action")
                elif stop_reason == StopReason.NONE:
                    print("Initial start")
                    self.start_cdsp()
                elif stop_reason in (StopReason.CAPTUREERROR, stop_reason.PLAYBACKERROR):
                    print("Stopped due to error, trying to restart", stop_reason)
                    self.start_cdsp()
                elif stop_reason == StopReason.PLAYBACKFORMATCHANGE:
                    print("Playback format changed, ")

            while len(self.events) > 0:
                event = self.events.pop(0)
                # handle each event
                print(event)
    
    def stop_cdsp(self):
        print("Stopping CamillaDSP")
        self.cdsp.general.stop()

    def start_cdsp(self):
        if self.config is not None:
            print("Starting CamillaDSP with new config")
            self.cdsp.config.set_active(self.config)
        else:
            print("No new config is available, not starting")

    def get_config_for_new_wave_format(self, sample_rate=None, sample_format=None, channels=None):
        print(f"Getting new config for rate: {sample_rate}, format: {sample_format}, channels: {channels}")
        for provider in self.config_providers:
            try:
                provider.change_wave_format(sample_rate=sample_rate, sample_format=sample_format, channels=channels)
                self.config = provider.get_config()
                if self.config is not None:
                    print(f"Using new config from {provider.name} provider")
                    return
            except Exception as e:
                print(f"Provider {provider.name} is unable to supply a new config for this wave format")
        print(f"No config available for rate: {sample_rate}, format: {sample_format}, channels: {channels}")
        self.config = None




class CamillaConfig():
    name = "base class for config provider"
    def __init__(self):
        self.config = None

    def get_config(self):
        return self.config
    
    def read_config(self, filename):
        with open(filename) as f:
            config = yaml.safe_load(f)
            return config
    
    def change_wave_format(self, sample_rate=None, sample_format=None, channels=None):
        pass

# Modify a single config file for different rates.
# If the config has resampling, change only 'capture_samplerate' (and disable resamplng if it's not needed).
# If no resampler, change 'samplerate'
class AdaptConfig(CamillaConfig):
    name = "Adapt"

    def __init__(self, config_path):
        self.base_config = self.read_config(config_path)
        self.config = self.base_config

    def change_sample_rate(self, config, rate):
        if config["devices"].get("resampler") is None:
            print(f"No resampler defined, change 'samplerate' to {rate}")
            config["devices"]["samplerate"] = rate
            return
        
        resampler_type = config["devices"]["resampler"]["type"]
        config["devices"]["capture_samplerate"] = rate
        print(f"Config has a resampler, change 'capture_samplerate' to {rate}")

        if config["devices"]["capture_samplerate"] == config["devices"]["samplerate"] and resampler_type == "Synchronous":
            print("No need for a 1:1 sync resampler, removing")
            config["devices"]["resampler"] = None

    def change_sample_format(self, config, fmt):
        if config["devices"]["capture"].get("format") is not None:
            print(f"Change capture sample format to {fmt}")
            config["devices"]["capture"]["format"] = fmt
        else:
            print(f"Capture sample format is automatic, no need to change")

    def change_channels(self, config, channels):
        raise NotImplementedError("Changing channels in not implemented")

    def change_wave_format(self, sample_rate=None, sample_format=None, channels=None):
        # adjust base_config and store as self.config
        config = deepcopy(self.base_config)
        # handle rate
        if sample_rate is not None:
            self.change_sample_rate(config, sample_rate)
        if sample_format is not None:
            self.change_sample_format(config, sample_format)
        if channels is not None:
            self.change_channels(config, channels)
        self.config = config


# Load separate config files for different rates
class SpecificConfigs(CamillaConfig):
    name = "Specific"

    def __init__(self, config_path, initial_rate, initial_format, initial_channels):
        self.config_path = config_path
        self.rate = initial_rate
        self.format = initial_format
        self.channels = initial_channels
        missing = []
        if "{samplerate}" in config_path and initial_rate is None:
            missing.append("sample rate")
        if "{sampleformat}" in config_path and initial_format is None:
            missing.append("sample format")
        if "{channels}" in config_path and initial_channels is None:
            missing.append("channels")
        if len(missing) > 0:
            raise ValueError(f"Missing initial values for {', '.join(missing)}")
        self.config = self.read_config(self.filename())

    def filename(self):
        # same token format as in CamillaDSP itself
        # "example_{sampleformat}_{channels}_{samplerate}.yml"
        name = self.config_path
        if self.rate is not None:
            name = name.replace("{samplerate}", str(self.rate))
        if self.channels is not None:
            name = name.replace("{channels}", str(self.channels))
        if self.format is not None:
            name = name.replace("{sampleformat}", self.format)
        return name

    def change_wave_format(self, sample_rate=None, sample_format=None, channels=None):
        if sample_rate is not None:
            self.rate = sample_rate
        if sample_format is not None:
            self.format = sample_format
        if channels is not None:
            self.channels = channels
        print("New config path:", self.filename())
        self.config = self.read_config(self.filename())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='CamillaDSP controller')
    # TODO linux only
    parser.add_argument('-d', '--device', help='Alsa device to monitor (Linux only)')
    parser.add_argument('-s', '--specific', help='Template for paths to config files for specific wave formats')
    parser.add_argument('-a', '--adapt', help='Path to a config file that can be adapted to new sample rates')
    parser.add_argument('-p', '--port', help='CamillaDSP websocket port', type=int, required=True)
    parser.add_argument('--host', help='CamillaDSP websocket host')
    parser.add_argument('-f', '--format', help='Initial value for sample format')
    parser.add_argument('-c', '--channels', help='Initial value for number of channels')
    parser.add_argument('-r', '--rate', help='Initial value for sample rate')


    args = parser.parse_args()
    
    if args.specific is None and args.adapt is None:
        parser.error("At least one of '--specific' and '--adapt' must be provided")

    if args.device is not None:
        listener = ControlListener(args.device)
    else:
        listener = None

    host = args.host
    if host is None:
        host = "localhost"

    configs = []
    if args.specific is not None:
        try:
            config = SpecificConfigs(args.specific, args.rate, args.format, args.channels)
            configs.append(config)
        except Exception as e:
            raise e
            parser.error(str(e))
    if args.adapt is not None:
        try:
            config = AdaptConfig(args.adapt)
            configs.append(config)
        except Exception as e:
            parser.error(str(e))

    controller = CamillaController(host, args.port, configs, listener)
    controller.main_loop()

# python controller.py -p 1234 -s "/Users/henrik/repos/camilladsp-controller/kladd/bh_int_{samplerate}.yml" -a "/Users/henrik/repos/camilladsp-controller/kladd/bh_int_resampler.yml" -r 44100