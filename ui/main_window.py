import os
import ctypes
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QGroupBox, QDoubleSpinBox, 
                             QTextEdit, QFrame, QGridLayout, QScrollArea, QApplication)
from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QIcon, QGuiApplication
from PyQt6.QtMultimedia import QSoundEffect

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker
from core.i18n import Translator
from ui.components import GroupWidget, SettingsDialog, DebugWindow, resource_path, BTN_STYLE

# 全局 CSS
GLOBAL_STYLE = """
QMainWindow { background-color: #121212; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 11px; color: #cccccc; }
QScrollArea { background-color: #121212; border: none; }
QScrollArea > QWidget > QWidget { background-color: #121212; }
QLineEdit, QDoubleSpinBox { background-color: #080808; border: 1px solid #333; color: #00bcd4; padding: 2px; }
QTextEdit { background-color: #080808; border: 1px solid #333; font-family: "Consolas", "Courier New", monospace; font-size: 10px; color: #aaa; }
QScrollBar:vertical { border: none; background: #111; width: 8px; }
QScrollBar::handle:vertical { background: #333; min-height: 20px; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(GLOBAL_STYLE)
        
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.i18n = Translator(self.refresh_ui_text) 
        
        self.init_core()
        self.setup_ui()
        self.refresh_ui_text()
        
        icon_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        pos = self.cfg.get("window_pos")
        if pos and len(pos) == 2:
            x, y = pos
            if x < 0 or y < 0:
                screens = QGuiApplication.screens()
                is_visible = False
                for screen in screens:
                    if screen.geometry().contains(x, y):
                        is_visible = True
                        break
                if not is_visible:
                    x, y = 100, 100
            self.move(x, y)

    def closeEvent(self, event):
        pos = [self.x(), self.y()]
        self.cfg.set("window_pos", pos)
        self.logic.stop()
        event.accept()

    def init_core(self):
        self.sounds = {} 
        self.load_sounds()
        self.logic.log_signal.connect(self.log)
        self.logic.log_signal.connect(self.handle_alarm_signal)
        self.logic.probe_signal.connect(self.handle_probe_signal)
        
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.update_debug_view)
        
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(120 * 1000) 
        self.idle_timer.timeout.connect(self.play_idle_sound)
        self.idle_timer.start() 

        QTimer.singleShot(1000, self.check_auto_start)

    def check_auto_start(self):
        groups = self.cfg.get("groups")
        if groups and (groups[0]["regions"].get("local") or groups[0]["regions"].get("overview")):
            self.log("Auto-Sequence Initiated...")
            self.toggle_monitoring()

    def load_sounds(self):
        for key in ["local", "overview", "monster", "mixed", "probe", "idle"]:
            path = self.cfg.get_audio_path(key)
            if path and os.path.exists(path):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(path))
                effect.setVolume(1.0)
                self.sounds[key] = effect

    def play_idle_sound(self):
        if not self.logic.running and "idle" in self.sounds:
            self.sounds["idle"].play()
            self.log(self.i18n.get("log_idle_alert"))

    def setup_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.resize(400, 600) # 高度可以稍微减小，因为移除了阈值区
        
        main_layout = QVBoxLayout(self.central)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # 1. 顶部标题
        top = QHBoxLayout()
        self.lbl_title = QLabel("EVE ALERT SYSTEM")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff; letter-spacing: 1px;")
        
        self.btn_lang = QPushButton("EN")
        self.btn_lang.setFixedSize(30, 24) 
        self.btn_lang.setStyleSheet(BTN_STYLE)
        self.btn_lang.clicked.connect(self.toggle_language)
        
        top.addWidget(self.lbl_title)
        top.addStretch()
        top.addWidget(self.btn_lang)
        main_layout.addLayout(top)

        # 2. 监控组列表 (Scroll Area)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #121212; border: none;")
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: #121212;") 
        
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0,0,0,0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.addStretch() 
        self.scroll.setWidget(self.scroll_content)
        
        main_layout.addWidget(self.scroll, 1) 

        # 3. 添加组按钮
        self.btn_add_group = QPushButton("+ ADD CLIENT GROUP")
        self.btn_add_group.setFixedHeight(36)
        self.btn_add_group.setStyleSheet("""
            QPushButton { border: 1px dashed #555; color: #888; background-color: #1a1a1a; border-radius: 4px; }
            QPushButton:hover { border-color: #00bcd4; color: #fff; }
        """)
        self.btn_add_group.clicked.connect(self.add_group)
        main_layout.addWidget(self.btn_add_group)

        # 4. 底部控制栏
        bot = QHBoxLayout()
        
        self.btn_settings = QPushButton("⚙ CONFIG")
        self.btn_settings.setFixedSize(80, 45)
        self.btn_settings.setStyleSheet(BTN_STYLE)
        self.btn_settings.clicked.connect(self.open_settings)
        
        self.btn_start = QPushButton("ENGAGE")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(45)
        self.btn_start.setStyleSheet("""
            QPushButton { background-color: #1b3a2a; border: 1px solid #2e7d32; color: #4caf50; font-weight: bold; font-size: 13px; }
            QPushButton:checked { background-color: #3b1a1a; border: 1px solid #c62828; color: #ef5350; }
            QPushButton:hover { background-color: #2e5e40; }
        """)
        self.btn_start.clicked.connect(self.toggle_monitoring)
        
        self.btn_debug = QPushButton("VIEW")
        self.btn_debug.setObjectName("btn_debug")
        self.btn_debug.setFixedSize(60, 45)
        self.btn_debug.setStyleSheet(BTN_STYLE)
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        bot.addWidget(self.btn_settings)
        bot.addWidget(self.btn_start)
        bot.addWidget(self.btn_debug)
        main_layout.addLayout(bot)

        # 5. 日志
        self.txt_log = QTextEdit()
        self.txt_log.setFixedHeight(100)
        self.txt_log.setReadOnly(True)
        self.txt_log.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self)
        self.log(self.i18n.get("log_ready"))

        self.refresh_group_list()

    def refresh_group_list(self):
        while self.scroll_layout.count() > 1: 
            item = self.scroll_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        groups = self.cfg.get("groups")
        for i, grp in enumerate(groups):
            w = GroupWidget(grp, i, self)
            self.scroll_layout.insertWidget(i, w)
            
        if hasattr(self, 'btn_add_group'):
            self.btn_add_group.setEnabled(len(groups) < 5)

    def add_group(self):
        groups = self.cfg.get("groups")
        if len(groups) >= 5: return
        
        new_id = len(groups)
        new_group = {
            "id": new_id,
            "name": f"Client {new_id+1}",
            "regions": {"local": None, "overview": None, "monster": None, "probe": None}
        }
        groups.append(new_group)
        self.cfg.set("groups", groups)
        self.refresh_group_list()
        self.log(f"System: Added Client {new_id+1}")

    def remove_group(self, index):
        groups = self.cfg.get("groups")
        if len(groups) <= 1:
            return
            
        groups.pop(index)
        for i, g in enumerate(groups):
            g["id"] = i
            g["name"] = f"Client {i+1}"
            
        self.cfg.set("groups", groups)
        self.refresh_group_list()
        self.log(f"System: Removed Client Group")

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        dlg.exec()
        self.load_sounds()

    def start_region_selection(self, group_index, key):
        self.selector = RegionSelector()
        self.selector.selection_finished.connect(lambda rect: self.save_region(group_index, key, rect))
        self.selector.show()

    def save_region(self, group_index, key, rect):
        groups = self.cfg.get("groups")
        if 0 <= group_index < len(groups):
            groups[group_index]["regions"][key] = list(rect)
            self.cfg.set("groups", groups)
            self.log(f"Client {group_index+1}: {key.upper()} Updated")

    def update_cfg(self, section, key, val):
        t = self.cfg.get(section)
        t[key] = val
        self.cfg.set(section, t)

    def refresh_ui_text(self):
        _ = self.i18n.get
        self.setWindowTitle(_("window_title"))
        self.lbl_title.setText(_("window_title"))
        self.btn_add_group.setText(_("btn_add"))
        
        if not self.logic.running:
            self.btn_start.setText(_("btn_start"))
        else:
            self.btn_start.setText(_("btn_stop"))
            
        self.btn_debug.setText(_("btn_debug"))
        self.btn_settings.setText(_("btn_settings"))
        self.btn_lang.setText(_("btn_lang"))

        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), GroupWidget):
                item.widget().update_texts()

    def toggle_language(self):
        self.i18n.toggle()
        self.cfg.set("language", self.i18n.lang)

    def toggle_monitoring(self):
        _ = self.i18n.get
        if not self.logic.running:
            groups = self.cfg.get("groups")
            any_set = False
            for g in groups:
                if g["regions"].get("local") or g["regions"].get("overview"):
                    any_set = True
                    break
            
            if not any_set:
                self.log(_("log_region_err"))
                return

            self.logic.start()
            self.idle_timer.stop()
            self.btn_start.setText(_("btn_stop"))
            self.btn_start.setChecked(True)
            self.log(_("log_start"))
        else:
            self.logic.stop()
            self.idle_timer.start()
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
                self.sounds["probe"].play()

    def show_debug_window(self):
        groups = self.cfg.get("groups")
        self.debug_window.refresh_tabs(len(groups))
        self.debug_window.show()
        self.debug_timer.start(100)

    def update_debug_view(self):
        if not self.debug_window.isVisible():
            self.debug_timer.stop()
            return
        
        groups = self.cfg.get("groups")
        images_to_show = {}
        
        for i, grp in enumerate(groups):
            regions = grp["regions"]
            images_to_show[(i, "local")] = self.vision.capture_screen(regions.get("local"))
            images_to_show[(i, "overview")] = self.vision.capture_screen(regions.get("overview"))
            images_to_show[(i, "monster")] = self.vision.capture_screen(regions.get("monster"))
            images_to_show[(i, "probe")] = self.vision.capture_screen(regions.get("probe"))
            
        self.debug_window.update_images(images_to_show)

    def log(self, text):
        if text.startswith("["):
            final_text = text
        else:
            from datetime import datetime
            now_str = datetime.now().strftime("[%H:%M:%S] ")
            final_text = now_str + text
            
        self.txt_log.append(final_text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())
