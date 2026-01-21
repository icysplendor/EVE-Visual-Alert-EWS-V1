from PyQt6.QtWidgets import QWidget, QRubberBand, QApplication
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QColor, QPalette

class RegionSelector(QWidget):
    # 信号：选区结束，发送 (x, y, w, h)
    selection_finished = pyqtSignal(tuple)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: black;")
        self.setWindowOpacity(0.3)  # 半透明遮罩
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 这个很重要，铺满全屏
        screen_geo = QApplication.primaryScreen().geometry()
        self.setGeometry(screen_geo)

        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()));
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self.rubberBand.geometry()
            # 转换为屏幕绝对坐标
            global_pos = self.mapToGlobal(rect.topLeft())
            x, y, w, h = global_pos.x(), global_pos.y(), rect.width(), rect.height()
            
            self.selection_finished.emit((x, y, w, h))
            self.close()
            
from PyQt6.QtCore import QSize
