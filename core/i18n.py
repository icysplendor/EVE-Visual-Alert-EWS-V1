LANGUAGES = {
    "CN": {
        "window_title": "EVE 视觉警报",
        "grp_monitor": "监控区域设定",
        "grp_config": "参数设置",
        "btn_local": "本地栏",
        "btn_overview": "总览栏",
        "btn_npc": "怪物栏",
        "btn_probe": "探针扫描",
        "lbl_th_local": "本地阈值:",
        "lbl_th_over": "总览阈值:",
        "lbl_th_npc": "怪物阈值:",
        "lbl_th_probe": "探针阈值:",
        "lbl_webhook": "Webhook:",
        "lbl_sound_local": "本地:",
        "lbl_sound_overview": "总览:",
        "lbl_sound_npc": "刷怪:",
        "lbl_sound_mixed": "混合:",
        "lbl_sound_probe": "探针:",
        "lbl_sound_idle": "待机:",
        "btn_select": "...",
        "btn_start": "启动监控",
        "btn_stop": "停止运行",
        "btn_debug": "实时画面",
        "log_ready": "系统就绪。",
        "log_start": ">>> 监控已启动",
        "log_stop": ">>> 监控已停止",
        "log_region_err": "错误: 未设置监控区域",
        "log_idle_alert": ">>> 提示: 程序处于待机状态",
        "region_updated": "区域已更新",
        "btn_lang": "EN"
    },
    "EN": {
        "window_title": "EVE Visual Alert",
        "grp_monitor": "Scanning Sectors",
        "grp_config": "Settings",
        "btn_local": "Local",
        "btn_overview": "Overview",
        "btn_npc": "Rats",
        "btn_probe": "Probes",
        "lbl_th_local": "Loc %:",
        "lbl_th_over": "Ovr %:",
        "lbl_th_npc": "Rat %:",
        "lbl_th_probe": "Prb %:",
        "lbl_webhook": "Webhook:",
        "lbl_sound_local": "Local:",
        "lbl_sound_overview": "Overvw:",
        "lbl_sound_npc": "Rats:",
        "lbl_sound_mixed": "Mixed:",
        "lbl_sound_probe": "Probe:",
        "lbl_sound_idle": "Idle:",
        "btn_select": "...",
        "btn_start": "ENGAGE",
        "btn_stop": "STOP",
        "btn_debug": "LIVE VIEW",
        "log_ready": "System Ready.",
        "log_start": ">>> Monitoring Engaged",
        "log_stop": ">>> Monitoring Halted",
        "log_region_err": "ERR: No Regions Set",
        "log_idle_alert": ">>> ALERT: System Idling",
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
