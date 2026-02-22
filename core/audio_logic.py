import time
import threading
import requests
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    log_signal = pyqtSignal(str)
    probe_signal = pyqtSignal(bool)
    location_update_signal = pyqtSignal(int, str)

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
                    f"[{now_str}] Logic: Security + Location Scan (3s)"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            any_probe_triggered = False
            major_sound = None
            pending_threat_detected = False
            
            check_location = (loop_start_time - self.last_location_check_time) >= 3.0
            if check_location:
                self.last_location_check_time = loop_start_time

            for i, grp in enumerate(groups):
                # 获取 Client ID (C1, C2...)
                client_id = f"C{i+1}"
                regions = grp["regions"]
                current_scale = grp.get("scale")
                
                img_local = self.vision.capture_screen(regions.get("local"))
                
                if not current_scale:
                    if img_local is not None:
                        self.log_signal.emit(f"[{now_str}-{client_id}] Detecting Scale...")
                        detected_scale = self.vision.detect_scale(img_local)
                        if detected_scale:
                            grp["scale"] = detected_scale
                            all_groups = self.cfg.get("groups")
                            all_groups[i]["scale"] = detected_scale
                            self.cfg.set("groups", all_groups)
                            self.log_signal.emit(f"[{now_str}-{client_id}] Scale: {detected_scale}%")
                            current_scale = detected_scale
                        else:
                            self.log_signal.emit(f"[{now_str}-{client_id}] ⚠️ Scale Fail")
                            continue 
                    else:
                        continue 

                if current_scale not in self.vision.SCALES:
                    grp["scale"] = None
                    continue

                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))
                
                current_system = ""
                if check_location:
                    img_location = self.vision.capture_screen(regions.get("location"))
                    loc_thresh = thresholds.get("location", 0.85)
                    sys_name, sys_score = self.vision.match_location_name(img_location, current_scale, loc_thresh)
                    if sys_name:
                        current_system = sys_name
                        self.location_update_signal.emit(i, sys_name)
                    else:
                        self.location_update_signal.emit(i, "Unknown")

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
                
                # === 极简日志格式 ===
                # [14:41:33-C1] L:3(99)🔴 O:0(0) M:0(0) P:0(0) @ Jita
                def fmt(cnt, score, confirmed, pending):
                    mark = ""
                    if confirmed: mark = "🔴"
                    elif pending: mark = "⚡"
                    # 分数转整数
                    return f"{cnt}({int(score*100)}){mark}"

                loc_str = f" @ {current_system}" if current_system else ""
                
                log_line = (
                    f"[{now_str}-{client_id}] "
                    f"L:{fmt(cnt_local, s_loc, is_local, p_local)} "
                    f"O:{fmt(cnt_overview, s_ovr, is_overview, p_overview)} "
                    f"M:{fmt(cnt_monster, s_mon, is_monster, p_monster)} "
                    f"P:{fmt(cnt_probe, s_prb, is_probe, p_probe)}"
                    f"{loc_str}"
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
                    # 移除了单独的 ALERT 日志行
                    # 依然发送信号给 webhook 和声音
                    self.last_alert_time = loop_start_time
                    self.last_alert_type = major_sound
                    
                    # 触发声音 (主界面 handle_alarm_signal 依赖 ⚠️，所以我们这里发一个隐形的信号或者复用 log_line 里的红点？)
                    # 不，handle_alarm_signal 监听的是日志文本。
                    # 如果删除了 ALERT 行，我们需要确保 log_line 里包含触发词，或者发送一个专门的控制信号。
                    # 为了兼容性，我们发送一个包含 ⚠️ 的控制日志，但不让它太占地方。
                    # 或者，我们在上面的 log_line 里已经有了 🔴。
                    # 最好还是发一个专门的控制消息，主界面可以拦截它不显示在文本框，只播放声音。
                    # 但为了简单，我们还是发一个极短的提示。
                    self.log_signal.emit(f"⚠️ {major_sound.upper()}")
                    
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
