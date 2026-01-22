# ================= 必须放在最开头 =================
import ctypes
import os
try:
    # 告诉 Windows 该程序支持高 DPI，防止坐标错位
    ctypes.windll.shcore.SetProcessDpiAwareness(1) 
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
# =================================================

import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QGroupBox, QDoubleSpinBox, QLineEdit, QTextEdit, 
                             QDialog, QGridLayout, QFrame)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QImage, QFont
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker

# === EVE 风格样式表 ===
STYLESHEET = """
QMainWindow {
    background-color: #121212;
}
QGroupBox {
    border: 1px solid #3d3d3d;
    border-radius: 4px;
    margin-top: 20px;
    font-weight: bold;
    color: #e0e0e0;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
    color: #00e5ff; /* EVE Cyan */
}
QLabel {
    color: #b0b0b0;
    font-family: "Segoe UI", sans-serif;
}
QLineEdit, QDoubleSpinBox {
    background-color: #1e1e1e;
    border: 1px solid #3d3d3d;
    color: #00ffaa;
    padding: 4px;
    border-radius: 2px;
}
QPushButton {
    background-color: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #444;
    padding: 6px;
    border-radius: 2px;
}
QPushButton:hover {
    background-color: #3d3d3d;
    border-color: #00e5ff;
}
QPushButton:pressed {
    background-color: #00e5ff;
    color: #000;
}
/* 启动按钮特殊样式 */
QPushButton#StartBtn {
    background-color: #1a3300;
    border: 1px solid #336600;
    color: #ccff99;
    font-weight: bold;
    font-size: 14px;
}
QPushButton#StartBtn:checked {
    background-color: #330000;
    border: 1px solid #ff3333;
    color: #ffcccc;
}
/* 日志区域 */
QTextEdit {
    background-color: #000000;
    border: 1px solid #00e5ff;
    color: #00ff00;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11px;
}
"""

class DebugWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EVE Sentry - 视觉调试")
        self.setStyleSheet("background-color: #121212; color: #fff;")
        layout = QHBoxLayout()
        
        self.lbl_local = self._create_monitor("Local")
        self.lbl_overview = self._create_monitor("Overview")
        self.lbl_monster = self._create_monitor("Monster")

        layout.addWidget(self.lbl_local)
        layout.addWidget(self.lbl_overview)
        layout.addWidget(self.lbl_monster)
        self.setLayout(layout)

    def _create_monitor(self, title):
        lbl = QLabel(title)
        lbl.setFixedSize(200, 200)
        lbl.setStyleSheet("border: 1px dashed #444; background: #000; color: #555;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

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
        self.setWindowTitle("EVE PRO SENTRY")
        self.resize(380, 550) # 缩小窗口尺寸
        
        # 应用样式表
        self.setStyleSheet(STYLESHEET)
        
        # 初始化核心
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.logic.log_signal.connect(self.log)
        
        self.sounds = {} 
        self.load_sounds()

        self.setup_ui()
        
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_view)
        
        self.logic.log_signal.connect(self.handle_alarm_signal)
        self.check_auto_start()

    def check_auto_start(self):
        regions = self.cfg.get("regions")
        if regions.get("local") is not None or regions.get("overview") is not None:
            self.log(">> SYSTEM READY. AUTO-START INITIATED.")
            self.toggle_monitoring()
        else:
            self.log(">> WAITING FOR CONFIGURATION...")

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
        # 使用更紧凑的边距
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === 标题栏 (伪装成HUD风格) ===
        title_box = QHBoxLayout()
        lbl_title = QLabel("TACTICAL ALERT SYSTEM")
        lbl_title.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 16px; letter-spacing: 2px;")
        title_box.addWidget(lbl_title)
        title_box.addStretch()
        main_layout.addLayout(title_box)

        # === 区域设置 (网格布局) ===
        grp_region = QGroupBox("SCAN SECTORS")
        # 横向排列，减少垂直占用
        grid_region = QGridLayout()
        grid_region.setSpacing(5)
        
        self.btns_region = {}
        for idx, key in enumerate(["local", "overview", "monster"]):
            # 简化按钮文字：L-Area, O-Area, M-Area
            display_name = f"{key.upper()} AREA"
            btn = QPushButton(display_name)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, k=key: self.start_region_selection(k))
            # 根据是否已配置，改变边框颜色（视觉反馈）
            if self.cfg.get("regions").get(key):
                btn.setStyleSheet("border-color: #00ffaa; color: #00ffaa;")
            self.btns_region[key] = btn
            
            # 放在一行
            grid_region.addWidget(btn, 0, idx)
            
        grp_region.setLayout(grid_region)
        main_layout.addWidget(grp_region)
        
        # === 核心配置 ===
        grp_config = QGroupBox("PARAMETERS")
        flow_layout = QGridLayout()
        flow_layout.setVerticalSpacing(8)

        # 阈值设置
        lbl_th = QLabel("HOSTILE THRESHOLD:")
        spin_hostile = QDoubleSpinBox()
        spin_hostile.setRange(0.1, 1.0)
        spin_hostile.setSingleStep(0.05)
        spin_hostile.setValue(self.cfg.get("thresholds")["hostile"])
        spin_hostile.valueChanged.connect(lambda v: self.update_threshold("hostile", v))
        spin_hostile.setFixedWidth(60)
        
        flow_layout.addWidget(lbl_th, 0, 0)
        flow_layout.addWidget(spin_hostile, 0, 1)

        # Webhook
        lbl_hook = QLabel("WEBHOOK:")
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.setPlaceholderText("Discord/Slack URL...")
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        
        flow_layout.addWidget(lbl_hook, 1, 0)
        flow_layout.addWidget(self.line_webhook, 1, 1)

        grp_config.setLayout(flow_layout)
        main_layout.addWidget(grp_config)

        # === 音频设置 (紧凑版) ===
        grp_audio = QGroupBox("AUDIO FEED")
        grid_audio = QGridLayout()
        grid_audio.setVerticalSpacing(4)
        
        self.audio_status_labels = {}

        # 2x2 布局
        audio_keys = ["local", "overview", "monster", "mixed"]
        for idx, key in enumerate(audio_keys):
            row = idx // 2
            col = idx % 2
            
            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0,0,0,0)
            h_layout.setSpacing(5)
            
            btn_load = QPushButton(key.upper())
            btn_load.setToolTip(f"Set sound for {key}")
            btn_load.setFixedWidth(80)
            
            # 状态指示灯 (小圆点或文字)
            lbl_status = QLabel("OFF")
            lbl_status.setStyleSheet("color: #555; font-size: 10px;")
            self.audio_status_labels[key] = lbl_status
            
            # 初始化状态颜色
            if self.cfg.get("audio_paths").get(key):
                lbl_status.setText("RDY")
                lbl_status.setStyleSheet("color: #00ffaa; font-weight:bold; font-size: 10px;")
            
            btn_load.clicked.connect(lambda _, k=key: self.select_audio(k))
            
            h_layout.addWidget(btn_load)
            h_layout.addWidget(lbl_status)
            h_layout.addStretch()
            
            grid_audio.addWidget(container, row, col)

        grp_audio.setLayout(grid_audio)
        main_layout.addWidget(grp_audio)

        # === 底部控制栏 ===
        ctrl_layout = QHBoxLayout()
        
        self.btn_start = QPushButton("START SYSTEM")
        self.btn_start.setObjectName("StartBtn") # 绑定特殊的QSSID
        self.btn_start.setCheckable(True) # 变成开关样式
        self.btn_start.setFixedHeight(45)
        self.btn_start.clicked.connect(self.toggle_monitoring)
        
        self.btn_debug = QPushButton("👁") # 仅用图标节省空间
        self.btn_debug.setFixedSize(45, 45)
        self.btn_debug.setToolTip("Open Visual Debugger")
        self.btn_debug.setStyleSheet("font-size: 20px; border-radius: 4px;")
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        ctrl_layout.addWidget(self.btn_start)
        ctrl_layout.addWidget(self.btn_debug)
        main_layout.addLayout(ctrl_layout)

        # === 日志终端 ===
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        # 固定高度，像一个控制台窗口
        self.txt_log.setFixedHeight(120) 
        self.txt_log.document().setMaximumBlockCount(200) 
        main_layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self)

    def start_region_selection(self, key):
        self.selector = RegionSelector()
        self.selector.selection_finished.connect(lambda rect: self.save_region(key, rect))
        self.selector.show()

    def save_region(self, key, rect):
        regions = self.cfg.get("regions")
        regions[key] = list(rect)
        self.cfg.set("regions", regions)
        self.log(f">> REGION SET [{key.upper()}]: {rect}")
        # 更新按钮样式表示已设置
        if key in self.btns_region:
             self.btns_region[key].setStyleSheet("border-color: #00ffaa; color: #00ffaa;")

    def update_threshold(self, key, val):
        t = self.cfg.get("thresholds")
        t[key] = val
        self.cfg.set("thresholds", t)

    def select_audio(self, key):
        fname, _ = QFileDialog.getOpenFileName(self, "Load Audio", "", "Audio (*.wav *.mp3)")
        if fname:
            paths = self.cfg.get("audio_paths")
            paths[key] = fname
            self.cfg.set("audio_paths", paths)
            self.load_sounds()
            # 更新UI状态
            lbl = self.audio_status_labels.get(key)
            if lbl:
                lbl.setText("RDY")
                lbl.setStyleSheet("color: #00ffaa; font-weight:bold; font-size: 10px;")

    def toggle_monitoring(self):
        # 按钮状态由 logic 驱动，或者这里驱动 logic
        if not self.logic.running:
            regions = self.cfg.get("regions")
            if not regions.get("local") and not regions.get("overview"):
                self.log(">> ERROR: NO REGION CONFIGURED.")
                self.btn_start.setChecked(False)
                return

            self.logic.start()
            self.btn_start.setText("SYSTEM ACTIVE")
            self.btn_start.setChecked(True) # 保持按下状态
            self.log(">> MONITORING STARTED")
        else:
            self.logic.stop()
            self.btn_start.setText("START SYSTEM")
            self.btn_start.setChecked(False)
            self.log(">> MONITORING STOPPED")

    def handle_alarm_signal(self, msg):
        self.log(msg)
        if "⚠️ 触发:" in msg:
            try:
                parts = msg.split("⚠️ 触发:")
                if len(parts) > 1:
                    sound_type = parts[1].strip().split()[0].lower()
                    if sound_type in self.sounds:
                        effect = self.sounds[sound_type]
                        if not effect.isPlaying():
                            effect.play()
            except: pass

    def show_debug_window(self):
        self.debug_window.show()
        self.debug_timer.start(100)

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
        # 移除过多的时间戳，因为 audio_logic 已经带了
        # 这里只做格式化
        clean_text = text.replace("⚠️", "[ALERT]").replace("✅", "[SAFE]")
        self.txt_log.append(clean_text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设置全局字体
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
