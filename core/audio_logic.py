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
            
            # 状态聚合
            global_threat = {
                "local": False, "overview": False, "monster": False, "probe": False
            }
            triggered_client_names = []
            
            # 遍历所有组
            for grp in groups:
                regions = grp["regions"]
                
                # 截图
                img_local = self.vision.capture_screen(regions.get("local"))
                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))

                # 匹配辅助
                def check(img, tmpls, th, color_check):
                    _, score = self.vision.match_templates(img, tmpls, th, True, color_check)
                    return score >= th

                # 检测
                is_local = check(img_local, self.vision.local_templates, thresholds.get("local", 0.95), True)
                is_overview = check(img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95), True)
                is_monster = check(img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95), False)
                is_probe = check(img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95), False)

                # 聚合状态
                if is_local: global_threat["local"] = True
                if is_overview: global_threat["overview"] = True
                if is_monster: global_threat["monster"] = True
                if is_probe: global_threat["probe"] = True
                
                if is_local or is_overview or is_probe:
                    triggered_client_names.append(grp["name"])

            # === 信号发射 ===
            if global_threat["probe"]:
                self.probe_signal.emit(True)

            # 主报警逻辑
            has_threat = global_threat["local"] or global_threat["overview"]
            sound_to_play = None
            
            if has_threat and global_threat["monster"]: sound_to_play = "mixed"
            elif global_threat["overview"]: sound_to_play = "overview"
            elif global_threat["local"]: sound_to_play = "local"
            elif global_threat["monster"]: sound_to_play = "monster"

            # 构建日志
            clients_str = ",".join(triggered_client_names) if triggered_client_names else "None"
            
            if sound_to_play:
                log_msg = f"[{now_str}] ⚠️ {sound_to_play.upper()} (Clients: {clients_str})"
                self.log_signal.emit(log_msg)
                
                webhook = self.cfg.get("webhook_url")
                if webhook:
                    try:
                        threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':sound_to_play}}).start()
                    except: pass
                time.sleep(2.0)
            elif global_threat["probe"]:
                log_msg = f"[{now_str}] ⚠️ PROBE (Clients: {clients_str})"
                self.log_signal.emit(log_msg)
                time.sleep(2.0)
            else:
                # 只有在调试或需要心跳时才输出安全日志，避免多开刷屏
                # 这里我们降低安全日志频率，或者只输出简单的
                log_msg = f"[{now_str}] ✅ Safe Scanning {len(groups)} Groups"
                self.log_signal.emit(log_msg)
                time.sleep(0.5)
