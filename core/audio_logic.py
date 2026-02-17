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
                    f"[{now_str}] Color Filter: Active (> {self.vision.GREEN_PIXEL_THRESHOLD}px)"
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
                
                # 截图
                img_local = self.vision.capture_screen(regions.get("local"))
                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))

                # 匹配
                def check(img, tmpls, th, color_check):
                    _, score = self.vision.match_templates(img, tmpls, th, True, color_check)
                    return score >= th, score

                is_local, s_loc = check(img_local, self.vision.local_templates, thresholds.get("local", 0.95), True)
                is_overview, s_ovr = check(img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95), True)
                is_monster, s_mon = check(img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95), False)
                is_probe, s_prb = check(img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95), False)

                # 状态判定
                has_threat = is_local or is_overview
                
                if is_probe: any_probe_triggered = True

                # 声音优先级判定 (累计所有客户端的最高威胁)
                if has_threat and is_monster: 
                    if major_sound != "mixed": major_sound = "mixed"
                elif is_overview:
                    if major_sound not in ["mixed"]: major_sound = "overview"
                elif is_local:
                    if major_sound not in ["mixed", "overview"]: major_sound = "local"
                elif is_monster:
                    if major_sound is None: major_sound = "monster"
                
                # 只有当有威胁，或者探针触发时，才输出详细日志，避免刷屏太快
                if has_threat or is_probe or is_monster:
                     log_line = (
                        f"[{now_str}] [{client_name}] "
                        f"L:{s_loc:.2f} "
                        f"O:{s_ovr:.2f} "
                        f"M:{s_mon:.2f} "
                        f"P:{s_prb:.2f}"
                    )
                     self.log_signal.emit(log_line)

            # === 循环结束后的动作 ===
            
            # 1. 探针声音 (独立通道)
            if any_probe_triggered:
                self.probe_signal.emit(True)

            # 2. 主报警声音
            if major_sound:
                # 关键修复：添加 "⚠️" 符号，因为 main.py 里的 handle_alarm_signal 依赖这个符号来触发声音
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
                # 如果什么都没发生，每隔 5 秒输出一个心跳，证明还在运行
                if int(time.time()) % 5 == 0:
                     self.log_signal.emit(f"[{now_str}] Scanning...")
                time.sleep(0.5)
