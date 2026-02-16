import time
import threading
import requests
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    log_signal = pyqtSignal(str)     # 主日志和主警报信号
    probe_signal = pyqtSignal(bool)  # 独立的探针警报信号

    def __init__(self, config_manager, vision_engine):
        super().__init__()
        self.cfg = config_manager
        self.vision = vision_engine
        self.running = False
        self.thread = None
        self.status = {"local": False, "overview": False, "monster": False, "probe": False}
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
                    f"--- 系统自检报告 ---\n"
                    f"{self.vision.template_status_msg}\n"
                    f"颜色过滤: 已启用 (阈值 > {self.vision.GREEN_PIXEL_THRESHOLD}px)\n"
                    f"--------------------"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            regions = self.cfg.get("regions")
            thresholds = self.cfg.get("thresholds")
            
            # 截图
            img_local = self.vision.capture_screen(regions.get("local"), "local")
            img_overview = self.vision.capture_screen(regions.get("overview"), "overview")
            img_monster = self.vision.capture_screen(regions.get("monster"), "monster")
            img_probe = self.vision.capture_screen(regions.get("probe"), "probe")

            # 辅助函数
            def process_match(img, templates, thresh, check_green=False):
                err_msg, score = self.vision.match_templates(
                    img, templates, thresh, 
                    return_max_val=True, 
                    check_green_exclusion=check_green
                )
                is_hit = score >= thresh
                return is_hit, score, err_msg

            # 1. 主威胁检测
            is_local, score_local, err_local = process_match(
                img_local, self.vision.local_templates, thresholds.get("local", 0.95), check_green=True
            )
            is_overview, score_overview, err_overview = process_match(
                img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95), check_green=True
            )
            is_monster, score_monster, err_monster = process_match(
                img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95), check_green=False
            )
            
            # 2. 探针检测 (独立逻辑，类似 Monster 不查颜色)
            is_probe, score_probe, err_probe = process_match(
                img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95), check_green=False
            )

            self.status["local"] = is_local
            self.status["overview"] = is_overview
            self.status["monster"] = is_monster
            self.status["probe"] = is_probe

            # === 探针独立信号 ===
            if is_probe:
                self.probe_signal.emit(True)

            # === 主报警逻辑 ===
            has_threat = is_local or is_overview
            sound_to_play = None
            if has_threat and is_monster: sound_to_play = "mixed"
            elif is_overview: sound_to_play = "overview"
            elif is_local: sound_to_play = "local"
            elif is_monster: sound_to_play = "monster"

            def fmt(score, err):
                if err: return f"❌{err}"
                return f"{score:.2f}"

            status_desc = (f"[L:{int(is_local)}({fmt(score_local, err_local)}) | "
                           f"O:{int(is_overview)}({fmt(score_overview, err_overview)}) | "
                           f"M:{int(is_monster)}({fmt(score_monster, err_monster)}) | "
                           f"P:{int(is_probe)}({fmt(score_probe, err_probe)})]")
            
            if sound_to_play:
                log_msg = f"[{now_str}] ⚠️ 触发: {sound_to_play.upper()} {status_desc}"
                self.log_signal.emit(log_msg)
                
                webhook = self.cfg.get("webhook_url")
                if webhook:
                    try:
                        threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':sound_to_play}}).start()
                    except: pass
                time.sleep(2.0)
            elif is_probe:
                # 只有探针触发，主报警没有触发时，也打一条日志
                log_msg = f"[{now_str}] ⚠️ 探针: PROBE {status_desc}"
                self.log_signal.emit(log_msg)
                time.sleep(2.0)
            else:
                log_msg = f"[{now_str}] ✅ 安全 {status_desc}"
                self.log_signal.emit(log_msg)
                time.sleep(0.5)
