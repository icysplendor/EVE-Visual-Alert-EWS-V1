import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        # 模板库结构: { "local": { "90": [], "100": [], "125": [] }, ... }
        self.templates = {
            "local": {},
            "overview": {},
            "monster": {},
            "probe": {},
            "scaling": {} 
        }
        
        self.SCALES = ["90", "100", "125"]
        self.template_status_msg = "初始化中..."
        self.last_screenshot_shape = "无"
        self.last_error = None
        
        self.clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8,8))
        
        # 颜色过滤器
        self.GREEN_LOWER = np.array([35, 40, 40])
        self.GREEN_UPPER = np.array([85, 255, 255])
        self.BLUE_LOWER = np.array([95, 40, 40])
        self.BLUE_UPPER = np.array([135, 255, 255])
        self.SAFE_COLOR_THRESHOLD = 8 
            
        self.load_templates()

    def load_templates(self):
        base_dir = os.getcwd()
        assets_dir = os.path.join(base_dir, "assets")
        
        folder_map = {
            "local": "hostile_icons_local",
            "overview": "hostile_icons_overview",
            "monster": "monster_icons",
            "probe": "probe_icons",
            "scaling": "ui_scaling_adaptation"
        }
        
        total_count = 0
        
        for type_key, folder_name in folder_map.items():
            for scale in self.SCALES:
                path = os.path.join(assets_dir, folder_name, scale)
                imgs = self._load_images_from_folder(path)
                self.templates[type_key][scale] = imgs
                total_count += len(imgs)
        
        self.template_status_msg = (
            f"Assets Path: {assets_dir}\n"
            f"Scales Loaded: {', '.join(self.SCALES)}\n"
            f"Total Templates: {total_count}"
        )

    def _load_images_from_folder(self, folder):
        templates = []
        if not os.path.exists(folder):
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
                except Exception:
                    pass
        return templates

    def apply_gamma(self, image, gamma=1.0):
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(image, table)

    def preprocess_image(self, gray_img):
        gamma_corrected = self.apply_gamma(gray_img, gamma=1.5)
        _, thresholded = cv2.threshold(gamma_corrected, 30, 255, cv2.THRESH_TOZERO)
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
            self.last_error = f"Screenshot Error: {str(e)}"
            return None

    def _is_safe_color(self, img_crop):
        if img_crop is None or img_crop.size == 0:
            return False
        hsv = cv2.cvtColor(img_crop, cv2.COLOR_BGR2HSV)
        mask_green = cv2.inRange(hsv, self.GREEN_LOWER, self.GREEN_UPPER)
        green_count = cv2.countNonZero(mask_green)
        mask_blue = cv2.inRange(hsv, self.BLUE_LOWER, self.BLUE_UPPER)
        blue_count = cv2.countNonZero(mask_blue)
        return (green_count > self.SAFE_COLOR_THRESHOLD) or (blue_count > self.SAFE_COLOR_THRESHOLD)

    def detect_scale(self, screen_img, threshold=0.85):
        if screen_img is None: return None

        best_scale = None
        best_score = 0.0

        for scale in self.SCALES:
            tmpls = self.templates["scaling"].get(scale, [])
            _, score = self.match_templates(screen_img, tmpls, threshold, return_max_val=True, check_safe_color=False)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_scale = scale
        
        return best_scale

    def count_matches(self, screen_img, template_list, threshold, check_safe_color=False):
        """
        统计匹配数量，并返回【非友军】的最高分（包括噪点）
        """
        if screen_img is None or not template_list:
            return 0, 0.0

        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        screen_processed = self.preprocess_image(screen_gray)
        
        total_count = 0
        global_max_score = 0.0
        
        mask_map = np.zeros(screen_processed.shape, dtype=np.uint8)

        for tmpl_processed, mask in template_list:
            tmpl_h, tmpl_w = tmpl_processed.shape[:2]
            if screen_processed.shape[0] < tmpl_h or screen_processed.shape[1] < tmpl_w:
                continue

            try:
                if mask is not None:
                    res = cv2.matchTemplate(screen_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED)
                
                while True:
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    
                    # 只要分数有意义（>0.2），就进入判断，哪怕它低于阈值
                    if max_val >= 0.2:
                        top_left = max_loc
                        bottom_right = (top_left[0] + tmpl_w, top_left[1] + tmpl_h)
                        
                        # 颜色检查
                        is_safe = False
                        if check_safe_color:
                            crop_img = screen_img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
                            if self._is_safe_color(crop_img):
                                is_safe = True
                        
                        if is_safe:
                            # 是友军：直接抹去，不记录分数，继续找下一个
                            cv2.rectangle(res, top_left, bottom_right, -1.0, -1)
                            continue
                        
                        else:
                            # 是非友军（可能是敌对，也可能是背景噪点）
                            # 记录最高分（哪怕是噪点）
                            if max_val > global_max_score:
                                global_max_score = max_val
                            
                            # 只有当分数真正达标时，才计数
                            if max_val >= threshold:
                                center_x = int(top_left[0] + tmpl_w/2)
                                center_y = int(top_left[1] + tmpl_h/2)
                                if mask_map[center_y, center_x] == 0:
                                    total_count += 1
                                    cv2.rectangle(mask_map, top_left, bottom_right, 255, -1)
                                
                                # 抹去已统计区域，继续找下一个
                                cv2.rectangle(res, top_left, bottom_right, -1.0, -1)
                            else:
                                # 分数没达标，说明剩下的都是更小的噪点了，退出当前模板的循环
                                break
                    else:
                        break 
            except Exception:
                continue

        return total_count, global_max_score

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False, check_safe_color=False):
        count, score = self.count_matches(screen_img, template_list, threshold, check_safe_color)
        if return_max_val:
            return (None, score)
        return score >= threshold
