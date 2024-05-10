import sys
import time
from copy import deepcopy
import yaml

from pyalsa_class import ControlListener

class CamillaController():

    def __init__(self, host, port, config, listener):
        self.listener = listener
        self.host = host
        self.port = port
        self.config = config
        self.events = []
        if self.listener is not None:
            self.listener.set_on_change(self.queue_event)
            self.listener.run()

    def queue_event(self, params):
        self.events.append(params)
    
    def main_loop(self):
        while True:
            time.sleep(1)
            
            # check camilla status,
            # if stopped, get stopreason
            # reload if needed

            while len(self.events) > 0:
                event = self.events.pop(0)
                # handle each event
                print(event)
    
    def stop_cdsp(self):
        pass

    def start_cdsp(self):
        config = self.config.get_config()
        # send to cdsp

    def change_sample_rate(self, new_rate):
        self.config.change_sample_rate(new_rate)


class CamillaConfig():
    def __init__(self):
        self.config = None

    def get_config(self):
        return self.config
    
    def read_config(self, filename):
        with open(filename) as f:
            config = yaml.safe_load(f)
            return config
    
    def change_sample_rate(self, new_rate):
        pass

# Modify a single config file for different rates.
# If the config has resampling, change only 'capture_samplerate' (and disable resamplng if it's not needed).
# If no resampler, change 'samplerate'
class ModifyConfig(CamillaConfig):
    def __init__(self, config):
        self.base_config = config
        self.config = config

    def change_sample_rate(self, new_rate):
        # adjust base_config and store as self.config
        config = deepcopy(self.base_config)
        # TODO modify
        self.config = config


# Load separate config files for different rates
class SeparateConfigs(CamillaConfig):
    def __init__(self, config_name, initial_rate):
        self.config_name = config_name
        self.rate = initial_rate
        self.config = self.read_config(self.filename())

    def filename(self):
        name = self.config_name.format(self.rate)
        return name

    def change_sample_rate(self, new_rate):
        self.rate = new_rate
        self.config = self.read_config(self.filename())


if __name__ == "__main__":
    device = sys.argv[1]
    listener = ControlListener(device)
    config = CamillaConfig()
    controller = CamillaController("localhost", 1234, config, listener)
    controller.main_loop()