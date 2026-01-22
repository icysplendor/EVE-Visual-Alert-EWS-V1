LANGUAGES = {
    "CN": {
        "window_title": "EVE 视觉警报",
        "grp_monitor": "监控区域设定",
        "grp_config": "参数设置",
        "btn_local": "本地栏",
        "btn_overview": "总览栏",
        "btn_npc": "怪物栏",
        "lbl_threshold": "识别阈值:",
        "lbl_webhook": "Webhook:",
        "lbl_sound_local": "本地预警:",
        "lbl_sound_overview": "总览预警:",
        "lbl_sound_npc": "刷怪提示:",
        "lbl_sound_mixed": "混合警报:",
        "btn_select": "...",
        "btn_start": "启动监控",
        "btn_stop": "停止运行",
        "btn_debug": "实时画面",
        "log_ready": "系统就绪。",
        "log_start": ">>> 监控已启动",
        "log_stop": ">>> 监控已停止",
        "log_region_err": "错误: 未设置监控区域",
        "region_updated": "区域已更新",
        "btn_lang": "EN"
    },
    "EN": {
        "window_title": "EVE Visual Alert",
        "grp_monitor": "Scanning Sectors",
        "grp_config": "Settings", # Configuration 太长改成 Settings
        "btn_local": "Local",
        "btn_overview": "Overview",
        "btn_npc": "Rats",
        "lbl_threshold": "Threshold:",
        "lbl_webhook": "Webhook:",
        "lbl_sound_local": "Local:",
        "lbl_sound_overview": "Overview:",
        "lbl_sound_npc": "Rats:",
        "lbl_sound_mixed": "Mixed:",
        "btn_select": "...",
        "btn_start": "ENGAGE",
        "btn_stop": "STOP",
        "btn_debug": "LIVE VIEW", # 改短，Visual Feed 太长
        "log_ready": "System Ready.",
        "log_start": ">>> Monitoring Engaged",
        "log_stop": ">>> Monitoring Halted",
        "log_region_err": "ERR: No Regions Set",
        "region_updated": "Region Set",
        "btn_lang": "CN"
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
