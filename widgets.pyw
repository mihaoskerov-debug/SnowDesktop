# -*- coding: utf-8 -*-
"""Виджеты рабочего стола для Windows 10/11 в стиле macOS.

  * Погода      - температура, прогноз по часам и на неделю, живой фон (снег, дождь, солнце).
  * Батарея     - заряд мыши / клавиатуры / наушников: Bluetooth и радио-приёмники Logitech
                  (Unifying, Bolt, Lightspeed), а также батарея ноутбука.
  * Фото        - слайд-шоу фотографий из папки (например, из "Загрузки\\Telegram Desktop").
  * Календарь   - листается стрелками и колёсиком мыши, праздники РФ.
  * Часы        - аналоговые часы с плавной секундной стрелкой.
  * Яндекс Музыка - что играет: крутящаяся пластинка, "волна" в такт музыке, кнопки управления.
  * Система     - загрузка процессора, памяти и диска.

Запуск: двойной клик по widgets.pyw (нужен Python 3.9+, PySide6 поставится сам).
Управление - значок в трее (возле часов): добавить виджет, тема, закрепить, автозапуск, выход.
Виджет: перетаскивай левой кнопкой, правая кнопка - размер и настройки, двойной клик - действие.
Данные: %APPDATA%\\SnowWidgets\\widgets.json
"""
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
import urllib.parse
import urllib.request

IS_WIN = sys.platform.startswith("win")
APP_NAME = "SnowWidgets"
APP_VERSION = "1.16"
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


def pythonw_exe():
    """pythonw.exe рядом с текущим python.exe - он запускает программы без окна консоли."""
    exe = sys.executable
    pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return pw if (IS_WIN and os.path.exists(pw)) else exe


def hide_console():
    """Если виджеты открылись через python.exe и Windows показала для них чёрное окно консоли -
    прячем его и отключаемся от него (оно закроется). Консоль, из которой запустили вручную, не трогаем."""
    if not IS_WIN or FROZEN:
        return
    try:
        k32 = ctypes.windll.kernel32
        hwnd = k32.GetConsoleWindow()
        if not hwnd:
            return                                   # уже без консоли (pythonw.exe)
        procs = (ctypes.c_uint32 * 8)()
        if k32.GetConsoleProcessList(procs, 8) > 1:
            return                                   # запущено из открытой командной строки - это её окно
        ctypes.windll.user32.ShowWindow(hwnd, 0)     # SW_HIDE
        k32.FreeConsole()
        devnull = open(os.devnull, "w")
        sys.stdout = sys.stderr = devnull
    except Exception:
        pass


hide_console()


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
    subprocess.Popen([pythonw_exe(), os.path.abspath(__file__)] + sys.argv[1:], creationflags=NO_WINDOW)
    sys.exit(0)


ensure_deps()

from PySide6.QtCore import (QObject, QPointF, QRectF, QStandardPaths, Qt,  # noqa: E402
                            QTimer, QUrl, Signal)
from PySide6.QtGui import (QActionGroup, QColor, QDesktopServices, QFont,  # noqa: E402
                           QIcon, QImage, QImageReader, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient, QConicalGradient)
from PySide6.QtWidgets import (QApplication, QFileDialog, QInputDialog, QMenu,  # noqa: E402
                               QSystemTrayIcon, QWidget)

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
               "music": ("#F2B705", "#E06A1B")}
OPACITY_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)


_ERR_SEEN = {}


def log_error(where):
    """Ошибка -> %APPDATA%\\SnowWidgets\\widgets_error.log (одна и та же - не чаще раза в минуту)."""
    tb = traceback.format_exc()
    key = where + tb[-200:]
    if time.time() - _ERR_SEEN.get(key, 0) < 60:
        return
    _ERR_SEEN[key] = time.time()
    try:
        with open(os.path.join(DATA_DIR, "widgets_error.log"), "a", encoding="utf-8") as fh:
            fh.write("%s  v%s  %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), APP_VERSION, where, tb))
    except Exception:
        pass


def log_error_text(msg):
    try:
        with open(os.path.join(DATA_DIR, "widgets_error.log"), "a", encoding="utf-8") as fh:
            fh.write("%s  v%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), APP_VERSION, msg))
    except Exception:
        pass


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


class WinHid:
    """Доступ к USB HID-устройствам через hid.dll и setupapi.dll самой Windows - без библиотеки hidapi.
    Повторяет ту часть интерфейса hidapi, что нужна виджету: enumerate() и device()."""

    def __init__(self):
        from ctypes import wintypes as W
        self.W = W
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hid = ctypes.WinDLL("hid", use_last_error=True)
        sa = ctypes.WinDLL("setupapi", use_last_error=True)
        HANDLE, BOOL, DWORD, ULONG = ctypes.c_void_p, W.BOOL, W.DWORD, W.ULONG
        self.INVALID = ctypes.c_void_p(-1).value

        class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
            _fields_ = [("cbSize", DWORD), ("InterfaceClassGuid", GUID), ("Flags", DWORD),
                        ("Reserved", ctypes.c_void_p)]

        class HIDD_ATTRIBUTES(ctypes.Structure):
            _fields_ = [("Size", ULONG), ("VendorID", ctypes.c_ushort), ("ProductID", ctypes.c_ushort),
                        ("VersionNumber", ctypes.c_ushort)]

        class HIDP_CAPS(ctypes.Structure):
            _fields_ = [("Usage", ctypes.c_ushort), ("UsagePage", ctypes.c_ushort),
                        ("InputReportByteLength", ctypes.c_ushort), ("OutputReportByteLength", ctypes.c_ushort),
                        ("FeatureReportByteLength", ctypes.c_ushort), ("Reserved", ctypes.c_ushort * 17),
                        ("Counts", ctypes.c_ushort * 10)]

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p), ("Offset", DWORD),
                        ("OffsetHigh", DWORD), ("hEvent", HANDLE)]

        class HIDP_VALUE_CAPS(ctypes.Structure):
            _fields_ = [("UsagePage", ctypes.c_ushort), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                        ("BitField", ctypes.c_ushort), ("LinkCollection", ctypes.c_ushort),
                        ("LinkUsage", ctypes.c_ushort), ("LinkUsagePage", ctypes.c_ushort),
                        ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                        ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                        ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte), ("BitSize", ctypes.c_ushort),
                        ("ReportCount", ctypes.c_ushort), ("Reserved2", ctypes.c_ushort * 5),
                        ("UnitsExp", ctypes.c_ulong), ("Units", ctypes.c_ulong), ("LogicalMin", ctypes.c_long),
                        ("LogicalMax", ctypes.c_long), ("PhysicalMin", ctypes.c_long), ("PhysicalMax", ctypes.c_long),
                        ("UsageMin", ctypes.c_ushort), ("UsageMax", ctypes.c_ushort), ("Rest", ctypes.c_ushort * 6)]

        self.HIDP_VALUE_CAPS = HIDP_VALUE_CAPS
        hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.POINTER(HIDP_VALUE_CAPS),
                                          ctypes.POINTER(ctypes.c_ushort), ctypes.c_void_p]
        hid.HidP_GetValueCaps.restype = ctypes.c_long
        hid.HidP_GetUsageValue.argtypes = [ctypes.c_int, ctypes.c_ushort, ctypes.c_ushort, ctypes.c_ushort,
                                           ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p, ctypes.c_void_p, ULONG]
        hid.HidP_GetUsageValue.restype = ctypes.c_long
        hid.HidD_GetInputReport.argtypes = [HANDLE, ctypes.c_void_p, ULONG]
        hid.HidD_GetInputReport.restype = BOOL
        self.SP_DEVICE_INTERFACE_DATA, self.HIDD_ATTRIBUTES = SP_DEVICE_INTERFACE_DATA, HIDD_ATTRIBUTES
        self.HIDP_CAPS, self.OVERLAPPED = HIDP_CAPS, OVERLAPPED
        hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
        hid.HidD_GetHidGuid.restype = None
        hid.HidD_GetAttributes.argtypes = [HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
        hid.HidD_GetAttributes.restype = BOOL
        hid.HidD_GetProductString.argtypes = [HANDLE, ctypes.c_void_p, ULONG]
        hid.HidD_GetProductString.restype = BOOL
        hid.HidD_GetPreparsedData.argtypes = [HANDLE, ctypes.POINTER(ctypes.c_void_p)]
        hid.HidD_GetPreparsedData.restype = BOOL
        hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
        hid.HidD_FreePreparsedData.restype = BOOL
        hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
        hid.HidP_GetCaps.restype = ctypes.c_long
        hid.HidD_SetFeature.argtypes = [HANDLE, ctypes.c_void_p, ULONG]
        hid.HidD_SetFeature.restype = BOOL
        hid.HidD_GetFeature.argtypes = [HANDLE, ctypes.c_void_p, ULONG]
        hid.HidD_GetFeature.restype = BOOL
        sa.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), W.LPCWSTR, W.HWND, DWORD]
        sa.SetupDiGetClassDevsW.restype = HANDLE
        sa.SetupDiEnumDeviceInterfaces.argtypes = [HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), DWORD,
                                                   ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
        sa.SetupDiEnumDeviceInterfaces.restype = BOOL
        sa.SetupDiGetDeviceInterfaceDetailW.argtypes = [HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
                                                        ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD), ctypes.c_void_p]
        sa.SetupDiGetDeviceInterfaceDetailW.restype = BOOL
        sa.SetupDiDestroyDeviceInfoList.argtypes = [HANDLE]
        sa.SetupDiDestroyDeviceInfoList.restype = BOOL
        k32.CreateFileW.argtypes = [W.LPCWSTR, DWORD, DWORD, ctypes.c_void_p, DWORD, DWORD, HANDLE]
        k32.CreateFileW.restype = HANDLE
        k32.CloseHandle.argtypes = [HANDLE]
        k32.CloseHandle.restype = BOOL
        k32.CreateEventW.argtypes = [ctypes.c_void_p, BOOL, BOOL, W.LPCWSTR]
        k32.CreateEventW.restype = HANDLE
        k32.WriteFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.c_void_p, ctypes.POINTER(OVERLAPPED)]
        k32.WriteFile.restype = BOOL
        k32.ReadFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.c_void_p, ctypes.POINTER(OVERLAPPED)]
        k32.ReadFile.restype = BOOL
        k32.WaitForSingleObject.argtypes = [HANDLE, DWORD]
        k32.WaitForSingleObject.restype = DWORD
        k32.GetOverlappedResult.argtypes = [HANDLE, ctypes.POINTER(OVERLAPPED), ctypes.POINTER(DWORD), BOOL]
        k32.GetOverlappedResult.restype = BOOL
        k32.CancelIoEx.argtypes = [HANDLE, ctypes.POINTER(OVERLAPPED)]
        k32.CancelIoEx.restype = BOOL
        self.k32, self.hid, self.sa = k32, hid, sa

    # ----- служебное -----
    def _open(self, path, access):
        h = self.k32.CreateFileW(path, access, 0x1 | 0x2, None, 3, 0x40000000, None)   # SHARE_RW, OPEN_EXISTING,
        return None if h in (None, self.INVALID) else h                                 # FILE_FLAG_OVERLAPPED

    def _info(self, path):
        h = self._open(path, 0)                         # без прав чтения: так можно спросить даже мышь/клавиатуру
        if h is None:
            return None
        try:
            at = self.HIDD_ATTRIBUTES()
            at.Size = ctypes.sizeof(at)
            if not self.hid.HidD_GetAttributes(h, ctypes.byref(at)):
                return None
            buf = ctypes.create_unicode_buffer(128)
            name = buf.value if self.hid.HidD_GetProductString(h, buf, ctypes.sizeof(buf)) else ""
            caps = self.HIDP_CAPS()
            pp = ctypes.c_void_p()
            if self.hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                try:
                    self.hid.HidP_GetCaps(pp, ctypes.byref(caps))
                finally:
                    self.hid.HidD_FreePreparsedData(pp)
            return {"path": path, "vendor_id": at.VendorID, "product_id": at.ProductID, "product_string": name,
                    "usage_page": caps.UsagePage, "usage": caps.Usage, "interface_number": -1,
                    "in_len": caps.InputReportByteLength, "out_len": caps.OutputReportByteLength,
                    "feat_len": caps.FeatureReportByteLength}
        finally:
            self.k32.CloseHandle(h)

    # Поля "заряд батареи" из стандарта HID: Battery Strength (страница 0x06, поле 0x20) и
    # Absolute State Of Charge / Remaining Capacity (страница 0x85). Их сообщают многие беспроводные
    # мыши и клавиатуры без фирменного протокола - Linux так и показывает их заряд, а Windows - нет.
    BATTERY_USAGES = {(0x06, 0x20), (0x85, 0x65), (0x85, 0x66)}

    def battery_usage(self, info):
        """Процент заряда из стандартного поля HID или None."""
        h = self._open(info["path"], 0)
        if h is None:
            return None
        pp = ctypes.c_void_p()
        try:
            if not self.hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
                return None
            caps = self.HIDP_CAPS()
            self.hid.HidP_GetCaps(pp, ctypes.byref(caps))
            for rtype, count, length, getter in ((2, caps.Counts[8], caps.FeatureReportByteLength,
                                                  self.hid.HidD_GetFeature),
                                                 (0, caps.Counts[2], caps.InputReportByteLength,
                                                  self.hid.HidD_GetInputReport)):
                if not count or not length:
                    continue
                arr = (self.HIDP_VALUE_CAPS * count)()
                n = ctypes.c_ushort(count)
                if self.hid.HidP_GetValueCaps(rtype, arr, ctypes.byref(n), pp) != 0x00110000:
                    continue
                for vc in arr[:n.value]:
                    if (vc.UsagePage, vc.UsageMin) not in self.BATTERY_USAGES:
                        continue
                    buf = ctypes.create_string_buffer(length)
                    buf[0] = bytes([vc.ReportID])
                    if not getter(h, buf, length):
                        continue
                    val = ctypes.c_ulong(0)
                    if self.hid.HidP_GetUsageValue(rtype, vc.UsagePage, vc.LinkCollection, vc.UsageMin,
                                                   ctypes.byref(val), pp, buf, length) != 0x00110000:
                        continue
                    lo, hi = vc.LogicalMin, vc.LogicalMax
                    v = val.value
                    if hi > lo:
                        pct = (v - lo) * 100.0 / (hi - lo)
                    else:
                        pct = float(v)
                    if 0 < pct <= 100:
                        return int(round(pct))
            return None
        finally:
            if pp:
                self.hid.HidD_FreePreparsedData(pp)
            self.k32.CloseHandle(h)

    # ----- как в hidapi -----
    def enumerate(self, vid=0, pid=0):
        guid = GUID()
        self.hid.HidD_GetHidGuid(ctypes.byref(guid))
        hdev = self.sa.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)   # PRESENT | DEVICEINTERFACE
        if hdev in (None, self.INVALID):
            return []
        out = []
        try:
            i = 0
            while True:
                ifd = self.SP_DEVICE_INTERFACE_DATA()
                ifd.cbSize = ctypes.sizeof(ifd)
                if not self.sa.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), i, ctypes.byref(ifd)):
                    break
                i += 1
                need = self.W.DWORD(0)
                self.sa.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifd), None, 0, ctypes.byref(need), None)
                if not need.value:
                    continue
                buf = ctypes.create_string_buffer(need.value + 4)
                ctypes.memmove(buf, ctypes.byref(self.W.DWORD(8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6)), 4)
                if not self.sa.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifd), buf, need.value, None, None):
                    continue
                path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
                try:
                    info = self._info(path)
                except Exception:
                    info = None
                if info and (not vid or info["vendor_id"] == vid) and (not pid or info["product_id"] == pid):
                    out.append(info)
        finally:
            self.sa.SetupDiDestroyDeviceInfoList(hdev)
        return out

    def device(self):
        return _WinHidDevice(self)


