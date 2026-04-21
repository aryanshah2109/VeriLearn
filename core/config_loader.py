import yaml

from core.path_constants import CONFIG_PATH

class Config:
    def __init__(self, data):
        self._data = data
    
    def __getattr__(self, key):
        if key not in self._data:
            raise AttributeError(f"Config key '{key}' not found")
    
        value = self._data.get(key)
        if isinstance(value, dict):
            return Config(value)
        return value


def load_config():
    """
        Function to load configs from config.yaml file and returns loaded object
    """

    try:
        with open(CONFIG_PATH, "r") as f:
            return yaml.safe_load(f)
    
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
    except yaml.YAMLError as e:
        raise ValueError(f"Error while parsing YAML : {e}")
    
config = Config(load_config())