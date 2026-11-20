# -*- coding: utf-8 -*-
"""Виджеты рабочего стола для Windows 10/11 в стиле macOS.

  * Батарея     - заряд Bluetooth-мыши, клавиатуры, наушников, геймпада и ноутбука.
  * Фото        - слайд-шоу фотографий из выбранной папки с плавной сменой кадров.
  * Часы        - аналоговые / цифровые часы с календарём на месяц.
  * Система     - загрузка процессора, памяти и диска.

Запуск: двойной клик по widgets.pyw (нужен Python 3.9+, PySide6 поставится сам).
Управление - значок в трее (возле часов): добавить виджет, тема, закрепить, автозапуск, выход.
Виджет: перетаскивай левой кнопкой, правая кнопка - размер и настройки, двойной клик - действие.
Данные: %APPDATA%\\SnowWidgets\\widgets.json
"""
import calendar
import ctypes
import datetime
import json
import math
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import traceback

IS_WIN = sys.platform.startswith("win")
APP_NAME = "SnowWidgets"
APP_VERSION = "1.0"
FROZEN = bool(getattr(sys, "frozen", False))
HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = "--demo" in sys.argv            # тестовые данные вместо настоящих устройств

if IS_WIN:
    _BASE = os.environ.get("APPDATA") or HERE
else:
    _BASE = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
DATA_DIR = os.path.join(_BASE, APP_NAME)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = HERE
CONFIG_FILE = os.path.join(DATA_DIR, "widgets.json")
NO_WINDOW = 0x08000000                 # CREATE_NO_WINDOW: без мелькающей консоли


def msgbox(text, title="Виджеты", flags=0x40):
    if IS_WIN:
        try:
            ctypes.windll.user32.MessageBoxW(0, text, title, flags)
            return
        except Exception:
            pass
    print(title + ": " + text)


def ensure_deps():
    try:
        import PySide6.QtWidgets  # noqa: F401
        return
    except ImportError:
        pass
    if not IS_WIN:
        print("Нужна библиотека PySide6:  pip install PySide6")
        sys.exit(1)
    msgbox("Для виджетов нужна библиотека PySide6.\n\n"
           "Сейчас она установится автоматически (нужен интернет, 1-3 минуты).\n"
           "Нажми OK и подожди - виджеты появятся сами.")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "PySide6"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=NO_WINDOW)
    except Exception:
        msgbox("Не получилось установить PySide6 автоматически.\n\n"
               "Открой командную строку (Win+R, cmd) и выполни:\n"
               "    pip install PySide6\n"
               "Потом запусти widgets.pyw снова.", "Виджеты - ошибка", 0x10)
        sys.exit(1)
    subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit(0)


ensure_deps()

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import (QActionGroup, QColor, QDesktopServices, QFont,  # noqa: E402
                           QIcon, QImage, QImageReader, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QFileDialog, QMenu,  # noqa: E402
                               QSystemTrayIcon, QWidget)

RH = (QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
      | QPainter.RenderHint.TextAntialiasing)
FONT = "Segoe UI" if IS_WIN else "Sans Serif"
NOPEN = Qt.PenStyle.NoPen

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
          "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

THEMES = {
    "dark": {"bg1": QColor(44, 46, 52, 238), "bg2": QColor(28, 29, 33, 238),
             "fg": QColor(245, 245, 247), "fg2": QColor(160, 162, 170),
             "track": QColor(255, 255, 255, 38), "line": QColor(255, 255, 255, 26)},
    "light": {"bg1": QColor(252, 252, 253, 242), "bg2": QColor(236, 237, 241, 242),
              "fg": QColor(28, 28, 30), "fg2": QColor(120, 120, 128),
              "track": QColor(0, 0, 0, 30), "line": QColor(0, 0, 0, 22)},
}
GREEN, YELLOW, RED, BLUE = QColor("#30D158"), QColor("#FFD60A"), QColor("#FF453A"), QColor("#0A84FF")
ACCENT = QColor("#FF9F0A")


def font(px, weight=QFont.Weight.Normal):
    f = QFont(FONT)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def level_color(v):
    return RED if v <= 15 else (YELLOW if v <= 30 else GREEN)


# ---------------------------------------------------------------------------
#  Батарея устройств
# ---------------------------------------------------------------------------
# Windows хранит заряд Bluetooth-устройств (то, что видно в "Параметры -> Bluetooth")
# в свойстве устройства {104EA319-...} 2. Читаем его одной командой PowerShell.
_PS_BATTERY = r"""
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$k = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$d = @(Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName })
if ($d.Count -gt 0) {
  $names = @{}
  foreach ($x in $d) { $names[$x.InstanceId] = $x.FriendlyName }
  foreach ($p in @(Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName $k)) {
    if ($p.Type -ne 'Empty' -and $p.Data -ne $null) {
      "{0}`t{1}`t{2}" -f $names[$p.InstanceId], $p.Data, $p.InstanceId
    }
  }
}
"""

KIND_WORDS = (
    ("mouse", ("mouse", "мыш", "mx master", "mx anywhere", "pebble", "trackball", "m720", "m590")),
    ("keyboard", ("keyboard", "клавиат", "keys", "mx keys", "k380", "k810")),
    ("headphones", ("head", "наушн", "buds", "airpods", "earbuds", "wh-", "wf-", "jbl", "bose",
                    "sony", "airdots", "freebuds", "galaxy buds", "гарнит", "hands-free")),
    ("gamepad", ("controller", "gamepad", "геймпад", "xbox", "dualsense", "dualshock", "joy-con")),
    ("pen", ("pen", "перо", "stylus")),
)


def guess_kind(name):
    n = name.lower()
    for kind, words in KIND_WORDS:
        if any(w in n for w in words):
            return kind
    return "bluetooth"


if IS_WIN:
    from ctypes import wintypes as wt

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", wt.DWORD), ("BatteryFullLifeTime", wt.DWORD)]

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wt.HWND), ("message", wt.UINT), ("wParam", wt.WPARAM),
                    ("lParam", wt.LPARAM), ("time", wt.DWORD), ("pt", wt.POINT)]

    class WINDOWPOS(ctypes.Structure):
        _fields_ = [("hwnd", wt.HWND), ("hwndInsertAfter", wt.HWND), ("x", ctypes.c_int),
                    ("y", ctypes.c_int), ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", wt.UINT)]

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _user32.SetWindowPos.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wt.UINT]
    _user32.GetForegroundWindow.restype = wt.HWND
    _user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]


def pc_battery():
    """Батарея самого компьютера (ноутбука) или None."""
    if IS_WIN:
        try:
            st = SYSTEM_POWER_STATUS()
            if _kernel32.GetSystemPowerStatus(ctypes.byref(st)):
                if st.BatteryFlag & 128 or st.BatteryLifePercent > 100:      # батареи нет
                    return None
                return {"name": "Этот компьютер", "level": int(st.BatteryLifePercent),
                        "kind": "laptop", "charging": st.ACLineStatus == 1}
        except Exception:
            pass
        return None
    try:
        root = "/sys/class/power_supply"
        for n in sorted(os.listdir(root)):
            p = os.path.join(root, n)
            if os.path.exists(os.path.join(p, "capacity")) and n.startswith("BAT"):
                lvl = int(open(os.path.join(p, "capacity")).read().strip())
                status = open(os.path.join(p, "status")).read().strip()
                return {"name": "Этот компьютер", "level": lvl, "kind": "laptop",
                        "charging": status in ("Charging", "Full")}
    except Exception:
        pass
    return None


