import cv2
import numpy as np
import mss
import os

class VisionEngine:
    def __init__(self):
        self.sct = mss.mss()
        self.hostile_templates = []
        self.monster_templates = []
        # 新增：记录最后一次的错误原因
        self.last_error = "" 
        
        # 调试目录
        self.debug_dir = "debug_scans"
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
            
        self.load_templates()

    def load_templates(self):
        # 获取绝对路径，防止打包后路径错乱
        base_dir = os.path.abspath(os.getcwd())
        path_hostile = os.path.join(base_dir, "assets", "hostile_icons")
        path_monster = os.path.join(base_dir, "assets", "monster_icons")
        
        self.hostile_templates = self._load_images_from_folder(path_hostile, "Hostile")
        self.monster_templates = self._load_images_from_folder(path_monster, "Monster")

    def _load_images_from_folder(self, folder, tag):
        templates = []
        if not os.path.exists(folder):
            os.makedirs(folder)
            return templates
            
        for filename in os.listdir(folder):
            if filename.lower().endswith(('.png', '.jpg', '.bmp')):
                path = os.path.join(folder, filename)
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is not None:
                    # 即使是JPG，也统一检查一下维度
                    templates.append(img)
                else:
                    print(f"Failed to load: {filename}")
        return templates

    def capture_screen(self, region, debug_name=None):
        if not region: return None
        monitor = {"top": int(region[1]), "left": int(region[0]), "width": int(region[2]), "height": int(region[3])}
        try:
            img = np.array(self.sct.grab(monitor))
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            # 保存一下截图，方便你看程序到底看见了什么
            if debug_name:
                cv2.imwrite(os.path.join(self.debug_dir, f"debug_{debug_name}.png"), img_bgr)
            return img_bgr
        except:
            return None

    def match_templates(self, screen_img, template_list, threshold, return_max_val=False):
        # 重置错误信息
        self.last_error = ""

        if screen_img is None:
            self.last_error = "截图无效(未画框?)"
            return (False, 0.0) if return_max_val else False
            
        if not template_list:
            self.last_error = "无模板文件"
            return (False, 0.0) if return_max_val else False

        screen_gray = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)
        screen_h, screen_w = screen_gray.shape[:2]
        
        max_score_found = 0.0
        valid_templates_count = 0 

        for i, tmpl in enumerate(template_list):
            tmpl_h, tmpl_w = tmpl.shape[:2]
            
            # === 关键检查：模板尺寸是否大于截图 ===
            if screen_h < tmpl_h or screen_w < tmpl_w:
                # 记录第一张出错模板的详情
                if self.last_error == "":
                    self.last_error = f"尺寸大过截图(模{tmpl_w}x{tmpl_h} vs 屏{screen_w}x{screen_h})"
                continue # 跳过这张过大的图

            valid_templates_count += 1
            
            mask = None
            if tmpl.shape[2] == 4:
                b, g, r, a = cv2.split(tmpl)
                tmpl_bgr = cv2.merge([b, g, r])
                tmpl_gray = cv2.cvtColor(tmpl_bgr, cv2.COLOR_BGR2GRAY)
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
                self.last_error = f"CV错误 {str(e)}"
                continue

        # 如果遍历完了，一个有效模板都没找到
        if valid_templates_count == 0 and not self.last_error:
             self.last_error = "所有模板均过大"

        if return_max_val:
            return (max_score_found >= threshold, max_score_found)
        else:
            return max_score_found >= threshold
