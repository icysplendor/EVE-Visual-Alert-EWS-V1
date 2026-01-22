import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "language": "CN",
    "regions": {
        "local": None,
        "overview": None,
        "monster": None
    },
    # === 修改点：拆分阈值，默认 0.95 ===
    "thresholds": {
        "local": 0.95,
        "overview": 0.95,
        "monster": 0.95
    },
    # ==================================
    "webhook_url": "",
    "audio_paths": {
        "local": "",
        "overview": "",
        "monster": "",
        "mixed": ""
    }
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k in self.config:
                            if isinstance(v, dict):
                                self.config[k].update(v)
                            else:
                                self.config[k] = v
            except:
                print("Config load failed, using defaults")

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4)

    def get(self, key):
        return self.config.get(key)

    def set(self, key, value):
        self.config[key] = value
        self.save()
