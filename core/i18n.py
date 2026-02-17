非常抱歉，你是对的。我在 `main.py` 中调用了翻译键值，但忘记在 `i18n.py` 中定义它们了。这会导致按钮上显示的是键名而不是实际的文字。

请更新 `i18n.py` 文件，补充缺失的翻译项。

### `i18n.py`

主要修改点：
1.  增加了 `btn_probe` 的翻译。
2.  调整了部分日志信息的格式以匹配新的纯文本风格。
3.  补充了 `btn_add` (添加客户端组) 的翻译。

```python
LANGUAGES = {
    "CN": {
        "window_title": "EVE 视觉警报 (多开版)",
        "btn_add": "+ 添加客户端组",
        "grp_thresh": "全局阈值设置",
        "btn_settings": "⚙ 详细设置",
        "btn_start": "启动监控",
        "btn_stop": "停止运行",
        "btn_debug": "实时画面",
        "btn_lang": "EN",
        "btn_local": "本地栏",
        "btn_overview": "总览栏",
        "btn_npc": "怪物栏",
        "btn_probe": "探针扫描",
        "log_ready": "系统就绪。请添加客户端并设置区域。",
        "log_start": ">>> 监控已启动",
        "log_stop": ">>> 监控已停止",
        "log_region_err": "错误: 未设置任何有效监控区域",
        "log_idle_alert": ">>> 提示: 程序处于待机状态"
    },
    "EN": {
        "window_title": "EVE Visual Alert (Multibox)",
        "btn_add": "+ ADD CLIENT GROUP",
        "grp_thresh": "Global Thresholds",
        "btn_settings": "⚙ SETTINGS",
        "btn_start": "ENGAGE",
        "btn_stop": "STOP",
        "btn_debug": "VIEW",
        "btn_lang": "CN",
        "btn_local": "LOCAL",
        "btn_overview": "OVERVIEW",
        "btn_npc": "RATS",
        "btn_probe": "PROBE",
        "log_ready": "System Ready. Add clients to begin.",
        "log_start": ">>> Monitoring Engaged",
        "log_stop": ">>> Monitoring Halted",
        "log_region_err": "ERR: No Active Regions Found",
        "log_idle_alert": ">>> ALERT: System Idling"
    }
}

class Translator:
    def __init__(self, updated_callback=None):
        self.lang = "CN" 
        self.callback = updated_callback

    def set_language(self, lang_code):
        if lang_code in LANGUAGES:
            self.lang = lang_code
            if self.callback:
                self.callback()

    def get(self, key):
        return LANGUAGES[self.lang].get(key, key)
    
    def toggle(self):
        new_lang = "EN" if self.lang == "CN" else "CN"
        self.set_language(new_lang)
```

本次回复已完毕。
