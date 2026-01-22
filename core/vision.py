import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        # 移除 self.sct = mss.mss()，因为这会导致跨线程崩溃
        self.hostile_templates = []
        self.monster_templates = []
        
        # 状态诊断变量
        self.template_status_msg = "初始化中..."
        self.last_screenshot_shape = "无"
        self.last_error = None
        
        # 调试目录
        self.debug_dir = os.path.join(os.getcwd(), "debug_scans")
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
            
        self.load_templates()

    def load_templates(self):
        base_dir = os.getcwd()
        path_hostile = os.path.join(base_dir, "assets", "hostile_icons")
        path_monster = os.path.join(base_dir, "assets", "monster_icons")
        
        self.hostile_templates = self._load_images_from_folder(path_hostile)
        self.monster_templates = self._load_images_from_folder(path_monster)
        
        self.template_status_msg = (
            f"路径: {base_dir}\n"
            f"敌对模板: {len(self.hostile_templates)} 张\n"
            f"怪物模板: {len(self.monster_templates)} 张"
        )

    def _load_images_from_folder(self, folder):
        templates = []
        if not os.path.exists(folder):
            try:
                os.makedirs(folder)
            except:
                pass
            return templates
            
        for filename in os.listdir(folder):
            if filename.lower().endswith(('.png', '.jpg', '.bmp')):
                path = os.path.join(folder, filename)
                try:
                    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        templates.append(img)
                except:
                    pass
        return templates

    def capture_screen(self, region, debug_name=None):
        self.last_error = None
        if not region: 
            return None
        
        monitor = {"top": int(region[1]), "left": int(region[0]), "width": int(region[2]), "height": int(region[3])}
        
        try:
            # === 核心修复 ===
            # 使用 with 语句，在当前线程内动态创建 mss 实例
            # 用完即销毁，确保线程安全
            with mss.mss() as sct:
                img = np.array(sct.grab(monitor))
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                # 记录这次截图的尺寸
                h, w = img_bgr.shape[:2]
                self.last_screenshot_shape = f"{w}x{h}"
                
                if debug_name:
                    cv2.imwrite(os.path.join(self.debug_dir, f"debug_{debug_name}.png"), img_bgr)
                return img_bgr
                
        except Exception as e:
            # 这里的错误信会非常具体
            self.last_error = f"截图失败: {str(e)}"
            return None

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False):
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图(区域未设置?)"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板文件(请检查assets)", 0.0) if return_max_val else False

        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        max_score_found = 0.0
        
        all_skipped = True 

        for tmpl in template_list:
            tmpl_h, tmpl_w = tmpl.shape[:2]
            screen_h, screen_w = screen_gray.shape[:2]
            
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            
            all_skipped = False 

            mask = None
            if tmpl.shape[2] == 4:
                b, g, r, a = cv2.split(tmpl)
                mask = a
                tmpl_gray = cv2.cvtColor(cv2.merge([b,g,r]), cv2.COLOR_BGR2GRAY)
            else:
                tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)

            try:
                if mask is not None:
                    res = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if max_val > max_score_found:
                    max_score_found = max_val
            except:
                continue

        if all_skipped:
            return ("所有模板均大于截图区域", 0.0) if return_max_val else False

        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
