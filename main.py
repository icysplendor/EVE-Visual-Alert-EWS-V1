import sys
import os
import ctypes
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QGroupBox, QDoubleSpinBox, QLineEdit, QTextEdit, 
                             QDialog, QFrame, QGridLayout, QScrollArea, QListWidget, QListWidgetItem)
from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl

from core.config_manager import ConfigManager
from core.vision import VisionEngine
from ui.selector import RegionSelector
from core.audio_logic import AlarmWorker
from core.i18n import Translator

# ... (Hi-DPI 修复代码保持不变，此处省略) ...
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

# === EVE Style CSS (微调) ===
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
QPushButton#btn_remove { background-color: #3a1a1a; border: 1px solid #7d2e2e; color: #af4c4c; }
QLineEdit, QDoubleSpinBox { background-color: #000; border: 1px solid #333; color: #00bcd4; padding: 2px; }
QTextEdit { background-color: #080808; border: 1px solid #333; font-family: "Consolas", "Courier New", monospace; font-size: 10px; color: #aaa; }
QScrollArea { border: none; background-color: transparent; }
QListWidget { background-color: #080808; border: 1px solid #333; }
QListWidget::item:selected { background-color: #00bcd4; color: #000; }
"""

# === 设置对话框 (Webhook & Audio) ===
class SettingsDialog(QDialog):
    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setWindowTitle("Advanced Settings")
        self.resize(400, 300)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Webhook
        grp_wh = QGroupBox("Webhook")
        l_wh = QHBoxLayout()
        self.line_webhook = QLineEdit(self.cfg.get("webhook_url"))
        self.line_webhook.textChanged.connect(lambda t: self.cfg.set("webhook_url", t))
        l_wh.addWidget(QLabel("URL:"))
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
            h_layout = QHBoxLayout(container)
            h_layout.setContentsMargins(0,0,0,0)
            
            lbl_name = QLabel(key.capitalize())
            lbl_name.setFixedWidth(50)
            
            path_val = self.cfg.get("audio_paths").get(key, "")
            fname = os.path.basename(path_val) if path_val else "-"
            lbl_file = QLabel(fname)
            lbl_file.setStyleSheet("color: #666; font-size: 9px;")
            
            btn_sel = QPushButton("..")
            btn_sel.setFixedSize(20, 20)
            btn_sel.clicked.connect(lambda _, k=key, l=lbl_file: self.select_audio(k, l))
            
            h_layout.addWidget(lbl_name)
            h_layout.addWidget(lbl_file)
            h_layout.addWidget(btn_sel)
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
            except ValueError:
                save_path = fname

            paths = self.cfg.get("audio_paths")
            paths[key] = save_path
            self.cfg.set("audio_paths", paths)
            label_widget.setText(os.path.basename(fname))
            # 通知主窗口重载音频
            if self.parent():
                self.parent().load_sounds()

# === 调试窗口 (支持多组切换) ===
class DebugWindow(QDialog):
    def __init__(self, parent=None, vision_engine=None, config_manager=None):
        super().__init__(parent)
        self.vision = vision_engine
        self.cfg = config_manager
        self.setWindowTitle("LIVE VIEW")
        self.resize(700, 550)
        
        main_layout = QHBoxLayout(self)
        
        # 左侧列表
        self.list_groups = QListWidget()
        self.list_groups.setFixedWidth(120)
        self.list_groups.currentRowChanged.connect(self.refresh_view)
        main_layout.addWidget(self.list_groups)
        
        # 右侧图像
        right_panel = QWidget()
        self.img_layout = QHBoxLayout(right_panel)
        self.labels = {}
        for key in ["Local", "Overview", "Npc", "Probe"]:
            vbox = QVBoxLayout()
            lbl_title = QLabel(key)
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_img = QLabel()
            lbl_img.setFixedSize(120, 500)
            lbl_img.setStyleSheet("border: 1px solid #333; background: #000;")
            lbl_img.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            vbox.addWidget(lbl_title)
            vbox.addWidget(lbl_img)
            self.img_layout.addLayout(vbox)
            self.labels[key] = lbl_img
        
        main_layout.addWidget(right_panel)
        
    def refresh_list(self):
        self.list_groups.clear()
        groups = self.cfg.get("groups")
        for g in groups:
            self.list_groups.addItem(g.get("name"))
        if self.list_groups.count() > 0:
            self.list_groups.setCurrentRow(0)

    def refresh_view(self, index):
        pass # 由 timer 调用 update_images

    def update_images(self):
        idx = self.list_groups.currentRow()
        if idx < 0: return
        
        groups = self.cfg.get("groups")
        if idx >= len(groups): return
        
        regions = groups[idx].get("regions", {})
        
        def update_lbl(key, r_key):
            img = self.vision.capture_screen(regions.get(r_key))
            if img is not None:
                h, w, ch = img.shape
                bytes_per_line = ch * w
                qimg = QImage(img.data, w, h, bytes_per_line, QImage.Format.Format_BGR888)
                pix = QPixmap.fromImage(qimg).scaled(120, 500, Qt.AspectRatioMode.KeepAspectRatio)
                self.labels[key].setPixmap(pix)
            else:
                self.labels[key].clear()

        update_lbl("Local", "local")
        update_lbl("Overview", "overview")
        update_lbl("Npc", "monster")
        update_lbl("Probe", "probe")

# === 监控组卡片组件 ===
class GroupCard(QGroupBox):
    def __init__(self, index, group_data, parent_window):
        super().__init__(group_data.get("name", f"Client {index+1}"))
        self.index = index
        self.win = parent_window
        self.setup_ui()

    def setup_ui(self):
        layout = QGridLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(5, 15, 5, 5) # Top margin for title

        # Buttons
        btn_local = QPushButton("Local")
        btn_ovr = QPushButton("Overvw")
        btn_rat = QPushButton("Rats")
        btn_prb = QPushButton("Probe")

        for btn, key, r, c in [
            (btn_local, "local", 0, 0), (btn_ovr, "overview", 0, 1),
            (btn_rat, "monster", 1, 0), (btn_prb, "probe", 1, 1)
        ]:
            btn.setFixedHeight(22)
            btn.clicked.connect(lambda _, k=key: self.win.start_region_selection(self.index, k))
            layout.addWidget(btn, r, c)
        
        # Remove Button
        if self.index > 0: # 不允许删除第一个组
            btn_del = QPushButton("X")
            btn_del.setObjectName("btn_remove")
            btn_del.setFixedSize(20, 20)
            btn_del.clicked.connect(lambda: self.win.remove_group(self.index))
            # 放在右上角
            # 由于 QGroupBox 布局限制，这里简单放在 grid 下方，或者你可以用绝对定位
            layout.addWidget(btn_del, 0, 2) 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.cfg = ConfigManager()
        self.vision = VisionEngine()
        self.logic = AlarmWorker(self.cfg, self.vision)
        self.i18n = Translator(None) 
        
        self.init_core()
        self.setup_ui()
        self.load_icon()
        
        self.setStyleSheet(EVE_STYLE)
        self.resize(400, 650) 

        self.i18n.callback = self.refresh_ui_text 
        saved_lang = self.cfg.get("language")
        if saved_lang:
            self.i18n.set_language(saved_lang)
        else:
            self.refresh_ui_text()

    def load_icon(self):
        # 尝试加载图标
        icon_path = os.path.join("assets", "icon.png") # 优先 png
        if not os.path.exists(icon_path):
            icon_path = os.path.join("assets", "icon.ico")
        
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

    def load_sounds(self):
        for key in ["local", "overview", "monster", "mixed", "probe", "idle"]:
            path = self.cfg.get_audio_path(key)
            if path and os.path.exists(path):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(path))
                effect.setVolume(1.0)
                self.sounds[key] = effect
            else:
                if key in self.sounds: del self.sounds[key]

    def play_idle_sound(self):
        if not self.logic.running and "idle" in self.sounds:
            self.sounds["idle"].play()
            self.log(self.i18n.get("log_idle_alert"))

    def setup_ui(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        
        main_layout = QVBoxLayout(self.central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # === 顶部 ===
        top_layout = QHBoxLayout()
        self.lbl_title = QLabel("EVE ALERT")
        self.lbl_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #fff;")
        
        btn_settings = QPushButton("⚙️")
        btn_settings.setFixedSize(30, 20)
        btn_settings.clicked.connect(self.open_settings)

        self.btn_lang = QPushButton("EN")
        self.btn_lang.setFixedSize(30, 20)
        self.btn_lang.clicked.connect(self.toggle_language)
        
        top_layout.addWidget(self.lbl_title)
        top_layout.addStretch()
        top_layout.addWidget(btn_settings)
        top_layout.addWidget(self.btn_lang)
        main_layout.addLayout(top_layout)

        # === 监控组列表 (Scroll Area) ===
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(10)
        self.scroll_layout.addStretch() # Push items up
        self.scroll_area.setWidget(self.scroll_content)
        
        main_layout.addWidget(self.scroll_area)
        
        # 添加组按钮
        self.btn_add_group = QPushButton("+ ADD CLIENT GROUP")
        self.btn_add_group.clicked.connect(self.add_group)
        main_layout.addWidget(self.btn_add_group)

        # === 阈值设置 (保留在主界面) ===
        self.grp_thresh = QGroupBox("Thresholds")
        grid_thresh = QGridLayout()
        grid_thresh.setSpacing(4)
        
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
        self.lbl_th_probe, self.spin_probe = create_thresh_ctrl("Prb %", "probe", 1, 1)
        
        self.grp_thresh.setLayout(grid_thresh)
        main_layout.addWidget(self.grp_thresh)

        # === 底部控制 ===
        layout_ctrl = QHBoxLayout()
        self.btn_start = QPushButton("ENGAGE")
        self.btn_start.setObjectName("btn_start") 
        self.btn_start.setFixedHeight(40) 
        self.btn_start.clicked.connect(self.toggle_monitoring)
        
        self.btn_debug = QPushButton("VIEW")
        self.btn_debug.setObjectName("btn_debug")
        self.btn_debug.setFixedSize(80, 40) 
        self.btn_debug.clicked.connect(self.show_debug_window)
        
        layout_ctrl.addWidget(self.btn_start)
        layout_ctrl.addWidget(self.btn_debug)
        main_layout.addLayout(layout_ctrl)

        # === 日志 ===
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedHeight(100)
        self.txt_log.setFrameShape(QFrame.Shape.NoFrame)
        main_layout.addWidget(self.txt_log)
        
        self.debug_window = DebugWindow(self, self.vision, self.cfg)
        
        # 初始化组显示
        self.refresh_groups_ui()
        self.log(self.i18n.get("log_ready"))

    def refresh_groups_ui(self):
        # 清空现有组
        for i in reversed(range(self.scroll_layout.count())): 
            item = self.scroll_layout.itemAt(i)
            if item.widget(): item.widget().deleteLater()
            elif item.spacerItem(): self.scroll_layout.removeItem(item)
            
        groups = self.cfg.get("groups")
        for idx, grp in enumerate(groups):
            card = GroupCard(idx, grp, self)
            self.scroll_layout.addWidget(card)
            
        self.scroll_layout.addStretch()

    def add_group(self):
        groups = self.cfg.get("groups")
        if len(groups) >= 5:
            self.log("Max 5 groups allowed.")
            return
            
        new_group = {
            "name": f"Client {len(groups) + 1}",
            "regions": {"local": None, "overview": None, "monster": None, "probe": None}
        }
        groups.append(new_group)
        self.cfg.set("groups", groups)
        self.refresh_groups_ui()

    def remove_group(self, index):
        groups = self.cfg.get("groups")
        if 0 < index < len(groups):
            del groups[index]
            # 重命名后续组以保持顺序
            for i in range(len(groups)):
                groups[i]["name"] = f"Client {i+1}"
            self.cfg.set("groups", groups)
            self.refresh_groups_ui()

    def start_region_selection(self, group_index, region_key):
        self.selector = RegionSelector()
        self.selector.selection_finished.connect(
            lambda rect: self.save_region(group_index, region_key, rect)
        )
        self.selector.show()

    def save_region(self, grp_idx, key, rect):
        groups = self.cfg.get("groups")
        if grp_idx < len(groups):
            groups[grp_idx]["regions"][key] = list(rect)
            self.cfg.set("groups", groups)
            self.log(f"Updated: Client {grp_idx+1} -> {key.upper()}")

    def open_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        dlg.exec()

    def update_cfg(self, section, key, val):
        t = self.cfg.get(section)
        t[key] = val
        self.cfg.set(section, t)

    def refresh_ui_text(self):
        _ = self.i18n.get
        self.setWindowTitle(_("window_title"))
        self.lbl_title.setText(_("window_title"))
        self.btn_add_group.setText("+ ADD CLIENT GROUP") # 暂不翻译
        self.grp_thresh.setTitle(_("grp_config"))
        
        self.lbl_th_local.setText(_("lbl_th_local"))
        self.lbl_th_over.setText(_("lbl_th_over"))
        self.lbl_th_npc.setText(_("lbl_th_npc"))
        self.lbl_th_probe.setText(_("lbl_th_probe"))
        
        if not self.logic.running:
            self.btn_start.setText(_("btn_start"))
        else:
            self.btn_start.setText(_("btn_stop"))
        self.btn_debug.setText(_("btn_debug"))
        self.btn_lang.setText(_("btn_lang"))

    def toggle_language(self):
        self.i18n.toggle()
        self.cfg.set("language", self.i18n.lang)

    def toggle_monitoring(self):
        _ = self.i18n.get
        if not self.logic.running:
            # 简单检查：至少有一个组设置了区域
            groups = self.cfg.get("groups")
            valid = False
            for g in groups:
                r = g.get("regions", {})
                if r.get("local") or r.get("overview"):
                    valid = True
                    break
            
            if not valid:
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
        if detected and "probe" in self.sounds:
            self.sounds["probe"].play()

    def show_debug_window(self):
        self.debug_window.refresh_list()
        self.debug_window.show()
        self.debug_timer.start(100)

    def update_debug_view(self):
        if not self.debug_window.isVisible():
            self.debug_timer.stop()
            return
        self.debug_window.update_images()

    def log(self, text):
        self.txt_log.append(text)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
