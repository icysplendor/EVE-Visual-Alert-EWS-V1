import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QGroupBox, QDoubleSpinBox, QLineEdit, QTextEdit, QDialog)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker

class DebugWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("实时监控视图")
        layout = QHBoxLayout()
        self.lbl_local = QLabel("本地栏")
        self.lbl_local.setFixedSize(200, 200)
        self.lbl_local.setStyleSheet("border: 1px solid red;")
        
        self.lbl_overview = QLabel("总览")
        self.lbl_overview.setFixedSize(200, 200)
        self.lbl_overview.setStyleSheet("border: 1px solid green;")

        self.lbl_monster = QLabel("怪物")
        self.lbl_monster.setFixedSize(200, 200)
        self.lbl_monster.setStyleSheet("border: 1px solid blue;")

        layout.addWidget(self.lbl_local)
        layout.addWidget(self.lbl_overview)
        layout.addWidget(self.lbl_monster)
        self.setLayout(layout)

    def update_images(self, img_local, img_overview, img_monster):
        def np2pixmap(np_img):
            if np_img is None: return QPixmap()
            h, w, ch = np_img.shape
            bytes_per_line = ch * w
            # OpenCV is BGR, Qt is RGB
            # img = cv2.cvtColor(np_img, cv2.COLOR_BGR2RGB) # assume external does this or display as is
            qimg = QImage(np_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            return QPixmap.fromImage(qimg).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)

        self.lbl_local.setPixmap(np2pixmap(img_local))
        self.lbl_overview.setPixmap(np2pixmap(img_overview))
        self.lbl_monster.setPixmap(np2pixmap(img_monster))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EVE Warning System Pro")
        self.resize(600, 700)
        
        # 初始化核心组件
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.logic.log_signal.connect(self.log)
        
        # 初始化音频播放器 (在主线程加载)
        self.sounds = {} # key: QSoundEffect
        self.load_sounds()

        self.setup_ui()
        
        # 定时器用于更新 Debug 窗口
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_view)
        
        # 定时器用于检查逻辑线程的报警请求（简化实现）
        # 实际上可以通过信号槽从 logic 传出 sound_key 
        self.logic.log_signal.connect(self.handle_alarm_signal) # 复用log信号做演示

    def load_sounds(self):
        paths = self.cfg.get("audio_paths")
        for key, path in paths.items():
            if path and os.path.exists(path):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
                effect.setVolume(1.0)
                self.sounds[key] = effect

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 区域设置区
        grp_region = QGroupBox("监控区域设置")
        layout_region = QHBoxLayout()
        for key in ["local", "overview", "monster"]:
            btn = QPushButton(f"设置 {key} 区域")
            btn.clicked.connect(lambda _, k=key: self.start_region_selection(k))
            layout_region.addWidget(btn)
        grp_region.setLayout(layout_region)
        layout.addWidget(grp_region)
        
        # 音频与配置区
        grp_config = QGroupBox("参数配置")
        layout_config = QVBoxLayout()
        
        # 阈值
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("敌对相似度:"))
        spin_hostile = QDoubleSpinBox()
        spin_hostile.setRange(0.1, 1.0)
        spin_hostile.setValue(self.cfg.get("thresholds")["hostile"])
        spin_hostile.valueChanged.connect(lambda v: self.update_threshold("hostile", v))
        row1.addWidget(spin_hostile)
        layout_config.addLayout(row1)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Webhook:"))
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        row2.addWidget(self.line_webhook)
        layout_config.addLayout(row2)

        # 音频选择按钮
        for key in ["local", "overview", "monster", "mixed"]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{key} 声音:"))
            path_label = QLabel(os.path.basename(self.cfg.get("audio_paths").get(key, "")))
            btn = QPushButton("选择...")
            btn.clicked.connect(lambda _, k=key, l=path_label: self.select_audio(k, l))
            row.addWidget(path_label)
            row.addWidget(btn)
            layout_config.addLayout(row)

        grp_config.setLayout(layout_config)
        layout.addWidget(grp_config)

        # 控制区
        box_ctrl = QHBoxLayout()
        self.btn_start = QPushButton("启动监控")
        self.btn_start.clicked.connect(self.toggle_monitoring)
        self.btn_start.setStyleSheet("background-color: green; color: white; font-weight: bold; height: 40px;")
        
        self.btn_debug = QPushButton("显示监控画面")
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        box_ctrl.addWidget(self.btn_start)
        box_ctrl.addWidget(self.btn_debug)
        layout.addLayout(box_ctrl)

        # 日志区
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self)

    def start_region_selection(self, key):
        self.selector = RegionSelector()
        self.selector.selection_finished.connect(lambda rect: self.save_region(key, rect))
        self.selector.show()

    def save_region(self, key, rect):
        regions = self.cfg.get("regions")
        regions[key] = list(rect)
        self.cfg.set("regions", regions)
        self.log(f"更新区域 {key}: {rect}")

    def update_threshold(self, key, val):
        t = self.cfg.get("thresholds")
        t[key] = val
        self.cfg.set("thresholds", t)

    def select_audio(self, key, label_widget):
        fname, _ = QFileDialog.getOpenFileName(self, "选择音频文件", "", "Audio Files (*.wav *.mp3)")
        if fname:
            paths = self.cfg.get("audio_paths")
            paths[key] = fname
            self.cfg.set("audio_paths", paths)
            label_widget.setText(os.path.basename(fname))
            self.load_sounds() # 重新加载

    def toggle_monitoring(self):
        if not self.logic.running:
            self.logic.start()
            self.btn_start.setText("停止监控")
            self.btn_start.setStyleSheet("background-color: red; color: white;")
            self.log("系统启动...")
        else:
            self.logic.stop()
            self.btn_start.setText("启动监控")
            self.btn_start.setStyleSheet("background-color: green; color: white;")
            self.log("系统停止.")

    def handle_alarm_signal(self, msg):
        # 这里实际上包含了日志和报警指令
        self.log(msg)
        if "类型: " in msg:
            sound_type = msg.split("类型: ")[1].strip()
            if sound_type in self.sounds:
                effect = self.sounds[sound_type]
                if not effect.isPlaying():
                    effect.play()

    def show_debug_window(self):
        self.debug_window.show()
        self.debug_timer.start(100) # 10FPS 刷新debug界面

    def update_debug_view(self):
        if not self.debug_window.isVisible():
            self.debug_timer.stop()
            return
        
        regions = self.cfg.get("regions")
        img_local = self.vision.capture_screen(regions["local"])
        img_overview = self.vision.capture_screen(regions["overview"])
        img_monster = self.vision.capture_screen(regions["monster"])
        self.debug_window.update_images(img_local, img_overview, img_monster)

    def log(self, text):
        self.txt_log.append(text)
        # 滚动到底部
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
