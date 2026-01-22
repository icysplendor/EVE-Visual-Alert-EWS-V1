# core/i18n.py

LANGUAGES = {
    "CN": {
        "window_title": "EVE 预警系统 [EWS]",
        "grp_monitor": "监控扇区",
        "grp_config": "系统参数",
        "btn_local": "设定 [本地]",
        "btn_overview": "设定 [总览]",
        "btn_npc": "设定 [刷怪]",
        "lbl_threshold": "威胁阈值:",
        "lbl_webhook": "数据流 (Webhook):",
        "lbl_sound_local": "本地警报:",
        "lbl_sound_overview": "总览警报:",
        "lbl_sound_npc": "异常警报:",
        "lbl_sound_mixed": "混合警报:",
        "btn_select": "加载...",
        "btn_start": "系统 启动",
        "btn_stop": "系统 终止",
        "btn_debug": "视觉 馈送",
        "log_ready": "系统就绪。等待指令。",
        "log_start": "监控进程已初始化...",
        "log_stop": "监控进程已挂起。",
        "log_region_err": "错误: 缺少遥测数据 (未设置区域)",
        "region_updated": "扇区已校准",
        "term_local": "本地",
        "term_overview": "总览",
        "term_npc": "异常",
        "status_safe": "安全",
        "status_alert": "警告",
        "btn_lang": "EN" # 切换到英文的按钮文字
    },
    "EN": {
        "window_title": "EVE Warning System [EWS]",
        "grp_monitor": "Telemetry Sectors",
        "grp_config": "System Parameters",
        "btn_local": "Set [Local]",
        "btn_overview": "Set [Overview]",
        "btn_npc": "Set [Rats]",
        "lbl_threshold": "Threat Threshold:",
        "lbl_webhook": "Webhook Stream:",
        "lbl_sound_local": "Local Alarm:",
        "lbl_sound_overview": "Overview Alarm:",
        "lbl_sound_npc": "Rat Alarm:",
        "lbl_sound_mixed": "Mixed Alarm:",
        "btn_select": "Load...",
        "btn_start": "SYSTEM ENGAGE",
        "btn_stop": "SYSTEM HALT",
        "btn_debug": "VISUAL FEED",
        "log_ready": "System ready. Awaiting command.",
        "log_start": "Monitoring process initialized...",
        "log_stop": "Monitoring process suspended.",
        "log_region_err": "ERROR: Missing Telemetry Data (No Regions)",
        "region_updated": "Sector Calibrated",
        "term_local": "Local",
        "term_overview": "Overview",
        "term_npc": "Rats",
        "status_safe": "CLEAR",
        "status_alert": "ALERT",
        "btn_lang": "CN"
    }
}

class Translator:
    def __init__(self, updated_callback=None):
        self.lang = "CN" # 默认中文
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
