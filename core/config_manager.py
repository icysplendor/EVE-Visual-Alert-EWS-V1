import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "language": "CN",
    "groups": [
        {
            "name": "Client 1",
            "regions": {"local": None, "overview": None, "monster": None, "probe": None}
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
                    
                    # === 迁移逻辑：旧版 regions 转换为新版 groups ===
                    if "regions" in data and isinstance(data["regions"], dict):
                        # 如果是旧版配置，将其包裹进第一个 group
                        old_regions = data["regions"]
                        # 补全可能缺失的 probe
                        if "probe" not in old_regions: old_regions["probe"] = None
                        
                        self.config["groups"] = [{
                            "name": "Client 1",
                            "regions": old_regions
                        }]
                        # 删除旧 key
                        del data["regions"]
                    
                    # 合并其他配置
                    for k, v in data.items():
                        if k in self.config:
                            if k == "groups":
                                self.config[k] = v # 直接覆盖 groups
                            elif isinstance(v, dict):
                                for sub_k, sub_v in v.items():
                                    if sub_k in self.config[k]:
                                        self.config[k][sub_k] = sub_v
                                    elif sub_k not in self.config[k]:
                                         self.config[k][sub_k] = DEFAULT_CONFIG[k].get(sub_k)
                            else:
                                self.config[k] = v
            except Exception as e:
                print(f"加载配置文件失败: {e}，使用默认配置")

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
        if not raw_path: return ""
        if os.path.isabs(raw_path): return raw_path
        return os.path.abspath(os.path.join(os.getcwd(), raw_path))
