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
                    # 必须保留 Alpha 通道
                    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                    if img is not None:
                        # 如果没有 Alpha 通道 (比如JPG)，手动加一个全白的 Alpha
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
                # mss 返回 BGRA，这很好，保留它用于后续比对
                # 但为了兼容之前的逻辑，我们这里返回 BGR，但在匹配时我们会重新处理
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
        重写的匹配逻辑：基于掩码的平方差匹配 (Masked SQDIFF)
        这种方式对颜色极其敏感，且完美支持透明度忽略。
        """
        if screen_img is None:
            err = self.last_error if self.last_error else "未获取到截图"
            return (err, 0.0) if return_max_val else False
            
        if not template_list:
            return ("无模板", 0.0) if return_max_val else False

        # 将屏幕截图保持 BGR 格式 (OpenCV默认)
        # 之前的逻辑是转灰度，现在我们用彩色匹配来提高准确度
        screen_h, screen_w = screen_img.shape[:2]
        
        max_score_found = 0.0
        all_skipped = True 

        for tmpl in template_list:
            tmpl_h, tmpl_w = tmpl.shape[:2]
            
            # 尺寸检查
            if screen_h < tmpl_h or screen_w < tmpl_w:
                continue 
            all_skipped = False 

            # 分离模板的 BGR 和 Alpha
            if tmpl.shape[2] == 4:
                tmpl_bgr = tmpl[:, :, :3]
                mask = tmpl[:, :, 3]
            else:
                tmpl_bgr = tmpl
                mask = np.ones((tmpl_h, tmpl_w), dtype=np.uint8) * 255

            try:
                # === 核心算法变更 ===
                # 使用 TM_SQDIFF (平方差匹配)
                # 这种算法计算的是：(T - I)^2
                # 结果越小越好 (0表示完全一样)
                # 支持 mask：mask为0的地方不参与计算
                
                res = cv2.matchTemplate(screen_img, tmpl_bgr, cv2.TM_SQDIFF, mask=mask)
                
                # 找到最小差异值 (min_val)
                min_val, _, _, _ = cv2.minMaxLoc(res)
                
                # === 将差异值转换为相似度分数 (0.0 - 1.0) ===
                # SQDIFF 的结果是像素差的平方和。
                # 我们需要归一化它。
                # 1. 计算掩码内的有效像素数
                valid_pixels = cv2.countNonZero(mask)
                if valid_pixels == 0: continue
                
                # 2. 计算平均每个像素的差异
                # min_val 是总平方差
                avg_diff_per_pixel = min_val / valid_pixels
                
                # 3. 转换为 0-1 分数
                # 假设最大允许的平均差异是 10000 (大概相当于每个颜色通道差60左右)
                # 这是一个经验值，可以调整。差异越小，score 越接近 1
                # 这种转换是非线性的，对精准匹配非常敏感
                
                # 稍微放宽一点分母，防止分数太低
                score = 1.0 / (1.0 + avg_diff_per_pixel / 1000.0)
                
                # 修正逻辑：如果差异极小，score 会接近 1.0
                # 如果差异很大，score 会迅速掉到 0.1 以下
                
                if score > max_score_found:
                    max_score_found = score

            except Exception as e:
                # print(f"Match error: {e}")
                continue

        if all_skipped:
            return ("尺寸错误", 0.0) if return_max_val else False

        # 由于 SQDIFF 转换的分数通常比较苛刻
        # 0.95 的阈值可能太高了，建议用户在 UI 上调整到 0.8 左右开始测试
        if return_max_val:
            return (None, max_score_found)
        else:
            return max_score_found >= threshold
