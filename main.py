import sys
import os
import ctypes
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QGroupBox, QDoubleSpinBox, QLineEdit, QTextEdit, 
                             QDialog, QFrame, QGridLayout, QScrollArea)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker
from core.i18n import Translator

# =============================================================================
# === 资源路径处理 (修复打包后找不到图标的问题) ===
# =============================================================================
def resource_path(relative_path):
    """ 获取资源的绝对路径，兼容开发环境和 PyInstaller 打包环境 """
    try:
        # PyInstaller 创建临时文件夹将路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# =============================================================================
# === Hi-DPI Fix ===
# =============================================================================
def apply_dpi_fix():
    if os.name == 'nt':
        try: ctypes.windll.shcore.SetProcessDpiAwareness(2) 
        except: pass

apply_dpi_fix()

# === CSS ===
EVE_STYLE = """
QMainWindow, QDialog { background-color: #121212; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 11px; color: #cccccc; }
QGroupBox { border: 1px solid #444; border-radius: 3px; margin-top: 10px; font-weight: bold; color: #00bcd4; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; left: 10px; }
QPushButton { background-color: #2a2a2a; border: 1px solid #444; color: #eee; padding: 4px; border-radius: 2px; }
QPushButton:hover { background-color: #3a3a3a; border-color: #00bcd4; }
QPushButton:pressed { background-color: #00bcd4; color: #000; }
QPushButton#btn_start { background-color: #1b3a2a; border: 1px solid #2e7d32; color: #4caf50; font-weight: bold; font-size: 12px; }
QPushButton#btn_start:checked { background-color: #3b1a1a; border: 1px solid #c62828; color: #ef5350; }
QPushButton#btn_remove { background-color: #3a1a1a; border: 1px solid #7f0000; color: #ff5555; font-weight: bold; }
QLineEdit, QDoubleSpinBox { background-color: #000; border: 1px solid #333; color: #00bcd4; padding: 2px; }
QTextEdit { background-color: #080808; border: 1px solid #333; font-family: "Consolas", "Courier New", monospace; font-size: 10px; color: #aaa; }
QScrollArea { border: none; background-color: transparent; }
QScrollBar:vertical { border: none; background: #111; width: 8px; }
QScrollBar::handle:vertical { background: #333; min-height: 20px; }
"""

# === 独立的设置窗口 ===
class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Advanced Settings")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.resize(400, 300)
        
        # 设置窗口图标
        icon_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setup_ui()
        self.setStyleSheet(EVE_STYLE)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Webhook
        grp_wh = QGroupBox("Webhook")
        l_wh = QVBoxLayout()
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        l_wh.addWidget(self.line_webhook)
        grp_wh.setLayout(l_wh)
        layout.addWidget(grp_wh)

        # Audio
        grp_audio = QGroupBox("Audio Assets")
        grid_audio = QGridLayout()
        grid_audio.setSpacing(5)
        
        audio_keys = ["local", "overview", "monster", "mixed", "probe", "idle"]
        for idx, key in enumerate(audio_keys):
            row = idx // 2
            col = idx % 2
            
            container = QWidget()
            h = QHBoxLayout(container)
            h.setContentsMargins(0,0,0,0)
            
            lbl_name = QLabel(key.capitalize())
            lbl_name.setFixedWidth(50)
            
            path_val = self.cfg.get("audio_paths").get(key, "")
            fname = os.path.basename(path_val) if path_val else "-"
            lbl_file = QLabel(fname)
            lbl_file.setStyleSheet("color: #666; font-size: 9px;")
            
            btn_sel = QPushButton("..")
            btn_sel.setFixedSize(20, 20)
            btn_sel.clicked.connect(lambda _, k=key, l=lbl_file: self.select_audio(k, l))
            
            h.addWidget(lbl_name)
            h.addWidget(lbl_file)
            h.addWidget(btn_sel)
            grid_audio.addWidget(container, row, col)
            
        grp_audio.setLayout(grid_audio)
        layout.addWidget(grp_audio)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def select_audio(self, key, label_widget):
        fname, _ = QFileDialog.getOpenFileName(self, "Audio File", "", "Audio (*.wav *.mp3)")
        if fname:
            cwd = os.getcwd()
            try:
                rel_path = os.path.relpath(fname, cwd)
                save_path = rel_path if not rel_path.startswith("..") else fname
            except:
                save_path = fname

            paths = self.cfg.get("audio_paths")
            paths[key] = save_path
            self.cfg.set("audio_paths", paths)
            label_widget.setText(os.path.basename(fname))

