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
        self.lbl_local.setStyleSheet("border: 1px solid red; background: #333;")
        self.lbl_local.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_overview = QLabel("总览")
        self.lbl_overview.setFixedSize(200, 200)
        self.lbl_overview.setStyleSheet("border: 1px solid green; background: #333;")
        self.lbl_overview.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_monster = QLabel("怪物")
        self.lbl_monster.setFixedSize(200, 200)
        self.lbl_monster.setStyleSheet("border: 1px solid blue; background: #333;")
        self.lbl_monster.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.lbl_local)
        layout.addWidget(self.lbl_overview)
        layout.addWidget(self.lbl_monster)
        self.setLayout(layout)

    def update_images(self, img_local, img_overview, img_monster):
        def np2pixmap(np_img):
            if np_img is None: return QPixmap()
            h, w, ch = np_img.shape
            bytes_per_line = ch * w
            qimg = QImage(np_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            return QPixmap.fromImage(qimg).scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)

        self.lbl_local.setPixmap(np2pixmap(img_local))
        self.lbl_overview.setPixmap(np2pixmap(img_overview))
        self.lbl_monster.setPixmap(np2pixmap(img_monster))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EVE Warning System Pro")
        self.resize(600, 750)
        
        # 初始化核心组件
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.logic.log_signal.connect(self.log)
        
        # 初始化音频播放器
        self.sounds = {} 
        self.load_sounds()

        self.setup_ui()
        
        # 定时器用于更新 Debug 窗口
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_view)
        
        # 监听逻辑线程的信号来播放声音
        self.logic.log_signal.connect(self.handle_alarm_signal)

        # === 自动启动检测 ===
        self.check_auto_start()

    def check_auto_start(self):
        """
        检查配置，如果区域已设置，自动启动
        """
        regions = self.cfg.get("regions")
        # 只要设置了 Local 或 Overview 其中之一，就视为有效配置，尝试自动启动
        if regions.get("local") is not None or regions.get("overview") is not None:
            self.log("配置文件检测有效，正在自动启动...")
            self.toggle_monitoring()
        else:
            self.log("未检测到预设区域，等待用户配置...")

    def load_sounds(self):
        paths = self.cfg.get("audio_paths")
        if not paths: return
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
        spin_hostile.setSingleStep(0.05)
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
            path_val = self.cfg.get("audio_paths").get(key, "")
            path_label = QLabel(os.path.basename(path_val) if path_val else "未设置")
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
        # 设置最大行数防止内存溢出
        self.txt_log.document().setMaximumBlockCount(1000) 
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
        self.log(f"已更新区域 {key}: {rect}")

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
            # 检查是否有区域
            regions = self.cfg.get("regions")
            if not regions.get("local") and not regions.get("overview"):
                self.log("⚠️ 错误: 请先设置至少一个监控区域 (Local 或 Overview)")
                return

            self.logic.start()
            self.btn_start.setText("停止监控")
            self.btn_start.setStyleSheet("background-color: red; color: white; font-weight: bold; height: 40px;")
        else:
            self.logic.stop()
            self.btn_start.setText("启动监控")
            self.btn_start.setStyleSheet("background-color: green; color: white; font-weight: bold; height: 40px;")
            self.log("系统停止.")

    def handle_alarm_signal(self, msg):
        # 尝试从日志消息中解析出报警类型来播放声音
        # 消息格式: "[timestamp] ⚠️ 触发报警: TYPE [status]"
        if "⚠️ 触发报警:" in msg:
            try:
                parts = msg.split("⚠️ 触发报警:")
                if len(parts) > 1:
                    # 取出 'LOCAL', 'OVERVIEW' 等
                    # 比如 " LOCAL [status...]" -> "LOCAL"
                    sound_type = parts[1].strip().split()[0].lower()
                    if sound_type in self.sounds:
                        effect = self.sounds[sound_type]
                        if not effect.isPlaying():
                            effect.play()
            except Exception as e:
                print(f"音频播放解析错误: {e}")

    def show_debug_window(self):
        self.debug_window.show()
        self.debug_timer.start(100) # 10FPS 刷新debug界面

    def update_debug_view(self):
        if not self.debug_window.isVisible():
            self.debug_timer.stop()
            return
        
        regions = self.cfg.get("regions")
        img_local = self.vision.capture_screen(regions.get("local"))
        img_overview = self.vision.capture_screen(regions.get("overview"))
        img_monster = self.vision.capture_screen(regions.get("monster"))
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