class _WinHidDevice:
    def __init__(self, api):
        self.api, self.h, self.info = api, None, None

    def open_path(self, path):
        api = self.api
        if isinstance(path, bytes):
            path = path.decode("utf-8", "replace")
        self.info = api._info(path) or {"in_len": 64, "out_len": 64, "feat_len": 91}
        self.h = api._open(path, 0x80000000 | 0x40000000) or api._open(path, 0)   # чтение+запись, иначе без прав
        if self.h is None:
            raise OSError("не открыть HID-устройство")

    def close(self):
        if self.h is not None:
            self.api.k32.CloseHandle(self.h)
            self.h = None

    def _io(self, fn, buf, size, timeout_ms):
        api = self.api
        ov = api.OVERLAPPED()
        ov.hEvent = api.k32.CreateEventW(None, True, False, None)
        try:
            ok = fn(self.h, buf, size, None, ctypes.byref(ov))
            if not ok and ctypes.get_last_error() != 997:            # ERROR_IO_PENDING
                return -1
            if api.k32.WaitForSingleObject(ov.hEvent, max(1, int(timeout_ms))) != 0:
                api.k32.CancelIoEx(self.h, ctypes.byref(ov))
            n = api.W.DWORD(0)
            if not api.k32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(n), True):
                return -1
            return n.value
        finally:
            api.k32.CloseHandle(ov.hEvent)

    def write(self, data):
        size = max(len(data), self.info.get("out_len") or 0)
        buf = ctypes.create_string_buffer(bytes(bytearray(data)) + bytes(size - len(data)), size)
        if self._io(self.api.k32.WriteFile, buf, size, 1000) < 0:
            raise OSError("запись в HID не удалась")
        return size

    def read(self, max_length, timeout_ms=0):
        size = max(max_length, self.info.get("in_len") or 0)
        buf = ctypes.create_string_buffer(size)
        n = self._io(self.api.k32.ReadFile, buf, size, timeout_ms or 1)
        return list(bytearray(buf.raw[:n])) if n > 0 else []

    def send_feature_report(self, data):
        size = max(len(data), self.info.get("feat_len") or 0)
        buf = ctypes.create_string_buffer(bytes(bytearray(data)) + bytes(size - len(data)), size)
        if not self.api.hid.HidD_SetFeature(self.h, buf, size):
            raise OSError("feature report не принят")
        return size

    def get_feature_report(self, report_id, max_length):
        size = max(max_length, self.info.get("feat_len") or 0)
        buf = ctypes.create_string_buffer(size)
        buf[0] = bytes([report_id])
        if not self.api.hid.HidD_GetFeature(self.h, buf, size):
            raise OSError("feature report не прочитан")
        return list(bytearray(buf.raw[:max_length]))


def _hid_module():
    """Доступ к HID-устройствам. В Windows - напрямую через системные hid.dll/setupapi.dll (ничего не
    нужно ставить). В других системах - библиотека hidapi, если она есть."""
    if _HID_STATE["mod"] is not None:
        return _HID_STATE["mod"]
    if IS_WIN:
        try:
            _HID_STATE["mod"] = WinHid()
            return _HID_STATE["mod"]
        except Exception:
            log_error("доступ к HID через Windows")
            _HID_STATE["error"] = "не удалось открыть hid.dll"
    try:
        import hid
        _HID_STATE["mod"] = hid
        return hid
    except ImportError:
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


# ----- Razer: протокол открыт проектом OpenRazer (отчёты по 90 байт через HID feature report) -----
RAZER_VID = 0x1532


def _razer_report(tid, cls, cmd, size, args=()):
    r = bytearray(90)
    r[1], r[5], r[6], r[7] = tid, size, cls, cmd
    for i, a in enumerate(args):
        r[8 + i] = a
    crc = 0
    for b in r[2:88]:
        crc ^= b
    r[88] = crc
    return r


def _razer_query(dev, cls, cmd, size=0x02):
    """Ответ мыши (90 байт) или None. Разные модели ждут разный "transaction id" - пробуем по очереди."""
    for tid in (0x1F, 0xFF, 0x3F, 0x08):
        try:
            dev.send_feature_report([0x00] + list(_razer_report(tid, cls, cmd, size)))
        except Exception:
            return None                              # этот интерфейс команды не принимает
        for _ in range(4):
            time.sleep(0.06)
            try:
                data = list(dev.get_feature_report(0x00, 91) or [])
            except Exception:
                return None
            if len(data) == 91:
                data = data[1:]
            if len(data) < 90:
                continue
            if data[0] == 0x01:                      # мышь занята - подождём
                continue
            if data[0] == 0x02 and data[6] == cls and data[7] == cmd:
                return data
            break                                    # "не поддерживается" - пробуем другой id
    return None


def razer_batteries(report=None):
    hid = _hid_module()
    if hid is None:
        return []
    out, done = [], set()
    try:
        infos = hid.enumerate(RAZER_VID, 0)
    except Exception:
        return []
    for d in infos:
        pid = d.get("product_id")
        if pid in done:
            continue
        dev = None
        try:
            dev = hid.device()
            dev.open_path(d["path"])
            r = _razer_query(dev, 0x07, 0x80)        # уровень заряда 0..255
            if r is None:
                continue
            done.add(pid)
            ch = _razer_query(dev, 0x07, 0x84)       # заряжается?
            level, charging = int(round(r[9] * 100 / 255.0)), bool(ch and ch[9])
            name = (d.get("product_string") or "Мышь Razer").strip()
            if level == 0 and not charging:
                if report is not None:
                    report.append("%s: ответила 0%% - скорее всего, мышь спит или выключена" % name)
                continue
            kind = guess_kind(name)
            out.append({"name": name, "level": level, "kind": "mouse" if kind == "bluetooth" else kind,
                        "charging": charging})
        except Exception:
            continue
        finally:
            try:
                if dev is not None:
                    dev.close()
            except Exception:
                pass
    return out


# ----- какие мыши вообще подключены (чтобы честно сказать, можно ли узнать заряд) -----
HID_BRANDS = {0x046D: "Logitech", 0x1532: "Razer", 0x1038: "SteelSeries", 0x1B1C: "Corsair", 0x0951: "HyperX",
              0x03F0: "HyperX", 0x0B05: "ASUS ROG", 0x258A: "SinoWealth (Glorious, Redragon, Defender и др.)",
              0x09DA: "A4Tech / Bloody", 0x3554: "VGN / VXE", 0x373B: "ATK / VXE", 0x1EA7: "приёмник 2.4G без фирмы",
              0x248A: "приёмник 2.4G без фирмы", 0x25A7: "приёмник 2.4G без фирмы", 0x1D57: "приёмник 2.4G без фирмы",
              0x30FA: "приёмник 2.4G без фирмы", 0x18F8: "приёмник 2.4G без фирмы", 0x04D9: "Holtek",
              0x093A: "PixArt", 0x2EA8: "Defender", 0x045E: "Microsoft", 0x17EF: "Lenovo", 0x413C: "Dell",
              0x1A81: "Holtek", 0x2717: "Xiaomi", 0x1BCF: "Sunplus"}