# === 单个监控组控件 ===
class GroupWidget(QGroupBox):
    def __init__(self, group_data, index, parent_win):
        super().__init__()
        self.group_data = group_data
        self.index = index
        self.parent_win = parent_win
        
        self.setTitle(f"Client {index + 1}")
        self.setup_ui()

    def setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(5, 8, 5, 5)
        layout.setSpacing(4)

        # 4个功能按钮
        self.btn_local = QPushButton("Local")
        self.btn_overview = QPushButton("Overview")
        self.btn_monster = QPushButton("Rats")
        self.btn_probe = QPushButton("Probe")
        
        # 删除按钮
        self.btn_remove = QPushButton("X")
        self.btn_remove.setObjectName("btn_remove")
        self.btn_remove.setFixedSize(20, 20)
        self.btn_remove.setToolTip("Remove this group")
        self.btn_remove.clicked.connect(lambda: self.parent_win.remove_group(self.index))

        layout.addWidget(self.btn_local, 0, 0)
        layout.addWidget(self.btn_overview, 0, 1)
        layout.addWidget(self.btn_monster, 1, 0)
        layout.addWidget(self.btn_probe, 1, 1)
        layout.addWidget(self.btn_remove, 0, 2, 2, 1)

        self.btn_local.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "local"))
        self.btn_overview.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "overview"))
        self.btn_monster.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "monster"))
        self.btn_probe.clicked.connect(lambda: self.parent_win.start_region_selection(self.index, "probe"))

