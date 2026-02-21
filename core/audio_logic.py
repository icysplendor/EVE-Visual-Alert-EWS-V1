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
        
        self.threat_persistence = {}
        self.CONFIRM_CYCLES = 2 
        
        # 非阻塞冷却记录
        self.last_alert_time = 0.0
        self.last_alert_type = None
        self.last_probe_time = 0.0
        self.REPEAT_INTERVAL = 2.0 

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True 
            self.threat_persistence = {}
            self.last_alert_time = 0.0
            self.last_alert_type = None
            self.last_probe_time = 0.0
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _loop(self):
        while self.running:
            loop_start_time = time.time()
            now = datetime.now()
            now_str = now.strftime("%H:%M:%S")
            
            # 读取配置
            jitter_delay = self.cfg.get("jitter_delay")
            if jitter_delay is None: jitter_delay = 0.18
            
            scan_interval = self.cfg.get("scan_interval")
            if scan_interval is None: scan_interval = 0.5
            
            if self.first_run:
                self.vision.load_templates()
                report = (
                    f"[{now_str}] System Check: Templates Loaded.\n"
                    f"[{now_str}] Config: Jitter={jitter_delay}s | Scan={scan_interval}s"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            any_probe_triggered = False
            major_sound = None
            pending_threat_detected = False

            # === 逐个客户端检测 ===
            for i, grp in enumerate(groups):
                client_name = grp["name"]
                regions = grp["regions"]
                
                if i not in self.threat_persistence:
                    self.threat_persistence[i] = {"local": 0, "overview": 0, "monster": 0, "probe": 0}

                img_local = self.vision.capture_screen(regions.get("local"))
                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))

                def check(img, tmpls, th, safe_color):
                    _, score = self.vision.match_templates(img, tmpls, th, True, check_safe_color=safe_color)
                    return score >= th, score

                raw_local, s_loc = check(img_local, self.vision.local_templates, thresholds.get("local", 0.95), True)
                raw_overview, s_ovr = check(img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95), True)
                raw_monster, s_mon = check(img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95), False)
                raw_probe, s_prb = check(img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95), False)

                def update_persistence(key, is_detected):
                    if is_detected:
                        self.threat_persistence[i][key] += 1
                        if self.threat_persistence[i][key] < self.CONFIRM_CYCLES:
                            return False, True 
                        else:
                            return True, False 
                    else:
                        self.threat_persistence[i][key] = 0
                        return False, False

                is_local, p_local = update_persistence("local", raw_local)
                is_overview, p_overview = update_persistence("overview", raw_overview)
                is_monster, p_monster = update_persistence("monster", raw_monster)
                is_probe, p_probe = update_persistence("probe", raw_probe)

                if p_local or p_overview or p_monster or p_probe:
                    pending_threat_detected = True

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
                
                def mark(confirmed, pending):
                    if confirmed: return "🔴"
                    if pending: return "⚡"
                    return ""

                log_line = (
                    f"[{now_str}] [{client_name}] "
                    f"L:{s_loc:.2f}{mark(is_local, p_local)} "
                    f"O:{s_ovr:.2f}{mark(is_overview, p_overview)} "
                    f"M:{s_mon:.2f}{mark(is_monster, p_monster)} "
                    f"P:{s_prb:.2f}{mark(is_probe, p_probe)}"
                )
                self.log_signal.emit(log_line)

            # === 循环结束后的动作 ===
            if any_probe_triggered:
                if loop_start_time - self.last_probe_time > 2.0:
                    self.probe_signal.emit(True)
                    self.last_probe_time = loop_start_time

            if major_sound:
                should_play = False
                if major_sound != self.last_alert_type:
                    should_play = True
                elif (loop_start_time - self.last_alert_time) > self.REPEAT_INTERVAL:
                    should_play = True
                
                if should_play:
                    alert_msg = f"[{now_str}] ⚠️ ALERT: {major_sound.upper()}"
                    self.log_signal.emit(alert_msg)
                    self.last_alert_time = loop_start_time
                    self.last_alert_type = major_sound
                    
                    webhook = self.cfg.get("webhook_url")
                    if webhook:
                        try:
                            threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':major_sound}}).start()
                        except: pass
            else:
                self.last_alert_type = None

            # === 睡眠控制 ===
            if major_sound or pending_threat_detected:
                time.sleep(jitter_delay)
            else:
                # 使用用户配置的扫描间隔
                time.sleep(scan_interval)
