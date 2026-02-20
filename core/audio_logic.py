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
        
        # === 新增：非阻塞冷却记录 ===
        self.last_alert_time = 0.0
        self.last_alert_type = None
        self.last_probe_time = 0.0
        
        # 同一种报警的重复间隔 (秒)
        self.REPEAT_INTERVAL = 2.0 

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True 
            self.threat_persistence = {}
            # 重置状态
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
            # 记录当前循环开始时间，用于非阻塞计时
            loop_start_time = time.time()
            now = datetime.now()
            now_str = now.strftime("%H:%M:%S")
            
            jitter_delay = self.cfg.get("jitter_delay")
            if jitter_delay is None: jitter_delay = 0.18
            
            if self.first_run:
                self.vision.load_templates()
                report = (
                    f"[{now_str}] System Check: Templates Loaded.\n"
                    f"[{now_str}] Logic: Non-Blocking High Frequency ({jitter_delay}s)"
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

            # === 循环结束后的动作 (非阻塞逻辑) ===
            
            # 1. 探针处理
            if any_probe_triggered:
                # 检查探针冷却 (2秒)
                if loop_start_time - self.last_probe_time > 2.0:
                    self.probe_signal.emit(True)
                    self.last_probe_time = loop_start_time

            # 2. 主报警处理
            if major_sound:
                should_play = False
                
                # 情况 A: 威胁升级/变更 (例如从 Local 变成 Mixed) -> 立即报警
                if major_sound != self.last_alert_type:
                    should_play = True
                    
                # 情况 B: 威胁相同，但冷却时间已过 -> 重复报警
                elif (loop_start_time - self.last_alert_time) > self.REPEAT_INTERVAL:
                    should_play = True
                
                if should_play:
                    alert_msg = f"[{now_str}] ⚠️ ALERT: {major_sound.upper()}"
                    self.log_signal.emit(alert_msg)
                    
                    # 更新状态
                    self.last_alert_time = loop_start_time
                    self.last_alert_type = major_sound
                    
                    webhook = self.cfg.get("webhook_url")
                    if webhook:
                        try:
                            threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':major_sound}}).start()
                        except: pass
            else:
                # 如果没有威胁，重置类型，这样下次有威胁时会视为“新类型”立即报警
                self.last_alert_type = None

            # === 睡眠控制 (关键优化) ===
            # 只要有任何 确认的威胁(major_sound) 或者 疑似的威胁(pending)
            # 都使用极速模式 (jitter_delay)，不再进行长休眠
            if major_sound or pending_threat_detected:
                time.sleep(jitter_delay)
            else:
                # 只有在完全安全、没有任何红点或闪电时，才慢下来
                time.sleep(0.5)
