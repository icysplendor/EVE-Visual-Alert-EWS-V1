import time
import threading
import requests
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    log_signal = pyqtSignal(str)
    probe_signal = pyqtSignal(bool)
    location_update_signal = pyqtSignal(int, str) # client_idx, system_name

    def __init__(self, config_manager, vision_engine):
        super().__init__()
        self.cfg = config_manager
        self.vision = vision_engine
        self.running = False
        self.thread = None
        self.first_run = True 
        
        self.threat_persistence = {}
        self.CONFIRM_CYCLES = 2 
        
        self.last_alert_time = 0.0
        self.last_alert_type = None
        self.last_probe_time = 0.0
        self.REPEAT_INTERVAL = 2.0 
        
        # 位置检测计时器
        self.last_location_check_time = 0.0

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True 
            self.threat_persistence = {}
            self.last_alert_time = 0.0
            self.last_alert_type = None
            self.last_probe_time = 0.0
            self.last_location_check_time = 0.0
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
            
            jitter_delay = self.cfg.get("jitter_delay")
            if jitter_delay is None: jitter_delay = 0.18
            scan_interval = self.cfg.get("scan_interval")
            if scan_interval is None: scan_interval = 0.5
            
            if self.first_run:
                self.vision.load_templates()
                report = (
                    f"[{now_str}] System Check: Templates Loaded.\n"
                    f"[{now_str}] Logic: Security + Location Scan"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            any_probe_triggered = False
            major_sound = None
            pending_threat_detected = False
            
            # 检查是否需要更新位置 (至少间隔 1 秒)
            check_location = (loop_start_time - self.last_location_check_time) >= 1.0
            if check_location:
                self.last_location_check_time = loop_start_time

            for i, grp in enumerate(groups):
                client_name = grp["name"]
                regions = grp["regions"]
                current_scale = grp.get("scale")
                
                # 1. 截图 (所有功能共用这些截图，保证同步)
                img_local = self.vision.capture_screen(regions.get("local"))
                
                # 自动缩放检测
                if not current_scale:
                    if img_local is not None:
                        self.log_signal.emit(f"[{now_str}] [{client_name}] Detecting UI Scale...")
                        detected_scale = self.vision.detect_scale(img_local)
                        if detected_scale:
                            grp["scale"] = detected_scale
                            all_groups = self.cfg.get("groups")
                            all_groups[i]["scale"] = detected_scale
                            self.cfg.set("groups", all_groups)
                            self.log_signal.emit(f"[{now_str}] [{client_name}] Scale Detected: {detected_scale}%")
                            current_scale = detected_scale
                        else:
                            self.log_signal.emit(f"[{now_str}] [{client_name}] ⚠️ Scale Detection Failed!")
                            continue 
                    else:
                        continue 

                if current_scale not in self.vision.SCALES:
                    grp["scale"] = None
                    continue

                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))
                
                # === 位置检测逻辑 (同步执行) ===
                current_system = "Unknown"
                if check_location:
                    img_location = self.vision.capture_screen(regions.get("location"))
                    loc_thresh = thresholds.get("location", 0.85)
                    sys_name, sys_score = self.vision.match_location_name(img_location, current_scale, loc_thresh)
                    if sys_name:
                        current_system = sys_name
                        # 发送更新信号给 UI
                        self.location_update_signal.emit(i, sys_name)
                    else:
                        self.location_update_signal.emit(i, "Unknown")

                # === 安全扫描逻辑 ===
                if i not in self.threat_persistence:
                    self.threat_persistence[i] = {"local": 0, "overview": 0, "monster": 0, "probe": 0}

                def check(img, type_key, th, safe_color):
                    tmpls = self.vision.templates[type_key].get(current_scale, [])
                    cnt, score = self.vision.count_matches(img, tmpls, th, check_safe_color=safe_color)
                    return cnt, score

                cnt_local, s_loc = check(img_local, "local", thresholds.get("local", 0.95), True)
                cnt_overview, s_ovr = check(img_overview, "overview", thresholds.get("overview", 0.95), True)
                cnt_monster, s_mon = check(img_monster, "monster", thresholds.get("monster", 0.95), False)
                cnt_probe, s_prb = check(img_probe, "probe", thresholds.get("probe", 0.95), False)

                def update_persistence(key, count):
                    is_detected = count > 0
                    if is_detected:
                        self.threat_persistence[i][key] += 1
                        if self.threat_persistence[i][key] < self.CONFIRM_CYCLES:
                            return False, True 
                        else:
                            return True, False 
                    else:
                        self.threat_persistence[i][key] = 0
                        return False, False

                is_local, p_local = update_persistence("local", cnt_local)
                is_overview, p_overview = update_persistence("overview", cnt_overview)
                is_monster, p_monster = update_persistence("monster", cnt_monster)
                is_probe, p_probe = update_persistence("probe", cnt_probe)

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
                
                def fmt(cnt, score, confirmed, pending):
                    mark = ""
                    if confirmed: mark = "🔴"
                    elif pending: mark = "⚡"
                    return f"{cnt}({score:.2f}){mark}"

                # 日志中加入位置信息
                # [12:00:00] [Client 1 @ Jita] L:0(0.00)...
                loc_str = f" @ {current_system}" if check_location and current_system != "Unknown" else ""
                
                log_line = (
                    f"[{now_str}] [{client_name}{loc_str}] "
                    f"L:{fmt(cnt_local, s_loc, is_local, p_local)} "
                    f"O:{fmt(cnt_overview, s_ovr, is_overview, p_overview)} "
                    f"M:{fmt(cnt_monster, s_mon, is_monster, p_monster)} "
                    f"P:{fmt(cnt_probe, s_prb, is_probe, p_probe)}"
                )
                self.log_signal.emit(log_line)

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

            if major_sound or pending_threat_detected:
                time.sleep(jitter_delay)
            else:
                time.sleep(scan_interval)