BATTERY_BRANDS = {0x046D, 0x1532}                    # чей протокол заряда виджет знает


def scan_mice():
    """[{brand, name, vid, pid, wireless, supported}] - мыши и радио-приёмники, которые видит Windows."""
    hid = _hid_module()
    if hid is None:
        return None
    try:
        infos = hid.enumerate(0, 0)
    except Exception:
        return None
    seen = {}
    for d in infos:
        vid, pid = d.get("vendor_id", 0), d.get("product_id", 0)
        name = (d.get("product_string") or "").strip()
        is_mouse = d.get("usage_page") == 1 and d.get("usage") == 2
        low = name.lower()
        wireless = any(w in low for w in ("wireless", "receiver", "dongle", "2.4", "unifying", "lightspeed",
                                          "bolt", "hyperspeed", "беспровод", "nano", "usb receiver"))
        if not (is_mouse or wireless):
            continue
        key = (vid, pid)
        e = seen.setdefault(key, {"vid": vid, "pid": pid, "name": name, "wireless": False, "mouse": False})
        e["name"] = e["name"] or name
        e["wireless"] |= wireless
        e["mouse"] |= is_mouse
    out = []
    for e in seen.values():
        if not e["mouse"] and not e["wireless"]:
            continue
        e["brand"] = HID_BRANDS.get(e["vid"], "неизвестная фирма")
        e["supported"] = e["vid"] in BATTERY_BRANDS
        out.append(e)
    out.sort(key=lambda e: (not e["wireless"], not e["supported"]))
    return out


def hid_std_batteries(skip_vids=(0x046D, 0x1532)):
    """Заряд из стандартных полей HID у всех остальных устройств (только Windows)."""
    api = _hid_module()
    if not isinstance(api, WinHid):
        return []
    out, done = [], set()
    try:
        infos = api.enumerate()
    except Exception:
        return []
    for info in infos:
        key = (info["vendor_id"], info["product_id"])
        if info["vendor_id"] in skip_vids or key in done:
            continue
        try:
            pct = api.battery_usage(info)
        except Exception:
            pct = None
        if pct is None:
            continue
        done.add(key)
        same = [i for i in infos if (i["vendor_id"], i["product_id"]) == key]
        name = next((i["product_string"] for i in same if i["product_string"]), "") or "Беспроводное устройство"
        usages = {(i["usage_page"], i["usage"]) for i in same}
        if (1, 2) in usages:
            kind = "mouse"
        elif (1, 6) in usages:
            kind = "keyboard"
        else:
            kind = guess_kind(name)
        if name.lower() in ("usb receiver", "2.4g wireless receiver", "wireless receiver", "usb dongle"):
            brand = HID_BRANDS.get(key[0], "приёмник 2.4G").split(" (")[0]
            name = ("Мышь" if kind == "mouse" else "Устройство") + " " + brand
        out.append({"name": name, "level": pct, "kind": kind, "charging": False})
    return out


def read_devices():
    if DEMO:
        return [{"name": "MX Master 3S", "level": 64, "kind": "mouse", "charging": False},
                {"name": "MX Keys", "level": 23, "kind": "keyboard", "charging": False},
                {"name": "WH-1000XM4", "level": 90, "kind": "headphones", "charging": False},
                {"name": "Xbox Wireless Controller", "level": 12, "kind": "gamepad", "charging": False},
                {"name": "Этот компьютер", "level": 81, "kind": "laptop", "charging": True}]
    devs, seen = [], set()
    notes = []
    for d in logi_batteries() + razer_batteries(notes) + hid_std_batteries() + [
            {"name": n, "level": lv, "kind": guess_kind(n), "charging": False} for n, lv in bt_batteries()]:
        if d["name"].lower() not in seen:
            seen.add(d["name"].lower())
            devs.append(d)
    order = ("mouse", "keyboard", "headphones", "gamepad", "pen", "bluetooth")
    devs.sort(key=lambda d: (order.index(d["kind"]) if d["kind"] in order else 9, d["name"].lower()))
    pc = pc_battery()
    if pc:
        devs.append(pc)
    _BATT_NOTES[:] = notes
    return devs


_BATT_NOTES = []


