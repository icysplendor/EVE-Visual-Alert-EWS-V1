import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        self.local_templates = []
        self.overview_templates = []
        self.monster_templates = []
        self.probe_templates = [] 
        
        self.template_status_msg = "初始化中..."
        self.last_screenshot_shape = "无"
        self.last_error = None
        
        # 初始化 CLAHE (保留对象备用)
        self.clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8,8))
        
        # === 颜色过滤器设置 (HSV空间) ===
        # 绿色友军
        self.GREEN_LOWER = np.array([35, 40, 40])
        self.GREEN_UPPER = np.array([85, 255, 255])
        
        # 蓝色友军 (EVE的蓝色通常在 100-130 之间)
        self.BLUE_LOWER = np.array([95, 40, 40])
        self.BLUE_UPPER = np.array([135, 255, 255])
        
        # 像素阈值：超过多少个像素认为是友军
        self.SAFE_COLOR_THRESHOLD = 8 
            
        self.load_templates()

    def load_templates(self):
        base_dir = os.getcwd()
        path_local = os.path.join(base_dir, "assets", "hostile_icons_local")
        path_overview = os.path.join(base_dir, "assets", "hostile_icons_overview")
        path_monster = os.path.join(base_dir, "assets", "monster_icons")
        path_probe = os.path.join(base_dir, "assets", "probe_icons") 
        
        self.local_templates = self._load_images_from_folder(path_local)
        self.overview_templates = self._load_images_from_folder(path_overview)
        self.monster_templates = self._load_images_from_folder(path_monster)
        self.probe_templates = self._load_images_from_folder(path_probe)
        
        self.template_status_msg = (
            f"路径: {base_dir}\n"
            f"本地图标: {len(self.local_templates)}\n"
            f"总览图标: {len(self.overview_templates)}\n"
            f"怪物图标: {len(self.monster_templates)}\n"
            f"探针图标: {len(self.probe_templates)}"
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
                    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                    
                    if img is not None:
                        if img.shape[2] == 4:
                            b, g, r, a = cv2.split(img)
                            gray = cv2.cvtColor(cv2.merge([b,g,r]), cv2.COLOR_BGR2GRAY)
                            processed = self.preprocess_image(gray)
                            templates.append((processed, a))
                        else:
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            processed = self.preprocess_image(gray)
                            templates.append((processed, None))
                except Exception as e:
                    print(f"Error loading {filename}: {e}")
                    pass
        return templates

    def apply_gamma(self, image, gamma=1.0):
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(image, table)

    def preprocess_image(self, gray_img):
        # 1. Gamma 校正
        gamma_corrected = self.apply_gamma(gray_img, gamma=1.5)
        # 2. 简单的阈值截断
        _, thresholded = cv2.threshold(gamma_corrected, 30, 255, cv2.THRESH_TOZERO)
        # 3. 移除 CLAHE (保持之前的优化)
        return thresholded

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
                return img_bgr
        except Exception as e:
            self.last_error = f"截图失败: {str(e)}"
            return None

    def _is_safe_color(self, img_crop):
        """
        检查图片切片中是否包含超过阈值的绿色或蓝色像素 (友军)
        """
        if img_crop is None or img_crop.size == 0:
            return False
            
        hsv = cv2.cvtColor(img_crop, cv2.COLOR_BGR2HSV)
        
        # 检查绿色
        mask_green = cv2.inRange(hsv, self.GREEN_LOWER, self.GREEN_UPPER)
        green_count = cv2.countNonZero(mask_green)
        
        # 检查蓝色
        mask_blue = cv2.inRange(hsv, self.BLUE_LOWER, self.BLUE_UPPER)
        blue_count = cv2.countNonZero(mask_blue)
        
        # 只要任意一种安全颜色达标，就认为是友军
        return (green_count > self.SAFE_COLOR_THRESHOLD) or (blue_count > self.SAFE_COLOR_THRESHOLD)

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False, check_safe_color=False):
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        screen_h, screen_w = screen_img.shape[:2]
        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        screen_processed = self.preprocess_image(screen_gray)
        
        max_score_found = 0.0
        all_skipped = True 

        for tmpl_processed, mask in template_list:
            tmpl_h, tmpl_w = tmpl_processed.shape[:2]
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            all_skipped = False 

            try:
                if mask is not None:
                    res = cv2.matchTemplate(screen_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED)
                
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                if np.isinf(max_val) or np.isnan(max_val): max_val = 0.0
                
                if max_val > max_score_found:
                    # 如果开启了安全颜色检查，且分数达标，则进行反向查验
                    if check_safe_color and max_val >= threshold:
                        top_left = max_loc
                        bottom_right = (top_left[0] + tmpl_w, top_left[1] + tmpl_h)
                        # 切出原图(彩色)
                        crop_img = screen_img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
                        
                        # 如果是安全颜色(蓝/绿)，则忽略这次匹配
                        if self._is_safe_color(crop_img):
                            continue
                            
                    max_score_found = max_val

            except Exception:
                continue

        if all_skipped:
            return ("尺寸错误", 0.0) if return_max_val else False

        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
