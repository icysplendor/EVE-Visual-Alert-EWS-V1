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
            now_str = datetime.now().strftime("%H:%M:%S")
            
            if self.first_run:
                self.vision.load_templates()
                report = (
                    f"--- System Check ---\n"
                    f"{self.vision.template_status_msg}\n"
                    f"Color Filter: ON (> {self.vision.GREEN_PIXEL_THRESHOLD}px)\n"
                    f"--------------------"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            any_probe_triggered = False
            any_major_threat = False
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
                if has_threat: any_major_threat = True

                # 确定当前客户端的显示符号
                def ico(cond): return "🔴" if cond else "🟢"
                
                # 详细日志行
                # 格式: [Client 1] 🟢Loc(0.12) 🟢Ovr(0.00) 🟢Rat(0.00) 🔴Prb(0.98)
                log_line = (
                    f"[{client_name}] "
                    f"{ico(is_local)}L:{s_loc:.2f} "
                    f"{ico(is_overview)}O:{s_ovr:.2f} "
                    f"{ico(is_monster)}M:{s_mon:.2f} "
                    f"{ico(is_probe)}P:{s_prb:.2f}"
                )
                
                # 只有当有威胁，或者探针触发时，或者每隔一定周期(为了不刷屏)才输出
                # 为了满足用户"详细日志"的需求，我们输出每一行，但可能需要界面上控制一下频率
                # 这里我们全部输出
                self.log_signal.emit(log_line)

                # 声音优先级判定 (保留最高优先级的)
                if has_threat and is_monster: 
                    if major_sound != "mixed": major_sound = "mixed"
                elif is_overview:
                    if major_sound not in ["mixed"]: major_sound = "overview"
                elif is_local:
                    if major_sound not in ["mixed", "overview"]: major_sound = "local"
                elif is_monster:
                    if major_sound is None: major_sound = "monster"

            # === 循环结束后的动作 ===
            
            # 发送探针信号
            if any_probe_triggered:
                self.probe_signal.emit(True)

            # 发送主报警信号
            if major_sound:
                self.log_signal.emit(f"⚠️ SOUND TRIGGER: {major_sound.upper()}")
                webhook = self.cfg.get("webhook_url")
                if webhook:
                    try:
                        threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':major_sound}}).start()
                    except: pass
                time.sleep(2.0) # 报警后冷却
            elif any_probe_triggered:
                time.sleep(2.0) # 探针冷却
            else:
                time.sleep(0.5) # 正常扫描间隔
