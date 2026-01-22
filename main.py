import sys
import os
import ctypes
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QGroupBox, QDoubleSpinBox, QLineEdit, QTextEdit, QDialog, QFrame)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker
from core.i18n import Translator

# === Hi-DPI Fix ===
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1) 
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

# === EVE Style CSS ===
EVE_STYLE = """
QMainWindow {
    background-color: #121212;
}
QWidget {
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 11px;
    color: #cccccc;
}
QGroupBox {
    border: 1px solid #444;
    border-radius: 3px;
    margin-top: 10px;
    font-weight: bold;
    color: #00bcd4; /* Cyan EVE Color */
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 3px;
    left: 10px;
}
QPushButton {
    background-color: #2a2a2a;
    border: 1px solid #444;
    color: #eee;
    padding: 4px;
    border-radius: 2px;
}
QPushButton:hover {
    background-color: #3a3a3a;
    border-color: #00bcd4;
}
QPushButton:pressed {
    background-color: #00bcd4;
    color: #000;
}
/* 特殊按钮样式：启动 */
QPushButton#btn_start {
    background-color: #1b3a2a;
    border: 1px solid #2e7d32;
    color: #4caf50;
    font-weight: bold;
    font-size: 12px;
}
QPushButton#btn_start:checked { /* 停止状态 */
    background-color: #3b1a1a;
    border: 1px solid #c62828;
    color: #ef5350;
}
QPushButton#btn_debug {
    background-color: #1a2a3a;
    border: 1px solid #0277bd;
    color: #29b6f6;
}
QLineEdit, QDoubleSpinBox {
    background-color: #000;
    border: 1px solid #333;
    color: #00bcd4;
    padding: 2px;
}
QTextEdit {
    background-color: #080808;
    border: 1px solid #333;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 10px;
    color: #aaa;
}
/* 滚动条美化 */
QScrollBar:vertical {
    border: none;
    background: #111;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #333;
    min-height: 20px;
}
"""

class DebugWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VISUAL FEED")
        self.setStyleSheet("background-color: #000; color: #00bcd4;")
        layout = QHBoxLayout()
        layout.setContentsMargins(5,5,5,5)
        
        self.labels = {}
        for key in ["Local", "Overview", "Npc"]:
            vbox = QVBoxLayout()
            lbl_title = QLabel(key.upper())
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_img = QLabel()
            lbl_img.setFixedSize(150, 150)
            lbl_img.setStyleSheet("border: 1px solid #333; background: #111;")
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_img)
            layout.addLayout(vbox)
            self.labels[key] = lbl_img
            
        self.setLayout(layout)

    def update_images(self, img_local, img_overview, img_monster):
        def np2pixmap(np_img):
            if np_img is None: return QPixmap()
            h, w, ch = np_img.shape
            bytes_per_line = ch * w
            qimg = QImage(np_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            return QPixmap.fromImage(qimg).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio)

        self.labels["Local"].setPixmap(np2pixmap(img_local))
        self.labels["Overview"].setPixmap(np2pixmap(img_overview))
        self.labels["Npc"].setPixmap(np2pixmap(img_monster))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.i18n = Translator(self.refresh_ui_text) # 绑定刷新回调
        
        # 恢复上次保存的语言
        saved_lang = self.cfg.get("language")
        if saved_lang:
            self.i18n.set_language(saved_lang)

        self.init_core()
        self.setup_ui()
        self.refresh_ui_text() # 第一次刷新文字
        
        # 应用样式
        self.setStyleSheet(EVE_STYLE)
        # 紧凑尺寸
        self.resize(380, 520) 

    def init_core(self):
        self.sounds = {} 
        self.load_sounds()
        self.logic.log_signal.connect(self.log)
        self.logic.log_signal.connect(self.handle_alarm_signal)
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_view)
        
        # Auto Start Logic
        QTimer.singleShot(1000, self.check_auto_start)

    def check_auto_start(self):
        regions = self.cfg.get("regions")
        if regions.get("local") is not None or regions.get("overview") is not None:
            self.log("Auto-Sequence Initiated...")
            self.toggle_monitoring()

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
        self.central = QWidget()
        self.setCentralWidget(self.central)
        
        # 主布局，紧凑模式
        main_layout = QVBoxLayout(self.central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === 顶部: 标题 + 语言切换 ===
        top_layout = QHBoxLayout()
        self.lbl_title = QLabel("EVE WARNING")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
        
        self.btn_lang = QPushButton("EN")
        self.btn_lang.setFixedSize(30, 20)
        self.btn_lang.clicked.connect(self.toggle_language)
        
        top_layout.addWidget(self.lbl_title)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_lang)
        main_layout.addLayout(top_layout)

        # === 区域设置 (一行三个小按钮) ===
        self.grp_monitor = QGroupBox("Monitoring Sectors")
        layout_mon = QHBoxLayout()
        layout_mon.setSpacing(5)
        
        self.btn_set_local = QPushButton("Local")
        self.btn_set_overview = QPushButton("Overview")
        self.btn_set_npc = QPushButton("Rats")
        
        for btn, key in [(self.btn_set_local, "local"), 
                         (self.btn_set_overview, "overview"), 
                         (self.btn_set_npc, "monster")]:
            btn.setFixedHeight(25)
            btn.clicked.connect(lambda _, k=key: self.start_region_selection(k))
            layout_mon.addWidget(btn)
            
        self.grp_monitor.setLayout(layout_mon)
        main_layout.addWidget(self.grp_monitor)

        # === 参数与音频配置 ===
        self.grp_config = QGroupBox("Configuration")
        layout_cfg = QVBoxLayout()
        layout_cfg.setSpacing(5)

        # 阈值 & Webhook
        row1 = QHBoxLayout()
        self.lbl_thresh = QLabel("Threshold:")
        self.spin_hostile = QDoubleSpinBox()
        self.spin_hostile.setRange(0.1, 1.0)
        self.spin_hostile.setSingleStep(0.05)
        self.spin_hostile.setValue(self.cfg.get("thresholds")["hostile"])
        self.spin_hostile.valueChanged.connect(lambda v: self.update_cfg("thresholds", "hostile", v))
        self.spin_hostile.setFixedWidth(50)
        
        row1.addWidget(self.lbl_thresh)
        row1.addWidget(self.spin_hostile)
        layout_cfg.addLayout(row1)
        
        row2 = QHBoxLayout()
        self.lbl_webhook = QLabel("Webhook:")
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        row2.addWidget(self.lbl_webhook)
        row2.addWidget(self.line_webhook)
        layout_cfg.addLayout(row2)

        # 音频选择 (简化显示)
        # 做成Grid，左边标签，右边按钮
        for key in ["local", "overview", "monster", "mixed"]:
            row = QHBoxLayout()
            lbl = QLabel(f"{key}:")
            # 存储引用以便翻译
            setattr(self, f"lbl_sound_{key}", lbl) 
            
            # 显示文件名的Label (淡色)
            path_val = self.cfg.get("audio_paths").get(key, "")
            fname = os.path.basename(path_val) if path_val else "---"
            lbl_file = QLabel(fname)
            lbl_file.setStyleSheet("color: #666;")
            
            btn_sel = QPushButton("...")
            btn_sel.setFixedSize(25, 20)
            btn_sel.clicked.connect(lambda _, k=key, l=lbl_file: self.select_audio(k, l))
            
            row.addWidget(lbl)
            row.addWidget(lbl_file)
            row.addStretch()
            row.addWidget(btn_sel)
            layout_cfg.addLayout(row)

        self.grp_config.setLayout(layout_cfg)
        main_layout.addWidget(self.grp_config)

        # === 主控制按钮区 ===
        layout_ctrl = QHBoxLayout()
        
        self.btn_start = QPushButton("ENGAGE")
        self.btn_start.setObjectName("btn_start") # 用于CSS
        self.btn_start.setFixedHeight(35)
        self.btn_start.clicked.connect(self.toggle_monitoring)
        
        self.btn_debug = QPushButton("VISUAL")
        self.btn_debug.setObjectName("btn_debug")
        self.btn_debug.setFixedSize(60, 35)
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        layout_ctrl.addWidget(self.btn_start)
        layout_ctrl.addWidget(self.btn_debug)
        main_layout.addLayout(layout_ctrl)

        # === 日志区 ===
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self)
        self.log(self.i18n.get("log_ready"))

    def refresh_ui_text(self):
        """核心方法：根据当前语言刷新所有界面文字"""
        _ = self.i18n.get
        
        self.setWindowTitle(_("window_title"))
        self.lbl_title.setText(_("window_title"))
        
        self.grp_monitor.setTitle(_("grp_monitor"))
        self.grp_config.setTitle(_("grp_config"))
        
        self.btn_set_local.setText(_("btn_local"))
        self.btn_set_overview.setText(_("btn_overview"))
        self.btn_set_npc.setText(_("btn_npc"))
        
        self.lbl_thresh.setText(_("lbl_threshold"))
        self.lbl_webhook.setText(_("lbl_webhook"))
        
        self.lbl_sound_local.setText(_("lbl_sound_local"))
        self.lbl_sound_overview.setText(_("lbl_sound_overview"))
        self.lbl_sound_monster.setText(_("lbl_sound_npc"))
        self.lbl_sound_mixed.setText(_("lbl_sound_mixed"))
        
        if not self.logic.running:
            self.btn_start.setText(_("btn_start"))
        else:
            self.btn_start.setText(_("btn_stop"))
            
        self.btn_debug.setText(_("btn_debug"))
        self.btn_lang.setText(_("btn_lang"))

    def toggle_language(self):
        self.i18n.toggle()
        # 保存设置
        self.cfg.set("language", self.i18n.lang)

    # ... (以下方法逻辑保持不变，只需微调日志输出) ...
    
    def start_region_selection(self, key):
        self.selector = RegionSelector()
        self.selector.selection_finished.connect(lambda rect: self.save_region(key, rect))
        self.selector.show()

    def save_region(self, key, rect):
        regions = self.cfg.get("regions")
        regions[key] = list(rect)
        self.cfg.set("regions", regions)
        self.log(f"{self.i18n.get('region_updated')}: {key.upper()}")

    def update_cfg(self, section, key, val):
        t = self.cfg.get(section)
        t[key] = val
        self.cfg.set(section, t)

    def select_audio(self, key, label_widget):
        fname, _ = QFileDialog.getOpenFileName(self, "Load Audio", "", "Audio (*.wav *.mp3)")
        if fname:
            paths = self.cfg.get("audio_paths")
            paths[key] = fname
            self.cfg.set("audio_paths", paths)
            label_widget.setText(os.path.basename(fname))
            self.load_sounds()

    def toggle_monitoring(self):
        _ = self.i18n.get
        if not self.logic.running:
            regions = self.cfg.get("regions")
            if not regions.get("local") and not regions.get("overview"):
                self.log(_("log_region_err"))
                return

            self.logic.start()
            self.btn_start.setText(_("btn_stop"))
            self.btn_start.setChecked(True) # 改变样式
            self.log(_("log_start"))
        else:
            self.logic.stop()
            self.btn_start.setText(_("btn_start"))
            self.btn_start.setChecked(False)
            self.log(_("log_stop"))

    def handle_alarm_signal(self, msg):
        # 注意：这里我们接收到的是 logic 层发来的原始字符串
        # 暂时不翻译日志里的动态分析数据，只翻译 UI
        if "⚠️" in msg:
            # 简单的解析逻辑，兼容中文和英文环境的底层逻辑
            for keyword in ["mixed", "overview", "local", "monster"]:
                if keyword.upper() in msg.upper():
                    if keyword in self.sounds:
                        effect = self.sounds[keyword]
                        if not effect.isPlaying():
                            effect.play()
                    break

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
        self.txt_log.append(text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
