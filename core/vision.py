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
        
        # 初始化 CLAHE
        self.clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8,8))
        
        # === 颜色过滤器设置 ===
        # EVE 界面中友军/舰队/同盟的绿色范围 (HSV空间)
        # H: 35-85 (涵盖了黄绿到青绿)
        # S: > 40 (有一定的饱和度，排除灰白)
        # V: > 40 (有一定的亮度，排除黑底)
        self.GREEN_LOWER = np.array([35, 40, 40])
        self.GREEN_UPPER = np.array([85, 255, 255])
        self.GREEN_PIXEL_THRESHOLD = 8  # 超过8个绿色像素则认为是友军
            
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
                        # 预处理模板：确保模板也经过同样的 Gamma 和 CLAHE 处理
                        if img.shape[2] == 4:
                            b, g, r, a = cv2.split(img)
                            gray = cv2.cvtColor(cv2.merge([b,g,r]), cv2.COLOR_BGR2GRAY)
                            processed = self.preprocess_image(gray)
                            templates.append((processed, a))
                        else:
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            processed = self.preprocess_image(gray)
                            templates.append((processed, None))
                except:
                    pass
        return templates

    def apply_gamma(self, image, gamma=1.0):
        """
        Gamma 校正：
        Gamma > 1.0: 压暗阴影 (消除背景噪声)
        Gamma < 1.0: 提亮阴影
        我们这里使用 Gamma > 1 来压制 EVE 的深色星空背景
        """
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255
            for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(image, table)

    def preprocess_image(self, gray_img):
        """
        统一的图像预处理流水线
        """
        # 1. Gamma 校正：压暗背景，突出高亮图标
        gamma_corrected = self.apply_gamma(gray_img, gamma=1.5)
        
        # 2. 简单的阈值截断：把低于 30 的像素直接置为 0
        _, thresholded = cv2.threshold(gamma_corrected, 30, 255, cv2.THRESH_TOZERO)
        
        # 3. CLAHE 增强：增强剩余有效像素的对比度
        enhanced = self.clahe.apply(thresholded)
        
        return enhanced

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
                
                # 内存返回，不写盘
                return img_bgr
                
        except Exception as e:
            self.last_error = f"截图失败: {str(e)}"
            return None

    def _is_green_region(self, img_crop):
        """
        检查图片切片中是否包含超过阈值的绿色像素
        """
        if img_crop is None or img_crop.size == 0:
            return False
            
        # 转换到 HSV 空间
        hsv = cv2.cvtColor(img_crop, cv2.COLOR_BGR2HSV)
        
        # 创建掩膜
        mask = cv2.inRange(hsv, self.GREEN_LOWER, self.GREEN_UPPER)
        
        # 统计非零像素点（即绿色像素点）
        green_pixel_count = cv2.countNonZero(mask)
        
        return green_pixel_count > self.GREEN_PIXEL_THRESHOLD

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False, check_green_exclusion=False):
        """
        执行模板匹配
        :param check_green_exclusion: 是否开启绿色排除逻辑（用于 Local/Overview）
        """
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        screen_h, screen_w = screen_img.shape[:2]
        
        # === 步骤 1: 预处理截图 (灰度用于匹配) ===
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
                # === 步骤 2: 匹配 ===
                if mask is not None:
                    res = cv2.matchTemplate(screen_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_processed, tmpl_processed, cv2.TM_CCOEFF_NORMED)
                
                # 获取最佳匹配位置
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                
                if np.isinf(max_val) or np.isnan(max_val):
                    max_val = 0.0
                
                # === 步骤 3: 绿色排除逻辑 ===
                # 只有当分数超过当前最大值，且需要检查颜色时，才进行昂贵的颜色检查
                if max_val > max_score_found:
                    if check_green_exclusion and max_val >= threshold:
                        # 切出匹配区域的原图（彩色）
                        top_left = max_loc
                        bottom_right = (top_left[0] + tmpl_w, top_left[1] + tmpl_h)
                        
                        # 注意：numpy 数组切片是 [y:y+h, x:x+w]
                        crop_img = screen_img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
                        
                        # 检查是否是绿色友军
                        if self._is_green_region(crop_img):
                            # 是绿色，忽略这次匹配结果，不更新 max_score_found
                            # print(f"忽略绿色目标，相似度: {max_val:.2f}")
                            continue
                    
                    # 如果通过了检查（或者是怪物不需要检查），则更新最大分
                    max_score_found = max_val

            except Exception as e:
                continue

        if all_skipped:
            return ("尺寸错误", 0.0) if return_max_val else False

        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
