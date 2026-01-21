import time
import threading
import requests
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl, QThread, pyqtSignal
from PyQt6.QtCore import QObject

class AlarmWorker(QObject):
    # 用信号来通知主界面状态更新（比如日志）
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
        
        # 音频播放器缓存
        self.players = {}

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _play_sound(self, sound_key):
        # 获取路径
        path = self.cfg.get("audio_paths").get(sound_key)
        if not path or not os.path.exists(path):
            return

        # 简单的播放逻辑，实际可以用PyQt的QSoundEffect
        # 这里为了线程安全和阻塞控制，简单演示逻辑
        # 在完整GUI中，推荐发送信号给主线程播放声音，或者使用winsound/pygame
        # 这里我们假定用 QSoundEffect 在主线程中预加载好了
        self.log_signal.emit(f"播放报警: {sound_key}")
        
        # 触发 Webhook (异步)
        webhook_url = self.cfg.get("webhook_url")
        if webhook_url:
            try:
                threading.Thread(target=requests.post, args=(webhook_url,), kwargs={'json':{'alert': sound_key}}).start()
            except:
                pass

    def _loop(self):
        import os # 确保在线程内可用
        # 使用 winsound 仅限 Windows，如果是Mac开发调试要改用其他库
        # 为了兼容性，这里我们模拟一个阻塞。
        # 实际建议在 Main GUI 初始化 QSoundEffect，通过信号触发播放。
        
        while self.running:
            # 1. 获取检测结果
            regions = self.cfg.get("regions")
            t_hostile = self.cfg.get("thresholds")["hostile"]
            t_monster = self.cfg.get("thresholds")["monster"]

            # 截图并检测
            img_local = self.vision.capture_screen(regions["local"])
            img_overview = self.vision.capture_screen(regions["overview"])
            img_monster = self.vision.capture_screen(regions["monster"])

            self.status["local"] = self.vision.match_templates(img_local, self.vision.hostile_templates, t_hostile)
            self.status["overview"] = self.vision.match_templates(img_overview, self.vision.hostile_templates, t_hostile)
            # 怪物识别可以用 detect_monster_text
            self.status["monster"] = self.vision.match_templates(img_monster, self.vision.monster_templates, t_monster)

            # 2. 决策逻辑 (优先级)
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

            # 3. 执行报警
            if sound_to_play:
                # 发送信号让主界面播放，或者直接在这里播放(如果在后台线程使用win32api)
                # 为了简化，我们假设这是一个阻塞操作，播放完才继续下一轮
                # 实际生产中，我们可以使用 PyQt 的 Signal 通知主线程播放
                self.log_signal.emit(f"检测到威胁!! 类型: {sound_to_play}")
                
                # 休眠模拟播放时间，或者直到声音结束
                # 这里发送一个信号给主程序去播放真正的声音
                # 这种设计下，logic模块不直接碰音频驱动，最稳定
                time.sleep(2) 
            else:
                # 安全状态，快速轮询
                time.sleep(0.2)