def bt_batteries():
    """[(имя, заряд)] Bluetooth-устройств, о которых Windows знает заряд."""
    if not IS_WIN:
        return []
    try:
        res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                              "-Command", _PS_BATTERY], capture_output=True, timeout=60,
                             creationflags=NO_WINDOW)
        text = res.stdout.decode("utf-8", "replace")
    except Exception:
        return []
    seen, out = set(), []
    for line in text.splitlines():
        parts = line.strip().lstrip("﻿").split("\t")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        try:
            lvl = int(float(parts[1]))
        except ValueError:
            continue
        if not name or not 0 <= lvl <= 100 or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append((name, lvl))
    return out


def read_devices():
    if DEMO:
        return [{"name": "MX Master 3S", "level": 64, "kind": "mouse", "charging": False},
                {"name": "MX Keys", "level": 23, "kind": "keyboard", "charging": False},
                {"name": "WH-1000XM4", "level": 90, "kind": "headphones", "charging": False},
                {"name": "Xbox Wireless Controller", "level": 12, "kind": "gamepad", "charging": False},
                {"name": "Этот компьютер", "level": 81, "kind": "laptop", "charging": True}]
    devs = [{"name": name, "level": lvl, "kind": guess_kind(name), "charging": False}
            for name, lvl in bt_batteries()]
    order = ("mouse", "keyboard", "headphones", "gamepad", "pen", "bluetooth")
    devs.sort(key=lambda d: (order.index(d["kind"]), d["name"].lower()))
    pc = pc_battery()
    if pc:
        devs.append(pc)
    return devs


class BatteryService(QObject):
    updated = Signal()
    _done = Signal(object)

    def __init__(self):
        super().__init__()
        self.devices, self.stamp, self._busy = [], None, False
        self._done.connect(self._finish)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(90 * 1000)
        QTimer.singleShot(300, self.refresh)

    def refresh(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            devs = read_devices()
        except Exception:
            devs = None
        try:
            self._done.emit(devs)      # сигнал доставится в главный поток
        except RuntimeError:
            pass

    def _finish(self, devs):
        self._busy = False
        if devs is not None:
            self.devices, self.stamp = devs, datetime.datetime.now()
            self.updated.emit()


# ---------------------------------------------------------------------------
#  Процессор / память / диск
# ---------------------------------------------------------------------------
class SystemService(QObject):
    updated = Signal()

    def __init__(self):
        super().__init__()
        self.cpu = 0.0
        self.mem = (0.0, 0, 0)          # процент, занято байт, всего байт
        self.disk = (0.0, 0, 0)
        self.disk_name = (os.environ.get("SystemDrive", "C:") + "\\") if IS_WIN else "/"
        self._prev = self._cpu_times()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sample)
        self.timer.start(2000)
        self.sample()

    @staticmethod
    def _cpu_times():
        if IS_WIN:
            idle, kern, user = (ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong())
            if _kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
                return idle.value, kern.value + user.value      # kernel уже включает idle
            return 0, 0
        try:
            vals = [int(x) for x in open("/proc/stat").readline().split()[1:]]
            return vals[3] + vals[4], sum(vals)
        except Exception:
            return 0, 0

    def sample(self):
        if DEMO:
            self.cpu = 23.0 + 10 * math.sin(time.time() / 5)
            self.mem, self.disk = (61.0, 9.8e9, 16e9), (72.0, 345e9, 476e9)
            self.updated.emit()
            return
        cur = self._cpu_times()
        di, dt = cur[0] - self._prev[0], cur[1] - self._prev[1]
        if dt > 0:
            self.cpu = max(0.0, min(100.0, 100.0 * (1.0 - di / dt)))
        self._prev = cur
        try:
            if IS_WIN:
                ms = MEMORYSTATUSEX()
                ms.dwLength = ctypes.sizeof(ms)
                _kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
                total, used = ms.ullTotalPhys, ms.ullTotalPhys - ms.ullAvailPhys
            else:
                info = {}
                for line in open("/proc/meminfo"):
                    k, v = line.split(":", 1)
                    info[k] = int(v.split()[0]) * 1024
                total, used = info["MemTotal"], info["MemTotal"] - info.get("MemAvailable", 0)
            self.mem = (100.0 * used / total if total else 0.0, used, total)
        except Exception:
            pass
        try:
            du = shutil.disk_usage(self.disk_name)
            self.disk = (100.0 * du.used / du.total if du.total else 0.0, du.used, du.total)
        except Exception:
            pass
        self.updated.emit()


def gb(n):
    return ("%.0f" if n >= 100e9 else "%.1f") % (n / 1e9)


# ---------------------------------------------------------------------------
#  Рисование: иконки устройств, кольца
# ---------------------------------------------------------------------------
def draw_icon(p, kind, cx, cy, s, color):
    """Простые линейные иконки размером примерно s x s."""
    p.save()
    pen = QPen(color, max(1.2, s * 0.085))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "mouse":
        w, h = s * 0.56, s * 0.86
        p.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2, w, h), w / 2, w / 2)
        p.drawLine(QPointF(cx, cy - h / 2 + s * 0.12), QPointF(cx, cy - h * 0.12))
    elif kind == "keyboard":
        w, h = s * 0.96, s * 0.6
        p.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2, w, h), s * 0.1, s * 0.1)
        p.setPen(NOPEN)
        p.setBrush(color)
        d = s * 0.075
        for row, n in ((0, 5), (1, 5)):
            for i in range(n):
                x = cx - w / 2 + w * (i + 0.5) / n + (s * 0.04 if row else 0) - (s * 0.02 if row else 0)
                y = cy - h * 0.22 + row * h * 0.24
                p.drawEllipse(QPointF(x, y), d / 1.4, d / 1.4)
        p.drawRoundedRect(QRectF(cx - w * 0.3, cy + h * 0.2, w * 0.6, d * 1.3), d / 2, d / 2)
    elif kind == "headphones":
        r = s * 0.38
        path = QPainterPath()
        path.moveTo(cx - r, cy + s * 0.12)
        path.arcTo(QRectF(cx - r, cy - r - s * 0.05, 2 * r, 2 * r), 180, -180)
        path.lineTo(cx + r, cy + s * 0.12)
        p.drawPath(path)
        p.setBrush(color)
        for sx in (-1, 1):
            p.drawRoundedRect(QRectF(cx + sx * r - s * 0.13, cy + s * 0.02, s * 0.26, s * 0.36),
                              s * 0.08, s * 0.08)
    elif kind == "gamepad":
        w, h = s * 0.98, s * 0.58
        p.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2, w, h), h / 2, h / 2)
        a = s * 0.12
        x0 = cx - w * 0.24
        p.drawLine(QPointF(x0 - a, cy), QPointF(x0 + a, cy))
        p.drawLine(QPointF(x0, cy - a), QPointF(x0, cy + a))
        p.setPen(NOPEN)
        p.setBrush(color)
        for dx, dy in ((0.2, -0.07), (0.3, 0.07)):
            p.drawEllipse(QPointF(cx + w * dx, cy + s * dy * 1.2), s * 0.055, s * 0.055)
    elif kind == "laptop":
        w, h = s * 0.74, s * 0.5
        p.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2 - s * 0.08, w, h), s * 0.06, s * 0.06)
        p.drawLine(QPointF(cx - s * 0.5, cy + h / 2 + s * 0.04), QPointF(cx + s * 0.5, cy + h / 2 + s * 0.04))
    elif kind == "pen":
        p.translate(cx, cy)
        p.rotate(45)
        p.drawRoundedRect(QRectF(-s * 0.1, -s * 0.45, s * 0.2, s * 0.7), s * 0.06, s * 0.06)
        tip = QPainterPath()
        tip.moveTo(-s * 0.1, s * 0.25)
        tip.lineTo(0, s * 0.45)
        tip.lineTo(s * 0.1, s * 0.25)
        p.drawPath(tip)
    else:                                   # руна Bluetooth
        h = s * 0.42
        path = QPainterPath()
        path.moveTo(cx - s * 0.22, cy - h * 0.5)
        path.lineTo(cx + s * 0.2, cy + h * 0.45)
        path.lineTo(cx, cy + h)
        path.lineTo(cx, cy - h)
        path.lineTo(cx + s * 0.2, cy - h * 0.45)
        path.lineTo(cx - s * 0.22, cy + h * 0.5)
        p.drawPath(path)
    p.restore()


