# -*- coding: utf-8 -*-
"""Виджеты рабочего стола для Windows 10/11 в стиле macOS.

  * Погода      - температура, прогноз по часам и на неделю, живой фон (снег, дождь, солнце).
  * Батарея     - заряд мыши / клавиатуры / наушников: Bluetooth и радио-приёмники Logitech
                  (Unifying, Bolt, Lightspeed), а также батарея ноутбука.
  * Фото        - слайд-шоу фотографий из папки (например, из "Загрузки\\Telegram Desktop").
  * Календарь   - листается стрелками и колёсиком мыши, праздники РФ.
  * Часы        - аналоговые часы с плавной секундной стрелкой.
  * Система     - загрузка процессора, памяти и диска.

Запуск: двойной клик по widgets.pyw (нужен Python 3.9+, PySide6 поставится сам).
Управление - значок в трее (возле часов): добавить виджет, тема, закрепить, автозапуск, выход.
Виджет: перетаскивай левой кнопкой, правая кнопка - размер и настройки, двойной клик - действие.
Данные: %APPDATA%\\SnowWidgets\\widgets.json
"""
import base64
import calendar
import ctypes
import datetime
import importlib
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
import urllib.error
import urllib.parse
import urllib.request

IS_WIN = sys.platform.startswith("win")
APP_NAME = "SnowWidgets"
APP_VERSION = "1.4"
FROZEN = bool(getattr(sys, "frozen", False))
HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = "--demo" in sys.argv            # тестовые данные вместо настоящих устройств и погоды

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
               "    pip install PySide6 hidapi\n"
               "Потом запусти widgets.pyw снова.", "Виджеты - ошибка", 0x10)
        sys.exit(1)
    subprocess.Popen([sys.executable, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit(0)


ensure_deps()

from PySide6.QtCore import (QObject, QPointF, QRectF, QStandardPaths, Qt,  # noqa: E402
                            QTimer, QUrl, Signal)
from PySide6.QtGui import (QActionGroup, QColor, QDesktopServices, QFont,  # noqa: E402
                           QIcon, QImage, QImageReader, QLinearGradient, QPainter,
                           QPainterPath, QPalette, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QInputDialog, QLineEdit,  # noqa: E402
                               QMenu, QSystemTrayIcon, QTextBrowser, QWidget)

RH = (QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
      | QPainter.RenderHint.TextAntialiasing)
FONT = "Segoe UI" if IS_WIN else "Sans Serif"
NOPEN = Qt.PenStyle.NoPen
AL, AR, AC = Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignCenter
AVC = Qt.AlignmentFlag.AlignVCenter
SEMI, LIGHT, NORMAL = QFont.Weight.DemiBold, QFont.Weight.Light, QFont.Weight.Normal

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
          "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
WD_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
HOLIDAYS = {(1, 1): "Новый год", (1, 2): "Новогодние каникулы", (1, 3): "Новогодние каникулы",
            (1, 4): "Новогодние каникулы", (1, 5): "Новогодние каникулы", (1, 6): "Новогодние каникулы",
            (1, 7): "Рождество Христово", (1, 8): "Новогодние каникулы",
            (2, 23): "День защитника Отечества", (3, 8): "Международный женский день",
            (5, 1): "Праздник Весны и Труда", (5, 9): "День Победы", (6, 12): "День России",
            (11, 4): "День народного единства"}

GREEN, YELLOW, RED, BLUE = QColor("#30D158"), QColor("#FFD60A"), QColor("#FF453A"), QColor("#0A84FF")
ACCENT = QColor("#FF9F0A")
WHITE = QColor(255, 255, 255)


def _style(name, mode="grad", **kw):
    st = {"name": name, "mode": mode, "light": False, "mono": False,
          "bg1": QColor(44, 46, 52, 238), "bg2": QColor(28, 29, 33, 238),
          "fg": QColor(245, 245, 247), "fg2": QColor(160, 162, 170),
          "track": QColor(255, 255, 255, 38), "line": QColor(255, 255, 255, 26), "btn": QColor(255, 255, 255, 30),
          "accent": ACCENT, "weekend": QColor(255, 105, 97), "today_bg": RED, "today_fg": WHITE,
          "pill": QColor(255, 69, 58, 210), "face": WHITE, "ink": QColor(20, 20, 22), "hand": ACCENT}
    st.update(kw)
    return st


DARK_INK = QColor(245, 245, 247)
STYLES = {
    "dark": _style("Тёмный"),
    "light": _style("Светлый", light=True, bg1=QColor(252, 252, 253, 242), bg2=QColor(236, 237, 241, 242),
                    fg=QColor(28, 28, 30), fg2=QColor(120, 120, 128), track=QColor(0, 0, 0, 30),
                    line=QColor(0, 0, 0, 22), btn=QColor(0, 0, 0, 18), face=QColor(30, 30, 32), ink=DARK_INK),
    "glass": _style("Стекло", "glass", tint=QColor(16, 18, 26, 105), fg=WHITE, fg2=QColor(255, 255, 255, 185),
                    track=QColor(255, 255, 255, 50), line=QColor(255, 255, 255, 70), btn=QColor(255, 255, 255, 45)),
    "frost": _style("Матовое стекло", "glass", light=True, tint=QColor(255, 255, 255, 160),
                    fg=QColor(18, 18, 22), fg2=QColor(50, 50, 62, 200), track=QColor(0, 0, 0, 35),
                    line=QColor(255, 255, 255, 150), btn=QColor(0, 0, 0, 22), face=QColor(30, 30, 32), ink=DARK_INK),
    "neon": _style("Неон", "neon", bg1=QColor(18, 14, 34, 242), bg2=QColor(7, 7, 16, 242),
                   fg=QColor(240, 240, 255), fg2=QColor(150, 150, 195), track=QColor(255, 255, 255, 24),
                   line=QColor(0, 0, 0, 0), btn=QColor(255, 255, 255, 26), accent=QColor("#00E5FF"),
                   weekend=QColor("#FF4FD8"), today_bg=QColor("#FF2D95"), pill=QColor("#FF2D95"),
                   face=QColor(16, 14, 30), ink=QColor("#E6E6FF"), hand=QColor("#00E5FF"),
                   glow1=QColor("#00E5FF"), glow2=QColor("#FF2D95")),
    "color": _style("Яркий", "color", mono=True, fg=WHITE, fg2=QColor(255, 255, 255, 205),
                    track=QColor(255, 255, 255, 64), line=QColor(255, 255, 255, 45), btn=QColor(255, 255, 255, 50),
                    accent=WHITE, weekend=QColor(255, 255, 255, 235), today_bg=WHITE, today_fg=None,
                    pill=QColor(255, 255, 255, 80)),
    "winter": _style("Зимний", "winter", bg1=QColor(40, 76, 126, 242), bg2=QColor(15, 30, 60, 242),
                     fg=QColor(240, 247, 255), fg2=QColor(172, 198, 228), track=QColor(255, 255, 255, 42),
                     line=QColor(255, 255, 255, 40), btn=QColor(255, 255, 255, 36), accent=QColor("#8FD3FF"),
                     weekend=QColor("#FF9A9A"), hand=QColor("#E04848")),
}
KIND_COLORS = {"battery": ("#2BC48A", "#0B8C8F"), "calendar": ("#FF6A5C", "#F29A3E"),
               "clock": ("#5B5BD6", "#A35BE0"), "system": ("#2D7FF9", "#2EC0EE"),
               "photos": ("#3A3A44", "#1E1E26"), "weather": ("#3B7BC4", "#83AFD9"),
               "music": ("#F2B705", "#E06A1B"), "claude": ("#D97757", "#A8553A"),
               "discord": ("#5865F2", "#4248C9"), "notify": ("#5865F2", "#4248C9")}
OPACITY_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)


def font(px, weight=NORMAL):
    f = QFont(FONT)
    f.setPixelSize(max(1, int(px)))
    f.setWeight(weight)
    return f


def level_color(v):
    return RED if v <= 15 else (YELLOW if v <= 30 else GREEN)


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else (hi if v > hi else v)


def ease_out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    t = clamp(t)
    c1 = 1.4
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def plural(n, one, few, many):
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def deg(t):
    t = int(round(t))
    return ("−%d°" % -t) if t < 0 else ("%d°" % t)


# ---------------------------------------------------------------------------
#  Батарея устройств: Bluetooth (Windows), радио-приёмники Logitech (HID++), ноутбук
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
    ("mouse", ("mouse", "мыш", "mx master", "mx anywhere", "pebble", "trackball", "m720", "m590", "g pro",
               "g502", "g305", "g703", "g903", "lift", "m575")),
    ("keyboard", ("keyboard", "клавиат", "keys", "k380", "k810", "craft")),
    ("headphones", ("head", "наушн", "buds", "airpods", "earbuds", "wh-", "wf-", "jbl", "bose",
                    "airdots", "freebuds", "гарнит", "hands-free")),
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
        text_out = res.stdout.decode("utf-8", "replace")
    except Exception:
        return []
    seen, out = set(), []
    for line in text_out.splitlines():
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


# ----- Logitech HID++ 2.0 (мыши и клавиатуры на радио-приёмниках Unifying / Bolt / Lightspeed) -----
LOGI_VID = 0x046D
_VOLT_CURVE = ((4186, 100), (4067, 90), (3989, 80), (3922, 70), (3859, 60), (3811, 50), (3778, 40),
               (3751, 30), (3717, 20), (3671, 10), (3646, 5), (3579, 2), (3500, 0))
_LOGI_TYPES = {0: "keyboard", 2: "keyboard", 3: "mouse", 4: "mouse", 5: "mouse", 8: "headphones",
               0x0B: "gamepad", 0x0C: "gamepad"}
_HID_STATE = {"tried_install": False, "mod": None}


def volt_to_pct(mv):
    if mv >= _VOLT_CURVE[0][0]:
        return 100
    for (v1, p1), (v2, p2) in zip(_VOLT_CURVE, _VOLT_CURVE[1:]):
        if mv >= v2:
            return int(round(p2 + (p1 - p2) * (mv - v2) / float(v1 - v2)))
    return 0


def _hid_module():
    """Модуль hidapi; при запуске из .pyw ставим его сам один раз, если его нет."""
    if _HID_STATE["mod"] is not None:
        return _HID_STATE["mod"]
    try:
        import hid
        _HID_STATE["mod"] = hid
        return hid
    except ImportError:
        pass
    if IS_WIN and not FROZEN and not _HID_STATE["tried_install"]:
        _HID_STATE["tried_install"] = True
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "hidapi"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, timeout=300)
            importlib.invalidate_caches()
            import hid
            _HID_STATE["mod"] = hid
            return hid
        except Exception:
            pass
    return None


class HidPP:
    """Минимальный клиент протокола Logitech HID++ 2.0 поверх одного HID-интерфейса."""
    SW = 0x0B          # наш "software id", чтобы отличать ответы от уведомлений

    def __init__(self, dev):
        self.dev = dev

    def request(self, idx, feat, fn, params=b"", timeout=0.5):
        fs = ((fn & 0x0F) << 4) | self.SW
        msg = bytes([0x11, idx & 0xFF, feat & 0xFF, fs]) + bytes(params)
        msg += bytes(20 - len(msg))
        try:
            self.dev.write(list(msg))
        except Exception:
            return None
        end = time.time() + timeout
        while True:
            left = int((end - time.time()) * 1000)
            if left <= 0:
                return None
            try:
                data = self.dev.read(20, left)
            except Exception:
                return None
            if not data or len(data) < 5 or data[1] != (idx & 0xFF):
                continue
            if data[0] == 0x11:
                if data[2] == 0xFF and data[3] == (feat & 0xFF) and data[4] == fs:
                    return None                                  # ошибка HID++ 2.0
                if data[2] == (feat & 0xFF) and data[3] == fs:
                    return bytes(data[4:])
            elif data[0] == 0x10 and data[2] == 0x8F:            # ошибка HID++ 1.0 (устройство выключено)
                return None

    def protocol(self, idx, timeout=0.5):
        r = self.request(idx, 0x00, 1, b"\x00\x00\x5A", timeout)
        return (r[0], r[1]) if r else None

    def feature(self, idx, fid):
        r = self.request(idx, 0x00, 0, bytes([fid >> 8, fid & 0xFF]))
        return r[0] if r and r[0] else None

    def name(self, idx):
        fi = self.feature(idx, 0x0005)
        if not fi:
            return None, None
        r = self.request(idx, fi, 0)
        if not r:
            return None, None
        n, name = r[0], b""
        while len(name) < n:
            c = self.request(idx, fi, 1, bytes([len(name)]))
            if not c:
                break
            name += c[:n - len(name)]
        t = self.request(idx, fi, 2)
        kind = _LOGI_TYPES.get(t[0]) if t else None
        return name.split(b"\x00")[0].decode("utf-8", "replace").strip() or None, kind

    def battery(self, idx):
        """(процент, заряжается) или None."""
        fi = self.feature(idx, 0x1004)                     # UNIFIED_BATTERY
        if fi:
            r = self.request(idx, fi, 1)
            if r:
                soc, lvl, chg = r[0], r[1], r[2]
                if not 0 < soc <= 100:                     # процент не поддерживается - только уровень
                    soc = 100 if lvl & 8 else 60 if lvl & 4 else 20 if lvl & 2 else 5 if lvl & 1 else 0
                return soc, chg in (1, 2, 3)
        fi = self.feature(idx, 0x1000)                     # BATTERY_STATUS
        if fi:
            r = self.request(idx, fi, 0)
            if r and 0 < r[0] <= 100:
                return r[0], 1 <= r[2] <= 4
        fi = self.feature(idx, 0x1001)                     # BATTERY_VOLTAGE
        if fi:
            r = self.request(idx, fi, 0)
            if r:
                mv = (r[0] << 8) | r[1]
                return volt_to_pct(mv), bool(r[2] & 0x80)
        return None

    def device(self, idx):
        bat = self.battery(idx)
        if bat is None:
            return None
        name, kind = self.name(idx)
        name = name or "Устройство Logitech"
        return {"name": name, "level": int(bat[0]), "kind": kind or guess_kind(name), "charging": bat[1]}


def logi_paths(hid):
    """Пути HID-интерфейсов Logitech, через которые идут длинные сообщения HID++."""
    out = []
    for d in hid.enumerate(LOGI_VID, 0):
        up, us = d.get("usage_page", 0), d.get("usage", 0)
        if up == 0xFF00 and us == 0x0002:                  # Windows / macOS: отдельная "коллекция"
            out.append(d["path"])
        elif up == 0 and d.get("interface_number") == 2:   # Linux hidraw: usage не сообщается
            out.append(d["path"])
    return list(dict.fromkeys(out))


def logi_scan_device(dev):
    hp = HidPP(dev)
    found = []
    ver = hp.protocol(0xFF, 0.4)
    if ver and ver[0] >= 2:                     # мышь подключена напрямую (провод / свой режим)
        d = hp.device(0xFF)
        if d:
            found.append(d)
        return found
    for idx in range(1, 7):                     # устройства на приёмнике
        ver = hp.protocol(idx, 0.5)
        if not ver or ver[0] < 2:
            continue
        d = hp.device(idx)
        if d:
            found.append(d)
    return found


def logi_batteries():
    hid = _hid_module()
    if hid is None:
        return []
    out = []
    try:
        paths = logi_paths(hid)
    except Exception:
        return []
    for path in paths:
        dev = None
        try:
            dev = hid.device()
            dev.open_path(path)
            out.extend(logi_scan_device(dev))
        except Exception:
            pass
        finally:
            try:
                if dev is not None:
                    dev.close()
            except Exception:
                pass
    return out


def read_devices():
    if DEMO:
        return [{"name": "MX Master 3S", "level": 64, "kind": "mouse", "charging": False},
                {"name": "MX Keys", "level": 23, "kind": "keyboard", "charging": False},
                {"name": "WH-1000XM4", "level": 90, "kind": "headphones", "charging": False},
                {"name": "Xbox Wireless Controller", "level": 12, "kind": "gamepad", "charging": False},
                {"name": "Этот компьютер", "level": 81, "kind": "laptop", "charging": True}]
    devs, seen = [], set()
    for d in logi_batteries() + [{"name": n, "level": lv, "kind": guess_kind(n), "charging": False}
                                 for n, lv in bt_batteries()]:
        if d["name"].lower() not in seen:
            seen.add(d["name"].lower())
            devs.append(d)
    order = ("mouse", "keyboard", "headphones", "gamepad", "pen", "bluetooth")
    devs.sort(key=lambda d: (order.index(d["kind"]) if d["kind"] in order else 9, d["name"].lower()))
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
#  Погода (Open-Meteo: бесплатно и без ключа)
# ---------------------------------------------------------------------------
UA = {"User-Agent": "SnowWidgets/" + APP_VERSION}
WMO = {0: ("Ясно", "clear"), 1: ("Преимущественно ясно", "partly"), 2: ("Переменная облачность", "partly"),
       3: ("Пасмурно", "cloudy"), 45: ("Туман", "fog"), 48: ("Изморозь", "fog"),
       51: ("Слабая морось", "rain"), 53: ("Морось", "rain"), 55: ("Сильная морось", "rain"),
       56: ("Ледяная морось", "rain"), 57: ("Ледяная морось", "rain"),
       61: ("Небольшой дождь", "rain"), 63: ("Дождь", "rain"), 65: ("Сильный дождь", "rain"),
       66: ("Ледяной дождь", "rain"), 67: ("Ледяной дождь", "rain"),
       71: ("Небольшой снег", "snow"), 73: ("Снег", "snow"), 75: ("Сильный снег", "snow"),
       77: ("Снежная крупа", "snow"), 80: ("Небольшой ливень", "rain"), 81: ("Ливень", "rain"),
       82: ("Сильный ливень", "rain"), 85: ("Снегопад", "snow"), 86: ("Сильный снегопад", "snow"),
       95: ("Гроза", "storm"), 96: ("Гроза с градом", "storm"), 99: ("Гроза с градом", "storm")}


def wmo(code):
    return WMO.get(int(code), ("—", "cloudy"))


def http_json(url, timeout=15):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def locate_by_ip():
    """(город, широта, долгота) по IP-адресу."""
    for url in ("https://ipwho.is/?lang=ru", "https://ipapi.co/json/"):
        try:
            j = http_json(url, 10)
            if j.get("latitude") is not None:
                return j.get("city") or "Моё место", float(j["latitude"]), float(j["longitude"])
        except Exception:
            continue
    return None


def geocode(name):
    url = ("https://geocoding-api.open-meteo.com/v1/search?count=1&language=ru&format=json&name="
           + urllib.parse.quote(name))
    res = http_json(url).get("results") or []
    if not res:
        return None
    r = res[0]
    return r.get("name") or name, float(r["latitude"]), float(r["longitude"])


def fetch_weather(lat, lon):
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%.4f&longitude=%.4f"
           "&current=temperature_2m,apparent_temperature,weather_code,is_day,wind_speed_10m,relative_humidity_2m"
           "&hourly=temperature_2m,weather_code,is_day"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min"
           "&timezone=auto&forecast_days=7&wind_speed_unit=ms" % (lat, lon))
    j = http_json(url)
    cur, hr, dl = j["current"], j["hourly"], j["daily"]
    now_h = cur["time"][:13]
    times = hr["time"]
    start = next((i for i, t in enumerate(times) if t[:13] >= now_h), 0)
    hours = []
    for k, i in enumerate(range(start, min(start + 6, len(times)))):
        hours.append({"label": "Сейчас" if k == 0 else times[i][11:13],
                      "temp": hr["temperature_2m"][i], "code": hr["weather_code"][i],
                      "day": hr["is_day"][i]})
    days = []
    for i, d in enumerate(dl["time"]):
        dd = datetime.date.fromisoformat(d)
        days.append({"label": "Сегодня" if i == 0 else WD_SHORT[dd.weekday()],
                     "code": dl["weather_code"][i], "max": dl["temperature_2m_max"][i],
                     "min": dl["temperature_2m_min"][i]})
    return {"temp": cur["temperature_2m"], "feels": cur["apparent_temperature"],
            "code": cur["weather_code"], "day": cur["is_day"], "wind": cur["wind_speed_10m"],
            "hum": cur["relative_humidity_2m"], "hours": hours, "days": days,
            "max": days[0]["max"] if days else None, "min": days[0]["min"] if days else None}


def demo_weather():
    code = int(os.environ.get("DEMO_WCODE", "73"))
    day = int(os.environ.get("DEMO_WDAY", "1"))
    hours = [{"label": "Сейчас" if k == 0 else "%02d" % ((14 + k) % 24), "temp": -3 - k * 0.6,
              "code": [code, code, 3, 2, 1, 0][k], "day": day if k < 3 else 0} for k in range(6)]
    days = [{"label": "Сегодня" if i == 0 else WD_SHORT[(4 + i) % 7], "code": c, "max": mx, "min": mn}
            for i, (c, mx, mn) in enumerate(((code, -1, -6), (75, -2, -8), (3, 0, -5), (2, 1, -3),
                                              (61, 3, 0), (0, -2, -9), (71, -4, -11)))]
    return {"temp": -3.4, "feels": -8.0, "code": code, "day": day, "wind": 4.2, "hum": 86,
            "hours": hours, "days": days, "max": -1, "min": -6}


