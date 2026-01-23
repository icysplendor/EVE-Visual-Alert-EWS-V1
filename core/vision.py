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
                    # 必须保留 Alpha 通道 (IMREAD_UNCHANGED)
                    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        # 如果是JPG没有透明通道，强制加一个全不透明的通道
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
                # mss 返回 BGRA
                # 我们这里直接保留 BGRA，或者转 BGR 都可以
                # 为了配合下面的匹配逻辑，我们统一转为 BGR，因为 mask 是独立传进去的
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
        单一算法：基于掩码的彩色平方差匹配 (Color Masked SQDIFF)
        
        原理：
        1. 严格比对 RGB 颜色。绿图标 vs 红模板 -> 差异极大 -> 低分。
        2. 严格遵守 Mask。模板透明部分 -> 完全不参与计算 -> 忽略背景。
        """
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        screen_h, screen_w = screen_img.shape[:2]
        max_score_found = 0.0
        all_skipped = True 

        for tmpl in template_list:
            tmpl_h, tmpl_w = tmpl.shape[:2]
            
            # 尺寸检查
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            all_skipped = False 

            # 准备数据：分离颜色通道(BGR) 和 Alpha通道(Mask)
            if tmpl.shape[2] == 4:
                tmpl_bgr = tmpl[:, :, :3]
                mask = tmpl[:, :, 3]
            else:
                tmpl_bgr = tmpl
                mask = np.ones((tmpl_h, tmpl_w), dtype=np.uint8) * 255

            try:
                # === 核心算法：TM_SQDIFF ===
                # 计算公式：Sum( (T(x,y) - I(x,y))^2 )
                # 只有 mask != 0 的点才计算
                res = cv2.matchTemplate(screen_img, tmpl_bgr, cv2.TM_SQDIFF, mask=mask)
                
                # min_val 是最小的平方差总和 (越小越匹配)
                min_val, _, _, _ = cv2.minMaxLoc(res)
                
                # === 分数转换逻辑 ===
                # 1. 计算有效像素点数量 (不透明的像素)
                valid_pixels = cv2.countNonZero(mask)
                if valid_pixels == 0: continue
                
                # 2. 计算平均每个像素的差异值
                # min_val 是所有像素差异的平方和。
                # 平均平方差 = min_val / valid_pixels
                # 平均像素差 (RMSE) = sqrt(平均平方差)
                # 比如：如果颜色完全一样，diff = 0
                # 如果只是亮度稍微变了一点，diff 可能是 10-20
                # 如果红变绿，diff 可能是 150+
                avg_diff = np.sqrt(min_val / valid_pixels)
                
                # 3. 线性映射到 0.0 - 1.0
                # 我们定义一个 "最大容忍差异" (Max Tolerance)
                # 假设容忍度是 60 (这意味着平均每个像素的颜色偏差在60以内都有分)
                # 偏差 0 -> 100分
                # 偏差 60 -> 0分
                # 偏差 > 60 -> 0分
                
                tolerance = 60.0 
                if avg_diff > tolerance:
                    score = 0.0
                else:
                    score = 1.0 - (avg_diff / tolerance)
                
                if score > max_score_found:
                    max_score_found = score

            except Exception as e:
                # print(f"Error: {e}")
                continue

        if all_skipped:
            return ("尺寸错误", 0.0) if return_max_val else False

        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
