import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        self.local_templates = []
        self.overview_templates = []
        self.monster_templates = []
        
        self.template_status_msg = "初始化中..."
        self.last_screenshot_shape = "无"
        self.last_error = None
        
        self.debug_dir = os.path.join(os.getcwd(), "debug_scans")
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
            
        self.load_templates()

    def load_templates(self):
        base_dir = os.getcwd()
        path_local = os.path.join(base_dir, "assets", "hostile_icons_local")
        path_overview = os.path.join(base_dir, "assets", "hostile_icons_overview")
        path_monster = os.path.join(base_dir, "assets", "monster_icons")
        
        self.local_templates = self._load_images_from_folder(path_local)
        self.overview_templates = self._load_images_from_folder(path_overview)
        self.monster_templates = self._load_images_from_folder(path_monster)
        
        self.template_status_msg = (
            f"路径: {base_dir}\n"
            f"本地图标: {len(self.local_templates)} 张\n"
            f"总览图标: {len(self.overview_templates)} 张\n"
            f"怪物图标: {len(self.monster_templates)} 张"
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
                        if img.shape[2] == 3:
                            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
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
            with mss.mss() as sct:
                img = np.array(sct.grab(monitor))
                img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                
                h, w = img_bgr.shape[:2]
                self.last_screenshot_shape = f"{w}x{h}"
                
                if debug_name:
                    cv2.imwrite(os.path.join(self.debug_dir, f"debug_{debug_name}.png"), img_bgr)
                return img_bgr
                
        except Exception as e:
            self.last_error = f"截图失败: {str(e)}"
            return None

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False):
        """
        修正版：增加防 Inf/Nan 检查的归一化匹配
        """
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        screen_h, screen_w = screen_img.shape[:2]
        
        # === 防御性检查 1: 截图是否纯色 ===
        # 计算标准差，如果标准差为0，说明是纯色图，没有信息量，归一化会除以零
        mean, std_dev = cv2.meanStdDev(screen_img)
        if np.sum(std_dev) < 1.0: # 几乎是纯色
             return ("区域无内容(纯色)", 0.0) if return_max_val else False

        # === 归一化截图 ===
        try:
            screen_norm = cv2.normalize(screen_img, None, 0, 255, cv2.NORM_MINMAX)
        except:
            return ("归一化失败", 0.0) if return_max_val else False
        
        max_score_found = 0.0
        all_skipped = True 

        for tmpl in template_list:
            tmpl_h, tmpl_w = tmpl.shape[:2]
            
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            all_skipped = False 

            # 准备数据
            mask = None
            if tmpl.shape[2] == 4:
                tmpl_bgr = cv2.cvtColor(tmpl, cv2.COLOR_BGRA2BGR)
                mask = tmpl[:, :, 3]
            else:
                tmpl_bgr = tmpl
            
            # === 防御性检查 2: 模板是否纯色 ===
            mean_t, std_dev_t = cv2.meanStdDev(tmpl_bgr)
            if np.sum(std_dev_t) < 1.0:
                continue # 跳过无效模板

            # === 归一化模板 ===
            tmpl_norm = cv2.normalize(tmpl_bgr, None, 0, 255, cv2.NORM_MINMAX)

            try:
                if mask is not None:
                    res = cv2.matchTemplate(screen_norm, tmpl_norm, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_norm, tmpl_norm, cv2.TM_CCOEFF_NORMED)
                
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                # === 防御性检查 3: 检查结果是否为 Inf 或 Nan ===
                if np.isinf(max_val) or np.isnan(max_val):
                    max_val = 0.0
                
                if max_val > max_score_found:
                    max_score_found = max_val

            except Exception as e:
                continue

        if all_skipped:
            return ("尺寸错误", 0.0) if return_max_val else False

        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