# ---------------------------------------------------------------------------
#  Рисование: иконки устройств и погоды, кольца, полосы
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
        for row in (0, 1):
            for i in range(5):
                x = cx - w / 2 + w * (i + 0.5) / 5 + (s * 0.02 if row else 0)
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


def draw_chevron(p, cx, cy, s, direction, color):
    pen = QPen(color, max(1.5, s * 0.16))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.save()
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    d = s * 0.22 * direction
    path.moveTo(cx - d, cy - s * 0.38)
    path.lineTo(cx + d, cy)
    path.lineTo(cx - d, cy + s * 0.38)
    p.drawPath(path)
    p.restore()


def cloud_path(cx, cy, s):
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    path.addEllipse(QPointF(cx - s * 0.22, cy + s * 0.06), s * 0.21, s * 0.21)
    path.addEllipse(QPointF(cx + s * 0.04, cy - s * 0.07), s * 0.29, s * 0.29)
    path.addEllipse(QPointF(cx + s * 0.29, cy + s * 0.08), s * 0.19, s * 0.19)
    path.addRoundedRect(QRectF(cx - s * 0.43, cy + s * 0.05, s * 0.91, s * 0.22), s * 0.11, s * 0.11)
    return path.simplified()


def draw_sun(p, cx, cy, s, t=0.0):
    p.save()
    p.setPen(NOPEN)
    g = QRadialGradient(QPointF(cx, cy), s * 0.5)
    g.setColorAt(0, QColor(255, 214, 10, 90))
    g.setColorAt(1, QColor(255, 214, 10, 0))
    p.setBrush(g)
    k = 1 + 0.05 * math.sin(t * 2)
    p.drawEllipse(QPointF(cx, cy), s * 0.5 * k, s * 0.5 * k)
    pen = QPen(QColor("#FFD60A"), s * 0.07)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    for i in range(8):
        a = math.radians(i * 45 + t * 12)
        p.drawLine(QPointF(cx + math.cos(a) * s * 0.3, cy + math.sin(a) * s * 0.3),
                   QPointF(cx + math.cos(a) * s * 0.42, cy + math.sin(a) * s * 0.42))
    p.setPen(NOPEN)
    p.setBrush(QColor("#FFD60A"))
    p.drawEllipse(QPointF(cx, cy), s * 0.21, s * 0.21)
    p.restore()


def draw_moon(p, cx, cy, s):
    a = QPainterPath()
    a.addEllipse(QPointF(cx, cy), s * 0.27, s * 0.27)
    b = QPainterPath()
    b.addEllipse(QPointF(cx + s * 0.14, cy - s * 0.1), s * 0.23, s * 0.23)
    p.save()
    p.setPen(NOPEN)
    p.setBrush(QColor("#F4F1C9"))
    p.drawPath(a.subtracted(b))
    p.restore()


def draw_wicon(p, kind, is_day, cx, cy, s, t=0.0):
    """Цветная иконка погоды размером примерно s x s; t - время для анимации."""
    bob = math.sin(t * 1.3) * s * 0.025
    if kind == "clear":
        if is_day:
            draw_sun(p, cx, cy, s, t)
        else:
            draw_moon(p, cx, cy, s)
        return
    p.save()
    p.setPen(NOPEN)
    if kind == "partly":
        if is_day:
            draw_sun(p, cx + s * 0.16, cy - s * 0.14, s * 0.8, t)
        else:
            draw_moon(p, cx + s * 0.18, cy - s * 0.16, s * 0.75)
        p.setBrush(QColor(255, 255, 255, 245))
        p.drawPath(cloud_path(cx - s * 0.06 + math.sin(t * 0.7) * s * 0.03, cy + s * 0.08, s * 0.8))
    elif kind == "fog":
        pen = QPen(QColor(255, 255, 255, 220), s * 0.09)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for i, (w, dx) in enumerate(((0.7, 0.0), (0.56, 0.1), (0.66, -0.06))):
            sh = math.sin(t * 0.8 + i) * s * 0.04
            y = cy - s * 0.18 + i * s * 0.18
            p.drawLine(QPointF(cx - s * w / 2 + dx * s + sh, y), QPointF(cx + s * w / 2 + dx * s + sh, y))
    else:
        top = cy - s * 0.1 + bob
        if kind == "cloudy":
            p.setBrush(QColor(205, 212, 224))
            p.drawPath(cloud_path(cx + s * 0.14, cy - s * 0.12 + bob * 0.5, s * 0.62))
            p.setBrush(QColor(255, 255, 255, 245))
            top = cy + bob
        else:
            p.setBrush(QColor(150, 158, 175) if kind == "storm" else QColor(228, 233, 242))
        p.drawPath(cloud_path(cx, top, s * (0.86 if kind == "cloudy" else 0.9)))
        if kind == "rain":
            pen = QPen(QColor("#64D2FF"), s * 0.07)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for i in range(3):
                ph = (t * 1.6 + i * 0.33) % 1.0
                x = cx - s * 0.2 + i * s * 0.2
                y = cy + s * 0.22 + ph * s * 0.14
                p.drawLine(QPointF(x, y), QPointF(x - s * 0.05, y + s * 0.1))
        elif kind == "snow":
            p.setBrush(WHITE)
            for i in range(3):
                ph = (t * 0.6 + i * 0.33) % 1.0
                x = cx - s * 0.2 + i * s * 0.2 + math.sin(t * 2 + i) * s * 0.02
                y = cy + s * 0.26 + ph * s * 0.14
                p.drawEllipse(QPointF(x, y), s * 0.05, s * 0.05)
        elif kind == "storm":
            draw_bolt(p, cx, cy + s * 0.32, s * 0.36, QColor("#FFD60A"))
    p.restore()


def draw_ring(p, cx, cy, r, width, frac, color, track):
    p.save()
    rc = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    pen = QPen(track, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rc)
    frac = clamp(frac)
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
    frac = clamp(frac)
    if frac > 0:
        p.setBrush(color)
        p.drawRoundedRect(QRectF(rc.x(), rc.y(), max(rc.height(), rc.width() * frac), rc.height()), rad, rad)
    p.restore()


def text(p, rc, s, f, color, align=AC, elide=True):
    p.setFont(f)
    p.setPen(color)
    if elide:
        s = p.fontMetrics().elidedText(s, Qt.TextElideMode.ElideRight, int(rc.width()))
    p.drawText(rc, int(align), s)


