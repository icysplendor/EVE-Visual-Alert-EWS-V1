import time
import threading
import requests
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

class AlarmWorker(QObject):
    log_signal = pyqtSignal(str)     
    probe_signal = pyqtSignal(bool)  

    def __init__(self, config_manager, vision_engine):
        super().__init__()
        self.cfg = config_manager
        self.vision = vision_engine
        self.running = False
        self.thread = None
        self.first_run = True 

    def start(self):
        if not self.running:
            self.running = True
            self.first_run = True 
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()

    def _loop(self):
        while self.running:
            now_str = datetime.now().strftime("%H:%M:%S")
            
            if self.first_run:
                self.vision.load_templates()
                report = (
                    f"--- 系统自检报告 ---\n"
                    f"{self.vision.template_status_msg}\n"
                    f"颜色过滤: 已启用\n"
                    f"--------------------"
                )
                self.log_signal.emit(report)
                self.first_run = False
                time.sleep(1)

            groups = self.cfg.get("groups")
            thresholds = self.cfg.get("thresholds")
            
            # 全局状态标志
            global_threat = False
            global_probe = False
            global_sound = None
            
            log_details = []

            # 遍历每一个监控组
            for idx, group in enumerate(groups):
                regions = group.get("regions", {})
                grp_name = group.get("name", f"Grp {idx+1}")
                
                # 截图
                img_local = self.vision.capture_screen(regions.get("local"))
                img_overview = self.vision.capture_screen(regions.get("overview"))
                img_monster = self.vision.capture_screen(regions.get("monster"))
                img_probe = self.vision.capture_screen(regions.get("probe"))

                # 辅助函数
                def process_match(img, templates, thresh, check_green=False):
                    err_msg, score = self.vision.match_templates(
                        img, templates, thresh, 
                        return_max_val=True, 
                        check_green_exclusion=check_green
                    )
                    is_hit = score >= thresh
                    return is_hit, score, err_msg

                # 检测
                is_local, s_loc, _ = process_match(img_local, self.vision.local_templates, thresholds.get("local", 0.95), True)
                is_over, s_ovr, _ = process_match(img_overview, self.vision.overview_templates, thresholds.get("overview", 0.95), True)
                is_mon, s_mon, _ = process_match(img_monster, self.vision.monster_templates, thresholds.get("monster", 0.95), False)
                is_prb, s_prb, _ = process_match(img_probe, self.vision.probe_templates, thresholds.get("probe", 0.95), False)

                # 状态聚合
                has_threat = is_local or is_over
                if has_threat: global_threat = True
                if is_prb: global_probe = True

                # 确定当前组的最高优先级声音
                current_sound = None
                if has_threat and is_mon: current_sound = "mixed"
                elif is_over: current_sound = "overview"
                elif is_local: current_sound = "local"
                elif is_mon: current_sound = "monster"

                # 提升全局声音优先级 (Mixed > Overview > Local > Monster)
                priority_map = {"mixed": 4, "overview": 3, "local": 2, "monster": 1, None: 0}
                if priority_map.get(current_sound, 0) > priority_map.get(global_sound, 0):
                    global_sound = current_sound

                # 记录简报 (仅记录有状态的组，或者如果都没有状态，记录第一个组)
                if has_threat or is_mon or is_prb:
                    log_details.append(f"{grp_name}:[L:{int(is_local)} O:{int(is_over)} M:{int(is_mon)} P:{int(is_prb)}]")

            # === 信号发射 ===
            if global_probe:
                self.probe_signal.emit(True)

            if global_sound:
                detail_str = " | ".join(log_details)
                log_msg = f"[{now_str}] ⚠️ 触发: {global_sound.upper()} >> {detail_str}"
                self.log_signal.emit(log_msg)
                
                webhook = self.cfg.get("webhook_url")
                if webhook:
                    try:
                        threading.Thread(target=requests.post, args=(webhook,), kwargs={'json':{'alert':global_sound}}).start()
                    except: pass
                time.sleep(2.0)
            elif global_probe:
                # 仅探针
                detail_str = " | ".join(log_details)
                log_msg = f"[{now_str}] ⚠️ 探针: PROBE >> {detail_str}"
                self.log_signal.emit(log_msg)
                time.sleep(2.0)
            else:
                # 安全 (降低日志频率，或者只打印 Safe)
                log_msg = f"[{now_str}] ✅ 安全"
                self.log_signal.emit(log_msg)
                time.sleep(0.5)