class BatteryService(QObject):
    updated = Signal()
    _done = Signal(object)

    def __init__(self):
        super().__init__()
        self.devices, self.stamp, self._busy = [], None, False
        self.mice = None                       # что за мыши подключены (None - не удалось узнать)
        self.notes = []
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
            log_error("чтение заряда")
            devs = None
        try:
            mice = [] if DEMO else scan_mice()
        except Exception:
            log_error("поиск мышей")
            mice = None
        try:
            self._done.emit((devs, mice, list(_BATT_NOTES)))      # сигнал доставится в главный поток
        except RuntimeError:
            pass

    def _finish(self, res):
        devs, self.mice, self.notes = res
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
        if "_av" not in self.__dict__:          # окно ещё не до конца создано или уже удаляется
            return
        self._last_paint = time.time()
        try:
            self._paint_frame()
        except Exception:
            log_error("кадр виджета %s" % self.KIND)
            self.want_frame(500)
        finally:
            self._wanted = self._frame_ms
            self._schedule()

    def needs_frames(self):
        """Виджет сейчас анимируется и ждёт следующего кадра не дольше пары секунд."""
        return 0 < getattr(self, "_wanted", 0) <= 2000 and self.isVisible()

    def _paint_frame(self):
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
        try:
            self._paint_card(p, e, press)
        finally:
            if p.isActive():
                p.end()

    def _paint_card(self, p, e, press):
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
        try:
            p.save()
            p.setOpacity(p.opacity() * op)
            self.paint_bg(p, path, r, th)
            p.restore()
            self.paint(p, r, th)
            if th["mode"] == "winter":
                self.paint_snowcap(p, r)
        except Exception:
            log_error("рисование виджета %s" % self.KIND)
            self.want_frame(1000)
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
            msg = self.mouse_hint(size == "s")
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

    def mouse_hint(self, short):
        b = self.mgr.battery
        if b.stamp is None:
            return "Ищу устройства..."
        if b.mice is None:
            return "Не удалось опросить USB-устройства (подробности - в widgets_error.log)"
        if b.notes:
            return b.notes[0]
        radio = [m for m in b.mice if m["wireless"]] or b.mice
        if not radio:
            return "Нет устройств с известным зарядом" if short else \
                "Нет устройств с известным зарядом.\nПодключи приёмник мыши в USB."
        m = radio[0]
        name = m["name"] or "мышь"
        if m["supported"]:
            return ("%s: пошевели мышь" % m["brand"]) if short else \
                ("%s (%s)\nМышь не ответила - пошевели её, она могла уснуть." % (name, m["brand"]))
        if short:
            return "%s: заряд не передаётся" % m["brand"].split(" (")[0]
        return ("%s - %s.\nЭта фирма не сообщает заряд компьютеру напрямую, его показывает только её "
                "программа. Нажми правой кнопкой → «Какие мыши видит программа»." % (name, m["brand"]))

    def mice_report(self):
        b = self.mgr.battery
        lines = ["Версия виджетов: %s" % APP_VERSION, ""]
        if b.mice is None:
            lines.append("USB-устройства опросить не удалось: %s" % (_HID_STATE.get("error") or "см. widgets_error.log"))
        elif not b.mice:
            lines.append("Мышей и радио-приёмников не найдено.")
        for m in b.mice or []:
            lines.append("%s | %s | VID %04X PID %04X | %s | заряд: %s" % (
                m["name"] or "(без названия)", m["brand"], m["vid"], m["pid"],
                "радио/беспроводная" if m["wireless"] else "мышь", "умею читать" if m["supported"] else "не умею"))
        for n in b.notes:
            lines.append(n)
        lines += ["", "Заряд найден у: " + (", ".join("%s %d%%" % (d["name"], d["level"]) for d in b.devices)
                                           or "ни у кого")]
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Icon.Information, "Батарея - какие мыши видит программа", "\n".join(lines))
        copy = box.addButton("Скопировать", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is copy:
            QApplication.clipboard().setText("\n".join(lines))

    def extra_menu(self, menu):
        menu.addAction("Обновить сейчас").triggered.connect(self.mgr.battery.refresh)
        menu.addAction("Какие мыши видит программа...").triggered.connect(self.mice_report)
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
#  Общие мелочи для виджета музыки: открыть программу, доставить библиотеку, кнопки плеера
# ---------------------------------------------------------------------------
def open_target(*targets):
    """Открыть первую сработавшую цель: протокол программы (yandexmusic://) или ссылку."""
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


def _cover_path(title, artist):
    import hashlib
    h = hashlib.md5(("%s|%s" % (artist.strip().lower(), title.strip().lower())).encode("utf-8")).hexdigest()
    return os.path.join(DATA_DIR, "covers", h + ".jpg")


def cover_from_cache(title, artist):
    p = _cover_path(title, artist)
    if os.path.exists(p):
        img = QImage(p)
        if not img.isNull():
            return img
    return None


def _norm(t):
    import re
    return re.sub(r"[^0-9a-zа-яё]+", " ", (t or "").lower()).strip()


def _similar(a, b):
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    return a in b or b in a or len(set(a.split()) & set(b.split())) >= max(1, min(len(a.split()), 2) // 2)


def cover_online(title, artist, log=None):
    """Обложка по названию и исполнителю: Яндекс Музыка, потом iTunes, потом Deezer. Сохраняется на диск."""
    q = urllib.parse.quote(("%s %s" % (artist, title)).strip())
    found = []
    try:
        j = http_json("https://api.music.yandex.net/search?type=track&page=0&text=" + q, 8)
        for t in ((j.get("result") or {}).get("tracks") or {}).get("results") or []:
            uri = t.get("coverUri") or ((t.get("albums") or [{}])[0].get("coverUri"))
            names = " ".join(a.get("name", "") for a in t.get("artists") or [])
            if uri:
                found.append((t.get("title"), names, "https://" + uri.replace("%%", "400x400")))
    except Exception as ex:
        log and log("обложка (Яндекс): %r" % (ex,))
    if not found:
        try:
            j = http_json("https://itunes.apple.com/search?entity=song&limit=5&term=" + q, 8)
            for t in j.get("results") or []:
                if t.get("artworkUrl100"):
                    found.append((t.get("trackName"), t.get("artistName"),
                                  t["artworkUrl100"].replace("100x100bb", "600x600bb")))
        except Exception as ex:
            log and log("обложка (iTunes): %r" % (ex,))
    if not found:
        try:
            j = http_json("https://api.deezer.com/search?limit=5&q=" + q, 8)
            for t in j.get("data") or []:
                url = (t.get("album") or {}).get("cover_xl") or (t.get("album") or {}).get("cover_big")
                if url:
                    found.append((t.get("title"), (t.get("artist") or {}).get("name"), url))
        except Exception as ex:
            log and log("обложка (Deezer): %r" % (ex,))
    # сначала совпадение и по названию, и по исполнителю, потом хотя бы по исполнителю, потом первое
    pick = next((f for f in found if _similar(f[0], title) and _similar(f[1], artist)), None) or \
        next((f for f in found if _similar(f[1], artist) or not artist), None) or (found[0] if found else None)
    if pick is None:
        return None
    try:
        req = urllib.request.Request(pick[2], headers=UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
        img = QImage.fromData(data)
        if img.isNull():
            return None
        p = _cover_path(title, artist)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        img.save(p, "JPG", 92)
        return img
    except Exception as ex:
        log and log("обложка (загрузка): %r" % (ex,))
        return None


# ----- обложки своих музыкальных файлов (MP3, FLAC, M4A): из самого файла или картинки рядом -----
AUDIO_EXT = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".alac", ".ogg", ".opus", ".wma", ".wav"}
FOLDER_IMAGES = ("cover", "folder", "front", "album", "albumart", "обложка")


def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _id3_text(body):
    if not body:
        return ""
    enc, data = body[0], body[1:]
    try:
        if enc == 0:
            t = data.decode("latin-1")
        elif enc == 1:
            t = data.decode("utf-16")
        elif enc == 2:
            t = data.decode("utf-16-be")
        else:
            t = data.decode("utf-8")
    except Exception:
        return ""
    return t.replace("\x00", " ").strip()


def _apic_image(body, v22=False):
    """Картинка из кадра APIC (ID3 2.3/2.4) или PIC (2.2): (тип картинки, байты)."""
    try:
        enc = body[0]
        if v22:
            ptype, i = body[4], 5
        else:
            m = body.index(b"\x00", 1)
            ptype, i = body[m + 1], m + 2
        rest = body[i:]
        if enc in (1, 2):                              # описание в UTF-16 - конец на двух нулях
            k = 0
            while k + 1 < len(rest) and rest[k:k + 2] != b"\x00\x00":
                k += 2
            return ptype, rest[k + 2:]
        j = rest.index(b"\x00")
        return ptype, rest[j + 1:]
    except Exception:
        return None, None


def read_id3(path, want_pic=False):
    """(название, исполнитель, картинка) из ID3-тега MP3. Большие кадры без нужды не читаем - перескакиваем."""
    with open(path, "rb") as f:
        head = f.read(10)
        if len(head) < 10 or head[:3] != b"ID3":
            return None
        ver, flags, size = head[3], head[5], _syncsafe(head[6:10])
        if flags & 0x80 or ver < 3:                    # редкие варианты - читаем тег целиком
            data = f.read(size)
            if flags & 0x80:
                data = data.replace(b"\xff\x00", b"\xff")
            return _id3_parse_mem(data, ver, flags, want_pic)
        end = 10 + size
        if flags & 0x40:                               # расширенный заголовок
            eh = f.read(4)
            f.seek((_syncsafe(eh) if ver == 4 else int.from_bytes(eh, "big") + 4) - 4, 1)
        title = artist = None
        pic, pic_type = None, None
        while f.tell() + 10 <= end:
            fh = f.read(10)
            fid = fh[:4]
            if not fid.strip(b"\x00") or not fid.isalnum():
                break
            fsize = _syncsafe(fh[4:8]) if ver == 4 else int.from_bytes(fh[4:8], "big")
            if fsize <= 0 or f.tell() + fsize > end:
                break
            if fid in (b"TIT2", b"TPE1", b"TPE2") or (want_pic and fid == b"APIC"):
                body = f.read(fsize)
                if fid == b"TIT2":
                    title = _id3_text(body)
                elif fid == b"TPE1":
                    artist = _id3_text(body)
                elif fid == b"TPE2" and not artist:
                    artist = _id3_text(body)
                elif fid == b"APIC":
                    ptype, img = _apic_image(body)
                    if img and (pic is None or (ptype == 3 and pic_type != 3)):   # 3 - лицевая обложка
                        pic, pic_type = img, ptype
            else:
                f.seek(fsize, 1)
        return title, artist, pic


def _id3_parse_mem(data, ver, flags, want_pic):
    title = artist = pic = None
    pos, hdr = 0, (10 if ver >= 3 else 6)
    while pos + hdr <= len(data):
        if ver >= 3:
            fid = data[pos:pos + 4]
            fsize = _syncsafe(data[pos + 4:pos + 8]) if ver == 4 else int.from_bytes(data[pos + 4:pos + 8], "big")
        else:
            fid = data[pos:pos + 3]
            fsize = int.from_bytes(data[pos + 3:pos + 6], "big")
        if not fid.strip(b"\x00") or fsize <= 0:
            break
        body = data[pos + hdr:pos + hdr + fsize]
        pos += hdr + fsize
        if fid in (b"TIT2", b"TT2"):
            title = _id3_text(body)
        elif fid in (b"TPE1", b"TP1"):
            artist = _id3_text(body)
        elif want_pic and pic is None and fid in (b"APIC", b"PIC"):
            pic = _apic_image(body, v22=(fid == b"PIC"))[1]
    return title, artist, pic


def read_flac(path, want_pic=False):
    title = artist = pic = None
    with open(path, "rb") as f:
        if f.read(4) != b"fLaC":
            return None
        while True:
            h = f.read(4)
            if len(h) < 4:
                break
            last, btype, ln = h[0] & 0x80, h[0] & 0x7F, int.from_bytes(h[1:4], "big")
            if btype == 4:                             # Vorbis comment - теги
                b = f.read(ln)
                try:
                    p = 4 + int.from_bytes(b[0:4], "little")
                    n = int.from_bytes(b[p:p + 4], "little")
                    p += 4
                    for _ in range(n):
                        cl = int.from_bytes(b[p:p + 4], "little")
                        kv = b[p + 4:p + 4 + cl].decode("utf-8", "replace")
                        p += 4 + cl
                        k, _s, v = kv.partition("=")
                        if k.upper() == "TITLE":
                            title = v
                        elif k.upper() == "ARTIST" and not artist:
                            artist = v
                except Exception:
                    pass
            elif btype == 6 and want_pic and pic is None:   # картинка
                b = f.read(ln)
                try:
                    p = 4
                    p += 4 + int.from_bytes(b[p:p + 4], "big")
                    p += 4 + int.from_bytes(b[p:p + 4], "big") + 16
                    plen = int.from_bytes(b[p:p + 4], "big")
                    pic = b[p + 4:p + 4 + plen]
                except Exception:
                    pass
            else:
                f.seek(ln, 1)
            if last:
                break
    return title, artist, pic


def _mp4_item(buf, name):
    i = buf.find(name)
    if i < 0:
        return None
    j = buf.find(b"data", i, i + 32)
    if j < 4:
        return None
    size = int.from_bytes(buf[j - 4:j], "big")
    return buf[j + 12:j - 4 + size]


def read_mp4(path, want_pic=False):
    if os.path.getsize(path) > 60 * 1024 * 1024:
        return None
    with open(path, "rb") as f:
        buf = f.read()
    dec = lambda b: b.decode("utf-8", "replace").strip() if b else None
    return dec(_mp4_item(buf, b"\xa9nam")), dec(_mp4_item(buf, b"\xa9ART")), \
        (_mp4_item(buf, b"covr") if want_pic else None)


def read_tags(path, want_pic=False):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            return read_id3(path, want_pic)
        if ext == ".flac":
            return read_flac(path, want_pic)
        if ext in (".m4a", ".mp4", ".aac", ".alac"):
            return read_mp4(path, want_pic)
    except Exception:
        return None
    return None


def file_cover(path):
    """Обложка музыкального файла: встроенная в файл, иначе cover.jpg / folder.jpg рядом с ним."""
    t = read_tags(path, want_pic=True)
    if t and t[2]:
        img = QImage.fromData(t[2])
        if not img.isNull():
            return img
    d = os.path.dirname(path)
    try:
        pics = [f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in (".jpg", ".jpeg", ".png", ".webp")]
    except Exception:
        pics = []
    pics.sort(key=lambda f: (not any(os.path.splitext(f)[0].lower().startswith(n) for n in FOLDER_IMAGES), f))
    stem = _norm(os.path.splitext(os.path.basename(path))[0])
    for f in pics:
        low = os.path.splitext(f)[0].lower()
        if any(low.startswith(n) for n in FOLDER_IMAGES) or _norm(low) == stem or len(pics) == 1:
            img = QImage(os.path.join(d, f))
            if not img.isNull():
                return img
    return None


PLAYER_HINTS = ("mpthree",)          # плееры, которые сами качают треки на диск (с тегами и обложками)


def player_dirs():
    """Папки программ-плееров вроде mpthree: в AppData, LocalAppData, Музыке, Документах, Загрузках."""
    home = os.path.expanduser("~")
    loc = QStandardPaths.StandardLocation
    bases = [os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages"),
             QStandardPaths.writableLocation(loc.MusicLocation), QStandardPaths.writableLocation(loc.DocumentsLocation),
             QStandardPaths.writableLocation(loc.DownloadLocation), home]
    out = []
    for b in bases:
        if not b or not os.path.isdir(b):
            continue
        try:
            names = os.listdir(b)
        except OSError:
            continue
        for n in names:
            if any(h in n.lower() for h in PLAYER_HINTS):
                p = os.path.join(b, n)
                if os.path.isdir(p) and p not in out:
                    out.append(p)
    return out


_RECENT = {"t": 0.0, "path": None}


def recent_player_file(max_age=20 * 60):
    """Самый свежий аудиофайл в папках плееров (его, скорее всего, и играют сейчас) или None."""
    now = time.time()
    if now - _RECENT["t"] < 5:
        return _RECENT["path"]
    best, best_t = None, now - max_age
    for d in player_dirs():
        count = 0
        for root, dirs, files in os.walk(d):
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in AUDIO_EXT:
                    continue
                count += 1
                p = os.path.join(root, fn)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                t = max(st.st_mtime, st.st_atime)
                if t > best_t:
                    best, best_t = p, t
            if count > 20000:
                break
    _RECENT.update(t=now, path=best)
    return best


_FILE_TRACK = {}


def file_track(path):
    """(название, исполнитель, обложка) играющего файла - из тегов, иначе из имени файла."""
    if path in _FILE_TRACK:
        return _FILE_TRACK[path]
    t = read_tags(path) or (None, None, None)
    title, artist = t[0], t[1]
    if not title:
        stem = os.path.splitext(os.path.basename(path))[0]
        if " - " in stem:
            artist, title = [x.strip() for x in stem.split(" - ", 1)]
        else:
            title = stem
    res = (title, artist or "", file_cover(path))
    _FILE_TRACK.clear() if len(_FILE_TRACK) > 50 else None
    _FILE_TRACK[path] = res
    return res


def music_folders(extra=()):
    loc = QStandardPaths.StandardLocation
    home = os.path.expanduser("~")
    cands = list(extra) + player_dirs() + [QStandardPaths.writableLocation(loc.MusicLocation) or os.path.join(home, "Music"),
                           QStandardPaths.writableLocation(loc.DownloadLocation) or os.path.join(home, "Downloads"),
                           QStandardPaths.writableLocation(loc.DesktopLocation) or os.path.join(home, "Desktop")]
    od = os.environ.get("OneDrive")
    if od:
        cands += [os.path.join(od, "Music"), os.path.join(od, "Музыка")]
    if IS_WIN:
        for letter in "CDEFGH":
            for name in ("Music", "Музыка", "MP3", "Mp3"):
                cands.append("%s:\\%s" % (letter, name))
    out, seen = [], set()
    for c in cands:
        if c and os.path.isdir(c):
            k = os.path.normcase(os.path.realpath(c))
            if k not in seen:
                seen.add(k)
                out.append(c)
    return out


class MusicIndex:
    """Список своих музыкальных файлов с названиями из тегов (запоминается в music_index.json)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.files = {}              # путь -> (mtime, нормализованное название, нормализованный исполнитель)
        self.built = 0.0
        self.path = os.path.join(DATA_DIR, "music_index.json")
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.files = {k: tuple(v) for k, v in json.load(fh).items()}
        except Exception:
            pass

    def rebuild(self, folders, log=None):
        found, fresh = {}, 0
        for root_dir in folders:
            for root, dirs, files in os.walk(root_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in ("node_modules", "$recycle.bin")]
                for fn in files:
                    if os.path.splitext(fn)[1].lower() not in AUDIO_EXT:
                        continue
                    p = os.path.join(root, fn)
                    try:
                        mt = os.path.getmtime(p)
                    except OSError:
                        continue
                    old = self.files.get(p)
                    if old and old[0] == mt:
                        found[p] = old
                        continue
                    t = read_tags(p) or (None, None, None)
                    found[p] = (mt, _norm(t[0]), _norm(t[1]))
                    fresh += 1
                    if len(found) > 40000:
                        break
        with self.lock:
            self.files = found
            self.built = time.time()
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(found, fh, ensure_ascii=False)
        except Exception:
            pass
        if log:
            log("музыкальные файлы: %d (новых или изменённых %d) в %d папках" % (len(found), fresh, len(folders)))

    def find(self, title, artist):
        nt, na = _norm(title), _norm(artist)
        if not nt:
            return None
        best, best_score = None, 0
        with self.lock:
            items = list(self.files.items())
        for p, (_mt, tt, ta) in items:
            stem = _norm(os.path.splitext(os.path.basename(p))[0])
            score = 0
            if tt and tt == nt:
                score += 6
            elif tt and (nt in tt or tt in nt):
                score += 3
            elif nt in stem:
                score += 3
            else:
                continue
            if na:
                if ta and (ta == na or na in ta or ta in na):
                    score += 4
                elif na in stem or na in _norm(os.path.dirname(p)):
                    score += 3
            if score > best_score:
                best, best_score = p, score
        return best if best_score >= 3 else None


_MUSIC_INDEX = None


def local_cover(title, artist, extra_folders=(), log=None):
    """Найти на компьютере файл, который играет, и достать его обложку."""
    global _MUSIC_INDEX
    if _MUSIC_INDEX is None:
        _MUSIC_INDEX = MusicIndex()
    idx = _MUSIC_INDEX
    path = idx.find(title, artist)
    if (path is None or not os.path.exists(path)) and time.time() - idx.built > 120:
        idx.rebuild(music_folders(extra_folders), log)          # файла нет в списке - пересканируем папки
        path = idx.find(title, artist)
    if path is None:
        return None
    img = file_cover(path)
    if img is None and log:
        log("в файле %s нет обложки и рядом нет картинки" % os.path.basename(path))
    return img


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
    for key, title in (("mpthree", "mpthree"), ("music.yandex", "Яндекс Музыка"), ("yandexmusic", "Яндекс Музыка"),
                       ("yandex.music", "Яндекс Музыка"), ("яндекс", "Яндекс Музыка"), ("yandex", "Яндекс"), ("spotify", "Spotify"), ("chrome", "Браузер Chrome"),
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
        self.gen = 0
        self._covers = {}
        self.reason = None
        self.need_winrt = False
        self.last_payload = time.time()
        self.dead_since = None
        self.none_count = 0
        self._start()

    def _start(self):
        self.gen += 1
        self.last_payload = time.time()
        self.dead_since = None
        threading.Thread(target=self._run, args=(self.gen,), daemon=True).start()

    def watch(self):
        """Вызывается раз в 2 с: если опрос завис или умер - запускаем новый."""
        if DEMO or not IS_WIN:
            return
        now = time.time()
        if self.dead_since is not None and now - self.dead_since > 30:
            self.log("переподключаюсь к плееру после ошибки")
            self._start()
        elif self.dead_since is None and now - self.last_payload > 15:
            self.log("опрос плеера не отвечает %.0f с - запускаю заново" % (now - self.last_payload))
            self._start()

    # ----- поток опроса -----
    def _emit(self, payload, gen=None):
        payload["gen"] = gen if gen is not None else self.gen
        try:
            self._got.emit(payload)
        except RuntimeError:
            pass

    def _run(self, gen):
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
        try:
            # Этот поток сам говорит Windows, что будет работать с WinRT (многопоточный режим).
            # Без этого после перезапуска опроса Windows переставала отвечать - название трека не приходило.
            ctypes.windll.ole32.CoInitializeEx(None, 0)
        except Exception:
            pass
        mods = _winrt_try()
        if mods is None and not _HID_STATE.get("winrt_tried"):
            _HID_STATE["winrt_tried"] = True                 # ставим компонент один раз за запуск
            self._emit({"error": "Ставлю компонент для связи с плеером..."}, gen)
            if pip_install(*_WINRT_PKGS):
                mods = _winrt_try()
        if mods is None:
            self.reason = "не установлен компонент winrt для связи с плеером"
            self._emit({"error": "Нет компонента winrt для связи с плеером", "dead": True, "need_winrt": True}, gen)
            return
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.loop = loop
        try:
            loop.run_until_complete(self._poll(mods, gen))
        except Exception as ex:
            self.log("опрос остановился: %r" % (ex,))
            self._emit({"error": "Не удалось подключиться к плееру Windows", "dead": True}, gen)
        finally:
            try:
                loop.close()
            except Exception:
                pass

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
        """Обложка, которую плеер передал Windows (пробуем три способа прочитать поток)."""
        import asyncio
        ref = getattr(props, "thumbnail", None)
        if ref is None:
            return None
        errors = []
        for way in (1, 2, 3):
            try:
                stream = await asyncio.wait_for(ref.open_read_async(), 4)
                size = int(stream.size)
                if not size or size > 20 * 1024 * 1024:
                    return None
                if way == 3:                                 # через DataReader поверх потока
                    reader = ss.DataReader(stream)
                    await asyncio.wait_for(reader.load_async(size), 4)
                    arr = bytearray(size)
                    reader.read_bytes(arr)
                    data = bytes(arr)
                else:
                    buf = ss.Buffer(size)
                    res = await asyncio.wait_for(stream.read_async(buf, size, ss.InputStreamOptions.READ_AHEAD), 4)
                    if way == 1:
                        data = bytes(memoryview(res))
                    else:
                        reader = ss.DataReader.from_buffer(res)
                        arr = bytearray(res.length)
                        reader.read_bytes(arr)
                        data = bytes(arr)
                img = QImage.fromData(data)
                if not img.isNull():
                    return img
                errors.append("способ %d: картинка не распознана" % way)
            except Exception as ex:
                errors.append("способ %d: %r" % (way, ex))
        self.log("обложка из Windows не прочиталась: " + "; ".join(errors))
        return None

    def _fetch_cover(self, key, title, artist):
        if key in getattr(self, "_fetching", set()):
            return
        self._fetching = getattr(self, "_fetching", set()) | {key}

        def work():
            img = None
            try:
                img = local_cover(title, artist, self.mgr.cfg.get("music_dirs") or (), self.log)
            except Exception as ex:
                self.log("обложка из файла: %r" % (ex,))
            if img is not None:
                try:
                    p = _cover_path(title, artist)
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    img.save(p, "JPG", 92)
                except Exception:
                    pass
            else:
                img = cover_online(title, artist, self.log)
            if img is not None:
                self._covers[key] = img
                self._emit({"cover_for": key, "img": img})

        threading.Thread(target=work, daemon=True).start()

    def _log_sessions(self, mgr, why):
        now = time.time()
        if now - getattr(self, "_sess_logged", 0) < 60:
            return
        self._sess_logged = now
        try:
            items = ["%s(статус %s)" % (x.source_app_user_model_id, self._status(x)) for x in mgr.get_sessions()]
        except Exception as ex:
            items = ["ошибка: %r" % (ex,)]
        self.log("%s; плееры в Windows: %s" % (why, ", ".join(items) or "нет"))

    @staticmethod
    def _status(s):
        try:
            return int(s.get_playback_info().playback_status)
        except Exception:
            return -1

    @staticmethod
    def is_yandex(aumid):
        a = (aumid or "").lower()
        return any(k in a for k in ("yandex", "яндекс", "music.yandex"))

    def _pick(self, mgr):
        """Какой плеер показывать: сначала играющая Яндекс Музыка, потом любой играющий плеер,
        потом тот, что показывали в прошлый раз, потом "текущий" по мнению Windows.
        Если Windows знает хоть один плеер - что-то показываем всегда (не отбрасываем "чужие")."""
        try:
            sessions = list(mgr.get_sessions() or [])
        except Exception:
            sessions = []
        aid = lambda s: (getattr(s, "source_app_user_model_id", "") or "")
        self.session_names = [aid(s) for s in sessions]
        if not sessions:
            return None
        ya = [s for s in sessions if self.is_yandex(aid(s))]
        for pool in (ya, sessions):
            playing = [s for s in pool if self._status(s) == 4]
            if playing:
                return playing[0]
        last = getattr(self, "_last_app", None)
        for s in sessions:
            if aid(s) == last:
                return s
        if ya:
            return ya[0]
        try:
            return mgr.get_current_session() or sessions[0]
        except Exception:
            return sessions[0]

    async def _poll(self, mods, gen):
        import asyncio
        mc, ss = mods
        mgr = None
        last_key, cover, fails = None, None, 0
        while gen == self.gen:                              # старый поток тихо завершится после перезапуска
            st = None
            try:
                if mgr is None or fails >= 5:              # после череды ошибок подключаемся заново
                    mgr = await asyncio.wait_for(mc.GlobalSystemMediaTransportControlsSessionManager.request_async(), 8)
                    fails = 0
                s = self._pick(mgr)
                self.session = s
                if s is None:
                    self._log_sessions(mgr, "нет подходящего плеера")
                    self.reason = ("Windows не знает ни одного плеера: приложение не передаёт ей трек "
                                   "(проверь - видно ли название песни у ползунка громкости)")
                if s is not None:
                    props = await asyncio.wait_for(s.try_get_media_properties_async(), 3)
                    title = (props.title or "").strip()
                    self.reason = None if title else "%s не передаёт название трека" % app_title(
                        s.source_app_user_model_id)
                    if title:
                        status = self._status(s)
                        tl = s.get_timeline_properties()
                        app = s.source_app_user_model_id or ""
                        key = (title, props.artist, app)
                        # не все плееры честно сообщают "играет" - смотрим ещё, идёт ли время трека
                        raw = _secs(tl.position)
                        prev = getattr(self, "_prev_pos", None)
                        moving = bool(prev and prev[0] == key and abs(raw - prev[1]) > 0.3)
                        self._prev_pos = (key, raw)
                        playing = status == 4 or (moving and status not in (3, 5))
                        sig = (app, status, title)
                        if sig != getattr(self, "_logged", None):
                            self._logged = sig
                            self.log("плеер: %s | статус %s (4 - играет, 5 - пауза) | %s" % (app, status, title))
                        if key != last_key:
                            last_key = key
                            cover = await self._thumb(props, ss)
                            if cover is None:
                                cover = cover_from_cache(title, props.artist or "")
                            if cover is None:
                                self._fetch_cover(key, title, props.artist or props.album_artist or "")
                        if cover is None:
                            cover = self._covers.get(key)
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
                              "status": status,
                              "dur": _secs(tl.end_time) - _secs(tl.start_time), "stamp": time.time(),
                              "cover": cover, "key": key}
                fails = 0
            except Exception as ex:
                fails += 1
                self.log("опрос: %r" % (ex,))
                self.reason = "ошибка связи с плеером: %s" % type(ex).__name__
                st = "keep"                                 # временная ошибка - не стираем трек с экрана
            self._emit({"state": st}, gen)
            await asyncio.sleep(1.0)

    def _on(self, payload):
        if payload.get("gen") != self.gen:
            return                                          # сообщение от старого (перезапущенного) опроса
        self.last_payload = time.time()
        if "error" in payload:
            self.error = payload["error"]
            if payload.get("dead"):
                self.dead_since = time.time()
            self.need_winrt = bool(payload.get("need_winrt"))
            self.updated.emit()
            return
        if "cover_for" in payload:                         # обложка нашлась в интернете
            if self.state and self.state.get("key") == payload["cover_for"] and self.state.get("cover") is None:
                self.state = dict(self.state, cover=payload["img"])
                self.updated.emit()
            return
        self.error = None
        st = payload["state"]
        if st == "keep":
            return
        if st is None:
            self.none_count += 1
            if self.state and self.none_count < 4:          # плеер "моргнул" - пару секунд ничего не меняем
                return
        else:
            self.none_count = 0
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
YA_ORANGE = QColor("#FF8A3D")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(text):
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{%s}" % text), ctypes.byref(g))
    return g


def _com(obj, index, argtypes, *args):
    """Вызов метода COM-объекта по номеру в таблице методов (без сторонних библиотек)."""
    vt = ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0]
    fp = ctypes.cast(vt, ctypes.POINTER(ctypes.c_void_p))[index]
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(fp)(obj, *args)


class AudioMeter:
    """Насколько громко сейчас играет звук (пиковый уровень из Windows Core Audio) -
    по нему "волна" прыгает в такт, а пластинка понимает, что музыка идёт."""

    def __init__(self):
        self.meter = None
        self.next_try = 0.0
        self.last = 0.0
        self.error = None

    def _release(self, obj):
        try:
            if obj:
                _com(obj, 2, [])
        except Exception:
            pass

    def _init(self):
        self.next_try = time.time() + 15.0              # раз в 15 с подключаемся заново (смена наушников и т.п.)
        self._release(self.meter)
        self.meter = None
        if not IS_WIN or DEMO:
            return
        enum = ctypes.c_void_p()
        dev = ctypes.c_void_p()
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitializeEx(None, 2)
            hr = ole32.CoCreateInstance(ctypes.byref(_guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 23,
                                        ctypes.byref(_guid("A95664D2-9614-4F35-A746-DE8DB63617E6")),
                                        ctypes.byref(enum))
            if hr != 0 or not enum:
                self.error = "MMDeviceEnumerator: 0x%08X" % (hr & 0xFFFFFFFF)
                return
            hr = _com(enum, 4, [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)], 0, 1, ctypes.byref(dev))
            if hr != 0 or not dev:
                self.error = "нет устройства вывода звука: 0x%08X" % (hr & 0xFFFFFFFF)
                return
            meter = ctypes.c_void_p()
            iid = _guid("C02216F6-8C67-4B5B-9D00-D008E73E0064")
            hr = _com(dev, 3, [ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                      ctypes.byref(iid), 23, None, ctypes.byref(meter))
            if hr != 0 or not meter:
                self.error = "AudioMeter: 0x%08X" % (hr & 0xFFFFFFFF)
                return
            self.meter = meter
            self.error = None
        except Exception as ex:
            self.error = repr(ex)
        finally:
            self._release(dev)
            self._release(enum)

    def peak(self):
        """0..1 или None, если узнать нельзя."""
        if time.time() >= self.next_try:
            self._init()
        if self.meter is None:
            return None
        try:
            v = ctypes.c_float()
            if _com(self.meter, 3, [ctypes.POINTER(ctypes.c_float)], ctypes.byref(v)) != 0:
                return None
            self.last = clamp(float(v.value))
            return self.last
        except Exception as ex:
            self.error = repr(ex)
            self.meter = None
            return None


_METER = AudioMeter()


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
        self.cover = None
        self.label = None
        self.blur = self.prev_blur = None
        self.dom = QColor(YA_YELLOW)
        self.fade_t0 = 0.0
        self.track_t0 = 0.0
        self.angle = 0.0
        self.level = 0.0
        self.bars = []
        rnd = random.Random("snow")
        self.shape = [0.45 + 0.55 * (0.5 + 0.5 * math.sin(i * 0.37 + rnd.random() * 6)) * rnd.uniform(0.6, 1.0)
                      for i in range(120)]
        self._changed()

    # ----- данные трека -----
    def _changed(self):
        st = self.media.state
        key = (st or {}).get("key")
        if key != self.cover_key:
            self.cover_key = key
            self.cover = (st or {}).get("cover")
            self.prev_blur = self.blur
            self._prepare()
            self.fade_t0 = time.time() if self.animated else 0.0
            self.track_t0 = self.fade_t0
            rnd = random.Random(str(key))                  # "форма волны" у каждого трека своя
            self.shape = [0.45 + 0.55 * (0.5 + 0.5 * math.sin(i * 0.37 + rnd.random() * 6)) * rnd.uniform(0.6, 1.0)
                          for i in range(120)]
        elif st is not None and st.get("cover") is not self.cover:   # обложка пришла позже (нашлась в интернете)
            self.cover = (st or {}).get("cover")
            self.prev_blur = self.blur
            self._prepare()
            self.fade_t0 = time.time() if self.animated else 0.0
        self.update()

    def _prepare(self):
        r = self.card_rect()
        img = self.cover
        if img is not None and not img.isNull():
            self.blur = blur_image(img, int(r.width() * 1.15), int(r.height() * 1.15), 10)
            side = min(img.width(), img.height())
            sq = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
            self.label = sq.scaled(160, 160, Qt.AspectRatioMode.IgnoreAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            avg = sq.scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            c = QColor(avg.pixel(0, 0))
            h, s, v, _a = c.getHsv()
            self.dom = QColor.fromHsv(max(0, h), max(90, s), max(200, v))     # яркий вариант цвета обложки
        else:
            self.blur = None
            self.label = None
            self.dom = QColor(YA_YELLOW)

    def size_changed(self):
        self._prepare()
        self.prev_blur = None

    # ----- живые величины: громкость, вращение -----
    def _tick(self, playing, has_track=True):
        t = time.time()
        peak = _METER.peak() if has_track else 0.0
        if not playing and peak is not None and peak > 0.02 and has_track:
            playing = True                                  # звук идёт - значит, играет
        if self.cfg.get("spin") == "always" and (self.media.state or {}).get("title"):
            playing = True
        self._vis_playing = playing
        if not playing:
            peak = 0.0
        elif peak is not None and peak < 0.02 and self.cfg.get("spin") == "always":
            peak = None                                     # тишина, но крутить велено - мягкий ритм
        if peak is None:                                    # нет данных о звуке - мягкий "ритм" ~120 уд/мин
            beat = max(0.0, math.sin(t * math.tau * 1.95)) ** 4
            peak = 0.38 + 0.42 * beat + 0.08 * math.sin(t * 7.3) + 0.05 * math.sin(t * 13.1)
        target = clamp(peak * 1.15) if playing else 0.0
        k = 1.0 - math.exp(-self._dt * (22.0 if target > self.level else 5.0))   # быстрый взлёт, плавный спад
        self.level += (target - self.level) * k
        spin = self.av("spin", 150.0 if playing else 0.0, 2.2)                     # градусов в секунду
        self.angle = (self.angle + spin * self._dt) % 360.0
        slide = self.av("slide", 1.0 if playing else 0.0, 3.5)
        if playing or spin > 0.5 or self.level > 0.01:
            self.want_frame(33)
        return slide

    # ----- фон -----
    def paint_bg(self, p, path, r, th):
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(46, 40, 26))
        g.setColorAt(1, QColor(14, 14, 16))
        p.fillPath(path, g)
        t = time.time()
        e = ease_out_cubic((t - self.fade_t0) / 0.8) if self.fade_t0 else 1.0
        if e < 1.0:
            self.want_frame(16)
        playing = bool((self.media.state or {}).get("playing")) and self.animated

        def draw_blur(img, op):
            if img is None:
                return
            dx = math.sin(t * 0.11) * 0.06 * r.width() if playing else 0.0      # фон медленно плывёт
            dy = math.cos(t * 0.09) * 0.06 * r.height() if playing else 0.0
            p.save()
            p.setOpacity(p.opacity() * op)
            p.drawImage(QPointF(r.x() - (img.width() - r.width()) / 2 + dx,
                                r.y() - (img.height() - r.height()) / 2 + dy), img)
            p.restore()

        if e < 1.0:
            draw_blur(self.prev_blur, 1.0)
        draw_blur(self.blur, e)
        p.fillPath(path, QColor(0, 0, 0, 120))

    # ----- элементы -----
    def _glow(self, p, cx, cy, rad):
        c = QColor(self.dom)
        g = QRadialGradient(QPointF(cx, cy), rad)
        c.setAlpha(int(40 + 120 * self.level))
        g.setColorAt(0, c)
        c2 = QColor(self.dom)
        c2.setAlpha(0)
        g.setColorAt(1, c2)
        p.save()
        p.setPen(NOPEN)
        p.setBrush(g)
        k = 1.0 + 0.12 * self.level
        p.drawEllipse(QPointF(cx, cy), rad * k, rad * k)
        p.restore()

    def _vinyl(self, p, cx, cy, R, label=True):
        p.save()
        p.setPen(NOPEN)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(QPointF(cx + 2, cy + 4), R, R)
        g = QRadialGradient(QPointF(cx, cy), R)
        g.setColorAt(0.0, QColor("#202022"))
        g.setColorAt(0.96, QColor("#0c0c0d"))
        g.setColorAt(1.0, QColor("#2c2c2e"))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), R, R)
        p.setBrush(Qt.BrushStyle.NoBrush)
        n = max(6, int(R / 4))
        for k in range(n):                                   # бороздки
            rr = R * (0.42 + 0.55 * k / n)
            p.setPen(QPen(QColor(255, 255, 255, 14 + (10 if k % 3 == 0 else 0)), 0.8))
            p.drawEllipse(QPointF(cx, cy), rr, rr)
        p.translate(cx, cy)
        p.rotate(self.angle)
        lr = R * 0.36
        if label:                                           # "яблоко" пластинки - обложка, крутится
            lp = QPainterPath()
            lp.addEllipse(QPointF(0, 0), lr, lr)
            p.save()
            p.setClipPath(lp, Qt.ClipOperation.IntersectClip)
            if self.label is not None:
                p.drawImage(QRectF(-lr, -lr, 2 * lr, 2 * lr), self.label)
            else:
                lg = QLinearGradient(-lr, -lr, lr, lr)
                lg.setColorAt(0, YA_YELLOW)
                lg.setColorAt(1, YA_ORANGE)
                p.fillRect(QRectF(-lr, -lr, 2 * lr, 2 * lr), lg)
            p.restore()
            p.setPen(QPen(QColor(0, 0, 0, 120), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), lr, lr)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1.4))       # метка - видно, что пластинка крутится
        p.drawLine(QPointF(lr + 3, 0), QPointF(R * 0.9, 0))
        p.rotate(-self.angle)
        ring = QPainterPath()                               # неподвижный блик (свет падает с одной стороны)
        ring.addEllipse(QPointF(0, 0), R * 0.98, R * 0.98)
        inner = QPainterPath()
        inner.addEllipse(QPointF(0, 0), lr + 2, lr + 2)
        cg = QConicalGradient(QPointF(0, 0), 40)
        clear = QColor(255, 255, 255, 0)
        for pos, a in ((0.0, 0), (0.05, 46), (0.1, 0), (0.5, 0), (0.55, 30), (0.6, 0), (1.0, 0)):
            c = QColor(255, 255, 255, a) if a else clear
            cg.setColorAt(pos, c)
        p.setPen(NOPEN)
        p.setBrush(cg)
        p.drawPath(ring.subtracted(inner))
        p.setBrush(QColor("#d9d9d9"))
        p.drawEllipse(QPointF(0, 0), max(1.6, R * 0.04), max(1.6, R * 0.04))
        p.restore()

    def _sleeve(self, p, rc, radius=10):
        p.save()
        p.setPen(NOPEN)
        for i in range(8, 0, -2):
            p.setBrush(QColor(0, 0, 0, 16))
            p.drawRoundedRect(rc.adjusted(-i * 0.3, -i * 0.1, i * 0.3, i * 0.7), radius + i * 0.3, radius + i * 0.3)
        path = QPainterPath()
        path.addRoundedRect(rc, radius, radius)
        p.setClipPath(path, Qt.ClipOperation.IntersectClip)
        img = self.cover
        if img is not None and not img.isNull():
            k = max(rc.width() / img.width(), rc.height() / img.height())
            w, h = img.width() * k, img.height() * k
            p.drawImage(QRectF(rc.center().x() - w / 2, rc.center().y() - h / 2, w, h), img)
        else:
            g = QLinearGradient(rc.topLeft(), rc.bottomRight())
            g.setColorAt(0, YA_YELLOW)
            g.setColorAt(1, YA_ORANGE)
            p.fillRect(rc, g)
            draw_note(p, rc.center().x(), rc.center().y(), rc.width() * 0.42, QColor(40, 24, 0, 200))
        hl = QLinearGradient(rc.topLeft(), rc.bottomLeft())  # лёгкий глянец сверху
        hl.setColorAt(0, QColor(255, 255, 255, 40))
        hl.setColorAt(0.35, QColor(255, 255, 255, 0))
        p.fillRect(rc, hl)
        p.restore()

    def _record(self, p, cover, R, slide_max, slide):
        """Обложка-конверт, из которой выезжает крутящаяся пластинка."""
        cx = cover.center().x() + slide_max * smooth(slide)
        cy = cover.center().y()
        self._glow(p, cover.center().x() + slide_max * 0.5, cy, cover.width() * 0.95)
        self._vinyl(p, cx, cy, R)
        self._sleeve(p, cover, 10 if cover.width() < 150 else 14)

    def _wave(self, p, rc, st):
        """Прогресс в виде "волны": проигранная часть жёлтая, столбики прыгают в такт."""
        dur = st["dur"]
        frac = self.media.position() / dur if dur > 0 else 0.0
        n = max(8, int(rc.width() / 5))
        if len(self.bars) != n:
            self.bars = [0.3] * n
        t = time.time()
        playing = getattr(self, "_vis_playing", st["playing"]) and self.animated
        mid = rc.center().y()
        played = QLinearGradient(rc.x(), 0, rc.right(), 0)
        played.setColorAt(0, YA_YELLOW)
        played.setColorAt(1, YA_ORANGE)
        p.save()
        for i in range(n):
            base = self.shape[i % len(self.shape)] if self.shape else 0.5
            if playing:
                wob = 0.5 + 0.5 * math.sin(t * (3.1 + (i % 7) * 0.9) + i * 1.7)
                target = base * (0.3 + 0.7 * min(1.0, self.level * 1.25) * (0.55 + 0.45 * wob))
            else:
                target = base * 0.35
            k = 1.0 - math.exp(-self._dt * (18.0 if target > self.bars[i] else 7.0))
            self.bars[i] += (target - self.bars[i]) * k
            h = max(2.0, rc.height() * self.bars[i])
            x = rc.x() + i * rc.width() / n
            bar = QRectF(x, mid - h / 2, 3.0, h)
            p.setPen(NOPEN)
            if (i + 0.5) / n <= frac or (dur <= 0 and playing):     # длина неизвестна - вся волна "живая"
                p.setBrush(played)
            else:
                p.setBrush(QColor(255, 255, 255, 70))
            p.drawRoundedRect(bar, 1.5, 1.5)
        p.restore()
        if dur > 0:
            self.hit(QRectF(rc.x(), rc.y() - 4, rc.width(), rc.height() + 8),
                     lambda: self.media.command("seek", self._seek_to))

    def _times(self, p, rc, st):
        dur = st["dur"]
        if dur <= 0:
            return
        pos = self.media.position()
        soft = QColor(255, 255, 255, 170)
        text(p, QRectF(rc.x(), rc.y(), 60, 14), fmt_time(pos), font(10), soft, AL)
        text(p, QRectF(rc.right() - 60, rc.y(), 60, 14), "-" + fmt_time(dur - pos), font(10), soft, AR)

    def _controls(self, p, cx, cy, size, gap):
        playing = bool(getattr(self, "_vis_playing", False))
        for name, dx, sc in (("prev", -gap, 0.7), ("toggle", 0, 1.0), ("next", gap, 0.7)):
            s = size * sc
            rc = QRectF(cx + dx - s * 0.75, cy - s * 0.75, s * 1.5, s * 1.5)
            if name == "toggle":
                pulse = 1.0 + 0.06 * self.level if playing else 1.0
                p.setPen(NOPEN)
                p.setBrush(QColor(255, 255, 255, 240))
                p.drawEllipse(rc.center(), s * 0.72 * pulse, s * 0.72 * pulse)
                draw_media_icon(p, "pause" if playing else "play", rc.center().x() + (0 if playing else s * 0.05),
                                rc.center().y(), s * 0.62, QColor(20, 20, 22))
            else:
                draw_media_icon(p, name, rc.center().x(), rc.center().y(), s * 0.62, WHITE)
            self.hit(rc, lambda n=name: self.media.command(n))

    def _titles(self, p, rc_title, rc_artist, st, align):
        k = ease_out_cubic((time.time() - self.track_t0) / 0.6) if self.track_t0 else 1.0
        if k < 1.0:
            self.want_frame(16)
        p.save()
        p.setOpacity(p.opacity() * k)
        p.translate((1 - k) * 14, 0)                         # новый трек мягко "въезжает"
        text(p, rc_title, st["title"], font(rc_title.height() * 0.68, SEMI), WHITE, align)
        text(p, rc_artist, st["artist"], font(rc_artist.height() * 0.68), QColor(255, 255, 255, 190), align)
        p.restore()

    # ----- мышь -----
    def mousePressEvent(self, ev):
        st = self.media.state
        self._seek_to = 0.0
        if st and st["dur"] > 0:
            x0, w = self._wave_geom(self.card_rect())
            self._seek_to = clamp((ev.position().x() - x0) / max(1.0, w)) * st["dur"]
        super().mousePressEvent(ev)

    def _wave_geom(self, r):
        if self.cfg["size"] == "m":
            return r.x() + 198, r.right() - 16 - (r.x() + 198)
        return r.x() + 24, r.width() - 48

    # ----- рисование -----
    def paint(self, p, r, th):
        st = self.media.state
        size = self.cfg["size"]
        if not st or not st.get("title"):
            pk = _METER.peak()
            if pk is not None and pk > 0.02:
                self._sound_t = time.time()
            if time.time() - getattr(self, "_sound_t", 0) < 3.0:
                # звук идёт, а название Windows не отдала. Если это плеер вроде mpthree, который сам качает
                # треки на диск, - берём самый свежий файл из его папки; иначе просто живая пластинка
                path = recent_player_file()
                if path:
                    title, artist, cover = file_track(path)
                    st = {"title": title, "artist": artist, "album": "", "app": "mpthree", "playing": True,
                          "pos": 0.0, "dur": 0.0, "stamp": time.time(), "cover": cover, "key": None, "status": 4}
                    if cover is not self.cover:
                        self.cover = cover
                        self.prev_blur = self.blur
                        self._prepare()
                        self.fade_t0 = time.time() if self.animated else 0.0
                else:
                    why = self.media.reason or self.media.error or "название трека не пришло от плеера"
                    st = {"title": "Играет музыка", "artist": why, "album": "",
                          "app": "", "playing": True, "pos": 0.0, "dur": 0.0, "stamp": time.time(), "cover": None,
                          "key": None, "status": 4}
        generic = bool(st) and st.get("key") is None and self.media.state is None
        if generic:
            r0 = self.card_rect()
            self.hit(QRectF(r0.x(), r0.y(), r0.width(), r0.height() * 0.62), self.diagnose)
            if self.media.need_winrt and not FROZEN:
                pill = QRectF(r0.right() - 176, r0.y() + 8, 164, 24)
                p.setPen(NOPEN)
                p.setBrush(YA_YELLOW)
                p.drawRoundedRect(pill, 12, 12)
                text(p, pill, "Установить компонент", font(11, SEMI), QColor(20, 20, 20))
                self.hit(pill, self.install_winrt)
        playing = bool(st and st.get("title") and st["playing"])
        # звук по громкости считаем "игрой", только если плеер не сказал прямо "пауза"/"стоп"
        slide = self._tick(playing, bool(st and st.get("title")) and (st or {}).get("status") not in (3, 5))
        playing = self._vis_playing
        if not st or not st.get("title"):
            R = 40 if size != "s" else 36
            cy = r.y() + (r.height() * 0.34 if size != "l" else 120)
            self._vinyl(p, r.center().x(), cy, R, label=True)
            msg = self.media.error or "Ничего не играет"
            text(p, QRectF(r.x() + 12, cy + R + 10, r.width() - 24, 20), msg, font(13, SEMI), WHITE)
            pill = QRectF(r.center().x() - 90, cy + R + 38, 180, 30) if size != "s" else \
                QRectF(r.x() + 16, r.bottom() - 40, r.width() - 32, 28)
            if pill.bottom() <= r.bottom() - 4:
                p.setPen(NOPEN)
                p.setBrush(YA_YELLOW)
                p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
                text(p, pill, "Открыть Яндекс Музыку" if size != "s" else "Открыть", font(12, SEMI), QColor(20, 20, 20))
                self.hit(pill, self.activate)
            return
        src = app_title(st.get("app"))
        if size == "s":
            cx, cy = r.center().x(), r.y() + 68
            self._glow(p, cx, cy, 80)
            self._vinyl(p, cx, cy, 52)
            self.hit(QRectF(cx - 52, cy - 52, 104, 104), lambda: self.media.command("toggle"))
            if not playing:                                  # на паузе - кнопка play поверх пластинки
                p.setPen(NOPEN)
                p.setBrush(QColor(255, 255, 255, 230))
                p.drawEllipse(QPointF(cx, cy), 17, 17)
                draw_media_icon(p, "play", cx + 1.5, cy, 15, QColor(20, 20, 22))
            self._titles(p, QRectF(r.x() + 12, r.y() + 126, r.width() - 24, 20),
                         QRectF(r.x() + 12, r.y() + 145, r.width() - 24, 17), st, AC)
            return
        if size == "m":
            cover = QRectF(r.x() + 16, r.y() + 24, 122, 122)
            self._record(p, cover, 56, 58, slide)
            x0 = r.x() + 198
            w = r.right() - 16 - x0
            text(p, QRectF(x0, r.y() + 14, w, 14), src.upper(), font(10, SEMI), YA_YELLOW, AL | AVC)
            self._titles(p, QRectF(x0, r.y() + 30, w, 22), QRectF(x0, r.y() + 52, w, 18), st, AL | AVC)
            self._wave(p, QRectF(x0, r.y() + 76, w, 28), st)
            self._times(p, QRectF(x0, r.y() + 106, w, 14), st)
            self._controls(p, x0 + w / 2, r.y() + 142, 24, 50)
            return
        cover = QRectF(r.x() + 30, r.y() + 24, 186, 186)
        self._record(p, cover, 86, 76, slide)
        text(p, QRectF(r.x() + 24, r.y() + 12, r.width() - 48, 12), src.upper(), font(9, SEMI), YA_YELLOW, AR | AVC)
        self._titles(p, QRectF(r.x() + 24, r.y() + 222, r.width() - 48, 24),
                     QRectF(r.x() + 24, r.y() + 246, r.width() - 48, 19), st, AC)
        self._wave(p, QRectF(r.x() + 24, r.y() + 274, r.width() - 48, 34), st)
        self._times(p, QRectF(r.x() + 24, r.y() + 310, r.width() - 48, 14), st)
        self._controls(p, r.center().x(), r.y() + 346, 26, 66)

    def wheel(self, pos, delta):
        if delta:
            self.media.command("next" if delta < 0 else "prev")

    def activate(self):
        local = os.environ.get("LOCALAPPDATA", "")
        open_target("yandexmusic://", os.path.join(local, "Programs", "YandexMusic", "Яндекс Музыка.exe"),
                    "https://music.yandex.ru/")

    def install_winrt(self):
        """Тихо (без окна консоли) поставить компонент связи с плеером, потом перезапустить виджеты."""
        if getattr(self, "_installing", False):
            return
        self._installing = True
        self.media.reason = "устанавливаю компонент... (1-2 минуты)"
        self.update()
        done = {"ok": None}
        threading.Thread(target=lambda: done.update(ok=pip_install(*_WINRT_PKGS)), daemon=True).start()
        self._pip_timer = QTimer(self)

        def check():
            if done["ok"] is None:
                return
            self._pip_timer.stop()
            self._installing = False
            if done["ok"] and _winrt_try() is not None:
                self.mgr.restart()
            else:
                self.media.reason = "не получилось установить компонент - проверь интернет"
                self.update()

        self._pip_timer.timeout.connect(check)
        self._pip_timer.start(1000)

    def add_music_dir(self):
        d = QFileDialog.getExistingDirectory(None, "Папка, где лежат твои MP3 (оттуда возьмутся обложки)",
                                             (self.mgr.cfg.get("music_dirs") or [""])[0])
        if d:
            dirs = [x for x in (self.mgr.cfg.get("music_dirs") or []) if os.path.normcase(x) != os.path.normcase(d)]
            self.mgr.set_opt("music_dirs", [os.path.normpath(d)] + dirs[:9])
            if _MUSIC_INDEX is not None:
                _MUSIC_INDEX.built = 0.0                       # пересканировать при следующем треке
            self.media._fetching = set()
            st = self.media.state
            if st and st.get("cover") is None and st.get("title"):
                self.media._fetch_cover(st["key"], st["title"], st.get("artist", ""))

    def diagnose(self):
        st = self.media.state or {}
        peak = _METER.peak()
        lines = ["Версия виджетов: %s" % APP_VERSION,
                 "Анимации включены: %s" % ("да" if self.animated else "НЕТ (Оформление → Анимации)"),
                 "Плеер: %s" % (st.get("app") or "не найден"),
                 "Трек: %s — %s" % (st.get("artist", ""), st.get("title", "")) if st.get("title") else "Трек: нет",
                 "Статус от плеера: %s (4 - играет, 5 - пауза, 3 - стоп)" % st.get("status", "?"),
                 "Программа считает, что играет: %s" % ("да" if st.get("playing") else "нет"),
                 "Громкость звука сейчас: %s" % ("%.2f" % peak if peak is not None else
                                                 "неизвестно (%s)" % (_METER.error or "нет данных")),
                 "Пластинка крутится: %s" % ("да" if getattr(self, "_vis_playing", False) else "нет"),
                 "Режим пластинки: %s" % ("всегда" if self.cfg.get("spin") == "always" else "когда играет"),
                 "Ошибка связи с плеером: %s" % (self.media.error or "нет"),
                 "Почему нет названия: %s" % (self.media.reason or "-"),
                 "Обложка: %s" % ("есть" if st.get("cover") is not None else "нет"),
                 "Папки плееров (mpthree): %s" % (", ".join(player_dirs()) or "не найдены"),
                 "Свежий файл в них: %s" % (recent_player_file() or "нет"),
                 "Папки с музыкой: %s" % (", ".join(music_folders(self.mgr.cfg.get("music_dirs") or ())) or "-"),
                 "Плееры, которые знает Windows: %s" % (", ".join(getattr(self.media, "session_names", []) or [])
                                                         or "ни одного"),
                 "", "Журналы: " + DATA_DIR]
        from PySide6.QtWidgets import QMessageBox
        box = QMessageBox(QMessageBox.Icon.Information, "Музыка - диагностика", "\n".join(lines))
        copy = box.addButton("Скопировать", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is copy:
            QApplication.clipboard().setText("\n".join(lines))

    def extra_menu(self, menu):
        menu.addAction("Открыть Яндекс Музыку").triggered.connect(self.activate)
        a = menu.addAction("Крутить пластинку всегда (если анимация не включается)")
        a.setCheckable(True)
        a.setChecked(self.cfg.get("spin") == "always")
        a.toggled.connect(lambda v: self.set_opt("spin", "always" if v else None))
        menu.addAction("Папка с моей музыкой (для обложек)...").triggered.connect(self.add_music_dir)
        menu.addAction("Диагностика...").triggered.connect(self.diagnose)



KINDS = {c.KIND: c for c in (WeatherCard, MusicCard, BatteryCard, PhotoCard, CalendarCard, ClockCard,
                                SystemCard)}


# ---------------------------------------------------------------------------
#  Автозапуск, один экземпляр
# ---------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command():
    if FROZEN:
        return '"%s"' % sys.executable
    return '"%s" "%s"' % (pythonw_exe(), os.path.abspath(__file__))


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
    if "--restart" in sys.argv:                 # перезапуск: ждём, пока старая копия закроется
        for _ in range(40):
            if _single_instance_once():
                return True
            time.sleep(0.25)
        return False
    return _single_instance_once()


def _single_instance_once():
    global _MUTEX
    if not IS_WIN:
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
        _MUTEX = k32.CreateMutexW(None, False, "Local\\SnowWidgets_v1")
        if ctypes.get_last_error() == 183:
            k32.CloseHandle(ctypes.c_void_p(_MUTEX))
            _MUTEX = None
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
        self.watchdog = QTimer(self)                  # сторож: замершие анимации и опрос плеера
        self.watchdog.timeout.connect(self.watch)
        self.watchdog.start(2000)
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
                data["widgets"] = [w for w in data["widgets"] if w.get("kind") in KINDS]
                data.pop("claude_key", None)
                for junk in ("web", "wpn_copy"):
                    shutil.rmtree(os.path.join(DATA_DIR, junk), ignore_errors=True)
                try:
                    os.remove(os.path.join(DATA_DIR, "notifications.json"))
                except OSError:
                    pass
                return data
        except Exception:
            pass
        return {"style": "dark", "opacity": 1.0, "locked": False, "animations": True, "widgets": []}

    def watch(self):
        now = time.time()
        for c in self.cards:
            try:
                if not c.needs_frames():
                    c._stalls = 0
                    continue
                late = now - getattr(c, "_last_paint", now)
                if late < max(2.0, c._wanted / 1000.0 * 4):
                    c._stalls = 0
                    continue
                c._stalls = getattr(c, "_stalls", 0) + 1
                c._ft.stop()
                if c._stalls >= 3:                         # окно перестало перерисовываться - показываем заново
                    log_error_text("анимация виджета %s стояла %.0f с, окно показано заново (visible=%s)"
                                   % (c.KIND, late, c.isVisible()))
                    c.hide()
                    c.show()
                    c._stalls = 0
                c.update()
            except Exception:
                log_error("сторож")
        m = getattr(self, "_media", None)
        if m is not None:
            m.watch()

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
        tray.setToolTip("Виджеты рабочего стола v" + APP_VERSION)
        menu = QMenu()

        def rebuild():
            menu.clear()
            menu.setStyleSheet(self.menu_css())
            head = menu.addAction("Виджеты, версия " + APP_VERSION)
            head.setEnabled(False)
            menu.addSeparator()
            self.fill_common_menu(menu)
            menu.addAction("Обновить заряд устройств").triggered.connect(self.battery.refresh)
            menu.addSeparator()
            if IS_WIN:
                a = menu.addAction("Запускать вместе с Windows")
                a.setCheckable(True)
                a.setChecked(autostart_get())
                a.toggled.connect(lambda v: autostart_set(bool(v)))
            if IS_WIN and not FROZEN:
                menu.addAction("Ярлык на рабочем столе (запуск без консоли)").triggered.connect(self.make_shortcut)
            menu.addAction("Папка с настройками").triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(DATA_DIR)))
            menu.addSeparator()
            menu.addAction("Перезапустить (после обновления)").triggered.connect(self.restart)
            menu.addAction("Выход").triggered.connect(self.quit)

        rebuild()
        menu.aboutToShow.connect(rebuild)
        tray.setContextMenu(menu)
        tray.show()
        self.tray, self._menu = tray, menu

    def make_shortcut(self):
        """Ярлык "Виджеты" на рабочем столе: запускает через pythonw.exe, то есть без чёрного окна."""
        script = os.path.abspath(__file__).replace("'", "''")
        exe = pythonw_exe().replace("'", "''")
        ps = ("$d=[Environment]::GetFolderPath('Desktop'); "
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Виджеты.lnk')); "
              "$s.TargetPath='%s'; $s.Arguments='\"%s\"'; $s.WorkingDirectory='%s'; "
              "$s.IconLocation='%s,0'; $s.Save()" % (exe, script, os.path.dirname(script), exe))
        try:
            res = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                  "-Command", ps], capture_output=True, timeout=30, creationflags=NO_WINDOW)
            ok = res.returncode == 0
        except Exception:
            ok = False
        if self.tray is not None:
            self.tray.showMessage("Виджеты", "Ярлык «Виджеты» создан на рабочем столе - запускай через него."
                                  if ok else "Не получилось создать ярлык.",
                                  QSystemTrayIcon.MessageIcon.Information, 5000)

    def restart(self):
        """Запустить программу заново - новая копия дождётся, пока эта закроется."""
        args = ([sys.executable] if FROZEN else [pythonw_exe(), os.path.abspath(__file__)]) + ["--restart"]
        try:
            subprocess.Popen(args, creationflags=NO_WINDOW if IS_WIN else 0)
        except Exception:
            log_error("перезапуск")
            return
        self.quit()

    def quit(self):
        self._save_timer.stop()
        self._write()
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


def main():
    if not single_instance():
        msgbox("Виджеты уже запущены - ищи значок в трее (возле часов).\n\n"
               "Если ты обновил программу: значок в трее -> «Перезапустить (после обновления)» "
               "или «Выход», а потом запусти снова. Иначе продолжит работать старая версия.")
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
