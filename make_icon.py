"""Генерирует иконку: snow.ico (для .exe) и snow.png (для .app). Запуск:  python make_icon.py"""
import math
import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPen


def render(size=256):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    k = size / 64.0
    g = QLinearGradient(0, 0, 0, size)
    g.setColorAt(0.0, QColor("#3C78C8"))
    g.setColorAt(1.0, QColor("#1B3A6B"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(size / 2, size / 2), 30 * k, 30 * k)
    p.translate(size / 2, size / 2)
    p.setPen(QPen(QColor("white"), 3.2 * k, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for i in range(6):
        p.save()
        p.rotate(i * 60.0)
        p.drawLine(QPointF(0, 0), QPointF(0, -24 * k))
        p.drawLine(QPointF(0, -14 * k), QPointF(-6 * k, -20 * k))
        p.drawLine(QPointF(0, -14 * k), QPointF(6 * k, -20 * k))
        p.restore()
    p.end()
    return img


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    img = render(1024)
    ok_png = img.save("snow.png", "PNG")
    ok_ico = render(256).save("snow.ico", "ICO")
    print("snow.png:", "ok" if ok_png else "ошибка", "| snow.ico:", "ok" if ok_ico else "ошибка")
    sys.exit(0 if (ok_png or ok_ico) else 1)
