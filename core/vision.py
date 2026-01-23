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
        三层复合匹配逻辑：
        1. 颜色层 (SQDIFF): 针对精准颜色匹配 (如完全一致的红名)
        2. 灰度层 (Grayscale): 针对有色图标但背景微变 (如暗红色、灰色图标)
        3. 高光层 (Binary): 针对亮背景下的纯白符号
        取三者最大值。
        """
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        screen_h, screen_w = screen_img.shape[:2]
        
        # --- 预处理屏幕图像 ---
        # 1. 灰度图 (用于层级 B)
        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        
        # 2. 二值化图 (用于层级 C)
        # 阈值 190: 过滤掉大部分背景，只留高亮符号
        _, screen_binary = cv2.threshold(screen_gray, 190, 255, cv2.THRESH_BINARY)
        
        max_score_found = 0.0
        all_skipped = True 

        for tmpl in template_list:
            tmpl_h, tmpl_w = tmpl.shape[:2]
            
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            all_skipped = False 

            # 准备模板数据
            if tmpl.shape[2] == 4:
                tmpl_bgr = tmpl[:, :, :3]
                mask = tmpl[:, :, 3]
                tmpl_gray_raw = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
            else:
                tmpl_bgr = tmpl
                mask = np.ones((tmpl_h, tmpl_w), dtype=np.uint8) * 255
                tmpl_gray_raw = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)

            # --- 层级 A: 颜色匹配 (SQDIFF) ---
            # 优势: 极低误报率，精准匹配颜色
            score_a = 0.0
            try:
                res_a = cv2.matchTemplate(screen_img, tmpl_bgr, cv2.TM_SQDIFF, mask=mask)
                min_val, _, _, _ = cv2.minMaxLoc(res_a)
                valid_pixels = cv2.countNonZero(mask)
                if valid_pixels > 0:
                    avg_diff = min_val / valid_pixels
                    # 转换分数的公式，对色差敏感
                    score_a = 1.0 / (1.0 + avg_diff / 1500.0)
            except: pass

            # --- 层级 B: 灰度形状匹配 (CCOEFF_NORMED) ---
            # 优势: 忽略色相，只看明暗轮廓。能识别暗红色、深灰色图标
            score_b = 0.0
            try:
                # 这种模式下，我们直接用灰度匹配，不二值化
                # 这样保留了“暗红”和“黑色”的区别 (灰度值不同)
                res_b = cv2.matchTemplate(screen_gray, tmpl_gray_raw, cv2.TM_CCOEFF_NORMED, mask=mask)
                _, max_val_b, _, _ = cv2.minMaxLoc(res_b)
                score_b = max_val_b
            except: pass

            # --- 层级 C: 高光二值化匹配 (Binary) ---
            # 优势: 忽略背景干扰，只看最亮的符号。解决“白符号+亮背景”问题
            score_c = 0.0
            try:
                # 模板也二值化
                _, tmpl_binary = cv2.threshold(tmpl_gray_raw, 190, 255, cv2.THRESH_BINARY)
                # 只有当模板里确实有高亮内容时才启用此模式
                if cv2.countNonZero(tmpl_binary) > 5:
                    res_c = cv2.matchTemplate(screen_binary, tmpl_binary, cv2.TM_CCOEFF_NORMED)
                    _, max_val_c, _, _ = cv2.minMaxLoc(res_c)
                    score_c = max_val_c
            except: pass

            # 取三者最大值作为最终得分
            final_score = max(score_a, score_b, score_c)

            if final_score > max_score_found:
                max_score_found = final_score

        if all_skipped:
            return ("尺寸错误", 0.0) if return_max_val else False

        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
