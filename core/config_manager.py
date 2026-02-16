import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "language": "CN",
    "regions": {
        "local": None,
        "overview": None,
        "monster": None,
        "probe": None  # 新增探针区域
    },
    "thresholds": {
        "local": 0.95,
        "overview": 0.95,
        "monster": 0.95,
        "probe": 0.95  # 新增探针阈值
    },
    "webhook_url": "",
    "audio_paths": {
        "local": "assets/sounds/01.wav",
        "overview": "assets/sounds/02.wav",
        "monster": "assets/sounds/10.wav",
        "mixed": "assets/sounds/100.wav",
        "probe": "assets/sounds/probe.wav", # 新增探针音效
        "idle": "assets/sounds/idle.wav"    # 新增待机音效
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
                                for sub_k, sub_v in v.items():
                                    if sub_k in self.config[k]:
                                        self.config[k][sub_k] = sub_v
                                    # 处理新增的键值（向前兼容）
                                    elif sub_k not in self.config[k]:
                                         self.config[k][sub_k] = DEFAULT_CONFIG[k].get(sub_k)
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

    def get_audio_path(self, key):
        """获取音频文件的绝对路径，自动处理相对路径"""
        raw_path = self.config.get("audio_paths", {}).get(key, "")
        if not raw_path:
            return ""
        
        if os.path.isabs(raw_path):
            return raw_path
        
        return os.path.abspath(os.path.join(os.getcwd(), raw_path))
