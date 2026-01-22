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
        self.first_run = True # 标记符，用于这是不是第一次运行

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True # 重置标记
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _loop(self):
        while self.running:
            now_str = datetime.now().strftime("%H:%M:%S")
            
            # === [新增] 系统自检报告 (仅第一次运行输出) ===
            if self.first_run:
                self.vision.load_templates() # 强制运行一次加载，确保状态最新
                report = (
                    f"--- 系统自检报告 ---\n"
                    f"{self.vision.template_status_msg}\n"
                    f"--------------------"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1) # 停顿一下让人看清
            # ==========================================

            regions = self.cfg.get("regions")
            t_hostile = self.cfg.get("thresholds")["hostile"]
            t_monster = self.cfg.get("thresholds")["monster"]

            # 截图 (带 debug_name)
            img_local = self.vision.capture_screen(regions.get("local"), "local")
            img_overview = self.vision.capture_screen(regions.get("overview"), "overview")
            img_monster = self.vision.capture_screen(regions.get("monster"), "monster")

            # 匹配逻辑 (注意现在的 match_templates 返回的是 (ErrorMsg/None, Score))
            def process_match(img, templates, thresh):
                err_msg, score = self.vision.match_templates(img, templates, thresh, True)
                is_hit = score >= thresh
                return is_hit, score, err_msg

            is_local, score_local, err_local = process_match(img_local, self.vision.hostile_templates, t_hostile)
            is_overview, score_overview, err_overview = process_match(img_overview, self.vision.hostile_templates, t_hostile)
            is_monster, score_monster, err_monster = process_match(img_monster, self.vision.monster_templates, t_monster)

            self.status["local"] = is_local
            self.status["overview"] = is_overview
            self.status["monster"] = is_monster

            # 报警逻辑
            has_threat = is_local or is_overview
            sound_to_play = None
            if has_threat and is_monster: sound_to_play = "mixed"
            elif is_overview: sound_to_play = "overview"
            elif is_local: sound_to_play = "local"
            elif is_monster: sound_to_play = "monster"

            # 格式化分数与错误
            def fmt(score, err):
                if err: return f"❌{err}" # 如果有具体错误(无模板/截图失败)，显示错误
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