# ---------------------------------------------------------------------------
#  Размытые обои рабочего стола - фон для стиля "Стекло" (как в macOS)
# ---------------------------------------------------------------------------
class Wallpaper:
    """Виджеты лежат прямо на рабочем столе, поэтому "стекло" - это размытый кусок обоев под виджетом."""

    def __init__(self):
        self.key = None
        self.cache = {}

    @staticmethod
    def info():
        """(путь к картинке или None, способ размещения, цвет фона)."""
        path, style, color = os.environ.get("SNOWWIDGETS_WALLPAPER"), "fill", QColor(30, 50, 80)
        if IS_WIN:
            try:
                buf = ctypes.create_unicode_buffer(520)
                if ctypes.windll.user32.SystemParametersInfoW(0x0073, 520, buf, 0) and buf.value:
                    path = buf.value
                if not path or not os.path.isfile(path):
                    tw = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Themes",
                                      "TranscodedWallpaper")
                    path = tw if os.path.isfile(tw) else None
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
                    ws = str(winreg.QueryValueEx(k, "WallpaperStyle")[0])
                    try:
                        tile = str(winreg.QueryValueEx(k, "TileWallpaper")[0])
                    except OSError:
                        tile = "0"
                style = {"2": "stretch", "6": "fit", "0": "tile" if tile == "1" else "center"}.get(ws, "fill")
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Colors") as k:
                    rgb = [int(x) for x in str(winreg.QueryValueEx(k, "Background")[0]).split()]
                    color = QColor(*rgb[:3])
            except Exception:
                pass
        return path, style, color

    def check(self):
        """True, если обои поменялись."""
        path, style, color = self.info()
        try:
            mt = os.path.getmtime(path) if path else 0
        except Exception:
            mt = 0
        key = (path, mt, style, color.name())
        if key != self.key:
            self.key = key
            self.cache.clear()
            return True
        return False

    def blurred(self, w, h):
        k = (w, h)
        if k not in self.cache:
            if self.key is None:
                self.check()
            path, _mt, style, color = self.key
            cw, ch = max(8, w // 4), max(8, h // 4)
            canvas = QImage(cw, ch, QImage.Format.Format_RGB32)
            canvas.fill(QColor(color))
            src = QImage(path) if path else QImage()
            if not src.isNull():
                p = QPainter(canvas)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                iw, ih = src.width(), src.height()
                if style == "stretch":
                    p.drawImage(QRectF(0, 0, cw, ch), src)
                elif style in ("center", "tile"):
                    s4 = 0.25
                    p.drawImage(QRectF((cw - iw * s4) / 2, (ch - ih * s4) / 2, iw * s4, ih * s4), src)
                else:
                    sc = (max if style == "fill" else min)(cw / iw, ch / ih)
                    p.drawImage(QRectF((cw - iw * sc) / 2, (ch - ih * sc) / 2, iw * sc, ih * sc), src)
                p.end()
            smooth_t = Qt.TransformationMode.SmoothTransformation
            ign = Qt.AspectRatioMode.IgnoreAspectRatio
            img = canvas
            for div in (10, 5):                      # размытие: уменьшить и снова растянуть (два прохода)
                small = img.scaled(max(2, cw // div), max(2, ch // div), ign, smooth_t)
                img = small.scaled(cw, ch, ign, smooth_t)
            self.cache[k] = img
        return self.cache[k]

    def draw(self, p, r, widget):
        scr = widget.screen() or QApplication.primaryScreen()
        g = scr.geometry()
        img = self.blurred(g.width(), g.height())
        tl = widget.mapToGlobal(r.topLeft().toPoint())
        sx, sy = img.width() / g.width(), img.height() / g.height()
        p.drawImage(r, img, QRectF((tl.x() - g.x()) * sx, (tl.y() - g.y()) * sy, r.width() * sx, r.height() * sy))


# ---------------------------------------------------------------------------
#  Базовый виджет: окно без рамки, скруглённая карточка, анимации, перетаскивание, меню
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
        self._press = False
        self._hits = []                    # [(QRectF, функция)] - кликабельные места, заполняются в paint
        self._av = {}                      # плавно анимируемые значения
        self._t_last = time.time()
        self._dt = 0.0
        self._frame_ms = 0
        self._born = None                  # время начала появления
        self._dying = None                 # время начала исчезновения
        self._on_dead = None
        self._ft = QTimer(self)
        self._ft.setSingleShot(True)
        self._ft.timeout.connect(self.update)
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
        return STYLES[self.mgr.style_name(self.cfg)]

    def opacity(self):
        v = self.cfg.get("opacity")
        return float(self.mgr.cfg.get("opacity", 1.0) if v is None else v)

    def kind_colors(self):
        return KIND_COLORS.get(self.KIND, ("#3A3A44", "#1E1E26"))

    def ring_col(self, col, low=False):
        """Цвет кольца/полосы: в стиле "Яркий" всё белое, кроме низкого заряда."""
        if self.theme["mono"]:
            return QColor("#FFE14D") if low else WHITE
        return col

    def today_fg(self, th):
        return th["today_fg"] if th["today_fg"] is not None else QColor(self.kind_colors()[0])

    def moveEvent(self, ev):
        super().moveEvent(ev)
        if self.theme["mode"] == "glass":
            self.update()                  # под виджетом другой кусок обоев

    @property
    def animated(self):
        return bool(self.mgr.cfg.get("animations", True))

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
        self.keep_on_screen()
        self.size_changed()
        self.appear()
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

    # ----- анимации -----
    def appear(self, delay=0.0):
        self._born = time.time() + (delay if self.animated else 0.0)
        self.update()

    def vanish(self, on_dead):
        if not self.animated:
            on_dead()
            return
        self._dying, self._on_dead = time.time(), on_dead
        self.update()

    def want_frame(self, ms=16):
        """Попросить следующий кадр через ms миллисекунд."""
        self._frame_ms = ms if not self._frame_ms else min(self._frame_ms, ms)

    def av(self, key, target, speed=7.0, start=None):
        """Плавно анимируемое значение: каждый кадр приближается к target."""
        cur = self._av.get(key)
        if cur is None:
            cur = target if (start is None or not self.animated) else start
        if not self.animated:
            cur = target
        else:
            cur += (target - cur) * (1.0 - math.exp(-self._dt * speed))
            if abs(target - cur) < 0.003 * max(1.0, abs(target)):
                cur = target
            else:
                self.want_frame(16)
        self._av[key] = cur
        return cur

    def hit(self, rc, fn):
        self._hits.append((QRectF(rc), fn))

    # ----- рисование -----
    def paintEvent(self, _ev):
        now = time.time()
        self._dt = clamp(now - self._t_last, 0.0, 0.05)
        self._t_last = now
        self._frame_ms = 0
        self._hits = []
        e = 1.0
        if self._born is not None:
            t = (now - self._born) / 0.5
            if t < 1.0:
                e = max(0.0, t)
                self.want_frame(16)
            else:
                self._born = None
        if self._dying is not None:
            t = (now - self._dying) / 0.22
            if t >= 1.0:
                cb, self._on_dead, self._dying = self._on_dead, None, None
                QTimer.singleShot(0, self.hide)
                if cb:
                    QTimer.singleShot(0, cb)
                return
            e = 1.0 - t
            self.want_frame(16)
        press = self.av("_press", 1.0 if self._press else 0.0, 22)
        if e <= 0.0:
            self._schedule()
            return
        p = QPainter(self)
        p.setRenderHints(RH)
        r = self.card_rect()
        th = self.theme
        scale = (0.86 + 0.14 * ease_out_back(e)) * (1.0 - 0.035 * press)
        p.setOpacity(ease_out_cubic(e))
        c = r.center()
        p.translate(c)
        p.scale(scale, scale)
        p.translate(-c)
        op = self.opacity()
        neon = th["mode"] == "neon"
        p.setPen(NOPEN)
        for i in range(MARGIN, 0, -2):                       # мягкая тень (у неона - цветное свечение)
            k = (1 - i / MARGIN) ** 2
            if neon:
                g = QLinearGradient(r.topLeft(), r.bottomRight())
                c1, c2 = QColor(th["glow1"]), QColor(th["glow2"])
                c1.setAlpha(int(70 * k * op) + 1)
                c2.setAlpha(int(70 * k * op) + 1)
                g.setColorAt(0, c1)
                g.setColorAt(1, c2)
                p.setBrush(g)
                p.drawRoundedRect(r.adjusted(-i * 0.8, -i * 0.8, i * 0.8, i * 0.8), RADIUS + i * 0.7, RADIUS + i * 0.7)
            else:
                p.setBrush(QColor(0, 0, 0, int(26 * k * (0.3 + 0.7 * op)) + 1))
                p.drawRoundedRect(r.adjusted(-i * 0.7, -i * 0.5, i * 0.7, i * 0.9), RADIUS + i * 0.6, RADIUS + i * 0.6)
        path = QPainterPath()
        path.addRoundedRect(r, RADIUS, RADIUS)
        p.save()
        p.setClipPath(path)
        p.save()
        p.setOpacity(p.opacity() * op)
        self.paint_bg(p, path, r, th)
        p.restore()
        try:
            self.paint(p, r, th)
            if th["mode"] == "winter":
                self.paint_snowcap(p, r)
        except Exception:
            traceback.print_exc()
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        if neon:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, th["glow1"])
            g.setColorAt(1, th["glow2"])
            p.setPen(QPen(g, 1.6))
        else:
            p.setPen(QPen(th["line"], 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        p.end()
        self._schedule()

    def _schedule(self):
        if self._frame_ms and not self._ft.isActive():
            self._ft.start(self._frame_ms)

    def paint_bg(self, p, path, r, th):
        mode = th["mode"]
        if mode == "glass":
            self.mgr.wall.draw(p, r, self)
            p.fillPath(path, th["tint"])
            g = QLinearGradient(r.topLeft(), r.bottomLeft())           # блик сверху
            g.setColorAt(0, QColor(255, 255, 255, 40))
            g.setColorAt(0.45, QColor(255, 255, 255, 0))
            p.fillPath(path, g)
            return
        if mode == "color":
            c1, c2 = self.kind_colors()
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(c1))
            g.setColorAt(1, QColor(c2))
            p.fillPath(path, g)
            return
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, th["bg1"])
        g.setColorAt(1, th["bg2"])
        p.fillPath(path, g)
        if mode == "winter":
            self.paint_flakes(p, r)

    def _rng(self):
        return random.Random(str(self.cfg.get("id", self.KIND)))

    def paint_flakes(self, p, r):
        """Едва заметные снежинки на фоне зимнего стиля."""
        rnd = self._rng()
        pen = QPen(QColor(255, 255, 255, 28), 1.1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for _ in range(int(r.width() * r.height() / 2600)):
            x, y, s = r.x() + rnd.random() * r.width(), r.y() + rnd.random() * r.height(), rnd.uniform(3, 8)
            for k in range(3):
                a = math.radians(k * 60 + rnd.random() * 0)
                dx, dy = math.cos(a) * s, math.sin(a) * s
                p.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))

    def paint_snowcap(self, p, r):
        """Шапка снега на верхнем крае виджета (стиль "Зимний")."""
        rnd = self._rng()
        path = QPainterPath()
        path.moveTo(r.left(), r.top())
        x = r.left()
        while x < r.right():
            step = rnd.uniform(16, 30)
            nx = min(r.right(), x + step)
            path.quadTo(QPointF((x + nx) / 2, r.top() + rnd.uniform(6, 11)), QPointF(nx, r.top() + rnd.uniform(2.5, 5)))
            x = nx
        path.lineTo(r.right(), r.top())
        path.closeSubpath()
        p.save()
        p.setPen(NOPEN)
        p.setBrush(QColor(120, 170, 220, 70))
        p.translate(0, 1.6)
        p.drawPath(path)
        p.translate(0, -1.6)
        g = QLinearGradient(0, r.top(), 0, r.top() + 10)
        g.setColorAt(0, QColor(255, 255, 255, 250))
        g.setColorAt(1, QColor(225, 238, 252, 245))
        p.setBrush(g)
        p.drawPath(path)
        p.setBrush(QColor(255, 255, 255, 235))               # капельки-сосульки
        for _ in range(int(r.width() / 70)):
            cx = r.left() + RADIUS + rnd.random() * (r.width() - 2 * RADIUS)
            ln = rnd.uniform(4, 9)
            drop = QPainterPath()
            drop.moveTo(cx - 2.2, r.top() + 4)
            drop.quadTo(QPointF(cx, r.top() + 4 + ln * 1.4), QPointF(cx + 2.2, r.top() + 4))
            p.drawPath(drop)
        p.restore()

    def paint(self, p, r, th):
        pass

    # ----- мышь -----
    def _hit_at(self, pos):
        for rc, fn in reversed(self._hits):
            if rc.contains(pos):
                return fn
        return None

    def mousePressEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = (None if self.mgr.cfg.get("locked")
                      else ev.globalPosition().toPoint() - self.frameGeometry().topLeft())
        self._moved = False
        if self._hit_at(ev.position()) is None:
            self._press = True
            self.update()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            pos = ev.globalPosition().toPoint() - self._drag
            if not self._moved and (pos - self.pos()).manhattanLength() <= 3:
                return
            self._moved = True
            self._press = False
            self.move(pos)

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        self._press = False
        self.update()
        if self._moved:
            x = round((self.x() + MARGIN) / GRID) * GRID - MARGIN       # прилипание к сетке
            y = round((self.y() + MARGIN) / GRID) * GRID - MARGIN
            self.move(x, y)
            self.keep_on_screen()
            self.cfg["x"], self.cfg["y"] = self.x(), self.y()
            self.mgr.save()
        else:
            fn = self._hit_at(ev.position())
            if fn is not None:
                fn()
            else:
                self.clicked(ev.position())
        self._drag = None
        self._moved = False

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            fn = self._hit_at(ev.position())
            if fn is not None:
                fn()                    # быстрые клики по стрелкам календаря листают дальше
            else:
                self.activate()

    def wheelEvent(self, ev):
        self.wheel(ev.position(), ev.angleDelta().y())

    def wheel(self, pos, delta):
        pass

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
        if self.KIND != "weather":
            dm = menu.addMenu("Дизайн этого виджета")
            grp2 = QActionGroup(dm)
            for key, label in [(None, "Как у всех (%s)" % STYLES[self.mgr.style_name({})]["name"])] + \
                    [(k, v["name"]) for k, v in STYLES.items()]:
                a = dm.addAction(label)
                a.setCheckable(True)
                a.setChecked(self.cfg.get("style") == key)
                grp2.addAction(a)
                a.triggered.connect(lambda _=False, k=key: self.set_opt("style", k))
        om = menu.addMenu("Прозрачность этого виджета")
        self.mgr.opacity_menu(om, self.cfg.get("opacity"), lambda v: self.set_opt("opacity", v), allow_none=True)
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

    def set_opt(self, key, val):
        if val is None:
            self.cfg.pop(key, None)
        else:
            self.cfg[key] = val
        self.mgr.save()
        self.update()

    def set_on_top(self, on):
        self.cfg["on_top"] = bool(on)
        self._apply_flags()
        self.mgr.save()

    def closing(self):
        pass


# ---------------------------------------------------------------------------
#  Календарь, который листается (общий для виджетов "Календарь" и "Часы")
# ---------------------------------------------------------------------------
class CalendarMixin:
    def cal_init(self):
        self.cal_off = 0
        self.cal_prev = 0
        self.cal_dir = 1
        self.cal_t0 = 0.0
        self._cal_rect = QRectF()
        self.cal_back = QTimer(self)                 # через 2 минуты без действий - снова текущий месяц
        self.cal_back.setSingleShot(True)
        self.cal_back.timeout.connect(self.cal_today)

    def cal_move(self, d):
        if not d:
            return
        self.cal_prev = self.cal_off
        self.cal_off += d
        self.cal_dir = 1 if d > 0 else -1
        self.cal_t0 = time.time() if self.animated else 0.0
        if self.cal_off:
            self.cal_back.start(120 * 1000)
        self.update()

    def cal_today(self):
        self.cal_move(-self.cal_off)

    @staticmethod
    def _ym(off):
        t = datetime.date.today()
        m = t.month - 1 + off
        return t.year + m // 12, m % 12 + 1

    def draw_month(self, p, grid, year, month, th, fs):
        today = datetime.date.today()
        weeks = calendar.Calendar(0).monthdayscalendar(year, month)
        cw = grid.width() / 7
        ch = grid.height() / 7
        for i, wd in enumerate(WD_SHORT):
            text(p, QRectF(grid.x() + i * cw, grid.y(), cw, ch), wd, font(fs * 0.85, SEMI),
                 th["fg2"] if i < 5 else th["weekend"])
        for wi, week in enumerate(weeks):
            for i, day in enumerate(week):
                if not day:
                    continue
                cell = QRectF(grid.x() + i * cw, grid.y() + (wi + 1) * ch, cw, ch)
                hol = (month, day) in HOLIDAYS
                col = th["fg"] if i < 5 and not hol else th["weekend"]
                is_today = (year, month, day) == (today.year, today.month, today.day)
                if is_today:
                    d = min(cw, ch) * 0.9
                    p.setPen(NOPEN)
                    p.setBrush(th["today_bg"])
                    p.drawEllipse(cell.center(), d / 2, d / 2)
                    col = self.today_fg(th)
                text(p, cell, str(day), font(fs, SEMI if (is_today or hol) else NORMAL), col)
                if hol and not is_today:
                    p.setPen(NOPEN)
                    p.setBrush(th["weekend"])
                    p.drawEllipse(QPointF(cell.center().x(), cell.bottom() - ch * 0.1), 1.6, 1.6)

    def paint_calendar(self, p, rc, th, fs, big=False):
        """Заголовок со стрелками + сетка месяца с анимацией перелистывания."""
        y, m = self._ym(self.cal_off)
        hh = fs * 2.0
        bs = hh * 0.95                                            # размер кнопки-стрелки
        title = (MONTHS[m - 1] + " " + str(y)) if big else MONTHS[m - 1].upper()
        if not big and y != datetime.date.today().year:
            title += " " + str(y)
        tf = font(fs * (1.25 if big else 1.0), SEMI)
        trc = QRectF(rc.x(), rc.y(), rc.width() - 2 * bs - 6, hh)
        text(p, trc, title, tf, th["fg"] if big else th["accent"], AL | AVC)
        p.setFont(tf)
        title_w = p.fontMetrics().horizontalAdvance(title)
        self.hit(QRectF(trc.x(), trc.y(), min(trc.width(), title_w + 6), hh), self.cal_today)
        for k, d in ((0, -1), (1, 1)):
            cx = rc.right() - bs * (1.5 - k) - (0 if k else 4)
            cy = rc.y() + hh / 2
            hov = QRectF(cx - bs / 2, cy - bs / 2, bs, bs)
            p.setPen(NOPEN)
            p.setBrush(th["btn"])
            p.drawEllipse(hov.center(), bs * 0.42, bs * 0.42)
            draw_chevron(p, cx, cy, bs * 0.42, d, th["fg"])
            self.hit(hov, lambda d=d: self.cal_move(d))
        if self.cal_off:
            pf = font(fs * 0.85, SEMI)
            p.setFont(pf)
            pw = p.fontMetrics().horizontalAdvance("Сегодня") + fs * 1.2
            pill = QRectF(rc.right() - 2 * bs - 10 - pw, rc.y() + hh * 0.15, pw, hh * 0.7)
            if pill.left() > rc.x() + title_w + 8:
                p.setPen(NOPEN)
                p.setBrush(th["pill"])
                p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
                text(p, pill, "Сегодня", pf, WHITE)
                self.hit(pill, self.cal_today)
        grid = QRectF(rc.x(), rc.y() + hh + fs * 0.2, rc.width(), rc.bottom() - rc.y() - hh - fs * 0.2)
        self._cal_rect = QRectF(rc)
        e = ease_out_cubic((time.time() - self.cal_t0) / 0.38) if self.cal_t0 else 1.0
        if e < 1.0:
            self.want_frame(16)
            p.save()
            p.setClipRect(grid.adjusted(-2, -2, 2, 2), Qt.ClipOperation.IntersectClip)
            w = grid.width()
            py, pm = self._ym(self.cal_prev)
            op = p.opacity()
            p.translate(-self.cal_dir * w * e, 0)
            p.setOpacity(op * (1 - e))
            self.draw_month(p, grid, py, pm, th, fs)
            p.translate(self.cal_dir * w, 0)
            p.setOpacity(op * e)
            self.draw_month(p, grid, y, m, th, fs)
            p.restore()
        else:
            self.draw_month(p, grid, y, m, th, fs)

    def wheel(self, pos, delta):
        if delta and self._cal_rect.contains(pos):
            self.cal_move(-1 if delta > 0 else 1)


def next_holiday(today):
    best = None
    for (m, d), name in HOLIDAYS.items():
        if name == "Новогодние каникулы":
            continue
        dt = datetime.date(today.year, m, d)
        if dt <= today:
            dt = datetime.date(today.year + 1, m, d)
        if best is None or dt < best[0]:
            best = (dt, name)
    return best


# ---------------------------------------------------------------------------
#  Виджет "Календарь"
# ---------------------------------------------------------------------------
class CalendarCard(CalendarMixin, Card):
    KIND = "calendar"
    TITLE = "Календарь"
    DEFAULT_SIZE = "m"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.cal_init()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(30 * 1000)

    def paint(self, p, r, th):
        today = datetime.date.today()
        size = self.cfg["size"]
        if size == "s":
            self._today_block(p, QRectF(r.x() + 18, r.y() + 16, r.width() - 36, r.height() - 30), today, th, 54)
            return
        if size == "m":
            self._today_block(p, QRectF(r.x() + 20, r.y() + 16, r.width() * 0.42 - 20, r.height() - 30),
                              today, th, 50)
            self.paint_calendar(p, QRectF(r.x() + r.width() * 0.44, r.y() + 12, r.width() * 0.56 - 16,
                                          r.height() - 22), th, 11)
            return
        self.paint_calendar(p, QRectF(r.x() + 18, r.y() + 16, r.width() - 36, r.height() - 92), th, 15, big=True)
        p.setPen(QPen(th["line"], 1))
        p.drawLine(QPointF(r.x() + 18, r.bottom() - 70), QPointF(r.right() - 18, r.bottom() - 70))
        _y, m = self._ym(self.cal_off)
        hols = [(d, n) for (mm, d), n in sorted(HOLIDAYS.items()) if mm == m and n != "Новогодние каникулы"]
        if hols:
            title, lines = "Праздники", ", ".join("%d — %s" % (d, n) for d, n in hols[:2])
        else:
            nh = next_holiday(today)
            days = (nh[0] - today).days
            title = nh[1]
            lines = "через %d %s — %d %s" % (days, plural(days, "день", "дня", "дней"), nh[0].day,
                                             MONTHS_GEN[nh[0].month - 1])
        text(p, QRectF(r.x() + 18, r.bottom() - 62, r.width() - 36, 20), title, font(12, SEMI),
             th["weekend"], AL | AVC)
        text(p, QRectF(r.x() + 18, r.bottom() - 42, r.width() - 36, 20), lines, font(12), th["fg2"], AL | AVC)

    def _today_block(self, p, rc, today, th, big):
        text(p, QRectF(rc.x(), rc.y(), rc.width(), 18), WEEKDAYS[today.weekday()].upper(), font(12, SEMI),
             th["weekend"] if th["mode"] not in ("grad",) or th["light"] else RED, AL)
        text(p, QRectF(rc.x(), rc.y() + 12, rc.width(), big * 1.3), str(today.day), font(big, LIGHT), th["fg"], AL)
        text(p, QRectF(rc.x(), rc.y() + 14 + big * 1.22, rc.width(), 18),
             "%s %d" % (MONTHS_GEN[today.month - 1], today.year), font(13), th["fg2"], AL)
        info = HOLIDAYS.get((today.month, today.day))
        if not info:
            nh = next_holiday(today)
            days = (nh[0] - today).days
            info = "%s через %d %s" % (nh[1], days, plural(days, "день", "дня", "дней"))
        p.setFont(font(11))
        p.setPen(th["fg2"])
        p.drawText(QRectF(rc.x(), rc.bottom() - 30, rc.width(), 32),
                   int(AL | Qt.AlignmentFlag.AlignBottom | Qt.TextFlag.TextWordWrap), info)

    def activate(self):
        self.cal_today()


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

    def lvl(self, d):
        return self.av("b:" + d["name"], float(d["level"]), 4.0, start=0.0)

    def paint(self, p, r, th):
        devs = self.devices()
        size = self.cfg["size"]
        if not devs:
            draw_icon(p, "mouse", r.center().x(), r.y() + (r.height() * 0.28 if size != "s" else 46), 30, th["fg2"])
            if self.mgr.battery.stamp is None:
                msg = "Ищу устройства..."
            elif size == "s":
                msg = "Нет устройств\nс известным зарядом"
            else:
                msg = ("Нет устройств с известным зарядом.\nПоддерживаются Bluetooth и радио-мыши Logitech\n"
                       "(Unifying, Bolt, Lightspeed).")
            p.setFont(font(12))
            p.setPen(th["fg2"])
            p.drawText(QRectF(r.x() + 12, r.y() + r.height() * (0.45 if size != "s" else 0.5), r.width() - 24,
                              r.height() * 0.5), int(AC | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), msg)
            return
        if size == "s":
            d = devs[0]
            v = self.lvl(d)
            cx, cy, rad = r.center().x(), r.y() + 70, 44
            self._ring(p, d, v, cx, cy, rad, 9, th, 38)
            text(p, QRectF(r.x(), r.y() + 120, r.width(), 26), "%d%%" % round(v), font(22, SEMI), th["fg"])
            text(p, QRectF(r.x() + 12, r.y() + 144, r.width() - 24, 18), d["name"], font(12), th["fg2"])
        elif size == "m":
            n = min(4, len(devs))
            slot = r.width() / 4
            x0 = r.x() + (r.width() - slot * n) / 2
            for i, d in enumerate(devs[:n]):
                v = self.lvl(d)
                cx = x0 + slot * (i + 0.5)
                self._ring(p, d, v, cx, r.y() + 66, 34, 7, th, 28)
                text(p, QRectF(cx - slot / 2, r.y() + 110, slot, 22), "%d%%" % round(v), font(16, SEMI), th["fg"])
                text(p, QRectF(cx - slot / 2 + 4, r.y() + 132, slot - 8, 18), d["name"], font(11), th["fg2"])
        else:
            text(p, QRectF(r.x() + 20, r.y() + 14, r.width() - 40, 24), "Батарея", font(15, SEMI), th["fg"], AL | AVC)
            if self.mgr.battery.stamp:
                text(p, QRectF(r.x() + 20, r.y() + 14, r.width() - 40, 24),
                     self.mgr.battery.stamp.strftime("%H:%M"), font(12), th["fg2"], AR | AVC)
            row = 54
            for i, d in enumerate(devs[:6]):
                v = self.lvl(d)
                y = r.y() + 48 + i * row
                p.setPen(NOPEN)
                p.setBrush(th["track"])
                p.drawEllipse(QPointF(r.x() + 40, y + row / 2), 19, 19)
                draw_icon(p, d["kind"], r.x() + 40, y + row / 2, 22, th["fg"])
                text(p, QRectF(r.x() + 70, y + 6, r.width() - 150, 20), d["name"], font(13), th["fg"], AL | AVC)
                text(p, QRectF(r.right() - 80, y + 6, 60, 20), "%d%%" % round(v), font(14, SEMI), th["fg"], AR | AVC)
                draw_bar(p, QRectF(r.x() + 70, y + 31, r.width() - 90, 7), v / 100.0,
                         self.ring_col(level_color(d["level"]), d["level"] <= 15), th["track"])
                if d.get("charging"):
                    draw_bolt(p, r.right() - 96, y + 16, 14, self.ring_col(GREEN))

    def _ring(self, p, d, v, cx, cy, rad, width, th, icon):
        draw_ring(p, cx, cy, rad, width, v / 100.0, self.ring_col(level_color(d["level"]), d["level"] <= 15),
                  th["track"])
        draw_icon(p, d["kind"], cx, cy, icon, th["fg"])
        if d.get("charging"):
            p.setPen(NOPEN)
            p.setBrush(QColor(self.kind_colors()[1]) if th["mode"] == "color" else th["bg2"])
            p.drawEllipse(QPointF(cx + rad * 0.72, cy - rad * 0.72), rad * 0.28, rad * 0.28)
            draw_bolt(p, cx + rad * 0.72, cy - rad * 0.72, rad * 0.4, self.ring_col(GREEN))

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

    def _pick(self, name):
        self.cfg["device"] = name
        self.mgr.save()
        self.update()

    def activate(self):
        self.mgr.battery.refresh()


# ---------------------------------------------------------------------------
#  Виджет "Фото"
# ---------------------------------------------------------------------------
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".jfif"}
KB_ZOOM = 1.12           # запас картинки под эффект медленного приближения


def is_image(name):
    return os.path.splitext(name)[1].lower() in IMG_EXT


def list_images(folder, recursive):
    out = []
    try:
        if recursive:
            for root, dirs, files in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                out.extend(os.path.join(root, f) for f in files if is_image(f))
                if len(out) > 50000:
                    break
        else:
            out = [os.path.join(folder, f) for f in os.listdir(folder) if is_image(f)]
    except Exception:
        pass
    out.sort(key=lambda s: s.lower())
    return out


def count_images(folder):
    try:
        return sum(1 for f in os.listdir(folder) if is_image(f))
    except Exception:
        return 0


def photo_places():
    """Папки, где обычно лежат фото: Telegram, Изображения, OneDrive, Загрузки, Рабочий стол."""
    loc = QStandardPaths.StandardLocation
    home = os.path.expanduser("~")
    dl = QStandardPaths.writableLocation(loc.DownloadLocation) or os.path.join(home, "Downloads")
    docs = QStandardPaths.writableLocation(loc.DocumentsLocation) or os.path.join(home, "Documents")
    pics = QStandardPaths.writableLocation(loc.PicturesLocation) or os.path.join(home, "Pictures")
    desk = QStandardPaths.writableLocation(loc.DesktopLocation) or os.path.join(home, "Desktop")
    cands = [("Telegram", os.path.join(dl, "Telegram Desktop")),
             ("Telegram", os.path.join(home, "Downloads", "Telegram Desktop")),
             ("Telegram", os.path.join(docs, "Telegram Desktop")),
             ("Изображения", pics)]
    od = os.environ.get("OneDrive")
    if od:
        cands += [("OneDrive", os.path.join(od, "Pictures")), ("OneDrive", os.path.join(od, "Изображения"))]
    cands += [("Загрузки", dl), ("Рабочий стол", desk)]
    out, seen = [], set()
    for label, path in cands:
        try:
            if not os.path.isdir(path):
                continue
            key = os.path.normcase(os.path.realpath(path))
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append((label, os.path.normpath(path)))
    return out


def load_cover(path, w, h):
    """Картинка, обрезанная по центру до размера w x h (как object-fit: cover)."""
    rd = QImageReader(path)
    rd.setAutoTransform(True)                 # поворот по EXIF
    src = rd.size()
    if src.isValid() and (src.width() < 200 or src.height() < 200):
        return None                           # стикеры и значки пропускаем
    if src.isValid() and src.width() > 0 and src.height() > 0:
        k = max(w / src.width(), h / src.height()) * 1.5     # грузим чуть больше, но не весь снимок
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


class Shot:
    """Показанная фотография и её медленное движение (эффект Кена Бёрнса, как на Mac).
    Картинка загружена с запасом zmax: видимая часть плавно приближается/отдаляется и сдвигается."""

    def __init__(self, img, path, zmax):
        self.img, self.path, self.zmax, self.t0 = img, path, zmax, time.time()
        self.z0, self.z1 = (1.0, zmax) if random.random() < 0.5 else (zmax, 1.0)
        self.c0 = (random.uniform(-1, 1), random.uniform(-1, 1))
        self.c1 = (random.uniform(-1, 1), random.uniform(-1, 1))

    def draw(self, p, r, period, moving):
        iw, ih = self.img.width(), self.img.height()
        if moving and self.zmax > 1.0:
            u = clamp((time.time() - self.t0) / max(1.0, period))
            z = self.z0 + (self.z1 - self.z0) * u
            cx = self.c0[0] + (self.c1[0] - self.c0[0]) * u
            cy = self.c0[1] + (self.c1[1] - self.c0[1]) * u
        else:
            z, cx, cy = self.zmax, 0.0, 0.0
        sw, sh = iw / z, ih / z
        p.drawImage(r, self.img, QRectF((iw - sw) / 2 * (1 + cx), (ih - sh) / 2 * (1 + cy), sw, sh))


