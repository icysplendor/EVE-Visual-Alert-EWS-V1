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
        
        # 防抖动计数器
        self.threat_persistence = {}
        # 阈值：连续 2 次检测到才报警
        self.CONFIRM_CYCLES = 2 

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True 
            self.threat_persistence = {}
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
                    f"[{now_str}] Mode: Fast-Confirm (0.1s Interval)"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            any_probe_triggered = False
            major_sound = None
            
            # 标记：本轮是否有任何“疑似”威胁（即计数器 > 0 但还没报警）
            pending_threat_detected = False

            # === 逐个客户端检测 ===
            for i, grp in enumerate(groups):
                client_name = grp["name"]
                regions = grp["regions"]
                
                if i not in self.threat_persistence:
                    self.threat_persistence[i] = {"local": 0, "overview": 0, "monster": 0, "probe": 0}

                # 截图
                img_local = self.vision.capture_screen(regions.get("local"))
                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))

                # 匹配
                def check(img, tmpls, th, safe_color):
                    _, score = self.vision.match_templates(img, tmpls, th, True, check_safe_color=safe_color)
                    return score >= th, score

                raw_local, s_loc = check(img_local, self.vision.local_templates, thresholds.get("local", 0.95), True)
                raw_overview, s_ovr = check(img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95), True)
                raw_monster, s_mon = check(img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95), False)
                raw_probe, s_prb = check(img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95), False)

                # === 防抖动逻辑 ===
                def update_persistence(key, is_detected):
                    if is_detected:
                        self.threat_persistence[i][key] += 1
                        # 如果检测到了，但还没达到阈值，说明是疑似威胁，需要加速确认
                        if self.threat_persistence[i][key] < self.CONFIRM_CYCLES:
                            return False, True # (Is Confirmed?, Is Pending?)
                        else:
                            return True, False # 已确认
                    else:
                        self.threat_persistence[i][key] = 0
                        return False, False

                is_local, p_local = update_persistence("local", raw_local)
                is_overview, p_overview = update_persistence("overview", raw_overview)
                is_monster, p_monster = update_persistence("monster", raw_monster)
                is_probe, p_probe = update_persistence("probe", raw_probe)

                # 只要有任意一个 Pending 状态，就激活极速重试
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
                
                # 日志标记
                # 🔴 = 已确认报警
                # ⚡ = 疑似威胁，正在极速重试中
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
                self.probe_signal.emit(True)

            if major_sound:
                # 确认威胁，报警，并强制冷却 2 秒
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
                
            elif pending_threat_detected:
                # === 关键优化 ===
                # 发现了疑似威胁（闪电标记），休眠 0.1 秒
                # 既保证了画面刷新，又保证了极速响应
                time.sleep(0.18)
                
            else:
                # 全程无事，正常休眠省资源
                time.sleep(0.5)