def draw_bolt(p, cx, cy, s, color):
    path = QPainterPath()
    path.moveTo(cx + s * 0.08, cy - s * 0.5)
    path.lineTo(cx - s * 0.28, cy + s * 0.06)
    path.lineTo(cx - s * 0.02, cy + s * 0.06)
    path.lineTo(cx - s * 0.08, cy + s * 0.5)
    path.lineTo(cx + s * 0.28, cy - s * 0.06)
    path.lineTo(cx + s * 0.02, cy - s * 0.06)
    path.closeSubpath()
    p.save()
    p.setPen(NOPEN)
    p.setBrush(color)
    p.drawPath(path)
    p.restore()


def draw_ring(p, cx, cy, r, width, frac, color, track):
    p.save()
    rc = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    pen = QPen(track, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rc)
    frac = max(0.0, min(1.0, frac))
    if frac > 0.004:
        pen.setColor(color)
        p.setPen(pen)
        p.drawArc(rc, 90 * 16, -int(round(frac * 360 * 16)))
    p.restore()


def draw_bar(p, rc, frac, color, track):
    p.save()
    p.setPen(NOPEN)
    p.setBrush(track)
    rad = rc.height() / 2
    p.drawRoundedRect(rc, rad, rad)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        p.setBrush(color)
        p.drawRoundedRect(QRectF(rc.x(), rc.y(), max(rc.height(), rc.width() * frac), rc.height()), rad, rad)
    p.restore()


def text(p, rc, s, f, color, align=Qt.AlignmentFlag.AlignCenter, elide=True):
    p.setFont(f)
    p.setPen(color)
    if elide:
        s = p.fontMetrics().elidedText(s, Qt.TextElideMode.ElideRight, int(rc.width()))
    p.drawText(rc, int(align), s)


# ---------------------------------------------------------------------------
#  Базовый виджет: окно без рамки, скруглённая карточка, перетаскивание, меню
# ---------------------------------------------------------------------------
SIZES = {"s": (170, 170), "m": (360, 170), "l": (360, 376), "xl": (552, 376)}
SIZE_NAMES = {"s": "Маленький", "m": "Средний", "l": "Большой", "xl": "Огромный"}
MARGIN = 14             # поля под тень
RADIUS = 22
GRID = 8


class Card(QWidget):
    KIND = ""
    TITLE = ""
    SIZES = ("s", "m", "l")
    DEFAULT_SIZE = "s"

    def __init__(self, mgr, cfg):
        super().__init__(None)
        self.mgr, self.cfg = mgr, cfg
        self._drag = None
        self._moved = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Виджет: " + self.TITLE)
        if cfg.get("size") not in self.SIZES:
            cfg["size"] = self.DEFAULT_SIZE
        self._apply_flags()
        self._apply_size()
        self.move(int(cfg.get("x", 100)), int(cfg.get("y", 100)))

    # ----- окно -----
    @property
    def theme(self):
        return THEMES[self.mgr.cfg.get("theme", "dark")]

    def _apply_flags(self):
        f = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
             | Qt.WindowType.NoDropShadowWindowHint)
        f |= (Qt.WindowType.WindowStaysOnTopHint if self.cfg.get("on_top")
              else Qt.WindowType.WindowStaysOnBottomHint)
        vis = self.isVisible()
        self.setWindowFlags(f)
        if vis:
            self.show()

    def _apply_size(self):
        w, h = SIZES[self.cfg["size"]]
        self.setFixedSize(w + 2 * MARGIN, h + 2 * MARGIN)

    def card_rect(self):
        w, h = SIZES[self.cfg["size"]]
        return QRectF(MARGIN, MARGIN, w, h)

    def set_size(self, size):
        self.cfg["size"] = size
        self._apply_size()
        self.size_changed()
        self.update()
        self.mgr.save()

    def size_changed(self):
        pass

    def keep_on_screen(self):
        scr = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        a = scr.availableGeometry()
        x = min(max(self.x(), a.left() - MARGIN), a.right() - self.width() + MARGIN)
        y = min(max(self.y(), a.top() - MARGIN), a.bottom() - self.height() + MARGIN)
        self.move(x, y)

    def nativeEvent(self, event_type, message):
        # Держим виджет под всеми окнами, как на рабочем столе (кроме режима "поверх всех окон"
        # и момента, когда показан рабочий стол - тогда виджеты поднимаются, см. Manager).
        if IS_WIN and not self.cfg.get("on_top") and not self.mgr.desktop_shown:
            try:
                m = MSG.from_address(int(message))
                if m.message == 0x0046:                       # WM_WINDOWPOSCHANGING
                    wp = WINDOWPOS.from_address(m.lParam)
                    wp.hwndInsertAfter = 1                    # HWND_BOTTOM
                    wp.flags &= ~0x0004                       # снять SWP_NOZORDER
            except Exception:
                pass
        return False, 0

    # ----- рисование -----
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHints(RH)
        r = self.card_rect()
        th = self.theme
        p.setPen(NOPEN)
        for i in range(MARGIN, 0, -2):                       # мягкая тень
            a = int(26 * (1 - i / MARGIN) ** 2) + 1
            p.setBrush(QColor(0, 0, 0, a))
            p.drawRoundedRect(r.adjusted(-i * 0.7, -i * 0.5, i * 0.7, i * 0.9), RADIUS + i * 0.6, RADIUS + i * 0.6)
        path = QPainterPath()
        path.addRoundedRect(r, RADIUS, RADIUS)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, th["bg1"])
        g.setColorAt(1, th["bg2"])
        p.fillPath(path, g)
        p.save()
        p.setClipPath(path)
        try:
            self.paint(p, r, th)
        except Exception:
            traceback.print_exc()
        p.restore()
        p.setPen(QPen(th["line"], 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        p.end()

    def paint(self, p, r, th):
        pass

    # ----- мышь -----
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and not self.mgr.cfg.get("locked"):
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            pos = ev.globalPosition().toPoint() - self._drag
            if (pos - self.pos()).manhattanLength() > 2:
                self._moved = True
            self.move(pos)

    def mouseReleaseEvent(self, ev):
        if self._drag is not None and self._moved:
            x = round((self.x() + MARGIN) / GRID) * GRID - MARGIN       # прилипание к сетке
            y = round((self.y() + MARGIN) / GRID) * GRID - MARGIN
            self.move(x, y)
            self.keep_on_screen()
            self.cfg["x"], self.cfg["y"] = self.x(), self.y()
            self.mgr.save()
        elif self._drag is not None and ev.button() == Qt.MouseButton.LeftButton:
            self.clicked(ev.position())
        self._drag = None

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.activate()

    def clicked(self, pos):
        pass

    def activate(self):
        pass

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        menu.setStyleSheet(self.mgr.menu_css())
        self.extra_menu(menu)
        if not menu.isEmpty():
            menu.addSeparator()
        sm = menu.addMenu("Размер")
        grp = QActionGroup(sm)
        for s in self.SIZES:
            w, h = SIZES[s]
            a = sm.addAction("%s  (%d×%d)" % (SIZE_NAMES[s], w, h))
            a.setCheckable(True)
            a.setChecked(self.cfg["size"] == s)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, s=s: self.set_size(s))
        a = menu.addAction("Поверх всех окон")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("on_top")))
        a.toggled.connect(self.set_on_top)
        menu.addSeparator()
        self.mgr.fill_common_menu(menu)
        menu.addSeparator()
        menu.addAction("Убрать этот виджет").triggered.connect(lambda: self.mgr.remove(self))
        menu.exec(ev.globalPos())

    def extra_menu(self, menu):
        pass

    def set_on_top(self, on):
        self.cfg["on_top"] = bool(on)
        self._apply_flags()
        self.mgr.save()

    def closing(self):
        pass


