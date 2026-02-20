import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "language": "CN",
    "window_pos": [100, 100],
    "jitter_delay": 0.18, # 新增：防抖延迟时间 (秒)
    "groups": [
        {
            "id": 0,
            "name": "Client 1",
            "regions": {
                "local": None,
                "overview": None,
                "monster": None,
                "probe": None
            }
        }
    ],
    "thresholds": {
        "local": 0.95,
        "overview": 0.95,
        "monster": 0.95,
        "probe": 0.95
    },
    "webhook_url": "",
    "audio_paths": {
        "local": "assets/sounds/01.wav",
        "overview": "assets/sounds/02.wav",
        "monster": "assets/sounds/10.wav",
        "mixed": "assets/sounds/100.wav",
        "probe": "assets/sounds/probe.wav",
        "idle": "assets/sounds/idle.wav"
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
                        if k == "regions" and "groups" not in data:
                            continue 
                        
                        if k in self.config:
                            if k == "groups":
                                self.config[k] = v 
                            elif isinstance(v, dict):
                                for sub_k, sub_v in v.items():
                                    if sub_k in self.config[k]:
                                        self.config[k][sub_k] = sub_v
                                    elif sub_k not in self.config[k]:
                                         self.config[k][sub_k] = DEFAULT_CONFIG[k].get(sub_k)
                            else:
                                self.config[k] = v
                    
                    # 确保新增字段存在
                    if "jitter_delay" not in self.config:
                        self.config["jitter_delay"] = 0.18

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

    def get_audio_path(self, key):
        raw_path = self.config.get("audio_paths", {}).get(key, "")
        if not raw_path:
            return ""
        if os.path.isabs(raw_path):
            return raw_path
        return os.path.abspath(os.path.join(os.getcwd(), raw_path))