class PhotoCard(Card):
    KIND = "photos"
    TITLE = "Фото"
    SIZES = ("s", "m", "l", "xl")
    DEFAULT_SIZE = "l"
    INTERVALS = ((5, "5 секунд"), (10, "10 секунд"), (30, "30 секунд"), (60, "1 минута"),
                 (300, "5 минут"), (900, "15 минут"), (3600, "1 час"))
    FADE = 1.0
    _listed = Signal(object, object)
    _loaded = Signal(object, object, object)

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        cfg.setdefault("interval", 10)
        cfg.setdefault("shuffle", True)
        cfg.setdefault("recursive", True)
        cfg.setdefault("caption", True)
        cfg.setdefault("kenburns", True)
        self.files, self.order, self.idx = None, [], -1      # files=None - ещё не искали
        self.cur = self.prev = None           # Shot
        self.fade_t0 = 0.0
        self.token = 0
        self.loading = False
        self._listed.connect(self._on_list)
        self._loaded.connect(self._on_loaded)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.next)
        self.rescan = QTimer(self)
        self.rescan.timeout.connect(self.scan)
        self.rescan.start(10 * 60 * 1000)
        self.scan()

    # ----- файлы -----
    def source_key(self):
        if self.cfg.get("files"):
            return ("files", tuple(self.cfg["files"]))
        return ("folder", self.cfg.get("folder"), bool(self.cfg.get("recursive")))

    def scan(self):
        key = self.source_key()
        files = self.cfg.get("files")
        folder = self.cfg.get("folder")
        if not files and (not folder or not os.path.isdir(folder)):
            self.files = [] if folder else None
            self.update()
            return
        rec = bool(self.cfg.get("recursive"))

        def work():
            res = [f for f in files if os.path.isfile(f)] if files else list_images(folder, rec)
            try:
                self._listed.emit(key, res)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_list(self, key, files):
        if key != self.source_key():
            return
        first = not self.files
        cur = self.order[self.idx] if 0 <= self.idx < len(self.order) else None
        self.files = files
        self._reorder(keep=cur)
        self.update()
        if first and files:
            self.next()
        self._restart_timer()

    def _reorder(self, keep=None):
        self.order = list(self.files or [])
        if self.cfg.get("shuffle"):
            random.shuffle(self.order)
        self.idx = self.order.index(keep) if keep in self.order else -1

    def _restart_timer(self):
        self.timer.start(int(self.cfg.get("interval", 10)) * 1000)

    def next(self, step=1):
        if not self.order or self.loading:
            return
        self.idx = (self.idx + step) % len(self.order)
        if self.idx == 0 and step > 0 and self.cfg.get("shuffle") and len(self.order) > 2:
            last = self.order[-1]
            random.shuffle(self.order)
            if self.order[0] == last:
                self.order.append(self.order.pop(0))
        self._load(self.order[self.idx])

    def _load(self, path, instant=False):
        self.token += 1
        r = self.card_rect()
        dpr = self.devicePixelRatioF() or 1.0
        zmax = KB_ZOOM if self.cfg.get("kenburns") else 1.0
        tok, w, h = self.token, int(r.width() * dpr * zmax), int(r.height() * dpr * zmax)
        self.loading = True

        def work():
            try:
                img = load_cover(path, w, h)
            except Exception:
                img = None
            try:
                self._loaded.emit(tok, (path, instant, zmax), img)
            except RuntimeError:                 # виджет уже закрыт
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, tok, info, img):
        self.loading = False
        if tok != self.token:
            return
        path, instant, zmax = info
        if img is None:                        # битый файл или стикер - пропускаем
            if path in self.order and len(self.order) > 1:
                i = self.order.index(path)
                self.order.pop(i)
                self.idx = i - 1
                QTimer.singleShot(30, self.next)
            elif self.cur is None:
                self.files = []
                self.update()
            return
        old = self.cur
        self.cur = Shot(img, path, zmax)
        if instant and old is not None and old.zmax == zmax:   # та же картинка, другой размер
            self.cur.t0, self.cur.z0, self.cur.z1, self.cur.c0, self.cur.c1 = old.t0, old.z0, old.z1, old.c0, old.c1
        self.prev = None if instant or not self.animated else old
        self.fade_t0 = time.time()
        self.update()

    def size_changed(self):
        if self.cur is not None:
            self._load(self.cur.path, instant=True)

    # ----- рисование -----
    def paint(self, p, r, th):
        if self.cur is None:
            self._paint_empty(p, r, th)
            return
        moving = bool(self.cfg.get("kenburns")) and self.animated
        period = int(self.cfg.get("interval", 10)) + self.FADE * 2
        p.save()
        p.setOpacity(p.opacity() * self.opacity())
        t = 1.0
        if self.prev is not None:
            t = smooth((time.time() - self.fade_t0) / self.FADE)
            if t >= 1.0:
                self.prev = None
            else:
                self.prev.draw(p, r, period, moving)
                self.want_frame(16)
        p.setOpacity(p.opacity() * t)
        self.cur.draw(p, r, period, moving)
        p.restore()
        if moving:
            self.want_frame(40)                # медленное движение: 25 кадров в секунду хватает
        if self.cfg.get("caption") and self.cfg["size"] != "s":
            g = QLinearGradient(0, r.bottom() - 70, 0, r.bottom())
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(1, QColor(0, 0, 0, 120))
            p.fillRect(QRectF(r.x(), r.bottom() - 70, r.width(), 70), g)
            path = self.cur.path
            try:
                dt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
                date = "%d %s %d" % (dt.day, MONTHS_GEN[dt.month - 1], dt.year)
            except Exception:
                date = ""
            name = os.path.basename(os.path.dirname(path))
            text(p, QRectF(r.x() + 18, r.bottom() - 46, r.width() - 36, 20), name, font(14, SEMI), WHITE, AL | AVC)
            text(p, QRectF(r.x() + 18, r.bottom() - 27, r.width() - 36, 18), date, font(12),
                 QColor(255, 255, 255, 200), AL | AVC)

    def _paint_empty(self, p, r, th):
        cx, cy = r.center().x(), r.center().y() - 18
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
        msg = ("В этой папке нет фотографий.\nНажми, чтобы выбрать другую" if self.files == []
               else "Нажми, чтобы выбрать\nпапку с фотографиями")
        p.setFont(font(12))
        p.setPen(th["fg2"])
        p.drawText(QRectF(r.x() + 10, cy + 30, r.width() - 20, 44),
                   int(AC | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), msg)

    # ----- выбор фото -----
    def clicked(self, pos):
        if self.cur is None:
            self.source_menu().exec(self.mapToGlobal(pos.toPoint()))

    def activate(self):
        if self.cur is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.cur.path))

    def source_menu(self, menu=None):
        if menu is None:
            menu = QMenu(self)
            menu.setStyleSheet(self.mgr.menu_css())
        for label, path in photo_places():
            n = count_images(path)
            title = ("Telegram — " + path) if label == "Telegram" else label
            title += ("   (%d фото)" % n) if n else "   (пусто)"
            a = menu.addAction(title)
            a.setCheckable(True)
            a.setChecked(not self.cfg.get("files") and
                         os.path.normcase(self.cfg.get("folder") or "") == os.path.normcase(path))
            a.triggered.connect(lambda _=False, pth=path: self.set_folder(pth))
        menu.addSeparator()
        menu.addAction("Другая папка...").triggered.connect(self.choose_folder)
        menu.addAction("Выбрать отдельные фото...").triggered.connect(self.choose_files)
        return menu

    def set_folder(self, folder):
        self.cfg["folder"] = os.path.normpath(folder)
        self.cfg.pop("files", None)
        self._reset_source()

    def _reset_source(self):
        self.files, self.order, self.idx = None, [], -1
        self.cur = self.prev = None
        self.mgr.save()
        self.update()
        self.scan()

    def _start_dir(self):
        return self.cfg.get("folder") or QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.PicturesLocation)

    def choose_folder(self):
        d = QFileDialog.getExistingDirectory(
            None, "Выбери ПАПКУ с фото (сами фото в этом окне не видны - это нормально)", self._start_dir())
        if d:
            self.set_folder(d)

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            None, "Выбери фото (можно сразу несколько: Ctrl+A)", self._start_dir(),
            "Фото (%s);;Все файлы (*)" % " ".join("*" + e for e in sorted(IMG_EXT)))
        if files:
            self.cfg["files"] = [os.path.normpath(f) for f in files]
            self.cfg["folder"] = os.path.dirname(self.cfg["files"][0])
            self._reset_source()

    def extra_menu(self, menu):
        self.source_menu(menu.addMenu("Откуда брать фото"))
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
                           ("kenburns", "Медленное приближение (как на Mac)"),
                           ("caption", "Подпись (папка и дата)")):
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg.get(key)))
            a.toggled.connect(lambda v, k=key: self._set(k, bool(v)))

    def reveal(self):
        if self.cur is None:
            return
        if IS_WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(self.cur.path)], creationflags=NO_WINDOW)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.cur.path)))

    def _set(self, key, val):
        self.cfg[key] = val
        self.mgr.save()
        if key == "interval":
            self._restart_timer()
        elif key == "shuffle":
            self._reorder(keep=self.cur.path if self.cur else None)
        elif key == "recursive":
            self.scan()
        elif key == "kenburns":
            self.size_changed()
        self.update()

    def closing(self):
        self.timer.stop()
        self.rescan.stop()


# ---------------------------------------------------------------------------
#  Виджет "Погода"
# ---------------------------------------------------------------------------
WEATHER_BG = {   # (верх, низ) для дня (1) и ночи (0)
    ("clear", 1): ("#2F80D8", "#73B6F0"), ("clear", 0): ("#0B1736", "#2A3B66"),
    ("partly", 1): ("#3B7BC4", "#83AFD9"), ("partly", 0): ("#141F3A", "#34446A"),
    ("cloudy", 1): ("#5B6E83", "#8EA0B4"), ("cloudy", 0): ("#1E2531", "#3B4555"),
    ("fog", 1): ("#7D8794", "#AEB6C0"), ("fog", 0): ("#2B3038", "#4A515C"),
    ("rain", 1): ("#3F5368", "#6A7F94"), ("rain", 0): ("#151C27", "#323D4E"),
    ("snow", 1): ("#6283AC", "#A7BEDA"), ("snow", 0): ("#1C2840", "#45577A"),
    ("storm", 1): ("#2A2F45", "#4E5470"), ("storm", 0): ("#12141F", "#2C3045"),
}


class WeatherCard(Card):
    KIND = "weather"
    TITLE = "Погода"
    DEFAULT_SIZE = "m"
    _got = Signal(object, object)

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        cfg.setdefault("anim", True)
        self.data = cfg.get("cache")
        self.error = None
        self.busy = False
        self.parts = []
        self.parts_kind = None
        self.flash = 0.0
        self.t0 = time.time()
        self._got.connect(self._on_data)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(20 * 60 * 1000)
        age = time.time() - float(cfg.get("cache_ts", 0) or 0)
        QTimer.singleShot(200 if age > 15 * 60 or not self.data else 15 * 60 * 1000 - int(age * 1000),
                          self.refresh)

    # ----- данные -----
    def refresh(self, relocate=False, city=None):
        if self.busy:
            return
        self.busy = True
        self.update()
        cfg = dict(self.cfg)

        def work():
            res, err = None, None
            try:
                if DEMO:
                    res = ((city or cfg.get("city") or "Москва", 55.75, 37.62), demo_weather())
                else:
                    if city:
                        loc = geocode(city)
                        if loc is None:
                            raise LookupError("Город «%s» не найден" % city)
                    elif relocate or cfg.get("lat") is None:
                        loc = locate_by_ip() or ("Москва", 55.7558, 37.6173)
                    else:
                        loc = (cfg.get("city") or "", float(cfg["lat"]), float(cfg["lon"]))
                    res = (loc, fetch_weather(loc[1], loc[2]))
            except LookupError as ex:
                err = str(ex)
            except Exception:
                err = "Нет связи с сервером погоды"
            try:
                self._got.emit(res, err)
            except RuntimeError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _on_data(self, res, err):
        self.busy = False
        self.error = err
        if res is not None:
            (city, lat, lon), data = res
            self.cfg.update({"city": city, "lat": lat, "lon": lon, "cache": data, "cache_ts": time.time()})
            self.data = data
            self.mgr.save()
        self.update()

    # ----- фон и частицы -----
    def wkind(self):
        if not self.data:
            return "cloudy", 1
        return wmo(self.data["code"])[1], int(self.data.get("day", 1))

    def paint_bg(self, p, path, r, th):
        top, bot = WEATHER_BG.get(self.wkind(), ("#3B7BC4", "#83AFD9"))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(top))
        g.setColorAt(1, QColor(bot))
        p.fillPath(path, g)

    def _particles(self, p, r, kind):
        if kind != self.parts_kind:
            self.parts_kind = kind
            heavy = self.data and int(self.data["code"]) in (65, 67, 75, 82, 86, 99)
            n = {"rain": 70, "storm": 80, "snow": 60}.get(kind, 0)
            n = int(n * (1.6 if heavy else 1.0) * r.width() * r.height() / (360 * 376) * 1.6)
            self.parts = [[random.random(), random.random(), random.uniform(0.5, 1.0), random.random()]
                          for _ in range(n)]
        if not self.parts:
            return
        dt = self._dt
        p.save()
        if kind == "snow":
            p.setPen(NOPEN)
            ts = time.time()
            for pt in self.parts:
                pt[1] += dt * 0.09 * pt[2] * 376 / r.height()
                pt[0] += dt * 0.02 * math.sin(ts * 1.2 + pt[3] * 6.28)
                if pt[1] > 1.02:
                    pt[1], pt[0] = -0.02, random.random()
                pt[0] %= 1.0
                rad = 0.8 + 2.0 * pt[2]
                p.setBrush(QColor(255, 255, 255, int(90 + 140 * pt[2])))
                p.drawEllipse(QPointF(r.x() + pt[0] * r.width(), r.y() + pt[1] * r.height()), rad, rad)
        else:
            for pt in self.parts:
                pt[1] += dt * 1.1 * pt[2] * 376 / r.height()
                pt[0] -= dt * 0.12 * pt[2]
                if pt[1] > 1.05:
                    pt[1], pt[0] = -0.05, random.uniform(0, 1.15)
                x, y = r.x() + pt[0] * r.width(), r.y() + pt[1] * r.height()
                p.setPen(QPen(QColor(200, 225, 255, int(50 + 90 * pt[2])), 1.2))
                p.drawLine(QPointF(x, y), QPointF(x + 3 * pt[2], y - 12 * pt[2]))
            if kind == "storm":
                if self.flash <= 0 and random.random() < dt * 0.25:
                    self.flash = 1.0
                if self.flash > 0:
                    p.fillRect(r, QColor(255, 255, 255, int(110 * self.flash ** 2)))
                    self.flash -= dt * 3.0
        p.restore()

    # ----- рисование -----
    def paint(self, p, r, th):
        anim = self.animated and self.cfg.get("anim", True)
        t = (time.time() - self.t0) if anim else 0.0
        if anim:
            self.want_frame(33)
        if not self.data:
            msg = self.error or "Загружаю погоду..."
            draw_wicon(p, "cloudy", 1, r.center().x(), r.center().y() - 18, 56, t)
            text(p, QRectF(r.x() + 10, r.center().y() + 22, r.width() - 20, 22), msg, font(13), WHITE)
            return
        d = self.data
        kind, day = self.wkind()
        if anim:
            self._particles(p, r, kind)
        size = self.cfg["size"]
        city = self.cfg.get("city") or ""
        cond = wmo(d["code"])[0]
        temp = self.av("temp", float(d["temp"]), 5.0, start=float(d["temp"]) - 6)
        hl = "Макс. %s, мин. %s" % (deg(d["max"]), deg(d["min"])) if d.get("max") is not None else ""
        soft = QColor(255, 255, 255, 210)
        if size == "s":
            text(p, QRectF(r.x() + 16, r.y() + 12, r.width() - 32, 20), city, font(14, SEMI), WHITE, AL | AVC)
            text(p, QRectF(r.x() + 16, r.y() + 30, r.width() - 32, 54), deg(temp), font(44, LIGHT), WHITE, AL | AVC)
            draw_wicon(p, kind, day, r.x() + 32, r.y() + 106, 34, t)
            text(p, QRectF(r.x() + 16, r.y() + 126, r.width() - 32, 18), cond, font(12, SEMI), WHITE, AL | AVC)
            text(p, QRectF(r.x() + 16, r.y() + 143, r.width() - 32, 16), hl, font(11), soft, AL | AVC)
            return
        text(p, QRectF(r.x() + 18, r.y() + 12, r.width() * 0.6, 22), city, font(15, SEMI), WHITE, AL | AVC)
        text(p, QRectF(r.x() + 18, r.y() + 32, 160, 52), deg(temp), font(44, LIGHT), WHITE, AL | AVC)
        draw_wicon(p, kind, day, r.right() - 40, r.y() + 34, 36, t)
        text(p, QRectF(r.right() - 220, r.y() + 56, 202, 18), cond, font(12, SEMI), WHITE, AR | AVC)
        text(p, QRectF(r.right() - 220, r.y() + 73, 202, 16), hl, font(11), soft, AR | AVC)
        if self.error:
            text(p, QRectF(r.x() + 18, r.y() + 82, r.width() - 36, 14), self.error, font(10),
                 QColor(255, 255, 255, 170), AL | AVC)
        hours = d.get("hours") or []
        if hours:
            top = r.y() + 98
            p.setPen(QPen(QColor(255, 255, 255, 50), 1))
            p.drawLine(QPointF(r.x() + 18, top - 4), QPointF(r.right() - 18, top - 4))
            slot = (r.width() - 24) / len(hours)
            for i, h in enumerate(hours):
                cx = r.x() + 12 + slot * (i + 0.5)
                text(p, QRectF(cx - slot / 2, top, slot, 16), h["label"], font(11, SEMI), soft)
                draw_wicon(p, wmo(h["code"])[1], h.get("day", 1), cx, top + 30, 22, t + i)
                text(p, QRectF(cx - slot / 2, top + 44, slot, 18), deg(h["temp"]), font(13, SEMI), WHITE)
        days = d.get("days") or []
        if size != "l" or not days:
            return
        top = r.y() + 172
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.drawLine(QPointF(r.x() + 18, top - 4), QPointF(r.right() - 18, top - 4))
        lo = min(x["min"] for x in days)
        hi = max(x["max"] for x in days)
        span = max(1.0, hi - lo)
        row = (r.bottom() - 10 - top) / len(days)
        for i, x in enumerate(days):
            y = top + i * row
            text(p, QRectF(r.x() + 18, y, 70, row), x["label"], font(13, SEMI), WHITE, AL | AVC)
            draw_wicon(p, wmo(x["code"])[1], 1, r.x() + 106, y + row / 2, 20, t + i * 0.7)
            text(p, QRectF(r.x() + 124, y, 46, row), deg(x["min"]), font(13), QColor(255, 255, 255, 170), AR | AVC)
            text(p, QRectF(r.right() - 64, y, 46, row), deg(x["max"]), font(13, SEMI), WHITE, AR | AVC)
            bar = QRectF(r.x() + 180, y + row / 2 - 2.5, r.right() - 70 - (r.x() + 180), 5)
            p.setPen(NOPEN)
            p.setBrush(QColor(0, 0, 0, 50))
            p.drawRoundedRect(bar, 2.5, 2.5)
            grow = self.av("bar%d" % i, 1.0, 4.0 + i * 0.4, start=0.0)
            a = bar.x() + bar.width() * (x["min"] - lo) / span
            b = bar.x() + bar.width() * (x["max"] - lo) / span
            b = a + (b - a) * grow
            g = QLinearGradient(bar.x(), 0, bar.right(), 0)
            g.setColorAt(0, QColor("#64D2FF"))
            g.setColorAt(0.5, QColor("#A8E063"))
            g.setColorAt(1, QColor("#FFB340"))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(a, bar.y(), max(5.0, b - a), 5), 2.5, 2.5)
            if i == 0 and d.get("temp") is not None and lo <= d["temp"] <= hi:
                cx = bar.x() + bar.width() * (d["temp"] - lo) / span
                p.setBrush(WHITE)
                p.setPen(QPen(QColor(0, 0, 0, 60), 1))
                p.drawEllipse(QPointF(cx, bar.center().y()), 3.5, 3.5)

    # ----- меню -----
    def extra_menu(self, menu):
        menu.addAction("Указать город...").triggered.connect(self.ask_city)
        menu.addAction("Определить место автоматически").triggered.connect(lambda: self.refresh(relocate=True))
        menu.addAction("Обновить").triggered.connect(lambda: self.refresh())
        a = menu.addAction("Живой фон (снег, дождь)")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("anim", True)))
        a.toggled.connect(self._set_anim)

    def _set_anim(self, v):
        self.cfg["anim"] = bool(v)
        self.mgr.save()
        self.update()

    def ask_city(self):
        name, ok = QInputDialog.getText(None, "Погода", "Город (например: Казань, Минск, Алматы):",
                                        text=self.cfg.get("city") or "")
        if ok and name.strip():
            self.refresh(city=name.strip())

    def activate(self):
        if self.cfg.get("lat") is not None:
            QDesktopServices.openUrl(QUrl("https://yandex.ru/pogoda/?lat=%.4f&lon=%.4f"
                                          % (float(self.cfg["lat"]), float(self.cfg["lon"]))))

    def closing(self):
        self.timer.stop()


