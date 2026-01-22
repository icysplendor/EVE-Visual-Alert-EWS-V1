import time
import threading
import requests
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    log_signal = pyqtSignal(str)

    def __init__(self, config_manager, vision_engine):
        super().__init__()
        self.cfg = config_manager
        self.vision = vision_engine
        self.running = False
        self.thread = None
        self.status = {"local": False, "overview": False, "monster": False}
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
                    f"--------------------"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            regions = self.cfg.get("regions")
            
            # === 修改点：分别读取三个阈值 ===
            thresholds = self.cfg.get("thresholds")
            # 兼容旧配置文件的保护措施
            t_local = thresholds.get("local", 0.95)
            t_overview = thresholds.get("overview", 0.95)
            t_monster = thresholds.get("monster", 0.95)
            # ============================

            img_local = self.vision.capture_screen(regions.get("local"), "local")
            img_overview = self.vision.capture_screen(regions.get("overview"), "overview")
            img_monster = self.vision.capture_screen(regions.get("monster"), "monster")

            def process_match(img, templates, thresh):
                err_msg, score = self.vision.match_templates(img, templates, thresh, True)
                is_hit = score >= thresh
                return is_hit, score, err_msg

            # === 修改点：传入对应的阈值 ===
            is_local, score_local, err_local = process_match(img_local, self.vision.hostile_templates, t_local)
            is_overview, score_overview, err_overview = process_match(img_overview, self.vision.hostile_templates, t_overview)
            is_monster, score_monster, err_monster = process_match(img_monster, self.vision.monster_templates, t_monster)

            self.status["local"] = is_local
            self.status["overview"] = is_overview
            self.status["monster"] = is_monster

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
                           f"M:{int(is_monster)}({fmt(score_monster, err_monster)})]")
            
            if sound_to_play:
                log_msg = f"[{now_str}] ⚠️ 触发: {sound_to_play.upper()} {status_desc}"
                self.log_signal.emit(log_msg)
                
                webhook = self.cfg.get("webhook_url")
                if webhook:
                    try:
                        threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':sound_to_play}}).start()
                    except: pass
                time.sleep(2.0)
            else:
                log_msg = f"[{now_str}] ✅ 安全 {status_desc}"
                self.log_signal.emit(log_msg)
                time.sleep(0.5)
