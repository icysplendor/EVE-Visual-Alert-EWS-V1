import time
import threading
import requests
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    log_signal = pyqtSignal(str)
    probe_signal = pyqtSignal(bool)

    def __init__(self, config_manager, vision_engine):
        super().__init__()
        self.cfg = config_manager
        self.vision = vision_engine
        self.running = False
        self.thread = None
        self.first_run = True 

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True 
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _loop(self):
        while self.running:
            now = datetime.now()
            now_str = now.strftime("%H:%M:%S")
            
            if self.first_run:
                self.vision.load_templates()
                report = (
                    f"[{now_str}] System Check: Templates Loaded.\n"
                    f"[{now_str}] Logic: Standard Matching"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            any_probe_triggered = False
            major_sound = None

            # === 逐个客户端检测 ===
            for grp in groups:
                client_name = grp["name"]
                regions = grp["regions"]
                
                img_local = self.vision.capture_screen(regions.get("local"))
                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))

                # 匹配 (不再传递 color_check)
                def check(img, tmpls, th):
                    _, score = self.vision.match_templates(img, tmpls, th, True)
                    return score >= th, score

                is_local, s_loc = check(img_local, self.vision.local_templates, thresholds.get("local", 0.95))
                is_overview, s_ovr = check(img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95))
                is_monster, s_mon = check(img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95))
                is_probe, s_prb = check(img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95))

                has_threat = is_local or is_overview
                if is_probe: any_probe_triggered = True

                if has_threat and is_monster: 
                    if major_sound != "mixed": major_sound = "mixed"
                elif is_overview:
                    if major_sound not in ["mixed"]: major_sound = "overview"
                elif is_local:
                    if major_sound not in ["mixed", "overview"]: major_sound = "local"
                elif is_monster:
                    if major_sound is None: major_sound = "monster"
                
                log_line = (
                    f"[{now_str}] [{client_name}] "
                    f"L:{s_loc:.2f} "
                    f"O:{s_ovr:.2f} "
                    f"M:{s_mon:.2f} "
                    f"P:{s_prb:.2f}"
                )
                self.log_signal.emit(log_line)

            if any_probe_triggered:
                self.probe_signal.emit(True)

            if major_sound:
                alert_msg = f"[{now_str}] ⚠️ ALERT: {major_sound.upper()}"
                self.log_signal.emit(alert_msg)
                
                webhook = self.cfg.get("webhook_url")
                if webhook:
                    try:
                        threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':major_sound}}).start()
                    except: pass
                time.sleep(2.0) 
            elif any_probe_triggered:
                time.sleep(2.0) 
            else:
                time.sleep(0.5)