# ---------------------------------------------------------------------------
#  Виджет "Часы"
# ---------------------------------------------------------------------------
class ClockCard(CalendarMixin, Card):
    KIND = "clock"
    TITLE = "Часы"
    DEFAULT_SIZE = "s"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.cal_init()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)

    def paint(self, p, r, th):
        now = datetime.datetime.now()
        size = self.cfg["size"]
        if size == "s":
            self._analog(p, r.center().x(), r.center().y(), 68, now, th)
        elif size == "m":
            self._analog(p, r.x() + 85, r.center().y(), 64, now, th)
            tx = r.x() + 170
            text(p, QRectF(tx, r.y() + 30, r.right() - tx - 16, 48), now.strftime("%H:%M"),
                 font(40, SEMI), th["fg"], AL | AVC)
            text(p, QRectF(tx, r.y() + 82, r.right() - tx - 16, 20), WEEKDAYS[now.weekday()],
                 font(14, SEMI), th["accent"], AL | AVC)
            text(p, QRectF(tx, r.y() + 102, r.right() - tx - 16, 20),
                 "%d %s %d" % (now.day, MONTHS_GEN[now.month - 1], now.year), font(13), th["fg2"], AL | AVC)
        else:
            self._analog(p, r.x() + 88, r.y() + 90, 66, now, th)
            tx = r.x() + 176
            text(p, QRectF(tx, r.y() + 36, r.right() - tx - 18, 46), now.strftime("%H:%M"),
                 font(38, SEMI), th["fg"], AL)
            text(p, QRectF(tx, r.y() + 86, r.right() - tx - 18, 20), WEEKDAYS[now.weekday()],
                 font(14, SEMI), th["accent"], AL)
            text(p, QRectF(tx, r.y() + 106, r.right() - tx - 18, 20),
                 "%d %s %d" % (now.day, MONTHS_GEN[now.month - 1], now.year), font(13), th["fg2"], AL)
            p.setPen(QPen(th["line"], 1))
            p.drawLine(QPointF(r.x() + 20, r.y() + 176), QPointF(r.right() - 20, r.y() + 176))
            self.paint_calendar(p, QRectF(r.x() + 20, r.y() + 184, r.width() - 40, r.height() - 196), th, 13)

    def _analog(self, p, cx, cy, rad, now, th):
        p.save()
        p.setPen(NOPEN)
        p.setBrush(th["face"])
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        if th["mode"] == "neon":
            p.setPen(QPen(th["glow1"], 1.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), rad - 0.7, rad - 0.7)
        ink = th["ink"]
        p.setFont(font(rad * 0.22, SEMI))
        p.setPen(ink)
        for h in range(1, 13):
            a = math.radians(h * 30)
            x, y = cx + math.sin(a) * rad * 0.72, cy - math.cos(a) * rad * 0.72
            p.drawText(QRectF(x - 14, y - 12, 28, 24), int(AC), str(h))
        p.setPen(QPen(QColor(ink.red(), ink.green(), ink.blue(), 90), 1))
        for m in range(60):
            if m % 5:
                a = math.radians(m * 6)
                p.drawLine(QPointF(cx + math.sin(a) * rad * 0.9, cy - math.cos(a) * rad * 0.9),
                           QPointF(cx + math.sin(a) * rad * 0.95, cy - math.cos(a) * rad * 0.95))
        sec = now.second + (now.microsecond / 1e6 if self.animated else 0.0)
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
        hand(sec * 6, 0.86, max(1.2, rad * 0.022), th["hand"], tail=0.16)
        p.setPen(NOPEN)
        p.setBrush(th["hand"])
        p.drawEllipse(QPointF(cx, cy), rad * 0.055, rad * 0.055)
        p.restore()
        if self.animated:
            self.want_frame(50)             # плавная секундная стрелка


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
        neon = self.theme["mode"] == "neon"
        cols = (QColor("#00E5FF"), QColor("#FF2D95"), QColor("#B4FF39")) if neon else \
               (BLUE, QColor("#BF5AF2"), QColor("#FF9F0A"))
        cols = [self.ring_col(c) for c in cols]
        return [("ЦП", self.av("cpu", s.cpu, 4.0, 0.0), "%d%%" % s.cpu, cols[0]),
                ("ОЗУ", self.av("mem", s.mem[0], 4.0, 0.0), "%s/%s ГБ" % (gb(s.mem[1]), gb(s.mem[2])), cols[1]),
                ("Диск " + s.disk_name.rstrip("\\"), self.av("disk", s.disk[0], 4.0, 0.0),
                 "своб. %s ГБ" % gb(s.disk[2] - s.disk[1]), cols[2])]

    def paint(self, p, r, th):
        items = self.items()
        size = self.cfg["size"]
        if size == "s":
            pos = ((0.3, 0.32), (0.7, 0.32), (0.5, 0.72))
            for (fx, fy), (name, val, _det, col) in zip(pos, items):
                cx, cy = r.x() + r.width() * fx, r.y() + r.height() * fy
                draw_ring(p, cx, cy, 30, 6, val / 100.0, col, th["track"])
                text(p, QRectF(cx - 30, cy - 15, 60, 18), "%d%%" % round(val), font(13, SEMI), th["fg"])
                text(p, QRectF(cx - 30, cy + 2, 60, 14), name.split()[0], font(10), th["fg2"])
        elif size == "m":
            slot = r.width() / 3
            for i, (name, val, det, col) in enumerate(items):
                cx = r.x() + slot * (i + 0.5)
                draw_ring(p, cx, r.y() + 66, 36, 7, val / 100.0, col, th["track"])
                text(p, QRectF(cx - 36, r.y() + 54, 72, 24), "%d%%" % round(val), font(17, SEMI), th["fg"])
                text(p, QRectF(cx - slot / 2, r.y() + 112, slot, 18), name, font(12, SEMI), th["fg"])
                text(p, QRectF(cx - slot / 2 + 4, r.y() + 130, slot - 8, 16), det, font(11), th["fg2"])
        else:
            text(p, QRectF(r.x() + 20, r.y() + 14, r.width() - 40, 24), "Система", font(15, SEMI), th["fg"], AL | AVC)
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
                lc = items[0][3]
                g = QLinearGradient(0, gr.y(), 0, gr.bottom())
                g.setColorAt(0, QColor(lc.red(), lc.green(), lc.blue(), 110))
                g.setColorAt(1, QColor(lc.red(), lc.green(), lc.blue(), 0))
                p.fillPath(fill, g)
                p.setPen(QPen(lc, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            for i, (name, val, det, col) in enumerate(items):
                y = r.y() + 180 + i * 62
                text(p, QRectF(r.x() + 20, y, 160, 20), name, font(13, SEMI), th["fg"], AL | AVC)
                text(p, QRectF(r.x() + 20, y, r.width() - 40, 20), "%d%%" % round(val), font(14, SEMI),
                     th["fg"], AR | AVC)
                draw_bar(p, QRectF(r.x() + 20, y + 26, r.width() - 40, 8), val / 100.0, col, th["track"])
                text(p, QRectF(r.x() + 20, y + 38, r.width() - 40, 16), det, font(11), th["fg2"], AL | AVC)

    def activate(self):
        if IS_WIN:
            subprocess.Popen(["taskmgr"], creationflags=NO_WINDOW)


# ---------------------------------------------------------------------------
#  Общие мелочи для новых виджетов: открыть программу, хранить ключ, кнопки плеера
# ---------------------------------------------------------------------------
def open_target(*targets):
    """Открыть первую сработавшую цель: протокол программы (discord://, yandexmusic://) или ссылку."""
    for t in targets:
        try:
            if IS_WIN and "://" in t and not t.startswith("http"):
                os.startfile(t)                     # noqa - есть только в Windows
                return True
            if os.path.isfile(t):
                subprocess.Popen([t], creationflags=NO_WINDOW if IS_WIN else 0)
                return True
            if t.startswith("http"):
                QDesktopServices.openUrl(QUrl(t))
                return True
        except Exception:
            continue
    return False


if IS_WIN:
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def secret_protect(text):
    """Шифруем ключ средствами Windows (DPAPI): расшифровать сможет только этот пользователь на этом ПК."""
    raw = text.encode("utf-8")
    if IS_WIN:
        try:
            buf = ctypes.create_string_buffer(raw, len(raw))
            inp = DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
            out = DATA_BLOB()
            if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
                data = ctypes.string_at(out.pbData, out.cbData)
                ctypes.windll.kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))
                return "dpapi:" + base64.b64encode(data).decode()
        except Exception:
            pass
    return "b64:" + base64.b64encode(raw).decode()


def secret_reveal(s):
    if not s:
        return ""
    try:
        kind, data = s.split(":", 1)
        raw = base64.b64decode(data)
        if kind == "b64":
            return raw.decode("utf-8")
        if kind == "dpapi" and IS_WIN:
            buf = ctypes.create_string_buffer(raw, len(raw))
            inp = DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
            out = DATA_BLOB()
            if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0,
                                                        ctypes.byref(out)):
                res = ctypes.string_at(out.pbData, out.cbData)
                ctypes.windll.kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))
                return res.decode("utf-8")
    except Exception:
        pass
    return ""


def pip_install(*pkgs):
    """Доставить библиотеку, если программа запущена из .pyw (в .exe всё уже внутри)."""
    if FROZEN:
        return False
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check"] + list(pkgs),
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=NO_WINDOW if IS_WIN else 0, timeout=600)
        importlib.invalidate_caches()
        return True
    except Exception:
        return False


def draw_media_icon(p, kind, cx, cy, s, color):
    """Кнопки плеера: play, pause, prev, next."""
    p.save()
    p.setPen(NOPEN)
    p.setBrush(color)
    if kind == "pause":
        w = s * 0.22
        p.drawRoundedRect(QRectF(cx - s * 0.3, cy - s * 0.4, w, s * 0.8), w * 0.3, w * 0.3)
        p.drawRoundedRect(QRectF(cx + s * 0.08, cy - s * 0.4, w, s * 0.8), w * 0.3, w * 0.3)
    elif kind == "play":
        path = QPainterPath()
        path.moveTo(cx - s * 0.28, cy - s * 0.42)
        path.lineTo(cx + s * 0.42, cy)
        path.lineTo(cx - s * 0.28, cy + s * 0.42)
        path.closeSubpath()
        p.drawPath(path)
    else:
        d = 1 if kind == "next" else -1
        for k in (0, 1):
            path = QPainterPath()
            x0 = cx + d * (-s * 0.36 + k * s * 0.34)
            path.moveTo(x0, cy - s * 0.3)
            path.lineTo(x0 + d * s * 0.34, cy)
            path.lineTo(x0, cy + s * 0.3)
            path.closeSubpath()
            p.drawPath(path)
        p.drawRect(QRectF(cx + d * s * 0.32 - s * 0.04, cy - s * 0.3, s * 0.08, s * 0.6))
    p.restore()


def draw_note(p, cx, cy, s, color):
    p.save()
    p.setPen(NOPEN)
    p.setBrush(color)
    p.drawEllipse(QPointF(cx - s * 0.18, cy + s * 0.26), s * 0.16, s * 0.12)
    p.drawEllipse(QPointF(cx + s * 0.26, cy + s * 0.16), s * 0.16, s * 0.12)
    p.drawRect(QRectF(cx - s * 0.06, cy - s * 0.36, s * 0.07, s * 0.62))
    p.drawRect(QRectF(cx + s * 0.38, cy - s * 0.46, s * 0.07, s * 0.62))
    path = QPainterPath()
    path.moveTo(cx - s * 0.06, cy - s * 0.36)
    path.lineTo(cx + s * 0.45, cy - s * 0.46)
    path.lineTo(cx + s * 0.45, cy - s * 0.3)
    path.lineTo(cx - s * 0.06, cy - s * 0.2)
    path.closeSubpath()
    p.drawPath(path)
    p.restore()


def draw_bubble(p, cx, cy, s, color, dots=True):
    """Облачко чата."""
    p.save()
    path = QPainterPath()
    path.addRoundedRect(QRectF(cx - s * 0.48, cy - s * 0.38, s * 0.96, s * 0.66), s * 0.2, s * 0.2)
    tail = QPainterPath()
    tail.moveTo(cx - s * 0.22, cy + s * 0.22)
    tail.lineTo(cx - s * 0.3, cy + s * 0.46)
    tail.lineTo(cx, cy + s * 0.24)
    tail.closeSubpath()
    p.setPen(NOPEN)
    p.setBrush(color)
    p.drawPath(path.united(tail))
    if dots:
        p.setBrush(QColor(0, 0, 0, 110))
        for k in (-1, 0, 1):
            p.drawEllipse(QPointF(cx + k * s * 0.22, cy - s * 0.05), s * 0.065, s * 0.065)
    p.restore()


