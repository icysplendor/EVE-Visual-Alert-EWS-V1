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
            
        # 初始化 CLAHE (对比度限制自适应直方图均衡化)
        # clipLimit: 对比度限制阈值，越高对比度越强，但也越容易放大噪点
        # tileGridSize: 局部处理的网格大小
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            
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
                        # 统一处理：加载后立刻转为灰度图并应用 CLAHE
                        # 这样模板和截图的处理逻辑完全一致
                        if img.shape[2] == 4:
                            # 分离 Alpha 作为 Mask
                            b, g, r, a = cv2.split(img)
                            gray = cv2.cvtColor(cv2.merge([b,g,r]), cv2.COLOR_BGR2GRAY)
                            # 对模板灰度图也做 CLAHE，保证特征一致
                            gray = self.clahe.apply(gray)
                            # 重新组合：灰度图 + 原始Mask
                            templates.append((gray, a))
                        else:
                            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                            gray = self.clahe.apply(gray)
                            # 没有Mask，用None
                            templates.append((gray, None))
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
        稳定性优化版：使用 CLAHE 增强 + 灰度匹配
        """
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        screen_h, screen_w = screen_img.shape[:2]
        
        # === 步骤 1: 预处理截图 ===
        # 转灰度
        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        
        # 应用 CLAHE 增强
        # 这会平衡光照，让暗处的图标变清晰，同时抑制亮处过曝
        # 最重要的是，它是局部的，不会因为屏幕边缘的一个亮点而导致整体数值漂移
        screen_enhanced = self.clahe.apply(screen_gray)
        
        max_score_found = 0.0
        all_skipped = True 

        # 注意：现在的 template_list 里存的是元组 (gray_image, mask)
        for tmpl_gray, mask in template_list:
            tmpl_h, tmpl_w = tmpl_gray.shape[:2]
            
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            all_skipped = False 

            try:
                # === 步骤 2: 匹配 ===
                # 使用 TM_CCOEFF_NORMED，配合 CLAHE 增强后的图像
                if mask is not None:
                    res = cv2.matchTemplate(screen_enhanced, tmpl_gray, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_enhanced, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                # 过滤无效值
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
