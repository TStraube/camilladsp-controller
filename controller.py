import sys
import time
from copy import deepcopy
import yaml

from camilladsp import CamillaClient, ProcessingState, StopReason


try:
    from pyalsa_class import ControlListener
except ModuleNotFoundError:
    from dummy_listener import ControlListener

class CamillaController():

    def __init__(self, host, port, config, listener):
        self.listener = listener
        self.host = host
        self.port = port
        self.config = config
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
                        self.config.change_wave_format(sample_rate=new_rate)
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
        print("Starting CamillaDSP with new config")
        config = self.config.get_config()
        self.cdsp.config.set_active(config)



class CamillaConfig():
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
class ModifyConfig(CamillaConfig):
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
        print("Changing channels in not implemented")

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
class SeparateConfigs(CamillaConfig):
    def __init__(self, config_path, initial_rate, initial_format, initial_channels):
        self.config_path = config_path
        self.rate = initial_rate
        self.format = initial_format
        self.channels = initial_channels
        self.config = self.read_config(self.filename())

    def filename(self):
        # same token format as in CamillaDSP itself
        # "conf_$sampleformat$_$channels$_$samplerate$.yml"
        name = self.config_path
        name = name.replace("$samplerate$", str(self.rate))
        name = name.replace("$channels$", str(self.channels))
        name = name.replace("$sampleformat$", self.format)
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
    if len(sys.argv) > 1:
        device = sys.argv[1]
        listener = ControlListener(device)
    else:
        listener = None
    #config = ModifyConfig("/Users/henrik/repos/camilladsp-controller/kladd/bh_int_resampler.yml")
    config = SeparateConfigs("/Users/henrik/repos/camilladsp-controller/kladd/bh_int_$samplerate$.yml", 44100, "FLOAT32LE", 2)
    controller = CamillaController("localhost", 1234, config, listener)
    controller.main_loop()