def fmt_time(sec):
    sec = max(0, int(sec))
    return "%d:%02d" % (sec // 60, sec % 60) if sec < 3600 else "%d:%02d:%02d" % (sec // 3600, sec // 60 % 60, sec % 60)


def blur_image(img, w, h, strength=12):
    if img is None or img.isNull():
        return None
    k = max(w / img.width(), h / img.height())
    sm = Qt.TransformationMode.SmoothTransformation
    ign = Qt.AspectRatioMode.IgnoreAspectRatio
    cov = img.scaled(max(1, int(img.width() * k)), max(1, int(img.height() * k)), ign, sm)
    cov = cov.copy((cov.width() - w) // 2, (cov.height() - h) // 2, w, h)
    small = cov.scaled(max(2, w // strength), max(2, h // strength), ign, sm)
    return small.scaled(w, h, ign, sm)


# ---------------------------------------------------------------------------
#  Музыка: что играет в Яндекс Музыке (и любом другом плеере) - через Windows
# ---------------------------------------------------------------------------
_WINRT_PKGS = ("winrt-runtime", "winrt-Windows.Foundation", "winrt-Windows.Foundation.Collections",
               "winrt-Windows.Media.Control", "winrt-Windows.Storage.Streams")


def _winrt_try():
    for base in ("winrt", "winsdk"):
        try:
            mc = importlib.import_module(base + ".windows.media.control")
            ss = importlib.import_module(base + ".windows.storage.streams")
            return mc, ss
        except Exception:
            continue
    return None


def _secs(v):
    if v is None:
        return 0.0
    if hasattr(v, "total_seconds"):
        return v.total_seconds()
    try:
        return float(v) / 1e7                   # TimeSpan в единицах по 100 нс
    except Exception:
        return 0.0


def media_key(name):
    """Запасной вариант управления: мультимедийные клавиши (работают с любым плеером)."""
    vk = {"toggle": 0xB3, "next": 0xB0, "prev": 0xB1}.get(name)
    if IS_WIN and vk:
        try:
            _user32.keybd_event(vk, 0, 0, 0)
            _user32.keybd_event(vk, 0, 2, 0)
        except Exception:
            pass


def app_title(aumid):
    a = (aumid or "").lower()
    for key, title in (("yandex", "Яндекс Музыка"), ("spotify", "Spotify"), ("chrome", "Браузер Chrome"),
                       ("msedge", "Браузер Edge"), ("firefox", "Браузер Firefox"), ("opera", "Браузер Opera"),
                       ("browser", "Яндекс Браузер"), ("vk", "VK Музыка"), ("zune", "Музыка Windows"),
                       ("media", "Медиаплеер")):
        if key in a:
            return title
    return "Плеер"


class MediaService(QObject):
    """Опрашивает "Системные элементы управления мультимедиа" Windows (то самое окошко, что
    всплывает при регулировке громкости). Туда пишут Яндекс Музыка, браузеры, Spotify и другие."""
    updated = Signal()
    _got = Signal(object)

    def __init__(self, mgr):
        super().__init__()
        self.mgr = mgr
        self.state = None
        self.error = None
        self.loop = None
        self.session = None
        self._got.connect(self._on)
        self._demo_play = True
        threading.Thread(target=self._run, daemon=True).start()

    # ----- поток опроса -----
    def _emit(self, payload):
        try:
            self._got.emit(payload)
        except RuntimeError:
            pass

    def _run(self):
        if DEMO:
            img = None
            for path in list_images(os.path.join(os.path.expanduser("~"), "Downloads", "Telegram Desktop"), False)[:1]:
                img = QImage(path)
            t0 = time.time()
            while True:
                self._emit({"state": {"title": "Снег идёт", "artist": "Тестовый исполнитель", "album": "",
                                      "app": "Yandex.Music", "playing": self._demo_play,
                                      "pos": 74.0 + ((time.time() - t0) if self._demo_play else 0), "dur": 213.0,
                                      "stamp": time.time(), "cover": img, "key": ("Снег идёт", "")}})
                time.sleep(1.0)
        if not IS_WIN:
            self._emit({"error": "Работает только в Windows"})
            return
        mods = _winrt_try()
        if mods is None:
            self._emit({"error": "Ставлю компонент для связи с плеером..."})
            if pip_install(*_WINRT_PKGS):
                mods = _winrt_try()
        if mods is None:
            self._emit({"error": "Нет компонента winrt. Выполни: pip install " + " ".join(_WINRT_PKGS)})
            return
        import asyncio
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._poll(mods))
        except Exception:
            self._emit({"error": "Не удалось подключиться к плееру Windows"})

    def log(self, msg):
        """Журнал ошибок связи с плеером: %APPDATA%\\SnowWidgets\\music.log (последние 300 строк)."""
        try:
            path = os.path.join(DATA_DIR, "music.log")
            lines = []
            if os.path.exists(path):
                with open(path, encoding="utf-8", errors="replace") as fh:
                    lines = fh.read().splitlines()[-299:]
            lines.append(time.strftime("%Y-%m-%d %H:%M:%S ") + msg)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except Exception:
            pass

    async def _thumb(self, props, ss):
        import asyncio
        try:
            ref = props.thumbnail
            if ref is None:
                return None
            stream = await asyncio.wait_for(ref.open_read_async(), 4)
            size = int(stream.size)
            if not size or size > 20 * 1024 * 1024:
                return None
            buf = ss.Buffer(size)
            res = await asyncio.wait_for(stream.read_async(buf, size, ss.InputStreamOptions.READ_AHEAD), 4)
            try:
                data = bytes(memoryview(res))
            except Exception:
                reader = ss.DataReader.from_buffer(res)
                arr = bytearray(res.length)
                reader.read_bytes(arr)
                data = bytes(arr)
            img = QImage.fromData(data)
            return None if img.isNull() else img
        except Exception as ex:
            self.log("обложка: %r" % (ex,))
            return None

    @staticmethod
    def _status(s):
        try:
            return int(s.get_playback_info().playback_status)
        except Exception:
            return -1

    def _pick(self, mgr):
        """Какой плеер показывать: сначала играющая Яндекс Музыка, потом любой играющий,
        потом тот, что показывали в прошлый раз, потом "текущий" по мнению Windows."""
        try:
            sessions = list(mgr.get_sessions() or [])
        except Exception:
            sessions = []
        only_ya = bool(self.mgr.cfg.get("music_only_yandex"))
        aid = lambda s: (getattr(s, "source_app_user_model_id", "") or "")
        ya = [s for s in sessions if "yandex" in aid(s).lower()]
        pool = ya if (ya or only_ya) else sessions
        playing = [s for s in pool if self._status(s) == 4]
        if playing:
            return playing[0]
        last = getattr(self, "_last_app", None)
        for s in pool:
            if aid(s) == last:
                return s
        if only_ya:
            return ya[0] if ya else None
        if ya:
            return ya[0]
        try:
            return mgr.get_current_session() or (sessions[0] if sessions else None)
        except Exception:
            return sessions[0] if sessions else None

    async def _poll(self, mods):
        import asyncio
        mc, ss = mods
        mgr = None
        last_key, cover, fails = None, None, 0
        while True:
            st = None
            try:
                if mgr is None or fails >= 5:              # после череды ошибок подключаемся заново
                    mgr = await asyncio.wait_for(mc.GlobalSystemMediaTransportControlsSessionManager.request_async(), 8)
                    fails = 0
                s = self._pick(mgr)
                self.session = s
                if s is not None:
                    props = await asyncio.wait_for(s.try_get_media_properties_async(), 3)
                    title = (props.title or "").strip()
                    if title:
                        playing = self._status(s) == 4
                        tl = s.get_timeline_properties()
                        app = s.source_app_user_model_id or ""
                        key = (title, props.artist, app)
                        if key != last_key:
                            last_key = key
                            cover = await self._thumb(props, ss)
                        pos = _secs(tl.position) - _secs(tl.start_time)
                        try:
                            lu = tl.last_updated_time
                            if playing and lu is not None and lu.year > 2000:
                                age = (datetime.datetime.now(datetime.timezone.utc) - lu).total_seconds()
                                if 0 < age < 6 * 3600:
                                    pos += age
                        except Exception:
                            pass
                        self._last_app = app
                        st = {"title": title, "artist": props.artist or props.album_artist or "",
                              "album": props.album_title or "", "app": app, "playing": playing, "pos": pos,
                              "dur": _secs(tl.end_time) - _secs(tl.start_time), "stamp": time.time(),
                              "cover": cover, "key": key}
                fails = 0
            except Exception as ex:
                fails += 1
                self.log("опрос: %r" % (ex,))
                st = "keep"                                 # временная ошибка - не стираем трек с экрана
            self._emit({"state": st})
            await asyncio.sleep(1.0)

    def _on(self, payload):
        if "error" in payload:
            self.error = payload["error"]
            self.updated.emit()
            return
        self.error = None
        st = payload["state"]
        if st == "keep":
            return
        if st is None and self.state:
            # плеер пропал (приложение закрыли, вкладку поставили на паузу) - показываем последний трек
            # как остановленный ещё 30 минут, а не пустой виджет
            if time.time() - self.state.get("seen", self.state["stamp"]) < 30 * 60:
                if self.state["playing"]:
                    self.state = dict(self.state, playing=False, pos=self.position(), stamp=time.time())
                    self.updated.emit()
                return
        if st is not None:
            st["seen"] = time.time()
        self.state = st
        self.updated.emit()

    # ----- команды -----
    def position(self):
        st = self.state
        if not st:
            return 0.0
        pos = st["pos"] + ((time.time() - st["stamp"]) if st["playing"] else 0.0)
        return clamp(pos, 0.0, st["dur"]) if st["dur"] > 0 else max(0.0, pos)

    def command(self, name, arg=None):
        if self.state and name == "toggle":          # сразу показываем результат, не ждём плеер
            self.state = dict(self.state, playing=not self.state["playing"], pos=self.position(), stamp=time.time())
            self.updated.emit()
        if DEMO:
            if name == "toggle":
                self._demo_play = not self._demo_play
            return
        s = self.session
        if self.loop is None or s is None:
            if name != "seek":
                media_key(name)
            return

        async def run():
            try:
                if name == "toggle":
                    await s.try_toggle_play_pause_async()
                elif name == "next":
                    await s.try_skip_next_async()
                elif name == "prev":
                    await s.try_skip_previous_async()
                elif name == "seek":
                    await s.try_change_playback_position_async(int(arg * 1e7))
            except Exception:
                if name != "seek":
                    media_key(name)

        try:
            import asyncio
            asyncio.run_coroutine_threadsafe(run(), self.loop)
        except Exception:
            media_key(name)


YA_YELLOW = QColor("#FFD83D")


class MusicCard(Card):
    KIND = "music"
    TITLE = "Яндекс Музыка"
    DEFAULT_SIZE = "m"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.media = mgr.media()
        self.media.updated.connect(self._changed)
        self._seek_to = 0.0
        self.cover_key = None
        self.blur = None
        self.prev_blur = None
        self.fade_t0 = 0.0

    def _changed(self):
        st = self.media.state
        key = (st or {}).get("key")
        if key != self.cover_key:
            self.cover_key = key
            self.prev_blur = self.blur
            self.blur = self._make_blur()
            self.fade_t0 = time.time() if self.animated else 0.0
        self.update()

    def _make_blur(self):
        st = self.media.state
        img = (st or {}).get("cover")
        r = self.card_rect()
        return blur_image(img, int(r.width()), int(r.height()), 10) if img is not None else None

    def size_changed(self):
        self.blur = self._make_blur()
        self.prev_blur = None

    def paint_bg(self, p, path, r, th):
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(48, 44, 30))
        g.setColorAt(1, QColor(16, 16, 18))
        p.fillPath(path, g)
        e = ease_out_cubic((time.time() - self.fade_t0) / 0.6) if self.fade_t0 else 1.0
        if e < 1.0:
            self.want_frame(16)
            if self.prev_blur is not None:
                p.drawImage(r.topLeft(), self.prev_blur)
        if self.blur is not None:
            p.save()
            p.setOpacity(p.opacity() * e)
            p.drawImage(r.topLeft(), self.blur)
            p.restore()
        p.fillPath(path, QColor(0, 0, 0, 115))

    def _cover(self, p, rc, img, radius=12):
        p.save()
        p.setPen(NOPEN)
        for i in range(6, 0, -2):
            p.setBrush(QColor(0, 0, 0, 18))
            p.drawRoundedRect(rc.adjusted(-i * 0.3, -i * 0.1, i * 0.3, i * 0.6), radius + i * 0.3, radius + i * 0.3)
        path = QPainterPath()
        path.addRoundedRect(rc, radius, radius)
        p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        if img is not None and not img.isNull():
            k = max(rc.width() / img.width(), rc.height() / img.height())
            w, h = img.width() * k, img.height() * k
            p.drawImage(QRectF(rc.center().x() - w / 2, rc.center().y() - h / 2, w, h), img)
        else:
            g = QLinearGradient(rc.topLeft(), rc.bottomRight())
            g.setColorAt(0, QColor("#FFD83D"))
            g.setColorAt(1, QColor("#FF8A3D"))
            p.fillRect(rc, g)
            draw_note(p, rc.center().x(), rc.center().y(), rc.width() * 0.45, QColor(30, 20, 0, 200))
        p.restore()

    def _eq(self, p, x, y, h, playing):
        """Маленький "эквалайзер" - прыгающие полоски, пока играет музыка."""
        t = time.time()
        p.save()
        p.setPen(NOPEN)
        p.setBrush(YA_YELLOW)
        for i in range(3):
            k = (0.35 + 0.65 * abs(math.sin(t * (5.0 + i * 1.7) + i))) if playing and self.animated else 0.35
            bh = h * k
            p.drawRoundedRect(QRectF(x + i * 4.5, y + h - bh, 3, bh), 1.2, 1.2)
        p.restore()
        if playing and self.animated:
            self.want_frame(60)

    def _controls(self, p, cx, cy, size, gap):
        playing = bool((self.media.state or {}).get("playing"))
        for name, dx, sc in (("prev", -gap, 0.7), ("toggle", 0, 1.0), ("next", gap, 0.7)):
            s = size * sc
            rc = QRectF(cx + dx - s * 0.75, cy - s * 0.75, s * 1.5, s * 1.5)
            if name == "toggle":
                p.setPen(NOPEN)
                p.setBrush(QColor(255, 255, 255, 235))
                p.drawEllipse(rc.center(), s * 0.72, s * 0.72)
                draw_media_icon(p, "pause" if playing else "play", rc.center().x() + (0 if playing else s * 0.05),
                                rc.center().y(), s * 0.62, QColor(20, 20, 22))
            else:
                draw_media_icon(p, name, rc.center().x(), rc.center().y(), s * 0.62, WHITE)
            self.hit(rc, lambda n=name: self.media.command(n))

    def _progress(self, p, rc, st):
        dur = st["dur"]
        pos = self.media.position()
        draw_bar(p, QRectF(rc.x(), rc.y(), rc.width(), 4), pos / dur if dur > 0 else 0.0, WHITE,
                 QColor(255, 255, 255, 60))
        if dur > 0:
            text(p, QRectF(rc.x(), rc.y() + 7, 60, 14), fmt_time(pos), font(10), QColor(255, 255, 255, 170), AL)
            text(p, QRectF(rc.right() - 60, rc.y() + 7, 60, 14), "-" + fmt_time(dur - pos), font(10),
                 QColor(255, 255, 255, 170), AR)
            self.hit(QRectF(rc.x(), rc.y() - 6, rc.width(), 16),
                     lambda: self.media.command("seek", self._seek_to))
        if st["playing"]:
            self.want_frame(500)

    def mousePressEvent(self, ev):
        r = self.card_rect()
        self._seek_to = 0.0
        st = self.media.state
        if st and st["dur"] > 0:
            x0, w = self._bar_geom(r)
            self._seek_to = clamp((ev.position().x() - x0) / max(1.0, w)) * st["dur"]
        super().mousePressEvent(ev)

    def _bar_geom(self, r):
        size = self.cfg["size"]
        if size == "m":
            return r.x() + 166, r.right() - 18 - (r.x() + 166)
        return r.x() + 24, r.width() - 48

    def paint(self, p, r, th):
        st = self.media.state
        size = self.cfg["size"]
        if not st or not st.get("title"):
            draw_note(p, r.center().x(), r.y() + r.height() * 0.32, 34 if size != "s" else 30, YA_YELLOW)
            msg = self.media.error or "Ничего не играет"
            text(p, QRectF(r.x() + 12, r.y() + r.height() * 0.48, r.width() - 24, 20), msg, font(13, SEMI), WHITE)
            pill = QRectF(r.center().x() - 90, r.y() + r.height() * 0.48 + 28, 180, 30)
            if size == "s":
                pill = QRectF(r.x() + 16, r.bottom() - 46, r.width() - 32, 30)
            p.setPen(NOPEN)
            p.setBrush(YA_YELLOW)
            p.drawRoundedRect(pill, 15, 15)
            text(p, pill, "Открыть Яндекс Музыку" if size != "s" else "Открыть", font(12, SEMI), QColor(20, 20, 20))
            self.hit(pill, self.activate)
            return
        cover = st.get("cover")
        src = app_title(st.get("app"))
        if size == "s":
            self._cover(p, QRectF(r.x(), r.y(), r.width(), r.height()), cover, RADIUS)
            g = QLinearGradient(0, r.y() + 50, 0, r.bottom())
            g.setColorAt(0, QColor(0, 0, 0, 0))
            g.setColorAt(1, QColor(0, 0, 0, 200))
            p.fillRect(r, g)
            text(p, QRectF(r.x() + 14, r.bottom() - 56, r.width() - 64, 20), st["title"], font(13, SEMI), WHITE, AL | AVC)
            text(p, QRectF(r.x() + 14, r.bottom() - 37, r.width() - 64, 18), st["artist"], font(11),
                 QColor(255, 255, 255, 200), AL | AVC)
            playing = st["playing"]
            pc = QRectF(r.right() - 50, r.bottom() - 52, 38, 38)
            p.setPen(NOPEN)
            p.setBrush(YA_YELLOW)
            p.drawEllipse(pc)
            draw_media_icon(p, "pause" if playing else "play", pc.center().x() + (0 if playing else 1.5),
                            pc.center().y(), 15, QColor(20, 20, 20))
            self.hit(pc, lambda: self.media.command("toggle"))
            self._eq(p, r.x() + 14, r.y() + 14, 12, playing)
            return
        if size == "m":
            self._cover(p, QRectF(r.x() + 18, r.y() + 18, 134, 134), cover)
            x0 = r.x() + 166
            w = r.right() - 18 - x0
            self._eq(p, x0, r.y() + 20, 11, st["playing"])
            text(p, QRectF(x0 + 18, r.y() + 17, w - 18, 16), src.upper(), font(10, SEMI), YA_YELLOW, AL | AVC)
            text(p, QRectF(x0, r.y() + 38, w, 22), st["title"], font(15, SEMI), WHITE, AL | AVC)
            text(p, QRectF(x0, r.y() + 60, w, 18), st["artist"], font(12), QColor(255, 255, 255, 190), AL | AVC)
            self._progress(p, QRectF(x0, r.y() + 90, w, 4), st)
            self._controls(p, x0 + w / 2, r.y() + 134, 26, 56)
            return
        cs = 196
        self._cover(p, QRectF(r.center().x() - cs / 2, r.y() + 24, cs, cs), cover, 16)
        self._eq(p, r.x() + 20, r.y() + 20, 12, st["playing"])
        text(p, QRectF(r.x() + 24, r.y() + 230, r.width() - 48, 24), st["title"], font(17, SEMI), WHITE)
        text(p, QRectF(r.x() + 24, r.y() + 254, r.width() - 48, 18), st["artist"] + "  ·  " + src, font(12),
             QColor(255, 255, 255, 190))
        self._progress(p, QRectF(r.x() + 24, r.y() + 286, r.width() - 48, 4), st)
        self._controls(p, r.center().x(), r.y() + 334, 30, 72)

    def wheel(self, pos, delta):
        if delta:
            self.media.command("next" if delta < 0 else "prev")

    def activate(self):
        local = os.environ.get("LOCALAPPDATA", "")
        open_target("yandexmusic://", os.path.join(local, "Programs", "YandexMusic", "Яндекс Музыка.exe"),
                    "https://music.yandex.ru/")

    def extra_menu(self, menu):
        menu.addAction("Открыть Яндекс Музыку").triggered.connect(self.activate)
        a = menu.addAction("Только Яндекс Музыка (не другие плееры)")
        a.setCheckable(True)
        a.setChecked(bool(self.mgr.cfg.get("music_only_yandex")))
        a.toggled.connect(lambda v: self.mgr.set_opt("music_only_yandex", bool(v)))


# ---------------------------------------------------------------------------
#  Claude: мини-чат на рабочем столе (официальная библиотека anthropic)
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-opus-5-5"
CLAUDE_SYSTEM = ("Ты помощник в маленьком виджете на рабочем столе Windows. Отвечай коротко и по делу, "
                 "на языке пользователя. Форматируй Markdown умеренно: короткие списки и код допустимы, "
                 "большие заголовки и таблицы - нет.")
CLAUDE_ORANGE = QColor("#D97757")


class ClaudeCard(Card):
    KIND = "claude"
    TITLE = "Claude"
    SIZES = ("s", "m", "l", "xl")
    DEFAULT_SIZE = "l"
    _chunk = Signal(object, object)
    _done = Signal(object, object)

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.msgs = []                      # история диалога для API
        self.streaming = ""
        self.busy = False
        self.error = None
        self.tok = 0
        self._style_key = None
        self.view = QTextBrowser(self)
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        self.view.viewport().setAutoFillBackground(False)
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Спроси Claude…  (Enter - отправить)")
        self.input.returnPressed.connect(self.send)
        self._chunk.connect(self._on_chunk)
        self._done.connect(self._on_done)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self.render)
        self.layout_children()
        self.render()

    # ----- раскладка и вид -----
    def layout_children(self):
        r = self.card_rect()
        small = self.cfg["size"] == "s"
        self.view.setVisible(not small)
        self.input.setVisible(not small)
        if small:
            return
        self.view.setGeometry(int(r.x() + 14), int(r.y() + 46), int(r.width() - 28), int(r.height() - 46 - 58))
        self.input.setGeometry(int(r.x() + 14), int(r.bottom() - 48), int(r.width() - 28), 34)

    def size_changed(self):
        self.layout_children()

    def restyle(self, th):
        key = (self.mgr.style_name(self.cfg),)
        if key == self._style_key:
            return
        self._style_key = key
        fg, fg2 = th["fg"].name(), th["fg2"].name()
        light = th["light"]
        field = "rgba(0,0,0,0.07)" if light else "rgba(255,255,255,0.10)"
        border = "rgba(0,0,0,0.15)" if light else "rgba(255,255,255,0.18)"
        self.view.setStyleSheet("QTextBrowser { background: transparent; color: %s; border: none; font-family: '%s';"
                                " font-size: 13px; } QScrollBar:vertical { width: 6px; background: transparent; }"
                                " QScrollBar::handle:vertical { background: %s; border-radius: 3px; min-height: 20px; }"
                                " QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
                                % (fg, FONT, border))
        self.input.setStyleSheet("QLineEdit { background: %s; color: %s; border: 1px solid %s; border-radius: 17px;"
                                 " padding: 0 14px; font-family: '%s'; font-size: 13px; }"
                                 " QLineEdit:focus { border: 1px solid %s; }"
                                 % (field, fg, border, FONT, CLAUDE_ORANGE.name()))
        self._fg2 = fg2
        link = "#8A3B1F" if light else "#F0A07E"
        self._link_col = QColor(link)
        self.render()

    def render(self):
        th = self.theme
        fg2 = th["fg2"].name()
        parts = []
        if self.mode() == "web":
            where = {"panel": "в окошке рядом с виджетом", "app": "в приложении Claude",
                     "browser": "в браузере"}[self.open_in()]
            if self.cfg["size"] == "m":
                parts.append("Напиши вопрос и нажми Enter - откроется claude.ai %s под твоим аккаунтом." % where)
            else:
                parts.append("**Claude без API-ключа.** Напиши вопрос внизу и нажми Enter - он откроется на claude.ai "
                             "%s, под твоим аккаунтом Claude (бесплатным или с подпиской). Войти нужно один раз."
                             % where)
            if self.cfg["size"] != "m":
                asked = self.cfg.get("recent") or []
                if asked:
                    parts.append("**Недавние вопросы** (нажми, чтобы спросить снова):")
                    parts.append("\n".join("- [%s](snowask:%d)" % (q.replace("[", "(").replace("]", ")")[:80], i)
                                           for i, q in enumerate(asked)))
                parts.append("*Где открывать и режим с API-ключом - правая кнопка по заголовку виджета.*")
        elif not self.msgs and not self.busy:
            if not self.api_key() and not os.environ.get("ANTHROPIC_API_KEY") and self.cfg["size"] == "m":
                parts.append("**Нужен API-ключ Claude.** Правая кнопка по виджету → «API-ключ Claude...». "
                             "Создать ключ: [platform.claude.com](https://platform.claude.com/settings/keys)")
            elif not self.api_key() and not os.environ.get("ANTHROPIC_API_KEY"):
                parts.append("**Чтобы общаться с Claude, нужен API-ключ.**\n\n"
                             "1. Открой [platform.claude.com](https://platform.claude.com/settings/keys) и создай ключ.\n"
                             "2. Правая кнопка по виджету → «API-ключ Claude...» и вставь его.\n\n"
                             "Ключ хранится на этом компьютере в зашифрованном виде. Запросы платные по тарифам API.\n\n"
                             "Без ключа: двойной клик по заголовку откроет claude.ai в браузере.")
            else:
                parts.append("Привет! Спроси что-нибудь: перевести текст, объяснить ошибку, придумать идею…")
        for m in self.msgs:
            if m["role"] == "user":
                parts.append("<p style='color:%s'><b>Вы:</b> %s</p>" % (fg2, m["content"].replace("<", "&lt;")))
            else:
                parts.append(m["content"])
        if self.busy:
            parts.append(self.streaming or "<i style='color:%s'>Думаю…</i>" % fg2)
        if self.error:
            parts.append("<p style='color:#FF6B6B'>%s</p>" % self.error)
        app = QApplication.instance()                 # Markdown берёт цвет ссылок из палитры приложения
        pal = app.palette()
        link = getattr(self, "_link_col", None) or QColor("#F0A07E")
        pal.setColor(QPalette.ColorRole.Link, link)
        pal.setColor(QPalette.ColorRole.LinkVisited, link)
        app.setPalette(pal)
        self.view.setMarkdown("\n\n".join(parts))
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _link(self, url):
        u = url.toString()
        if u.startswith("snowask:"):
            try:
                self.ask_web((self.cfg.get("recent") or [])[int(u[8:])])
            except (ValueError, IndexError):
                pass
        else:
            QDesktopServices.openUrl(url)

    def api_key(self):
        return secret_reveal(self.mgr.cfg.get("claude_key"))

    def mode(self):
        """web - через claude.ai под своим аккаунтом (без ключа), api - через API-ключ."""
        m = self.cfg.get("mode")
        if m in ("web", "api"):
            return m
        return "api" if (self.api_key() or os.environ.get("ANTHROPIC_API_KEY")) else "web"

    def open_in(self):
        o = self.cfg.get("open_in")
        if o in ("panel", "app", "browser"):
            return o
        return "panel" if web_engine() is not None else "app"

    def ask_web(self, q=""):
        where = self.open_in()
        if where == "panel":
            panel = self.mgr.claude_panel()
            if panel is not None:
                panel.open(claude_url(q), near=self.frameGeometry())
                return
            where = "app"
        if where == "app":
            open_target("claude://claude.ai/new" + (("?q=" + urllib.parse.quote(q)) if q else ""), claude_url(q))
        else:
            open_target(claude_url(q))

    # ----- запрос -----
    def send(self):
        q = self.input.text().strip()
        if self.mode() == "web":
            self.input.clear()
            if q:
                recent = [x for x in (self.cfg.get("recent") or []) if x != q]
                self.cfg["recent"] = ([q] + recent)[:6]
                self.mgr.save()
                self.render()
            self.ask_web(q)
            return
        if not q or self.busy:
            return
        if not DEMO and not self.api_key() and not os.environ.get("ANTHROPIC_API_KEY"):
            self.ask_key()
            if not self.api_key():
                return
        self.input.clear()
        self.msgs.append({"role": "user", "content": q})
        self.busy, self.streaming, self.error = True, "", None
        self.tok += 1
        tok, history, key = self.tok, list(self.msgs), self.api_key()
        self.render()
        self.update()
        threading.Thread(target=self._work, args=(tok, history, key), daemon=True).start()

    def _emit(self, sig, *args):
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    def _work(self, tok, history, key):
        if DEMO:
            for word in ("Это **тестовый** ответ виджета. ", "Здесь появится ответ Claude, ",
                         "который печатается по мере генерации."):
                time.sleep(0.15)
                self._emit(self._chunk, tok, word)
            self._emit(self._done, tok, None)
            return
        try:
            import anthropic
        except ImportError:
            pip_install("anthropic")
            try:
                import anthropic
            except ImportError:
                self._emit(self._done, tok, "Нет библиотеки anthropic. Выполни: pip install anthropic")
                return
        err = None
        try:
            client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
            params = dict(model=CLAUDE_MODEL, max_tokens=64000, system=CLAUDE_SYSTEM, messages=history)
            try:
                # если запрос отклонят фильтры безопасности, API сам повторит его на подходящей модели
                ctx = client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                                                  **params)
            except TypeError:                            # старая версия библиотеки без fallbacks
                ctx = client.messages.stream(**params)
            with ctx as stream:
                for piece in stream.text_stream:
                    self._emit(self._chunk, tok, piece)
                final = stream.get_final_message()
            if final.stop_reason == "refusal":
                err = "Claude не стал отвечать на этот запрос."
            elif final.stop_reason == "max_tokens":
                err = "Ответ получился слишком длинным и обрезан."
        except anthropic.AuthenticationError:
            err = "Неверный API-ключ. Правая кнопка → «API-ключ Claude...»"
        except anthropic.PermissionDeniedError:
            err = "У ключа нет доступа к этой модели."
        except anthropic.RateLimitError:
            err = "Слишком много запросов - подожди минутку."
        except anthropic.APIStatusError as ex:
            err = "Ошибка сервера Claude (%s). Попробуй ещё раз." % ex.status_code
        except anthropic.APIConnectionError:
            err = "Нет связи с сервером Claude."
        except anthropic.AnthropicError as ex:
            err = "Не получилось: %s" % (str(ex)[:160] or "нужен API-ключ")
        except Exception as ex:
            err = "Не получилось: %s" % str(ex)[:160]
        self._emit(self._done, tok, err)

    def _on_chunk(self, tok, piece):
        if tok != self.tok:
            return
        self.streaming += piece
        if not self._render_timer.isActive():
            self._render_timer.start(60)

    def _on_done(self, tok, err):
        if tok != self.tok:
            return
        self.busy = False
        if self.streaming.strip():
            self.msgs.append({"role": "assistant", "content": self.streaming})
        elif self.msgs and self.msgs[-1]["role"] == "user":
            self.msgs.pop()                       # ответа нет - вопрос из истории убираем
        self.streaming, self.error = "", err
        self.render()
        self.update()

    def new_chat(self):
        self.tok += 1
        self.msgs, self.streaming, self.busy, self.error = [], "", False, None
        self.render()
        self.update()

    def ask_key(self):
        key, ok = QInputDialog.getText(None, "API-ключ Claude",
                                       "Вставь API-ключ (начинается с sk-ant-).\n"
                                       "Создать: platform.claude.com → Settings → API keys.",
                                       QLineEdit.EchoMode.Password)
        if ok and key.strip():
            self.mgr.set_opt("claude_key", secret_protect(key.strip()))
            self.set_opt("mode", "api")
            self.render()

    # ----- рисование -----
    def paint(self, p, r, th):
        self.restyle(th)
        if self.cfg["size"] == "s":
            draw_bubble(p, r.center().x(), r.y() + 62, 64, WHITE if th["mode"] == "color" else CLAUDE_ORANGE)
            text(p, QRectF(r.x(), r.y() + 104, r.width(), 22), "Claude", font(16, SEMI), th["fg"])
            text(p, QRectF(r.x() + 8, r.y() + 126, r.width() - 16, 18), "Спросить в чате", font(12), th["fg2"])
            return
        draw_bubble(p, r.x() + 30, r.y() + 24, 24, WHITE if th["mode"] == "color" else CLAUDE_ORANGE, dots=False)
        text(p, QRectF(r.x() + 50, r.y() + 12, 120, 24), "Claude", font(15, SEMI), th["fg"], AL | AVC)
        if self.busy:
            t = time.time()
            for i in range(3):
                a = 0.3 + 0.7 * abs(math.sin(t * 4 - i * 0.6))
                c = QColor(WHITE if th["mode"] == "color" else CLAUDE_ORANGE)
                c.setAlphaF(a)
                p.setPen(NOPEN)
                p.setBrush(c)
                p.drawEllipse(QPointF(r.x() + 118 + i * 9, r.y() + 24), 2.6, 2.6)
            self.want_frame(40)
        nb = QRectF(r.right() - 44, r.y() + 10, 28, 28)
        p.setPen(NOPEN)
        p.setBrush(th["btn"])
        p.drawEllipse(nb.center(), 13, 13)
        pen = QPen(th["fg"], 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c = nb.center()
        p.drawLine(QPointF(c.x() - 5, c.y()), QPointF(c.x() + 5, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 5), QPointF(c.x(), c.y() + 5))
        self.hit(nb, self.new_chat if self.mode() == "api" else (lambda: self.ask_web("")))
        text(p, QRectF(r.right() - 200, r.y() + 12, 150, 24), "Opus 5.5" if self.mode() == "api" else "claude.ai",
             font(11), th["fg2"], AR | AVC)

    def clicked(self, pos):
        if self.cfg["size"] == "s":
            self.ask_web("") if self.mode() == "web" else self.activate()
        else:
            self.activateWindow()
            self.input.setFocus()

    def activate(self):
        if self.mode() == "web":
            self.ask_web("")
            return
        local = os.environ.get("LOCALAPPDATA", "")
        open_target(os.path.join(local, "AnthropicClaude", "claude.exe"), "https://claude.ai/new")

    def extra_menu(self, menu):
        mm = menu.addMenu("Режим")
        grp = QActionGroup(mm)
        for key, label in (("web", "Через claude.ai - без ключа, под своим аккаунтом"),
                           ("api", "Через API-ключ - ответ прямо в виджете")):
            a = mm.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.mode() == key)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: (self.set_opt("mode", k), self.render()))
        om = menu.addMenu("Где открывать claude.ai")
        grp2 = QActionGroup(om)
        for key, label in (("panel", "В окошке рядом с виджетом"), ("app", "В приложении Claude"),
                           ("browser", "В браузере")):
            a = om.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.open_in() == key)
            a.setEnabled(key != "panel" or web_engine() is not None)
            grp2.addAction(a)
            a.triggered.connect(lambda _=False, k=key: (self.set_opt("open_in", k), self.render()))
        menu.addAction("Новый чат").triggered.connect(self.new_chat if self.mode() == "api" else (lambda: self.ask_web("")))
        menu.addAction("API-ключ Claude...").triggered.connect(self.ask_key)
        if self.mgr.cfg.get("claude_key"):
            menu.addAction("Удалить сохранённый ключ").triggered.connect(
                lambda: (self.mgr.cfg.pop("claude_key", None), self.mgr.save(), self.render()))
        menu.addAction("Открыть claude.ai").triggered.connect(lambda: open_target("https://claude.ai/new"))


