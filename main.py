import sys
import os
import ctypes
from ctypes import wintypes
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QGroupBox, QDoubleSpinBox, QLineEdit, QTextEdit, QDialog, QFrame, QGridLayout)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker
from core.i18n import Translator

# =============================================================================
# === 增强版 Hi-DPI 修复 ===
# =============================================================================
def apply_dpi_fix():
    if os.name == 'nt':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2) 
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass

apply_dpi_fix()
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"

# === EVE Style CSS ===
EVE_STYLE = """
QMainWindow { background-color: #121212; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 11px; color: #cccccc; }
QGroupBox { border: 1px solid #444; border-radius: 3px; margin-top: 10px; font-weight: bold; color: #00bcd4; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; left: 10px; }
QPushButton { background-color: #2a2a2a; border: 1px solid #444; color: #eee; padding: 4px; border-radius: 2px; }
QPushButton:hover { background-color: #3a3a3a; border-color: #00bcd4; }
QPushButton:pressed { background-color: #00bcd4; color: #000; }
QPushButton#btn_start { background-color: #1b3a2a; border: 1px solid #2e7d32; color: #4caf50; font-weight: bold; font-size: 12px; }
QPushButton#btn_start:checked { background-color: #3b1a1a; border: 1px solid #c62828; color: #ef5350; }
QPushButton#btn_debug { background-color: #1a2a3a; border: 1px solid #0277bd; color: #29b6f6; font-weight: bold; }
QLineEdit, QDoubleSpinBox { background-color: #000; border: 1px solid #333; color: #00bcd4; padding: 2px; }
QTextEdit { background-color: #080808; border: 1px solid #333; font-family: "Consolas", "Courier New", monospace; font-size: 10px; color: #aaa; }
QScrollBar:vertical { border: none; background: #111; width: 8px; }
QScrollBar::handle:vertical { background: #333; min-height: 20px; }
"""

class DebugWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LIVE VIEW")
        self.setStyleSheet("background-color: #000; color: #00bcd4;")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(5,5,5,5)
        layout.setSpacing(10)
        
        self.labels = {}
        # 增加 Probe 调试窗口
        for key in ["Local", "Overview", "Npc", "Probe"]:
            vbox = QVBoxLayout()
            lbl_title = QLabel(key.upper())
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_title.setFixedHeight(20)
            
            lbl_img = QLabel()
            lbl_img.setFixedSize(100, 500) # 稍微调小一点宽度以容纳4个
            lbl_img.setStyleSheet("border: 1px solid #333; background: #111;")
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_img)
            layout.addLayout(vbox)
            self.labels[key] = lbl_img
            
        self.setLayout(layout)
        self.resize(500, 550)

    def update_images(self, img_local, img_overview, img_monster, img_probe):
        def np2pixmap(np_img):
            if np_img is None: return QPixmap()
            h, w, ch = np_img.shape
            bytes_per_line = ch * w
            qimg = QImage(np_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
            return QPixmap.fromImage(qimg).scaled(100, 500, Qt.AspectRatioMode.KeepAspectRatio)

        self.labels["Local"].setPixmap(np2pixmap(img_local))
        self.labels["Overview"].setPixmap(np2pixmap(img_overview))
        self.labels["Npc"].setPixmap(np2pixmap(img_monster))
        self.labels["Probe"].setPixmap(np2pixmap(img_probe))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.i18n = Translator(None) 
        
        self.init_core()
        self.setup_ui()
        
        self.setStyleSheet(EVE_STYLE)
        self.resize(420, 600) 

        self.i18n.callback = self.refresh_ui_text 
        saved_lang = self.cfg.get("language")
        if saved_lang:
            self.i18n.set_language(saved_lang)
        else:
            self.refresh_ui_text()

    def init_core(self):
        self.sounds = {} 
        self.load_sounds()
        self.logic.log_signal.connect(self.log)
        self.logic.log_signal.connect(self.handle_alarm_signal)
        # 连接探针独立信号
        self.logic.probe_signal.connect(self.handle_probe_signal)
        
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_view)
        
        # === 待机提示计时器 ===
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(120 * 1000) # 2分钟 = 120秒
        self.idle_timer.timeout.connect(self.play_idle_sound)
        self.idle_timer.start() # 软件启动即开始计时

        QTimer.singleShot(1000, self.check_auto_start)

    def check_auto_start(self):
        regions = self.cfg.get("regions")
        if regions.get("local") is not None or regions.get("overview") is not None:
            self.log("Auto-Sequence Initiated...")
            self.toggle_monitoring()

    def load_sounds(self):
        # 增加 probe 和 idle
        for key in ["local", "overview", "monster", "mixed", "probe", "idle"]:
            path = self.cfg.get_audio_path(key)
            if path and os.path.exists(path):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(path))
                effect.setVolume(1.0)
                self.sounds[key] = effect
            else:
                if key in self.sounds:
                    del self.sounds[key]

    def play_idle_sound(self):
        # 只有当逻辑没有运行（即处于停止状态）时才播放
        if not self.logic.running:
            if "idle" in self.sounds:
                self.sounds["idle"].play()
                self.log(self.i18n.get("log_idle_alert"))

    def setup_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        
        main_layout = QVBoxLayout(self.central)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === 顶部 ===
        top_layout = QHBoxLayout()
        self.lbl_title = QLabel("EVE ALERT SYSTEM")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
        
        self.btn_lang = QPushButton("EN")
        self.btn_lang.setFixedSize(30, 20)
        self.btn_lang.clicked.connect(self.toggle_language)
        
        top_layout.addWidget(self.lbl_title)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_lang)
        main_layout.addLayout(top_layout)

        # === 区域设置 (Grid) ===
        self.grp_monitor = QGroupBox("Sectors")
        grid_mon = QGridLayout()
        grid_mon.setSpacing(4)
        
        self.btn_set_local = QPushButton("Local")
        self.btn_set_overview = QPushButton("Overview")
        self.btn_set_npc = QPushButton("Rats")
        self.btn_set_probe = QPushButton("Probe") # 新增
        
        buttons = [
            (self.btn_set_local, "local", 0, 0),
            (self.btn_set_overview, "overview", 0, 1),
            (self.btn_set_npc, "monster", 1, 0),
            (self.btn_set_probe, "probe", 1, 1)
        ]
        
        for btn, key, r, c in buttons:
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, k=key: self.start_region_selection(k))
            grid_mon.addWidget(btn, r, c)
            
        self.grp_monitor.setLayout(grid_mon)
        main_layout.addWidget(self.grp_monitor)

        # === 配置区 (Grid) ===
        self.grp_config = QGroupBox("Settings")
        layout_cfg = QVBoxLayout()
        layout_cfg.setSpacing(6)

        # 阈值 Grid
        grid_thresh = QGridLayout()
        grid_thresh.setSpacing(4)
        
        # 封装阈值控件生成
        def create_thresh_ctrl(label_text, config_key, r, c):
            lbl = QLabel(label_text)
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 1.0)
            spin.setSingleStep(0.01)
            spin.setValue(self.cfg.get("thresholds").get(config_key, 0.95))
            spin.valueChanged.connect(lambda v: self.update_cfg("thresholds", config_key, v))
            grid_thresh.addWidget(lbl, r, c*2)
            grid_thresh.addWidget(spin, r, c*2+1)
            return lbl, spin

        self.lbl_th_local, self.spin_local = create_thresh_ctrl("Loc %", "local", 0, 0)
        self.lbl_th_over, self.spin_over = create_thresh_ctrl("Ovr %", "overview", 0, 1)
        self.lbl_th_npc, self.spin_npc = create_thresh_ctrl("Rat %", "monster", 1, 0)
        self.lbl_th_probe, self.spin_probe = create_thresh_ctrl("Prb %", "probe", 1, 1) # 新增
        
        layout_cfg.addLayout(grid_thresh)
        
        # Webhook
        row_wh = QHBoxLayout()
        self.lbl_webhook = QLabel("Webhook:")
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        row_wh.addWidget(self.lbl_webhook)
        row_wh.addWidget(self.line_webhook)
        layout_cfg.addLayout(row_wh)
        
        # 音频设置 (使用两列 Grid 以节省空间)
        grid_audio = QGridLayout()
        grid_audio.setSpacing(4)
        
        audio_keys = ["local", "overview", "monster", "mixed", "probe", "idle"]
        self.audio_labels = {}
        
        for idx, key in enumerate(audio_keys):
            row = idx // 2
            col = idx % 2
            
            # 容器 widget
            container = QWidget()
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0,0,0,0)
            h_layout.setSpacing(2)
            
            lbl_name = QLabel(key.capitalize())
            lbl_name.setFixedWidth(40)
            self.audio_labels[key] = lbl_name # 保存引用以便翻译
            
            path_val = self.cfg.get("audio_paths").get(key, "")
            fname = os.path.basename(path_val) if path_val else "-"
            lbl_file = QLabel(fname)
            lbl_file.setStyleSheet("color: #666; font-size: 9px;")
            
            btn_sel = QPushButton("..")
            btn_sel.setFixedSize(18, 18)
            btn_sel.clicked.connect(lambda _, k=key, l=lbl_file: self.select_audio(k, l))
            
            h_layout.addWidget(lbl_name)
            h_layout.addWidget(lbl_file)
            h_layout.addWidget(btn_sel)
            
            grid_audio.addWidget(container, row, col)

        layout_cfg.addLayout(grid_audio)

        self.grp_config.setLayout(layout_cfg)
        main_layout.addWidget(self.grp_config)

        # === 底部控制 ===
        layout_ctrl = QHBoxLayout()
        
        self.btn_start = QPushButton("ENGAGE")
        self.btn_start.setObjectName("btn_start") 
        self.btn_start.setFixedHeight(35) 
        self.btn_start.clicked.connect(self.toggle_monitoring)
        
        self.btn_debug = QPushButton("VIEW")
        self.btn_debug.setObjectName("btn_debug")
        self.btn_debug.setFixedSize(70, 35) 
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        layout_ctrl.addWidget(self.btn_start)
        layout_ctrl.addWidget(self.btn_debug)
        main_layout.addLayout(layout_ctrl)

        # === 日志 ===
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self)
        self.log(self.i18n.get("log_ready"))

    def refresh_ui_text(self):
        _ = self.i18n.get
        
        self.setWindowTitle(_("window_title"))
        self.lbl_title.setText(_("window_title"))
        
        self.grp_monitor.setTitle(_("grp_monitor"))
        self.grp_config.setTitle(_("grp_config"))
        
        self.btn_set_local.setText(_("btn_local"))
        self.btn_set_overview.setText(_("btn_overview"))
        self.btn_set_npc.setText(_("btn_npc"))
        self.btn_set_probe.setText(_("btn_probe"))
        
        self.lbl_th_local.setText(_("lbl_th_local"))
        self.lbl_th_over.setText(_("lbl_th_over"))
        self.lbl_th_npc.setText(_("lbl_th_npc"))
        self.lbl_th_probe.setText(_("lbl_th_probe"))
        
        self.lbl_webhook.setText(_("lbl_webhook"))
        
        # 更新音频标签
        mapping = {
            "local": _("lbl_sound_local"),
            "overview": _("lbl_sound_overview"),
            "monster": _("lbl_sound_npc"),
            "mixed": _("lbl_sound_mixed"),
            "probe": _("lbl_sound_probe"),
            "idle": _("lbl_sound_idle")
        }
        for k, text in mapping.items():
            if k in self.audio_labels:
                self.audio_labels[k].setText(text)
        
        if not self.logic.running:
            self.btn_start.setText(_("btn_start"))
        else:
            self.btn_start.setText(_("btn_stop"))
            
        self.btn_debug.setText(_("btn_debug"))
        self.btn_lang.setText(_("btn_lang"))

    def toggle_language(self):
        self.i18n.toggle()
        self.cfg.set("language", self.i18n.lang)

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
        fname, _ = QFileDialog.getOpenFileName(self, "Audio File", "", "Audio (*.wav *.mp3)")
        if fname:
            cwd = os.getcwd()
            try:
                rel_path = os.path.relpath(fname, cwd)
                if rel_path.startswith(".."):
                    save_path = fname
                else:
                    save_path = rel_path
            except ValueError:
                save_path = fname

            paths = self.cfg.get("audio_paths")
            paths[key] = save_path
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
            self.idle_timer.stop() # 停止待机计时
            self.btn_start.setText(_("btn_stop"))
            self.btn_start.setChecked(True)
            self.log(_("log_start"))
        else:
            self.logic.stop()
            self.idle_timer.start() # 重新开始待机计时
            self.btn_start.setText(_("btn_start"))
            self.btn_start.setChecked(False)
            self.log(_("log_stop"))

    def handle_alarm_signal(self, msg):
        if "⚠️" in msg:
            for keyword in ["mixed", "overview", "local", "monster"]:
                if keyword.upper() in msg.upper():
                    if keyword in self.sounds:
                        effect = self.sounds[keyword]
                        if not effect.isPlaying():
                            effect.play()
                    break

    def handle_probe_signal(self, detected):
        if detected:
            if "probe" in self.sounds:
                # 探针声音直接播放，不检查 isPlaying，允许叠加
                self.sounds["probe"].play()

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
        img_probe = self.vision.capture_screen(regions.get("probe"))
        self.debug_window.update_images(img_local, img_overview, img_monster, img_probe)

    def log(self, text):
        self.txt_log.append(text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