# ---------------------------------------------------------------------------
#  Виджет "Батарея"
# ---------------------------------------------------------------------------
class BatteryCard(Card):
    KIND = "battery"
    TITLE = "Батарея"
    DEFAULT_SIZE = "m"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        mgr.battery.updated.connect(self.update)

    def devices(self):
        devs = self.mgr.battery.devices
        want = self.cfg.get("device")
        if want:
            devs = sorted(devs, key=lambda d: d["name"] != want)
        return devs

    def paint(self, p, r, th):
        devs = self.devices()
        size = self.cfg["size"]
        if not devs:
            msg = ("Ищу устройства..." if self.mgr.battery.stamp is None
                   else "Нет устройств\nс известным зарядом")
            draw_icon(p, "bluetooth", r.center().x(), r.y() + r.height() * 0.38, 34, th["fg2"])
            text(p, QRectF(r.x() + 10, r.y() + r.height() * 0.55, r.width() - 20, 44), msg,
                 font(13), th["fg2"], elide=False)
            return
        if size == "s":
            d = devs[0]
            cx, cy, rad = r.center().x(), r.y() + 70, 44
            self._ring(p, d, cx, cy, rad, 9, th, 38)
            text(p, QRectF(r.x(), r.y() + 120, r.width(), 26), "%d%%" % d["level"],
                 font(22, QFont.Weight.DemiBold), th["fg"])
            text(p, QRectF(r.x() + 12, r.y() + 144, r.width() - 24, 18), d["name"], font(12), th["fg2"])
        elif size == "m":
            n = min(4, len(devs))
            slot = r.width() / 4
            x0 = r.x() + (r.width() - slot * n) / 2
            for i, d in enumerate(devs[:n]):
                cx = x0 + slot * (i + 0.5)
                self._ring(p, d, cx, r.y() + 66, 34, 7, th, 28)
                text(p, QRectF(cx - slot / 2, r.y() + 110, slot, 22), "%d%%" % d["level"],
                     font(16, QFont.Weight.DemiBold), th["fg"])
                text(p, QRectF(cx - slot / 2 + 4, r.y() + 132, slot - 8, 18), d["name"], font(11), th["fg2"])
        else:
            text(p, QRectF(r.x() + 20, r.y() + 14, r.width() - 40, 24), "Батарея",
                 font(15, QFont.Weight.DemiBold), th["fg"], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if self.mgr.battery.stamp:
                text(p, QRectF(r.x() + 20, r.y() + 14, r.width() - 40, 24),
                     self.mgr.battery.stamp.strftime("%H:%M"), font(12), th["fg2"],
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row = 54
            for i, d in enumerate(devs[:6]):
                y = r.y() + 48 + i * row
                col = level_color(d["level"])
                p.setPen(NOPEN)
                p.setBrush(th["track"])
                p.drawEllipse(QPointF(r.x() + 40, y + row / 2), 19, 19)
                draw_icon(p, d["kind"], r.x() + 40, y + row / 2, 22, th["fg"])
                text(p, QRectF(r.x() + 70, y + 6, r.width() - 150, 20), d["name"], font(13), th["fg"],
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                text(p, QRectF(r.right() - 80, y + 6, 60, 20), "%d%%" % d["level"],
                     font(14, QFont.Weight.DemiBold), th["fg"],
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                draw_bar(p, QRectF(r.x() + 70, y + 31, r.width() - 90, 7), d["level"] / 100.0, col, th["track"])
                if d.get("charging"):
                    draw_bolt(p, r.right() - 96, y + 16, 14, GREEN)

    def _ring(self, p, d, cx, cy, rad, width, th, icon):
        draw_ring(p, cx, cy, rad, width, d["level"] / 100.0, level_color(d["level"]), th["track"])
        draw_icon(p, d["kind"], cx, cy, icon, th["fg"])
        if d.get("charging"):
            p.setPen(NOPEN)
            p.setBrush(self.theme["bg2"])
            p.drawEllipse(QPointF(cx + rad * 0.72, cy - rad * 0.72), rad * 0.28, rad * 0.28)
            draw_bolt(p, cx + rad * 0.72, cy - rad * 0.72, rad * 0.4, GREEN)

    def extra_menu(self, menu):
        menu.addAction("Обновить сейчас").triggered.connect(self.mgr.battery.refresh)
        devs = self.mgr.battery.devices
        if devs:
            sm = menu.addMenu("Главное устройство")
            grp = QActionGroup(sm)
            for name in [None] + [d["name"] for d in devs]:
                a = sm.addAction(name or "Как в списке")
                a.setCheckable(True)
                a.setChecked(self.cfg.get("device") == name)
                grp.addAction(a)
                a.triggered.connect(lambda _=False, n=name: self._pick(n))
        menu.addAction("Открыть настройки Bluetooth").triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("ms-settings:bluetooth")))

    def _pick(self, name):
        self.cfg["device"] = name
        self.mgr.save()
        self.update()

    def activate(self):
        self.mgr.battery.refresh()


# ---------------------------------------------------------------------------
#  Виджет "Фото"
# ---------------------------------------------------------------------------
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".jfif", ".heic"}


def list_images(folder, recursive):
    out = []
    try:
        if recursive:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                out.extend(os.path.join(root, f) for f in files if os.path.splitext(f)[1].lower() in IMG_EXT)
                if len(out) > 50000:
                    break
        else:
            out = [os.path.join(folder, f) for f in os.listdir(folder)
                   if os.path.splitext(f)[1].lower() in IMG_EXT]
    except Exception:
        pass
    out.sort(key=lambda s: s.lower())
    return out


def load_cover(path, w, h):
    """Картинка, обрезанная по центру до размера w x h (как object-fit: cover)."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)                 # поворот по EXIF
    src = rd.size()
    if src.isValid() and src.width() > 0 and src.height() > 0:
        k = max(w / src.width(), h / src.height()) * 1.6     # грузим чуть больше, но не весь снимок
        if k < 1.0:
            rd.setScaledSize(src * k)
    img = rd.read()
    if img.isNull():
        return None
    k = max(w / img.width(), h / img.height())
    img = img.scaled(max(1, math.ceil(img.width() * k)), max(1, math.ceil(img.height() * k)),
                     Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    x, y = (img.width() - w) // 2, (img.height() - h) // 2
    return img.copy(x, y, w, h).convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


class PhotoCard(Card):
    KIND = "photos"
    TITLE = "Фото"
    SIZES = ("s", "m", "l", "xl")
    DEFAULT_SIZE = "l"
    INTERVALS = ((5, "5 секунд"), (10, "10 секунд"), (30, "30 секунд"), (60, "1 минута"),
                 (300, "5 минут"), (900, "15 минут"), (3600, "1 час"))
    FADE = 0.9
    _listed = Signal(object, object)
    _loaded = Signal(object, object, object)

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        cfg.setdefault("interval", 10)
        cfg.setdefault("shuffle", True)
        cfg.setdefault("recursive", True)
        cfg.setdefault("caption", True)
        self.files, self.order, self.pos = [], [], -1
        self.cur = self.prev = None           # (QImage, путь)
        self.fade_t0 = 0.0
        self.token = 0
        self.loading = False
        self._listed.connect(self._on_list)
        self._loaded.connect(self._on_loaded)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next)
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._anim_step)
        self.rescan = QTimer(self)
        self.rescan.timeout.connect(self.scan)
        self.rescan.start(10 * 60 * 1000)
        self.scan()

    # ----- файлы -----
    def scan(self):
        folder = self.cfg.get("folder")
        if not folder or not os.path.isdir(folder):
            if DEMO and not folder:
                return
            self.files = []
            self.update()
            return
        rec = bool(self.cfg.get("recursive"))

        def work():
            files = list_images(folder, rec)
            try:
                self._listed.emit(folder, files)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_list(self, folder, files):
        if folder != self.cfg.get("folder"):
            return
        first = not self.files
        cur = self.order[self.pos] if 0 <= self.pos < len(self.order) else None
        self.files = files
        self._reorder(keep=cur)
        self.update()
        if first and files:
            self.next()
        self._restart_timer()

    def _reorder(self, keep=None):
        self.order = list(self.files)
        if self.cfg.get("shuffle"):
            random.shuffle(self.order)
        self.pos = self.order.index(keep) if keep in self.order else -1

    def _restart_timer(self):
        self.timer.start(int(self.cfg.get("interval", 10)) * 1000)

    def target_px(self):
        r = self.card_rect()
        dpr = self.devicePixelRatioF() or 1.0
        return int(r.width() * dpr), int(r.height() * dpr)

    def next(self, step=1):
        if not self.order or self.loading:
            return
        self.pos = (self.pos + step) % len(self.order)
        if self.pos == 0 and step > 0 and self.cfg.get("shuffle") and len(self.order) > 2:
            last = self.order[-1]
            random.shuffle(self.order)
            if self.order[0] == last:
                self.order.append(self.order.pop(0))
        self._load(self.order[self.pos])

    def _load(self, path, instant=False):
        self.token += 1
        tok, (w, h) = self.token, self.target_px()
        self.loading = True

        def work():
            try:
                img = load_cover(path, w, h)
            except Exception:
                img = None
            try:
                self._loaded.emit(tok, (path, instant), img)
            except RuntimeError:                 # виджет уже закрыт
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, tok, info, img):
        self.loading = False
        if tok != self.token:
            return
        path, instant = info
        if img is None:                        # битый файл - пропускаем
            if path in self.order and len(self.order) > 1:
                i = self.order.index(path)
                self.order.pop(i)
                self.pos = i - 1
                QTimer.singleShot(50, self.next)
            return
        img.setDevicePixelRatio(self.devicePixelRatioF() or 1.0)
        self.prev = None if instant else self.cur
        self.cur = (img, path)
        self.fade_t0 = time.time()
        if self.prev is not None:
            self.anim.start(16)
        self.update()

    def _anim_step(self):
        if time.time() - self.fade_t0 >= self.FADE:
            self.anim.stop()
            self.prev = None
        self.update()

    def size_changed(self):
        if self.cur is not None:
            self._load(self.cur[1], instant=True)

    # ----- рисование -----
    def paint(self, p, r, th):
        if self.cur is None:
            self._paint_empty(p, r, th)
            return
        t = min(1.0, (time.time() - self.fade_t0) / self.FADE) if self.prev else 1.0
        t = t * t * (3 - 2 * t)                # плавное начало и конец
        if self.prev is not None:
            p.drawImage(r.topLeft(), self.prev[0])
        p.setOpacity(t)
        p.drawImage(r.topLeft(), self.cur[0])
        p.setOpacity(1.0)
        if self.cfg.get("caption") and self.cfg["size"] != "s":
            g = QLinearGradient(0, r.bottom() - 70, 0, r.bottom())
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(1, QColor(0, 0, 0, 120))
            p.fillRect(QRectF(r.x(), r.bottom() - 70, r.width(), 70), g)
            path = self.cur[1]
            try:
                dt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
                date = "%d %s %d" % (dt.day, MONTHS_GEN[dt.month - 1], dt.year)
            except Exception:
                date = ""
            name = os.path.basename(os.path.dirname(path))
            text(p, QRectF(r.x() + 18, r.bottom() - 46, r.width() - 36, 20), name,
                 font(14, QFont.Weight.DemiBold), QColor(255, 255, 255),
                 Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            text(p, QRectF(r.x() + 18, r.bottom() - 27, r.width() - 36, 18), date,
                 font(12), QColor(255, 255, 255, 200), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def _paint_empty(self, p, r, th):
        cx, cy = r.center().x(), r.center().y() - 16
        p.save()
        pen = QPen(th["fg2"], 2.2)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(cx - 26, cy - 20, 52, 40), 7, 7)
        mount = QPainterPath()
        mount.moveTo(cx - 20, cy + 14)
        mount.lineTo(cx - 6, cy - 2)
        mount.lineTo(cx + 4, cy + 8)
        mount.lineTo(cx + 10, cy + 2)
        mount.lineTo(cx + 20, cy + 14)
        p.drawPath(mount)
        p.drawEllipse(QPointF(cx + 11, cy - 9), 4, 4)
        p.restore()
        folder = self.cfg.get("folder")
        msg = ("Нет фотографий в папке" if folder and self.files == [] and os.path.isdir(folder)
               else "Нажми, чтобы выбрать\nпапку с фотографиями")
        text(p, QRectF(r.x() + 10, cy + 30, r.width() - 20, 40), msg, font(13), th["fg2"], elide=False)

    # ----- действия -----
    def clicked(self, pos):
        if self.cur is None:
            self.choose_folder()

    def activate(self):
        if self.cur is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.cur[1]))
        else:
            self.choose_folder()

    def choose_folder(self):
        start = self.cfg.get("folder") or os.path.join(os.path.expanduser("~"), "Pictures")
        d = QFileDialog.getExistingDirectory(None, "Папка с фотографиями", start)
        if d:
            self.cfg["folder"] = os.path.normpath(d)
            self.files, self.order, self.pos = [], [], -1
            self.cur = self.prev = None
            self.mgr.save()
            self.update()
            self.scan()

    def extra_menu(self, menu):
        menu.addAction("Выбрать папку...").triggered.connect(self.choose_folder)
        if self.cur is not None:
            menu.addAction("Следующее фото").triggered.connect(lambda: (self.next(), self._restart_timer()))
            menu.addAction("Предыдущее фото").triggered.connect(lambda: (self.next(-1), self._restart_timer()))
            menu.addAction("Открыть фото").triggered.connect(self.activate)
            menu.addAction("Показать в папке").triggered.connect(self.reveal)
        sm = menu.addMenu("Менять каждые")
        grp = QActionGroup(sm)
        for sec, label in self.INTERVALS:
            a = sm.addAction(label)
            a.setCheckable(True)
            a.setChecked(int(self.cfg.get("interval", 10)) == sec)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, s=sec: self._set("interval", s))
        for key, label in (("shuffle", "Случайный порядок"), ("recursive", "Включая подпапки"),
                           ("caption", "Подпись (папка и дата)")):
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg.get(key)))
            a.toggled.connect(lambda v, k=key: self._set(k, bool(v)))

    def reveal(self):
        if self.cur is None:
            return
        if IS_WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.cur[1])], creationflags=NO_WINDOW)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.cur[1])))

    def _set(self, key, val):
        self.cfg[key] = val
        self.mgr.save()
        if key == "interval":
            self._restart_timer()
        elif key == "shuffle":
            self._reorder(keep=self.cur[1] if self.cur else None)
        elif key == "recursive":
            self.scan()
        self.update()

    def closing(self):
        self.timer.stop()
        self.anim.stop()
        self.rescan.stop()


# ---------------------------------------------------------------------------
#  Виджет "Часы"
# ---------------------------------------------------------------------------
class ClockCard(Card):
    KIND = "clock"
    TITLE = "Часы и календарь"
    DEFAULT_SIZE = "m"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)

    def paint(self, p, r, th):
        now = datetime.datetime.now()
        size = self.cfg["size"]
        if size == "s":
            self._analog(p, r.center().x(), r.center().y(), 66, now, th)
        elif size == "m":
            left = QRectF(r.x() + 20, r.y() + 18, r.width() * 0.48 - 20, r.height() - 36)
            text(p, QRectF(left.x(), left.y(), left.width(), 18), WEEKDAYS[now.weekday()].upper(),
                 font(12, QFont.Weight.DemiBold), ACCENT, Qt.AlignmentFlag.AlignLeft)
            text(p, QRectF(left.x(), left.y() + 16, left.width(), 60), str(now.day),
                 font(48, QFont.Weight.Light), th["fg"], Qt.AlignmentFlag.AlignLeft)
            text(p, QRectF(left.x(), left.y() + 82, left.width(), 46), now.strftime("%H:%M"),
                 font(34, QFont.Weight.DemiBold), th["fg"], Qt.AlignmentFlag.AlignLeft)
            text(p, QRectF(left.x(), left.y() + 120, left.width(), 18),
                 "%s %d" % (MONTHS_GEN[now.month - 1], now.year), font(12), th["fg2"], Qt.AlignmentFlag.AlignLeft)
            self._calendar(p, QRectF(r.x() + r.width() * 0.48, r.y() + 14, r.width() * 0.52 - 16,
                                     r.height() - 26), now, th, 11)
        else:
            self._analog(p, r.x() + 88, r.y() + 90, 66, now, th)
            tx = r.x() + 176
            text(p, QRectF(tx, r.y() + 36, r.right() - tx - 18, 46), now.strftime("%H:%M"),
                 font(38, QFont.Weight.DemiBold), th["fg"], Qt.AlignmentFlag.AlignLeft)
            text(p, QRectF(tx, r.y() + 86, r.right() - tx - 18, 20), WEEKDAYS[now.weekday()],
                 font(14, QFont.Weight.DemiBold), ACCENT, Qt.AlignmentFlag.AlignLeft)
            text(p, QRectF(tx, r.y() + 106, r.right() - tx - 18, 20),
                 "%d %s %d" % (now.day, MONTHS_GEN[now.month - 1], now.year), font(13), th["fg2"],
                 Qt.AlignmentFlag.AlignLeft)
            p.setPen(QPen(th["line"], 1))
            p.drawLine(QPointF(r.x() + 20, r.y() + 178), QPointF(r.right() - 20, r.y() + 178))
            self._calendar(p, QRectF(r.x() + 20, r.y() + 188, r.width() - 40, r.height() - 202), now, th, 13)

    def _analog(self, p, cx, cy, rad, now, th):
        p.save()
        light = self.mgr.cfg.get("theme") == "light"
        p.setPen(NOPEN)
        p.setBrush(QColor(255, 255, 255) if not light else QColor(30, 30, 32))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        ink = QColor(20, 20, 22) if not light else QColor(245, 245, 247)
        p.setFont(font(rad * 0.24, QFont.Weight.DemiBold))
        p.setPen(ink)
        for h in range(1, 13):
            a = math.radians(h * 30)
            x, y = cx + math.sin(a) * rad * 0.76, cy - math.cos(a) * rad * 0.76
            p.drawText(QRectF(x - 14, y - 12, 28, 24), int(Qt.AlignmentFlag.AlignCenter), str(h))
        for m in range(60):
            if m % 5:
                a = math.radians(m * 6)
                p.setPen(QPen(QColor(ink.red(), ink.green(), ink.blue(), 90), 1))
                p.drawLine(QPointF(cx + math.sin(a) * rad * 0.9, cy - math.cos(a) * rad * 0.9),
                           QPointF(cx + math.sin(a) * rad * 0.95, cy - math.cos(a) * rad * 0.95))
        sec = now.second
        mins = now.minute + sec / 60.0
        hrs = (now.hour % 12) + mins / 60.0

        def hand(angle, length, width, color, tail=0.0):
            a = math.radians(angle)
            pen = QPen(color, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(cx - math.sin(a) * rad * tail, cy + math.cos(a) * rad * tail),
                       QPointF(cx + math.sin(a) * rad * length, cy - math.cos(a) * rad * length))

        hand(hrs * 30, 0.5, rad * 0.075, ink)
        hand(mins * 6, 0.78, rad * 0.055, ink)
        hand(sec * 6, 0.86, max(1.2, rad * 0.022), ACCENT, tail=0.16)
        p.setPen(NOPEN)
        p.setBrush(ACCENT)
        p.drawEllipse(QPointF(cx, cy), rad * 0.055, rad * 0.055)
        p.restore()

    def _calendar(self, p, rc, now, th, fs):
        text(p, QRectF(rc.x(), rc.y(), rc.width(), fs * 1.8), MONTHS[now.month - 1].upper(),
             font(fs, QFont.Weight.DemiBold), ACCENT, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        weeks = calendar.Calendar(0).monthdayscalendar(now.year, now.month)
        top = rc.y() + fs * 2.0
        cw = rc.width() / 7
        ch = (rc.bottom() - top) / (len(weeks) + 1)
        for i, wd in enumerate(WD_SHORT):
            text(p, QRectF(rc.x() + i * cw, top, cw, ch), wd, font(fs * 0.85, QFont.Weight.DemiBold),
                 th["fg2"] if i < 5 else QColor(255, 69, 58, 170))
        for wi, week in enumerate(weeks):
            for i, day in enumerate(week):
                if not day:
                    continue
                cell = QRectF(rc.x() + i * cw, top + (wi + 1) * ch, cw, ch)
                col = th["fg"] if i < 5 else QColor(255, 105, 97)
                if day == now.day:
                    d = min(cw, ch) * 0.92
                    p.setPen(NOPEN)
                    p.setBrush(RED)
                    p.drawEllipse(cell.center(), d / 2, d / 2)
                    col = QColor(255, 255, 255)
                text(p, cell, str(day), font(fs, QFont.Weight.DemiBold if day == now.day else QFont.Weight.Normal), col)


# ---------------------------------------------------------------------------
#  Виджет "Система"
# ---------------------------------------------------------------------------
class SystemCard(Card):
    KIND = "system"
    TITLE = "Система"
    DEFAULT_SIZE = "s"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.hist = []
        mgr.system.updated.connect(self._tick)

    def _tick(self):
        self.hist = (self.hist + [self.mgr.system.cpu])[-60:]
        self.update()

    def items(self):
        s = self.mgr.system
        return [("ЦП", s.cpu, "%d%%" % s.cpu, BLUE),
                ("ОЗУ", s.mem[0], "%s/%s ГБ" % (gb(s.mem[1]), gb(s.mem[2])), QColor("#BF5AF2")),
                ("Диск " + s.disk_name.rstrip("\\"), s.disk[0], "своб. %s ГБ" % gb(s.disk[2] - s.disk[1]),
                 QColor("#FF9F0A"))]

    def paint(self, p, r, th):
        items = self.items()
        size = self.cfg["size"]
        if size == "s":
            pos = ((0.3, 0.32), (0.7, 0.32), (0.5, 0.72))
            for (fx, fy), (name, val, _det, col) in zip(pos, items):
                cx, cy = r.x() + r.width() * fx, r.y() + r.height() * fy
                draw_ring(p, cx, cy, 30, 6, val / 100.0, col, th["track"])
                text(p, QRectF(cx - 30, cy - 15, 60, 18), "%d%%" % val, font(13, QFont.Weight.DemiBold), th["fg"])
                text(p, QRectF(cx - 30, cy + 2, 60, 14), name.split()[0], font(10), th["fg2"])
        elif size == "m":
            slot = r.width() / 3
            for i, (name, val, det, col) in enumerate(items):
                cx = r.x() + slot * (i + 0.5)
                draw_ring(p, cx, r.y() + 66, 36, 7, val / 100.0, col, th["track"])
                text(p, QRectF(cx - 36, r.y() + 54, 72, 24), "%d%%" % val, font(17, QFont.Weight.DemiBold), th["fg"])
                text(p, QRectF(cx - slot / 2, r.y() + 112, slot, 18), name, font(12, QFont.Weight.DemiBold), th["fg"])
                text(p, QRectF(cx - slot / 2 + 4, r.y() + 130, slot - 8, 16), det, font(11), th["fg2"])
        else:
            text(p, QRectF(r.x() + 20, r.y() + 14, r.width() - 40, 24), "Система",
                 font(15, QFont.Weight.DemiBold), th["fg"], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            gr = QRectF(r.x() + 20, r.y() + 48, r.width() - 40, 110)       # график ЦП
            p.setPen(QPen(th["line"], 1))
            for k in (0.25, 0.5, 0.75):
                p.drawLine(QPointF(gr.x(), gr.y() + gr.height() * k), QPointF(gr.right(), gr.y() + gr.height() * k))
            if len(self.hist) > 1:
                path, n = QPainterPath(), 60
                pts = [QPointF(gr.right() - (len(self.hist) - 1 - i) * gr.width() / (n - 1),
                               gr.bottom() - gr.height() * v / 100.0) for i, v in enumerate(self.hist)]
                path.moveTo(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                fill = QPainterPath(path)
                fill.lineTo(pts[-1].x(), gr.bottom())
                fill.lineTo(pts[0].x(), gr.bottom())
                g = QLinearGradient(0, gr.y(), 0, gr.bottom())
                g.setColorAt(0, QColor(10, 132, 255, 110))
                g.setColorAt(1, QColor(10, 132, 255, 0))
                p.fillPath(fill, g)
                p.setPen(QPen(BLUE, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            for i, (name, val, det, col) in enumerate(items):
                y = r.y() + 180 + i * 62
                text(p, QRectF(r.x() + 20, y, 160, 20), name, font(13, QFont.Weight.DemiBold), th["fg"],
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                text(p, QRectF(r.x() + 20, y, r.width() - 40, 20), "%d%%" % val, font(14, QFont.Weight.DemiBold),
                     th["fg"], Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                draw_bar(p, QRectF(r.x() + 20, y + 26, r.width() - 40, 8), val / 100.0, col, th["track"])
                text(p, QRectF(r.x() + 20, y + 38, r.width() - 40, 16), det, font(11), th["fg2"],
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def activate(self):
        if IS_WIN:
            subprocess.Popen(["taskmgr"], creationflags=NO_WINDOW)


KINDS = {c.KIND: c for c in (BatteryCard, PhotoCard, ClockCard, SystemCard)}


# ---------------------------------------------------------------------------
#  Автозапуск, один экземпляр
# ---------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    if FROZEN:
        return '"%s"' % sys.executable
    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pw):
        exe = pw
    return '"%s" "%s"' % (exe, os.path.abspath(__file__))


def autostart_get():
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except Exception:
        return False


def autostart_set(on):
    if not IS_WIN:
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass


_MUTEX = None


def single_instance():
    global _MUTEX
    if not IS_WIN:
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
        _MUTEX = k32.CreateMutexW(None, False, "Local\\SnowWidgets_v1")
        if ctypes.get_last_error() == 183:
            return False
    except Exception:
        pass
    return True


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHints(RH)
    p.setPen(NOPEN)
    for (x, y), c in zip(((4, 4), (34, 4), (4, 34), (34, 34)),
                         ("#0A84FF", "#30D158", "#FF9F0A", "#BF5AF2")):
        p.setBrush(QColor(c))
        p.drawRoundedRect(QRectF(x, y, 26, 26), 7, 7)
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------------------
#  Управление виджетами
# ---------------------------------------------------------------------------
class Manager(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cards = []
        self.tray = None
        self.desktop_shown = False
        self.low_alerted = set()
        self.cfg = self.load()
        self.battery = BatteryService()
        self.system = SystemService()
        self.battery.updated.connect(self.check_low)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._write)
        first = not self.cfg.get("widgets")
        if first:
            self.cfg["widgets"] = self.default_layout()
        for wc in list(self.cfg["widgets"]):
            self._create(wc)
        if first:
            self.save()
        if IS_WIN:                                # показ рабочего стола (Win+D, "Свернуть всё")
            self.desk_timer = QTimer(self)
            self.desk_timer.timeout.connect(self.watch_desktop)
            self.desk_timer.start(400)

    # ----- конфиг -----
    def load(self):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("theme", "dark")
                data.setdefault("widgets", [])
                if data["theme"] not in THEMES:
                    data["theme"] = "dark"
                return data
        except Exception:
            pass
        return {"theme": "dark", "locked": False, "widgets": []}

    def save(self):
        self._save_timer.start(500)

    def _write(self):
        try:
            tmp = CONFIG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, CONFIG_FILE)
        except Exception:
            pass

    def default_layout(self):
        a = QApplication.primaryScreen().availableGeometry()
        right = a.right() - 24 - MARGIN
        x_m = right - SIZES["m"][0] + 1
        y = a.top() + 24 - MARGIN
        out = []
        for kind, size in (("clock", "m"), ("battery", "m"), ("photos", "l")):
            out.append({"id": "%s-%d" % (kind, len(out)), "kind": kind, "size": size,
                        "x": x_m, "y": y})
            y += SIZES[size][1] + 16
        return out

    def _create(self, wc):
        cls = KINDS.get(wc.get("kind"))
        if cls is None:
            return None
        card = cls(self, wc)
        card.show()
        card.keep_on_screen()
        self.cards.append(card)
        return card

    def add(self, kind):
        a = QApplication.primaryScreen().availableGeometry()
        cls = KINDS[kind]
        w, h = SIZES[cls.DEFAULT_SIZE]
        n = len(self.cards)
        wc = {"id": "%s-%d" % (kind, int(time.time() * 1000) % 10 ** 8), "kind": kind,
              "size": cls.DEFAULT_SIZE,
              "x": a.center().x() - w // 2 - MARGIN + (n % 5) * 24,
              "y": a.center().y() - h // 2 - MARGIN + (n % 5) * 24}
        self.cfg["widgets"].append(wc)
        card = self._create(wc)
        self.save()
        if kind == "photos" and card is not None:
            QTimer.singleShot(200, card.choose_folder)

    def remove(self, card):
        card.closing()
        if card.cfg in self.cfg["widgets"]:
            self.cfg["widgets"].remove(card.cfg)
        if card in self.cards:
            self.cards.remove(card)
        card.close()
        card.deleteLater()
        self.save()

    def set_theme(self, name):
        self.cfg["theme"] = name
        for c in self.cards:
            c.update()
        self.save()

    def set_locked(self, on):
        self.cfg["locked"] = bool(on)
        self.save()

    def menu_css(self):
        if self.cfg.get("theme") == "light":
            return ""
        return ("QMenu { background:#2a2b30; color:#f2f2f4; border:1px solid #3a3b42; padding:4px; }"
                "QMenu::item { padding:5px 22px 5px 24px; border-radius:4px; }"
                "QMenu::item:selected { background:#0A84FF; }"
                "QMenu::separator { height:1px; background:#3a3b42; margin:4px 6px; }")

    def fill_common_menu(self, menu):
        add = menu.addMenu("Добавить виджет")
        for kind, cls in KINDS.items():
            add.addAction(cls.TITLE).triggered.connect(lambda _=False, k=kind: self.add(k))
        th = menu.addMenu("Оформление")
        grp = QActionGroup(th)
        for key, label in (("dark", "Тёмное"), ("light", "Светлое")):
            a = th.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg.get("theme") == key)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_theme(k))
        a = menu.addAction("Закрепить виджеты (не двигать)")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("locked")))
        a.toggled.connect(self.set_locked)

    # ----- низкий заряд -----
    def check_low(self):
        for d in self.battery.devices:
            if d["kind"] == "laptop":
                continue
            key = d["name"]
            if d["level"] <= 15 and key not in self.low_alerted:
                self.low_alerted.add(key)
                if self.tray is not None:
                    self.tray.showMessage("Низкий заряд", "%s: осталось %d%%" % (d["name"], d["level"]),
                                          QSystemTrayIcon.MessageIcon.Warning, 8000)
            elif d["level"] >= 25:
                self.low_alerted.discard(key)

    # ----- Win+D: при показе рабочего стола поднимаем виджеты над ним -----
    def watch_desktop(self):
        try:
            fg = _user32.GetForegroundWindow()
            if not fg:
                return
            pid = wt.DWORD()
            _user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
            if pid.value == os.getpid():
                return                                  # фокус на нашем виджете - ничего не меняем
            buf = ctypes.create_unicode_buffer(64)
            _user32.GetClassNameW(fg, buf, 64)
            desk = buf.value in ("Progman", "WorkerW")
        except Exception:
            return
        if desk == self.desktop_shown:
            return
        self.desktop_shown = desk
        flags = 0x0001 | 0x0002 | 0x0010               # NOSIZE | NOMOVE | NOACTIVATE
        for c in self.cards:
            if c.cfg.get("on_top"):
                continue
            h = ctypes.c_void_p(int(c.winId()))
            if desk:
                _user32.SetWindowPos(h, ctypes.c_void_p(-1), 0, 0, 0, 0, flags)    # HWND_TOPMOST
            else:
                _user32.SetWindowPos(h, ctypes.c_void_p(-2), 0, 0, 0, 0, flags)    # HWND_NOTOPMOST
                _user32.SetWindowPos(h, ctypes.c_void_p(1), 0, 0, 0, 0, flags)     # HWND_BOTTOM

    # ----- трей -----
    def build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(make_icon(), self)
        tray.setToolTip("Виджеты рабочего стола")
        menu = QMenu()

        def rebuild():
            menu.clear()
            menu.setStyleSheet(self.menu_css())
            self.fill_common_menu(menu)
            menu.addAction("Обновить заряд устройств").triggered.connect(self.battery.refresh)
            menu.addSeparator()
            if IS_WIN:
                a = menu.addAction("Запускать вместе с Windows")
                a.setCheckable(True)
                a.setChecked(autostart_get())
                a.toggled.connect(lambda v: autostart_set(bool(v)))
            menu.addAction("Папка с настройками").triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR)))
            menu.addSeparator()
            menu.addAction("Выход").triggered.connect(self.quit)

        rebuild()
        menu.aboutToShow.connect(rebuild)
        tray.setContextMenu(menu)
        tray.show()
        self.tray, self._menu = tray, menu

    def quit(self):
        self._save_timer.stop()
        self._write()
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


def main():
    if not single_instance():
        msgbox("Виджеты уже запущены - ищи значок в трее (возле часов).")
        return 0
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(make_icon())
    mgr = Manager(app)
    mgr.build_tray()
    app.aboutToQuit.connect(mgr._write)
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        try:
            with open(os.path.join(DATA_DIR, "widgets_error.log"), "w", encoding="utf-8") as fh:
                fh.write(err)
        except Exception:
            pass
        msgbox("Виджеты упали с ошибкой. Подробности в widgets_error.log (" + DATA_DIR + ").\n\n" + err[-600:],
               "Виджеты - ошибка", 0x10)
