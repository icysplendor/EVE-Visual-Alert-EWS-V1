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
        核心匹配逻辑：增加颜色校验
        """
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

            # 处理掩码
            mask = None
            tmpl_bgr = tmpl
            if tmpl.shape[2] == 4:
                b, g, r, a = cv2.split(tmpl)
                mask = a
                tmpl_bgr = cv2.merge([b,g,r])
                tmpl_gray = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
            else:
                tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)

            try:
                # 1. 形状匹配 (TM_CCOEFF_NORMED)
                if mask is not None:
                    res = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED, mask=mask)
                else:
                    res = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
                
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                
                # 2. === 新增：颜色绝对值校验 ===
                # 如果形状分数达标，我们再检查一遍颜色是否真的对
                if max_val >= threshold:
                    top_left = max_loc
                    bottom_right = (top_left[0] + tmpl_w, top_left[1] + tmpl_h)
                    
                    # 把屏幕上匹配到的这一小块切出来
                    screen_crop = screen_img[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
                    
                    # 计算色差 (screen_crop - template)
                    # 我们只关心 mask 部分的色差
                    diff = cv2.absdiff(screen_crop, tmpl_bgr)
                    
                    if mask is not None:
                        # 计算掩码区域内的平均色差
                        mean_diff = cv2.mean(diff, mask=mask)
                    else:
                        mean_diff = cv2.mean(diff)
                    
                    # mean_diff 返回 (B_diff, G_diff, R_diff, A_diff)
                    # 我们计算 RGB 平均差异值
                    avg_color_diff = (mean_diff[0] + mean_diff[1] + mean_diff[2]) / 3.0
                    
                    # 设定一个严格的色差容忍度 (0-255)
                    # 比如 30，意味着颜色平均偏差不能超过 30
                    # 红色(0,0,255) 和 白色(255,255,255) 的差异极大，会被这里过滤掉
                    color_tolerance = 40.0 
                    
                    if avg_color_diff > color_tolerance:
                        # 虽然形状像，但颜色不对，强行扣分
                        # print(f"形状匹配但颜色不对: 差异 {avg_color_diff:.2f}")
                        max_val = 0.1 # 降级为低分
                    
                # ===============================

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
