import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        self.sct = mss.mss()
        self.hostile_templates = []
        self.monster_templates = []
        self.load_templates()

    def load_templates(self):
        # 加载非友军图标
        self.hostile_templates = self._load_images_from_folder("assets/hostile_icons")
        # 加载怪物图标/文字
        self.monster_templates = self._load_images_from_folder("assets/monster_icons")

    def _load_images_from_folder(self, folder):
        templates = []
        if not os.path.exists(folder):
            os.makedirs(folder)
            return templates
            
        for filename in os.listdir(folder):
            if filename.lower().endswith(('.png', '.jpg', '.bmp')):
                path = os.path.join(folder, filename)
                # 使用 cv2.IMREAD_UNCHANGED 读取透明通道
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    templates.append(img)
        return templates

    def capture_screen(self, region):
        # region: (x, y, w, h)
        if not region: return None
        monitor = {"top": region[1], "left": region[0], "width": region[2], "height": region[3]}
        img = np.array(self.sct.grab(monitor))
        # MSS返回的是BGRA，OpenCV通常用BGR
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def match_templates(self, screen_img, template_list, threshold):
        """
        核心匹配逻辑
        """
        if screen_img is None or not template_list:
            return False

        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)

        for tmpl in template_list:
            # 检查模板是否有透明通道
            mask = None
            if tmpl.shape[2] == 4:
                # 提取 alpha 通道作为掩码
                _, _, _, alpha = cv2.split(tmpl)
                mask = alpha
                tmpl_bgr = cv2.cvtColor(tmpl, cv2.COLOR_BGRA2BGR) # 仅用于转换格式
                tmpl_gray = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
            else:
                tmpl_gray = cv2.cvtColor(tmpl, cv2.COLOR_BGR2GRAY)

            # 匹配
            # 注意：OpenCV的带MASK匹配只支持 cv2.TM_CCORR_NORMED 或 cv2.TM_SQDIFF
            # 但常用的 TM_CCOEFF_NORMED 不支持 mask。
            # 简化策略：如果不需要极高精度mask，直接灰度匹配通常足够，
            # 若背景干扰大，建议对screen_gray也做二值化处理（特别是针对文字）。
            
            res = cv2.matchTemplate(screen_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
            
            loc = np.where(res >= threshold)
            if len(loc[0]) > 0:
                return True # 发现目标

        return False

    def detect_monster_text(self, screen_img, threshold):
        """
        针对文字的特殊处理：二值化后匹配
        """
        if screen_img is None or not self.monster_templates:
            return False
            
        gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        # 假设游戏内文字是亮的，背景是暗的。二值化处理
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        # 这里假设 monster_templates 里的图片也是经过处理的黑底白字
        # 实际使用建议在 match_templates 里统一逻辑，这里为了演示区分开
        return self.match_templates(screen_img, self.monster_templates, threshold)
