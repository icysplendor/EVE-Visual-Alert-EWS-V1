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
    "thresholds": {
        "local": 0.95,
        "overview": 0.95,
        "monster": 0.95
    },
    "webhook_url": "",
    # 修改点：使用相对路径
    "audio_paths": {
        "local": "assets/sounds/01.wav",
        "overview": "assets/sounds/02.wav",
        "monster": "assets/sounds/10.wav",
        "mixed": "assets/sounds/100.wav"
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

    # 新增辅助方法：获取绝对路径
    def get_audio_path(self, key):
        """获取音频文件的绝对路径，自动处理相对路径"""
        raw_path = self.config.get("audio_paths", {}).get(key, "")
        if not raw_path:
            return ""
        
        # 如果已经是绝对路径，直接返回
        if os.path.isabs(raw_path):
            return raw_path
        
        # 如果是相对路径，拼接当前工作目录
        return os.path.abspath(os.path.join(os.getcwd(), raw_path))