# ---------------------------------------------------------------------------
#  Discord: кто в сети на твоём сервере (официальный виджет сервера Discord)
# ---------------------------------------------------------------------------
DISCORD_BLURPLE = QColor("#5865F2")
DISCORD_STATUS = {"online": QColor("#23A55A"), "idle": QColor("#F0B232"), "dnd": QColor("#F23F43")}


def demo_discord():
    names = [("Снеговик", "online", "Minecraft"), ("Лиса", "idle", None), ("Пельмень", "dnd", "Dota 2"),
             ("Кот Борис", "online", None), ("Ёлка", "online", "Spotify"), ("Мандарин", "online", None),
             ("Зима", "idle", None), ("Сугроб", "online", "CS2")]
    members = []
    for i, (n, s, g) in enumerate(names):
        m = {"id": str(i), "username": n, "status": s, "avatar_url": ""}
        if g:
            m["game"] = {"name": g}
        if i in (0, 3, 5):
            m["channel_id"] = "v1"
        members.append(m)
    return {"id": "1", "name": "Снежный сервер", "presence_count": 42, "instant_invite": "https://discord.gg/example",
            "channels": [{"id": "v1", "name": "Общий голосовой", "position": 0},
                         {"id": "v2", "name": "Игры", "position": 1}], "members": members}


class DiscordCard(Card):
    KIND = "discord"
    TITLE = "Discord: сервер"
    DEFAULT_SIZE = "m"
    _got = Signal(object, object, object)
    _ava = Signal(object, object)

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        self.data = cfg.get("cache")
        self.error = None
        self.busy = False
        self.avatars = {}
        self._got.connect(self._on_data)
        self._ava.connect(self._on_avatar)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2 * 60 * 1000)
        QTimer.singleShot(300, self.refresh)

    # ----- данные -----
    def refresh(self):
        gid = self.cfg.get("guild")
        if self.busy or (not gid and not DEMO):
            return
        self.busy = True

        def work():
            data, err = None, None
            try:
                if DEMO:
                    data = demo_discord()
                else:
                    data = http_json("https://discord.com/api/guilds/%s/widget.json" % gid)
            except urllib.error.HTTPError as ex:
                err = ("У сервера выключен виджет: Настройки сервера → Виджет → «Включить виджет сервера»"
                       if ex.code == 403 else "Сервер не найден - проверь ID" if ex.code in (400, 404)
                       else "Discord ответил ошибкой %d" % ex.code)
            except Exception:
                err = "Нет связи с Discord"
            self._emit(self._got, gid, data, err)
            for m in ((data or {}).get("members") or [])[:16]:
                url = m.get("avatar_url")
                if not url or m.get("id") in self.avatars:
                    continue
                try:
                    req = urllib.request.Request(url, headers=UA)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        img = QImage.fromData(resp.read())
                    if not img.isNull():
                        self._emit(self._ava, m["id"], img)
                except Exception:
                    continue

        threading.Thread(target=work, daemon=True).start()

    def _emit(self, sig, *args):
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    def _on_data(self, gid, data, err):
        self.busy = False
        self.error = err
        if data is not None:
            self.data = data
            self.cfg["cache"] = data
            self.mgr.save()
        self.update()

    def _on_avatar(self, mid, img):
        self.avatars[mid] = img.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
        self.update()

    # ----- рисование -----
    def _avatar(self, p, m, cx, cy, rad, th):
        img = self.avatars.get(m.get("id"))
        p.save()
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), rad, rad)
        if img is not None:
            p.setClipPath(path, Qt.ClipOperation.IntersectClip)
            p.drawImage(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), img)
            p.setClipping(False)
        else:
            hue = (sum(map(ord, m.get("username", "?"))) * 37) % 360
            p.setPen(NOPEN)
            p.setBrush(QColor.fromHsv(hue, 120, 200))
            p.drawPath(path)
            text(p, QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), (m.get("username") or "?")[:1].upper(),
                 font(rad * 0.95, SEMI), WHITE)
        p.restore()
        col = DISCORD_STATUS.get(m.get("status"), DISCORD_STATUS["online"])
        p.setPen(QPen(th["bg2"] if th["mode"] != "color" else QColor(self.kind_colors()[1]), max(2.0, rad * 0.16)))
        p.setBrush(col)
        p.drawEllipse(QPointF(cx + rad * 0.72, cy + rad * 0.72), rad * 0.3, rad * 0.3)

    def _header(self, p, r, th, d):
        draw_bubble(p, r.x() + 30, r.y() + 25, 24, DISCORD_BLURPLE if th["mode"] != "color" else WHITE, dots=False)
        text(p, QRectF(r.x() + 50, r.y() + 12, r.width() - 160, 24), d.get("name") or "Discord", font(15, SEMI),
             th["fg"], AL | AVC)
        online = int(d.get("presence_count") or 0)
        pill = QRectF(r.right() - 104, r.y() + 13, 88, 22)
        p.setPen(NOPEN)
        p.setBrush(th["btn"])
        p.drawRoundedRect(pill, 11, 11)
        p.setBrush(DISCORD_STATUS["online"])
        p.drawEllipse(QPointF(pill.x() + 13, pill.center().y()), 4, 4)
        text(p, pill.adjusted(22, 0, -6, 0), "%d в сети" % online, font(11, SEMI), th["fg"], AL | AVC)

    def voice(self, d):
        chans = {c["id"]: c for c in d.get("channels") or []}
        groups = {}
        for m in d.get("members") or []:
            if m.get("channel_id") in chans:
                groups.setdefault(m["channel_id"], []).append(m)
        return [(chans[k], v) for k, v in sorted(groups.items(), key=lambda kv: chans[kv[0]].get("position", 0))]

    def paint(self, p, r, th):
        d = self.data
        size = self.cfg["size"]
        if not d:
            draw_bubble(p, r.center().x(), r.y() + r.height() * 0.3, 40, DISCORD_BLURPLE, dots=False)
            msg = self.error or ("Загружаю…" if self.cfg.get("guild") else "Нажми, чтобы подключить свой сервер")
            p.setFont(font(12))
            p.setPen(th["fg2"])
            p.drawText(QRectF(r.x() + 14, r.y() + r.height() * 0.48, r.width() - 28, r.height() * 0.5),
                       int(AC | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), msg)
            return
        members = d.get("members") or []
        if size == "s":
            draw_bubble(p, r.x() + 28, r.y() + 26, 22, DISCORD_BLURPLE if th["mode"] != "color" else WHITE, dots=False)
            text(p, QRectF(r.x() + 46, r.y() + 14, r.width() - 60, 24), d.get("name") or "", font(13, SEMI),
                 th["fg"], AL | AVC)
            online = self.av("online", float(d.get("presence_count") or 0), 4.0, start=0.0)
            text(p, QRectF(r.x() + 16, r.y() + 42, r.width() - 32, 50), str(int(round(online))), font(42, LIGHT),
                 th["fg"], AL | AVC)
            p.setPen(NOPEN)
            p.setBrush(DISCORD_STATUS["online"])
            p.drawEllipse(QPointF(r.x() + 21, r.y() + 102), 4, 4)
            text(p, QRectF(r.x() + 30, r.y() + 93, r.width() - 40, 18), "в сети", font(12), th["fg2"], AL | AVC)
            for i, m in enumerate(members[:5]):
                self._avatar(p, m, r.x() + 30 + i * 26, r.bottom() - 30, 13, th)
            return
        self._header(p, r, th, d)
        if size == "m":
            n = min(8, len(members))
            for i, m in enumerate(members[:n]):
                self._avatar(p, m, r.x() + 36 + i * 41, r.y() + 74, 17, th)
            y = r.y() + 106
            vc = self.voice(d)
            if vc:
                for ch, ms in vc[:2]:
                    text(p, QRectF(r.x() + 20, y, r.width() - 40, 20), "🔊 %s — %d" % (ch["name"], len(ms)),
                         font(12), th["fg2"], AL | AVC)
                    y += 22
            else:
                games = [m for m in members if m.get("game")]
                line = ", ".join("%s: %s" % (m["username"], m["game"]["name"]) for m in games[:3]) or "Никто не в голосовых каналах"
                p.setFont(font(12))
                p.setPen(th["fg2"])
                p.drawText(QRectF(r.x() + 20, y, r.width() - 40, 44),
                           int(AL | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), line)
            return
        y = r.y() + 50
        vc = self.voice(d)
        for ch, ms in vc[:2]:
            text(p, QRectF(r.x() + 20, y, r.width() - 40, 18), "🔊 " + ch["name"], font(12, SEMI), th["accent"], AL | AVC)
            y += 20
            for i, m in enumerate(ms[:6]):
                self._avatar(p, m, r.x() + 32 + i * 32, y + 14, 12, th)
            y += 34
        if vc:
            p.setPen(QPen(th["line"], 1))
            p.drawLine(QPointF(r.x() + 20, y), QPointF(r.right() - 20, y))
            y += 6
        row = 38
        for m in members:
            if y + row > r.bottom() - 8:
                break
            self._avatar(p, m, r.x() + 36, y + row / 2, 14, th)
            game = (m.get("game") or {}).get("name")
            if game:
                text(p, QRectF(r.x() + 60, y + 2, r.width() - 80, 18), m.get("username", ""), font(13, SEMI),
                     th["fg"], AL | AVC)
                text(p, QRectF(r.x() + 60, y + 19, r.width() - 80, 16), "Играет в " + game, font(11), th["fg2"],
                     AL | AVC)
            else:
                text(p, QRectF(r.x() + 60, y, r.width() - 80, row), m.get("username", ""), font(13, SEMI), th["fg"],
                     AL | AVC)
            y += row

    # ----- действия -----
    def clicked(self, pos):
        if not self.cfg.get("guild") and not DEMO:
            self.ask_guild()

    def activate(self):
        gid = self.cfg.get("guild") or ""
        open_target("discord://-/channels/%s" % gid if gid else "discord://",
                    "https://discord.com/channels/%s" % gid if gid else "https://discord.com/app")

    def ask_guild(self):
        val, ok = QInputDialog.getText(
            None, "Discord - мой сервер",
            "1. Discord → Настройки сервера → Виджет → включи «Включить виджет сервера».\n"
            "2. На той же странице скопируй «ID сервера» и вставь сюда\n"
            "    (подойдёт и ссылка вида discord.com/channels/123456...).",
            text=self.cfg.get("guild") or "")
        if not ok:
            return
        import re
        nums = re.findall(r"\d{15,22}", val)
        if not nums:
            self.error = "Не нашёл ID сервера (это длинное число)"
            self.update()
            return
        self.cfg["guild"] = nums[0]
        self.cfg.pop("cache", None)
        self.data, self.error, self.avatars = None, None, {}
        self.mgr.save()
        self.update()
        self.refresh()

    def extra_menu(self, menu):
        menu.addAction("Указать сервер...").triggered.connect(self.ask_guild)
        menu.addAction("Обновить").triggered.connect(self.refresh)
        menu.addAction("Открыть Discord").triggered.connect(self.activate)
        inv = (self.data or {}).get("instant_invite")
        if inv:
            menu.addAction("Скопировать приглашение").triggered.connect(
                lambda: QApplication.clipboard().setText(inv))

    def closing(self):
        self.timer.stop()


# ---------------------------------------------------------------------------
#  Уведомления (Discord и других программ) - из журнала уведомлений Windows
# ---------------------------------------------------------------------------
NOTIFY_APPS = {"discord": "Discord", "telegram": "Telegram", "all": "Все программы"}


def notify_app_name(aumid):
    a = (aumid or "").lower()
    for key, title in (("discord", "Discord"), ("telegram", "Telegram"), ("whatsapp", "WhatsApp"),
                       ("chrome", "Chrome"), ("msedge", "Edge"), ("firefox", "Firefox"), ("outlook", "Outlook"),
                       ("teams", "Teams"), ("steam", "Steam"), ("vk", "VK"), ("yandex", "Яндекс")):
        if key in a:
            return title
    base = (aumid or "").split("!")[0].split("_")[0]          # Microsoft.WindowsStore_8wekyb3d8bbwe!App
    tail = base.split(".")[-1] if base else ""
    return tail[:24] or "Программа"


def wpn_db_path():
    p = os.environ.get("SNOWWIDGETS_WPNDB")
    if p:
        return p
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Notifications", "wpndatabase.db")


def parse_toast(payload):
    """XML уведомления -> (заголовок, текст, путь к картинке)."""
    import xml.etree.ElementTree as ET
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8", "replace")
    try:
        root = ET.fromstring(payload)
    except Exception:
        return None
    texts = [(t.text or "").strip() for t in root.iter("text") if (t.text or "").strip()]
    img = None
    for im in root.iter("image"):
        src = im.get("src") or ""
        if src.startswith("file:///"):
            src = urllib.parse.unquote(src[8:])
            if not (len(src) > 1 and src[1] == ":"):         # не "C:/..." - путь Linux/macOS
                src = "/" + src
        elif src.startswith("file://"):
            src = urllib.parse.unquote(src[7:])
        if src and os.path.isfile(src):
            img = src
            if im.get("placement") == "appLogoOverride":
                break
    if not texts:
        return None
    return texts[0], "\n".join(texts[1:]), img


class NotifyService(QObject):
    """Раз в 2 секунды смотрит журнал уведомлений Windows (тот же, что показывает Центр уведомлений).
    Уведомления, которые уже закрыли в Windows, остаются в виджете - он хранит свою историю."""
    updated = Signal()
    _got = Signal(object)

    def __init__(self):
        super().__init__()
        self.items = []            # [{id, app, aumid, title, body, img, time}] новые сверху
        self.error = None
        self.seen = set()
        self.read_until = 0.0
        self._sig = None
        self.hist_file = os.path.join(DATA_DIR, "notifications.json")
        try:
            with open(self.hist_file, encoding="utf-8") as fh:
                data = json.load(fh)
            self.items = data.get("items", [])[:200]
            self.read_until = float(data.get("read_until", 0))
            self.seen = {it["id"] for it in self.items}
        except Exception:
            pass
        self._got.connect(self._on)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(2000)
        self._busy = False
        QTimer.singleShot(200, self.poll)

    def poll(self):
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        try:
            res = self._read()
        except Exception as ex:
            res = {"error": "Не удалось прочитать уведомления Windows (%s)" % type(ex).__name__}
        try:
            self._got.emit(res)
        except RuntimeError:
            pass

    def _read(self):
        if DEMO and not os.environ.get("SNOWWIDGETS_WPNDB"):
            return {"rows": []}
        db = wpn_db_path()
        if not os.path.isfile(db):
            return {"error": "Журнал уведомлений Windows не найден" if IS_WIN else "Работает только в Windows"}
        sig = []
        for ext in ("", "-wal"):
            try:
                st = os.stat(db + ext)
                sig.append((st.st_mtime, st.st_size))
            except OSError:
                sig.append(None)
        if sig == self._sig:
            return None                                     # ничего не поменялось
        self._sig = sig
        import sqlite3
        tmp = os.path.join(DATA_DIR, "wpn_copy")
        os.makedirs(tmp, exist_ok=True)
        dst = os.path.join(tmp, "wpn.db")
        for ext in ("", "-wal", "-shm"):                   # копия, чтобы не мешать Windows
            try:
                if os.path.exists(db + ext):
                    shutil.copyfile(db + ext, dst + ext)
                elif os.path.exists(dst + ext):
                    os.remove(dst + ext)
            except OSError:
                pass
        con = sqlite3.connect(dst, timeout=2)
        try:
            rows = con.execute(
                "SELECT n.Id, n.ArrivalTime, n.Payload, h.PrimaryId FROM Notification n "
                "LEFT JOIN NotificationHandler h ON n.HandlerId = h.RecordId "
                "WHERE n.Type = 'toast' ORDER BY n.ArrivalTime DESC LIMIT 150").fetchall()
        finally:
            con.close()
        out = []
        for nid, arrival, payload, aumid in rows:
            t = parse_toast(payload)
            if t is None:
                continue
            try:
                ts = (int(arrival) / 1e7) - 11644473600     # FILETIME -> unix
            except Exception:
                ts = time.time()
            out.append({"id": "%s:%s" % (aumid, nid), "aumid": aumid or "", "app": notify_app_name(aumid),
                        "title": t[0], "body": t[1], "img": t[2], "time": ts})
        return {"rows": out}

    def _on(self, res):
        self._busy = False
        if res is None:
            return
        if "error" in res:
            self.error = res["error"]
            self.updated.emit()
            return
        self.error = None
        fresh = [r for r in res["rows"] if r["id"] not in self.seen]
        if not fresh:
            if self.error is not None:
                self.updated.emit()
            return
        for r in fresh:
            self.seen.add(r["id"])
        self.items = sorted(fresh + self.items, key=lambda r: -r["time"])[:200]
        self.save()
        self.updated.emit()

    def add_demo(self, app, title, body):
        r = {"id": "demo:%f" % time.time(), "aumid": app, "app": notify_app_name(app), "title": title,
             "body": body, "img": None, "time": time.time()}
        self._on({"rows": [r]})

    def save(self):
        try:
            with open(self.hist_file, "w", encoding="utf-8") as fh:
                json.dump({"items": self.items[:200], "read_until": self.read_until}, fh, ensure_ascii=False)
        except Exception:
            pass

    def filtered(self, which):
        if which == "all":
            return list(self.items)
        return [it for it in self.items if which in (it.get("aumid") or "").lower()]

    def mark_read(self):
        self.read_until = time.time()
        self.save()
        self.updated.emit()

    def clear(self, which):
        keep = [it for it in self.items if it not in self.filtered(which)]
        self.items = keep
        self.save()
        self.updated.emit()