# === 调试窗口 ===
class DebugWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LIVE VIEW")
        
        # 设置窗口图标
        icon_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.setStyleSheet("background-color: #000; color: #00bcd4;")
        self.main_layout = QHBoxLayout(self)
        self.image_labels = {} 

    def setup_grid(self, num_groups):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        
        self.image_labels = {}
        
        for i in range(num_groups):
            vbox = QVBoxLayout()
            vbox.setSpacing(2)
            
            lbl_group = QLabel(f"Client {i+1}")
            lbl_group.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_group.setStyleSheet("font-weight: bold; color: #fff; background: #222;")
            vbox.addWidget(lbl_group)
            
            for key in ["local", "overview", "monster", "probe"]:
                lbl_img = QLabel()
                lbl_img.setFixedSize(90, 400) 
                lbl_img.setStyleSheet("border: 1px solid #333; background: #111;")
                lbl_img.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
                
                vbox.addWidget(lbl_img)
                self.image_labels[(i, key)] = lbl_img
            
            self.main_layout.addLayout(vbox)
        
        self.resize(110 * num_groups, 600)

    def update_images(self, images_dict):
        for k, img in images_dict.items():
            if k in self.image_labels:
                self.set_pixmap(self.image_labels[k], img)

    def set_pixmap(self, label, np_img):
        if np_img is None: 
            label.clear()
            return
        h, w, ch = np_img.shape
        bytes_per_line = ch * w
        qimg = QImage(np_img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
        label.setPixmap(QPixmap.fromImage(qimg).scaled(label.width(), label.height(), Qt.AspectRatioMode.KeepAspectRatio))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.i18n = Translator(self.refresh_ui_text) 
        
        self.init_core()
        self.setup_ui()
        self.refresh_ui_text()
        
        # 设置主窗口图标 (使用 resource_path 确保打包后能找到)
        icon_path = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

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
        self.resize(380, 650)
        
        main_layout = QVBoxLayout(self.central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # 1. 顶部标题
        top = QHBoxLayout()
        self.lbl_title = QLabel("EVE ALERT")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff;")
        self.btn_lang = QPushButton("EN")
        self.btn_lang.setFixedSize(30, 20)
        self.btn_lang.clicked.connect(self.toggle_language)
        top.addWidget(self.lbl_title)
        top.addStretch()
        top.addWidget(self.btn_lang)
        main_layout.addLayout(top)

        # 2. 监控组列表 (Scroll Area)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0,0,0,0)
        self.scroll_layout.setSpacing(5)
        self.scroll_layout.addStretch() 
        self.scroll.setWidget(self.scroll_content)
        
        main_layout.addWidget(self.scroll, 1) 

        # 3. 添加组按钮 (必须在 refresh_group_list 之前定义)
        self.btn_add_group = QPushButton("+ ADD CLIENT GROUP")
        self.btn_add_group.setFixedHeight(28)
        self.btn_add_group.clicked.connect(self.add_group)
        main_layout.addWidget(self.btn_add_group)

        # 4. 全局阈值 (Compact Grid)
        self.grp_thresh = QGroupBox("Global Thresholds")
        grid_th = QGridLayout()
        grid_th.setContentsMargins(5, 8, 5, 5)
        
        def mk_th(label, key, r, c):
            lbl = QLabel(label)
            sp = QDoubleSpinBox()
            sp.setRange(0.1, 1.0)
            sp.setSingleStep(0.01)
            sp.setValue(self.cfg.get("thresholds").get(key, 0.95))
            sp.valueChanged.connect(lambda v: self.update_cfg("thresholds", key, v))
            grid_th.addWidget(lbl, r, c*2)
            grid_th.addWidget(sp, r, c*2+1)
            return lbl
            
        self.lbl_th_l = mk_th("Loc", "local", 0, 0)
        self.lbl_th_o = mk_th("Ovr", "overview", 0, 1)
        self.lbl_th_m = mk_th("Rat", "monster", 1, 0)
        self.lbl_th_p = mk_th("Prb", "probe", 1, 1)
        
        self.grp_thresh.setLayout(grid_th)
        main_layout.addWidget(self.grp_thresh)

        # 5. 底部控制栏
        bot = QHBoxLayout()
        
        self.btn_settings = QPushButton("⚙ SETTINGS")
        self.btn_settings.setFixedSize(80, 40)
        self.btn_settings.clicked.connect(self.open_settings)
        
        self.btn_start = QPushButton("ENGAGE")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedHeight(40)
        self.btn_start.clicked.connect(self.toggle_monitoring)
        
        self.btn_debug = QPushButton("VIEW")
        self.btn_debug.setObjectName("btn_debug")
        self.btn_debug.setFixedSize(60, 40)
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        bot.addWidget(self.btn_settings)
        bot.addWidget(self.btn_start)
        bot.addWidget(self.btn_debug)
        main_layout.addLayout(bot)

        # 6. 日志
        self.txt_log = QTextEdit()
        self.txt_log.setFixedHeight(80)
        self.txt_log.setReadOnly(True)
        self.txt_log.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self)
        self.log(self.i18n.get("log_ready"))

        # === 关键修复：最后再刷新列表 ===
        # 此时 self.btn_add_group 已经创建完毕，不会报错了
        self.refresh_group_list()

    def refresh_group_list(self):
        # 清除现有
        while self.scroll_layout.count() > 1: # 保留最后一个 stretch
            item = self.scroll_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        groups = self.cfg.get("groups")
        for i, grp in enumerate(groups):
            w = GroupWidget(grp, i, self)
            self.scroll_layout.insertWidget(i, w)
            
        # 禁用添加按钮如果超过5个
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
        self.log(f"Added Client {new_id+1}")

    def remove_group(self, index):
        groups = self.cfg.get("groups")
        if len(groups) <= 1:
            self.log("Cannot remove the last group.")
            return
            
        groups.pop(index)
        # 重置ID和名称
        for i, g in enumerate(groups):
            g["id"] = i
            g["name"] = f"Client {i+1}"
            
        self.cfg.set("groups", groups)
        self.refresh_group_list()
        self.log(f"Removed Client Group")

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        dlg.exec()
        # 重新加载声音
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
            self.log(f"Client {group_index+1} {key.upper()} Set.")

    def update_cfg(self, section, key, val):
        t = self.cfg.get(section)
        t[key] = val
        self.cfg.set(section, t)

    def refresh_ui_text(self):
        _ = self.i18n.get
        self.setWindowTitle(_("window_title"))
        self.lbl_title.setText(_("window_title"))
        self.btn_add_group.setText(_("btn_add"))
        self.grp_thresh.setTitle(_("grp_thresh"))
        
        if not self.logic.running:
            self.btn_start.setText(_("btn_start"))
        else:
            self.btn_start.setText(_("btn_stop"))
            
        self.btn_debug.setText(_("btn_debug"))
        self.btn_settings.setText(_("btn_settings"))
        self.btn_lang.setText(_("btn_lang"))

    def toggle_language(self):
        self.i18n.toggle()
        self.cfg.set("language", self.i18n.lang)

    def toggle_monitoring(self):
        _ = self.i18n.get
        if not self.logic.running:
            # 检查是否有任意一个区域被设置
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
        self.debug_window.setup_grid(len(groups))
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
            # 批量截图
            images_to_show[(i, "local")] = self.vision.capture_screen(regions.get("local"))
            images_to_show[(i, "overview")] = self.vision.capture_screen(regions.get("overview"))
            images_to_show[(i, "monster")] = self.vision.capture_screen(regions.get("monster"))
            images_to_show[(i, "probe")] = self.vision.capture_screen(regions.get("probe"))
            
        self.debug_window.update_images(images_to_show)

    def log(self, text):
        self.txt_log.append(text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
