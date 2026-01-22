import time
import threading
import requests
import os
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    # 信号通知主界面及日志
    log_signal = pyqtSignal(str)

    def __init__(self, config_manager, vision_engine):
        super().__init__()
        self.cfg = config_manager
        self.vision = vision_engine
        self.running = False
        self.thread = None
        
        # 状态矩阵
        self.status = {
            "local": False,
            "overview": False,
            "monster": False
        }

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _loop(self):
        while self.running:
            # 获取当前时间戳 (带毫秒)
            now_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # 1. 获取检测参数
            regions = self.cfg.get("regions")
            t_hostile = self.cfg.get("thresholds")["hostile"]
            t_monster = self.cfg.get("thresholds")["monster"]

            # 2. 截图与识别
            # 如果区域还没设置，vision返回None，match_templates返回False
            img_local = self.vision.capture_screen(regions.get("local"))
            img_overview = self.vision.capture_screen(regions.get("overview"))
            img_monster = self.vision.capture_screen(regions.get("monster"))

            self.status["local"] = self.vision.match_templates(img_local, self.vision.hostile_templates, t_hostile)
            self.status["overview"] = self.vision.match_templates(img_overview, self.vision.hostile_templates, t_hostile)
            self.status["monster"] = self.vision.match_templates(img_monster, self.vision.monster_templates, t_monster)

            # 3. 决策逻辑
            is_local = self.status["local"]
            is_overview = self.status["overview"]
            is_monster = self.status["monster"]
            has_threat = is_local or is_overview

            sound_to_play = None
            
            if has_threat and is_monster:
                sound_to_play = "mixed" # 混合报警
            elif is_overview:
                sound_to_play = "overview" # 总览优先
            elif is_local:
                sound_to_play = "local"
            elif is_monster:
                sound_to_play = "monster"

            # 4. 强制日志输出 (包含状态)
            status_desc = f"[状态: L:{int(is_local)} | O:{int(is_overview)} | M:{int(is_monster)}]"
            
            if sound_to_play:
                log_msg = f"[{now_str}] ⚠️ 触发报警: {sound_to_play.upper()} {status_desc}"
                self.log_signal.emit(log_msg)
                
                # 触发Webhook (异步)
                webhook_url = self.cfg.get("webhook_url")
                if webhook_url:
                    try:
                        threading.Thread(target=requests.post, args=(webhook_url,), kwargs={'json':{'alert': sound_to_play}}).start()
                    except:
                        pass
                
                # 休眠较长时间，模拟声音播放或避免刷屏
                # 因为用户要求"持续输出检测状态"，这里的sleep建议适中，
                # 如果是真实环境，可能要等待声音播放完。这里设置为2秒。
                # 在这2秒内界面会暂停日志刷新，代表"正在报警中"
                time.sleep(2.0)
                
            else:
                log_msg = f"[{now_str}] ✅ 监控中...安全 {status_desc}"
                self.log_signal.emit(log_msg)
                
                # 安全状态下的快速轮询间隔 (例如 0.5秒)
                time.sleep(0.5)