def time_ago(ts):
    d = time.time() - ts
    if d < 60:
        return "сейчас"
    if d < 3600:
        return "%d мин" % (d // 60)
    t = datetime.datetime.fromtimestamp(ts)
    if t.date() == datetime.date.today():
        return t.strftime("%H:%M")
    if (datetime.date.today() - t.date()).days == 1:
        return "вчера"
    return "%d %s" % (t.day, MONTHS_GEN[t.month - 1][:3])


class NotifyCard(Card):
    KIND = "notify"
    TITLE = "Уведомления Discord"
    DEFAULT_SIZE = "l"

    def __init__(self, mgr, cfg):
        super().__init__(mgr, cfg)
        cfg.setdefault("apps", "discord")
        self.svc = mgr.notify()
        self.svc.updated.connect(self._changed)
        self.imgs = {}
        self.flash_t0 = 0.0
        self._count = len(self.items())

    def items(self):
        return self.svc.filtered(self.cfg.get("apps", "discord"))

    def _changed(self):
        n = len(self.items())
        if n > self._count and self.animated:
            self.flash_t0 = time.time()                    # новое уведомление - вспышка рамки
        self._count = n
        self.update()

    def unread(self):
        return [it for it in self.items() if it["time"] > self.svc.read_until]

    def _img(self, path):
        if not path:
            return None
        if path not in self.imgs:
            img = QImage(path)
            self.imgs[path] = None if img.isNull() else img.scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        return self.imgs[path]

    def _avatar(self, p, it, cx, cy, rad):
        img = self._img(it.get("img"))
        p.save()
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), rad, rad)
        p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        if img is not None:
            p.drawImage(QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), img)
        else:
            col = DISCORD_BLURPLE if "discord" in it.get("aumid", "").lower() else \
                QColor.fromHsv((sum(map(ord, it["title"])) * 37) % 360, 120, 200)
            p.fillPath(path, col)
            text(p, QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad), it["title"][:1].upper(), font(rad * 0.9, SEMI), WHITE)
        p.restore()

    def _title(self):
        return {"discord": "Discord", "telegram": "Telegram"}.get(self.cfg.get("apps"), "Уведомления")

    def paint(self, p, r, th):
        items = self.items()
        unread = self.unread()
        icon_col = WHITE if th["mode"] == "color" else DISCORD_BLURPLE
        e = (time.time() - self.flash_t0) / 1.4 if self.flash_t0 else 1.0
        if e < 1.0:                                        # вспышка при новом уведомлении
            self.want_frame(16)
            c = QColor(DISCORD_BLURPLE)
            c.setAlpha(int(150 * (1 - e) * (0.6 + 0.4 * math.sin(e * 18))))
            p.save()
            p.setPen(QPen(c, 6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(3, 3, -3, -3), RADIUS - 2, RADIUS - 2)
            p.restore()
        size = self.cfg["size"]
        if size == "s":
            draw_bubble(p, r.x() + 28, r.y() + 26, 22, icon_col, dots=False)
            text(p, QRectF(r.x() + 46, r.y() + 14, r.width() - 56, 24), self._title(), font(13, SEMI), th["fg"], AL | AVC)
            n = self.av("unread", float(len(unread)), 5.0, start=0.0)
            text(p, QRectF(r.x() + 16, r.y() + 42, r.width() - 32, 50), str(int(round(n))), font(42, LIGHT),
                 th["fg"], AL | AVC)
            text(p, QRectF(r.x() + 18, r.y() + 92, r.width() - 32, 18),
                 plural(len(unread), "новое", "новых", "новых"), font(12), th["fg2"], AL | AVC)
            if items:
                text(p, QRectF(r.x() + 16, r.bottom() - 34, r.width() - 32, 18), items[0]["title"], font(11, SEMI),
                     th["fg"], AL | AVC)
            return
        draw_bubble(p, r.x() + 30, r.y() + 25, 24, icon_col, dots=False)
        text(p, QRectF(r.x() + 50, r.y() + 12, r.width() - 150, 24), self._title(), font(15, SEMI), th["fg"], AL | AVC)
        if unread:
            label = str(len(unread)) if len(unread) < 100 else "99+"
            p.setFont(font(15, SEMI))
            tw = p.fontMetrics().horizontalAdvance(self._title())
            p.setFont(font(11, SEMI))
            bw = max(22, p.fontMetrics().horizontalAdvance(label) + 14)
            pill = QRectF(r.x() + 50 + tw + 8, r.y() + 14, bw, 20)
            p.setPen(NOPEN)
            p.setBrush(RED)
            p.drawRoundedRect(pill, 10, 10)
            text(p, pill, label, font(11, SEMI), WHITE)
        if items:
            cb = QRectF(r.right() - 104, r.y() + 13, 88, 22)
            p.setPen(NOPEN)
            p.setBrush(th["btn"])
            p.drawRoundedRect(cb, 11, 11)
            text(p, cb, "Прочитано" if unread else "Очистить", font(11, SEMI), th["fg"])
            self.hit(cb, self.svc.mark_read if unread else (lambda: self.svc.clear(self.cfg.get("apps", "discord"))))
        if not items:
            msg = self.svc.error or ("Пока нет уведомлений.\nВ Discord: Настройки → Уведомления → «Включить "
                                     "уведомления на рабочем столе». Пока окно Discord открыто, он их не присылает.")
            p.setFont(font(12))
            p.setPen(th["fg2"])
            p.drawText(QRectF(r.x() + 18, r.y() + 52, r.width() - 36, r.height() - 64),
                       int(AL | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), msg)
            return
        y = r.y() + 48
        row = 56 if size != "m" else 50
        for i, it in enumerate(items):
            if y + row > r.bottom() - 6:
                break
            k = self.av("in:" + it["id"], 1.0, 9.0, start=0.0)       # новое уведомление выезжает сверху
            p.save()
            p.setOpacity(p.opacity() * k)
            p.translate((1 - k) * 30, 0)
            new = it["time"] > self.svc.read_until
            rc = QRectF(r.x() + 10, y, r.width() - 20, row - 4)
            if new:
                p.setPen(NOPEN)
                p.setBrush(th["btn"])
                p.drawRoundedRect(rc, 12, 12)
            self._avatar(p, it, rc.x() + 24, rc.center().y(), 16)
            tx = rc.x() + 48
            text(p, QRectF(tx, rc.y() + 5, rc.width() - 48 - 54, 18), it["title"], font(13, SEMI), th["fg"], AL | AVC)
            text(p, QRectF(rc.right() - 56, rc.y() + 5, 48, 18), time_ago(it["time"]), font(11), th["fg2"], AR | AVC)
            body = " ".join((it.get("body") or "").split())
            if self.cfg.get("apps") == "all":
                body = it["app"] + " · " + body
            text(p, QRectF(tx, rc.y() + 24, rc.width() - 48 - 10, 18), body, font(12), th["fg2"], AL | AVC)
            if new:
                p.setPen(NOPEN)
                p.setBrush(DISCORD_BLURPLE)
                p.drawEllipse(QPointF(rc.x() + 6, rc.center().y()), 3, 3)
            p.restore()
            self.hit(rc, lambda a=it.get("aumid", ""): self.open_app(a))
            y += row
        self.want_frame(30 * 1000)                          # обновлять "5 мин назад"

    def open_app(self, aumid=""):
        self.svc.mark_read()
        a = aumid.lower()
        if "telegram" in a:
            open_target("tg://", "https://web.telegram.org/")
        elif "discord" in a or self.cfg.get("apps") == "discord":
            open_target("discord://", "https://discord.com/app")

    def activate(self):
        self.open_app(self.cfg.get("apps", "discord"))

    def extra_menu(self, menu):
        sm = menu.addMenu("Чьи уведомления показывать")
        grp = QActionGroup(sm)
        for key, label in NOTIFY_APPS.items():
            a = sm.addAction(label)
            a.setCheckable(True)
            a.setChecked(self.cfg.get("apps") == key)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: (self.set_opt("apps", k), setattr(self, "_count",
                                                                                         len(self.items()))))
        menu.addAction("Отметить всё прочитанным").triggered.connect(self.svc.mark_read)
        menu.addAction("Очистить список").triggered.connect(lambda: self.svc.clear(self.cfg.get("apps", "discord")))
        menu.addAction("Открыть Discord").triggered.connect(lambda: open_target("discord://", "https://discord.com/app"))
        menu.addAction("Настройки уведомлений Windows").triggered.connect(
            lambda: open_target("ms-settings:notifications"))


# ---------------------------------------------------------------------------
#  Claude без API-ключа: claude.ai во встроенном окошке (вход под своим аккаунтом)
# ---------------------------------------------------------------------------
CLAUDE_WEB_HOSTS = ("claude.ai", "claude.com", "anthropic.com", "accounts.google.com", "google.com",
                    "gstatic.com", "googleusercontent.com", "apple.com", "cloudflare.com", "challenges.cloudflare.com")


def claude_url(q=""):
    return "https://claude.ai/new" + (("?q=" + urllib.parse.quote(q)) if q else "")


_WEB = {}


def web_engine():
    """Встроенный браузер Qt (QtWebEngine) или None."""
    if "mod" not in _WEB:
        try:
            from PySide6 import QtWebEngineCore, QtWebEngineWidgets
            _WEB["mod"] = (QtWebEngineCore, QtWebEngineWidgets)
        except Exception:
            _WEB["mod"] = None
    return _WEB["mod"]


class ClaudePanel(QWidget):
    """Окошко с claude.ai рядом с виджетом. Профиль браузера свой и сохраняется - входить нужно один раз."""

    def __init__(self, mgr):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        core, widgets = web_engine()
        self.mgr = mgr
        self.setWindowTitle("Claude")
        self.resize(460, 680)
        self.setStyleSheet("QWidget#bar { background: #262624; } QLabel { color: #F5F4EF; font-size: 13px; "
                           "font-weight: 600; } QPushButton { color: #F5F4EF; background: transparent; border: none;"
                           " font-size: 15px; padding: 4px 9px; border-radius: 6px; }"
                           " QPushButton:hover { background: rgba(255,255,255,0.12); }")
        from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QHBoxLayout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QWidget(self)
        bar.setObjectName("bar")
        bar.setFixedHeight(36)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 0, 6, 0)
        bl.addWidget(QLabel("Claude"))
        bl.addStretch(1)
        self.b_new = QPushButton("+")
        self.b_new.setToolTip("Новый чат")
        self.b_ext = QPushButton("↗")
        self.b_ext.setToolTip("Открыть в браузере")
        self.b_pin = QPushButton("📌")
        self.b_pin.setToolTip("Не скрывать, когда щёлкаешь в другом месте")
        self.b_pin.setCheckable(True)
        self.b_close = QPushButton("✕")
        self.b_close.setToolTip("Скрыть (Esc)")
        for b in (self.b_new, self.b_ext, self.b_pin, self.b_close):
            bl.addWidget(b)
        lay.addWidget(bar)
        self.bar = bar
        self.profile = core.QWebEngineProfile("snowwidgets-claude", self)
        store = os.path.join(DATA_DIR, "web")
        self.profile.setPersistentStoragePath(store)
        self.profile.setCachePath(os.path.join(store, "cache"))
        self.profile.setPersistentCookiesPolicy(core.QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        import re
        ua = re.sub(r"\s*QtWebEngine/\S+", "", self.profile.httpUserAgent())   # обычный Chrome, а не "QtWebEngine"
        self.profile.setHttpUserAgent(ua)
        panel = self

        class Page(core.QWebEnginePage):
            def acceptNavigationRequest(self, url, nav_type, is_main):
                host = url.host().lower()
                if url.scheme() in ("http", "https") and host and not any(
                        host == h or host.endswith("." + h) for h in CLAUDE_WEB_HOSTS):
                    QDesktopServices.openUrl(url)          # посторонние ссылки - в обычный браузер
                    return False
                return super().acceptNavigationRequest(url, nav_type, is_main)

            def createWindow(self, _type):
                tmp = core.QWebEnginePage(panel.profile, panel)
                tmp.urlChanged.connect(lambda u, t=tmp: (QDesktopServices.openUrl(u), t.deleteLater()))
                return tmp

        self.view = widgets.QWebEngineView(self)
        self.page = Page(self.profile, self.view)
        self.view.setPage(self.page)
        self.view.setZoomFactor(0.9)
        lay.addWidget(self.view, 1)
        self.b_new.clicked.connect(lambda: self.open(claude_url()))
        self.b_ext.clicked.connect(lambda: QDesktopServices.openUrl(self.view.url()))
        self.b_close.clicked.connect(self.hide)
        self._drag = None

    def open(self, url, near=None):
        self.view.setUrl(QUrl(url))
        if near is not None and not self.isVisible():
            scr = QApplication.screenAt(near.center()) or QApplication.primaryScreen()
            a = scr.availableGeometry()
            x = near.left() - self.width() - 8 if near.left() - self.width() - 8 >= a.left() else near.right() + 8
            x = max(a.left(), min(x, a.right() - self.width()))
            y = max(a.top(), min(near.top(), a.bottom() - self.height()))
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.view.setFocus()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(ev)

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == ev.Type.ActivationChange and not self.isActiveWindow() and not self.b_pin.isChecked():
            QTimer.singleShot(150, lambda: (not self.isActiveWindow() and QApplication.activePopupWidget() is None
                                            and QApplication.activeModalWidget() is None and self.hide()))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton and ev.position().y() <= self.bar.height():
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag is not None:
            self.move(ev.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, ev):
        self._drag = None


KINDS = {c.KIND: c for c in (WeatherCard, MusicCard, BatteryCard, PhotoCard, CalendarCard, ClockCard,
                                SystemCard, ClaudeCard, NotifyCard, DiscordCard)}


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
        self.wall = Wallpaper()
        self.wall.check()
        self.battery = BatteryService()
        self.system = SystemService()
        self.battery.updated.connect(self.check_low)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._write)
        first = not self.cfg.get("widgets")
        if first:
            self.cfg["widgets"] = self.default_layout()
        for i, wc in enumerate(list(self.cfg["widgets"])):
            card = self._create(wc)
            if card is not None:
                card.appear(0.15 + i * 0.09)            # виджеты появляются по очереди
        if first:
            self.save()
        self.wall_timer = QTimer(self)                # сменились обои - обновить "стекло"
        self.wall_timer.timeout.connect(self.check_wallpaper)
        self.wall_timer.start(20 * 1000)
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
                if "style" not in data:                          # старые настройки: theme dark/light
                    data["style"] = "light" if data.get("theme") == "light" else "dark"
                data.pop("theme", None)
                if data["style"] not in STYLES:
                    data["style"] = "dark"
                data.setdefault("widgets", [])
                return data
        except Exception:
            pass
        return {"style": "dark", "opacity": 1.0, "locked": False, "animations": True, "widgets": []}

    def notify(self):
        if getattr(self, "_notify", None) is None:
            self._notify = NotifyService()
        return self._notify

    def claude_panel(self):
        """Окошко claude.ai (одно на все виджеты Claude) или None, если встроенного браузера нет."""
        if getattr(self, "_claude_panel", None) is None:
            if web_engine() is None:
                return None
            try:
                self._claude_panel = ClaudePanel(self)
            except Exception:
                traceback.print_exc()
                self._claude_panel = False
        return self._claude_panel or None

    def media(self):
        """Общий опрос плеера (создаётся, когда появляется первый виджет музыки)."""
        if getattr(self, "_media", None) is None:
            self._media = MediaService(self)
        return self._media

    def style_name(self, wcfg):
        name = wcfg.get("style") or self.cfg.get("style") or "dark"
        return name if name in STYLES else "dark"

    def check_wallpaper(self):
        if self.wall.check():
            for c in self.cards:
                c.update()

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
        """Колонками справа налево; если колонка не помещается по высоте - начинаем следующую."""
        a = QApplication.primaryScreen().availableGeometry()
        right = a.right() - 24
        y = a.top() + 24
        col_w = 0
        out = []
        for kind, size in (("weather", "m"), ("battery", "m"), ("photos", "l")):
            w, h = SIZES[size]
            if out and y + h > a.bottom() - 16:
                right -= col_w + 16
                y, col_w = a.top() + 24, 0
            wc = {"id": "%s-%d" % (kind, len(out)), "kind": kind, "size": size,
                  "x": right - w + 1 - MARGIN, "y": y - MARGIN}
            if kind == "photos":
                wc["folder"] = self.auto_photo_folder()
            out.append(wc)
            y += h + 16
            col_w = max(col_w, w)
        return out

    @staticmethod
    def auto_photo_folder():
        """Первая папка с фото: Telegram Desktop, Изображения, OneDrive."""
        for label, path in photo_places():
            if label in ("Загрузки", "Рабочий стол"):
                continue
            if count_images(path):
                return path
        return None

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
        if kind == "photos":
            wc["folder"] = self.auto_photo_folder()
        self.cfg["widgets"].append(wc)
        card = self._create(wc)
        if card is not None:
            card.appear()
        self.save()

    def remove(self, card):
        card.closing()
        if card.cfg in self.cfg["widgets"]:
            self.cfg["widgets"].remove(card.cfg)
        if card in self.cards:
            self.cards.remove(card)
        self.save()

        def dead():
            card.close()
            card.deleteLater()

        card.vanish(dead)

    def set_opt(self, key, val):
        self.cfg[key] = val
        for c in self.cards:
            c.update()
        self.save()

    def set_style_all(self, name):
        """Выбрать дизайн для всех виджетов (сбрасывает личный дизайн у каждого)."""
        for c in self.cards:
            c.cfg.pop("style", None)
        self.set_opt("style", name)

    def set_opacity_all(self, v):
        for c in self.cards:
            c.cfg.pop("opacity", None)
        self.set_opt("opacity", v)

    def set_flag(self, key, on):
        self.set_opt(key, bool(on))

    @staticmethod
    def opacity_menu(menu, cur, setter, allow_none=False):
        grp = QActionGroup(menu)
        items = ([(None, "Как у всех")] if allow_none else []) + \
            [(v, "Нет (непрозрачный)" if v >= 1.0 else "%d%%" % round((1 - v) * 100)) for v in OPACITY_STEPS]
        for v, label in items:
            a = menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(cur == v if (cur is None or v is None) else abs(float(cur) - v) < 0.01)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, v=v: setter(v))

    def menu_css(self):
        if STYLES[self.style_name({})]["light"]:
            return ""
        return ("QMenu { background:#2a2b30; color:#f2f2f4; border:1px solid #3a3b42; padding:4px; }"
                "QMenu::item { padding:5px 22px 5px 24px; border-radius:4px; }"
                "QMenu::item:selected { background:#0A84FF; }"
                "QMenu::separator { height:1px; background:#3a3b42; margin:4px 6px; }")

    def fill_common_menu(self, menu):
        add = menu.addMenu("Добавить виджет")
        for kind, cls in KINDS.items():
            add.addAction(cls.TITLE).triggered.connect(lambda _=False, k=kind: self.add(k))
        th = menu.addMenu("Оформление всех виджетов")
        grp = QActionGroup(th)
        for key, st in STYLES.items():
            a = th.addAction(st["name"])
            a.setCheckable(True)
            a.setChecked(self.style_name({}) == key)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self.set_style_all(k))
        th.addSeparator()
        self.opacity_menu(th.addMenu("Прозрачность"), self.cfg.get("opacity", 1.0), self.set_opacity_all)
        a = th.addAction("Анимации")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("animations", True)))
        a.toggled.connect(lambda v: self.set_flag("animations", v))
        a = menu.addAction("Закрепить виджеты (не двигать)")
        a.setCheckable(True)
        a.setChecked(bool(self.cfg.get("locked")))
        a.toggled.connect(lambda v: self.set_flag("locked", v))

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
        pan = getattr(self, "_claude_panel", None)
        if pan:                                   # страница браузера должна закрыться раньше своего профиля
            pan.view.setPage(None)
            pan.page.deleteLater()
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


def main():
    if not single_instance():
        msgbox("Виджеты уже запущены - ищи значок в трее (возле часов).")
        return 0
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)   # для встроенного браузера
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
