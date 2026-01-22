import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        self.sct = mss.mss()
        self.hostile_templates = []
        self.monster_templates = []
        
        # 调试目录
        self.debug_dir = "debug_scans"
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
            
        print(">>> [Vision] 视觉引擎初始化...")
        self.load_templates()

    def load_templates(self):
        # 强制打印加载路径，让你确认路径对不对
        cwd = os.getcwd()
        print(f">>> [Vision] 当前工作目录: {cwd}")
        
        path_hostile = os.path.join(cwd, "assets", "hostile_icons")
        path_monster = os.path.join(cwd, "assets", "monster_icons")
        
        print(f">>> [Vision] 正在尝试加载敌对图标: {path_hostile}")
        self.hostile_templates = self._load_images_from_folder(path_hostile, "HOSTILE")
        
        print(f">>> [Vision] 正在尝试加载怪物图标: {path_monster}")
        self.monster_templates = self._load_images_from_folder(path_monster, "MONSTER")
        
        print(f"==========================================")
        print(f"   模板加载统计: 敌对[{len(self.hostile_templates)}] | 怪物[{len(self.monster_templates)}]")
        print(f"==========================================")

    def _load_images_from_folder(self, folder, tag):
        templates = []
        if not os.path.exists(folder):
            print(f"!!! [Vision] 错误: 文件夹不存在 -> {folder}")
            os.makedirs(folder)
            return templates
            
        files = os.listdir(folder)
        if not files:
            print(f"!!! [Vision] 警告: 文件夹是空的 -> {folder}")

        for filename in files:
            if filename.lower().endswith(('.png', '.jpg', '.bmp')):
                path = os.path.join(folder, filename)
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    h, w = img.shape[:2]
                    templates.append(img)
                    print(f"    -> [{tag}] 已加载: {filename} (尺寸: {w}x{h})")
                else:
                    print(f"    -> [{tag}] 读取失败 (损坏?): {filename}")
        return templates

    def capture_screen(self, region, debug_name=None):
        if not region: 
            return None
        
        monitor = {
            "top": int(region[1]), 
            "left": int(region[0]), 
            "width": int(region[2]), 
            "height": int(region[3])
        }
        
        try:
            img = np.array(self.sct.grab(monitor))
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            
            # 保存截图供检查
            if debug_name:
                cv2.imwrite(os.path.join(self.debug_dir, f"debug_{debug_name}.png"), img_bgr)
                
            return img_bgr
        except Exception as e:
            print(f"!!! [Vision] 截图失败: {e}")
            return None

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False):
        # 1. 检查截图是否存在
        if screen_img is None:
            # 这种情况通常是因为用户还没画框
            return (False, 0.0) if return_max_val else False
            
        # 2. 检查模板列表是否为空
        if not template_list:
            # 如果这里返回了，说明 assets 文件夹里没图片，或者还没加载
            # 这是导致相似度 0.0 的第一大原因
            return (False, 0.0) if return_max_val else False

        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        screen_h, screen_w = screen_gray.shape[:2]
        
        max_score_found = 0.0
        
        # 遍历每一个模板
        for i, tmpl in enumerate(template_list):
            tmpl_h, tmpl_w = tmpl.shape[:2]
            
            # 3. 尺寸检查 (这是导致相似度 0.0 的第二大原因)
            if screen_h < tmpl_h or screen_w < tmpl_w:
                # 你的截图比你的模板还小，根本没法找
                if return_max_val:
                    # 只有调试模式才打印，防止刷屏
                    print(f"!!! [Vision] 尺寸错误: 截图({screen_w}x{screen_h}) 小于 模板{i}({tmpl_w}x{tmpl_h})，跳过比对。")
                continue

            mask = None
            if tmpl.shape[2] == 4:
                b, g, r, a = cv2.split(tmpl)
                tmpl_bgr = cv2.merge([b, g, r])
                tmpl_gray = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
                # 如果是完全透明的像素，a=0，mask起作用
                mask = a 
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
                    
            except Exception as e:
                print(f"!!! [Vision] OpenCV 内部错误: {e}")
                continue

        if return_max_val:
            return (max_score_found >= threshold, max_score_found)
        else:
            return max_score_found >= threshold
