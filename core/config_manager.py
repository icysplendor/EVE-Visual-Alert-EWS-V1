import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "regions": {
        "local": None,     # [x, y, w, h]
        "overview": None,
        "monster": None
    },
    "thresholds": {
        "hostile": 0.85,
        "monster": 0.85
    },
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
                    # 简单合并，防止新版本缺字段
                    for k, v in data.items():
                        if k in self.config:
                            if isinstance(v, dict):
                                self.config[k].update(v)
                            else:
                                self.config[k] = v
            except:
                print("加载配置文件失败，使用默认配置")

    def save(self):
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=4)

    def get(self, key):
        return self.config.get(key)

    def set(self, key, value):
        self.config[key] = value
        self.save()
