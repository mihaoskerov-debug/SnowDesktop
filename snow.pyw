# -*- coding: utf-8 -*-
"""Снег на рабочем столе (Windows и macOS): падающий снег, сугробы на окнах и панели задач / Dock,
гирлянды, сосульки, иней, ёлка, метель, снегоуборочные машины, снеговики, снежки.
Все настройки - в окне настроек (значок снежинки в трее / строке меню).

Горячие клавиши (работают всегда, Ctrl+Shift+...):
                     Windows        macOS
    настройки          F1             S
    снегоуборщик       F2             B
    метель вкл/выкл    F3             W
    режим снежков      F10            T
    опережение сугробов при таскании окна +/-:   F7 / F8     ] / [
    Y - лепить снеговика   C - стряхнуть снег с окон   P - пауза   Q - выход
Те же команды есть в меню значка снежинки.

Как лепить снеговика:
    1. Включи режим лепки (Ctrl+Shift+Y).
    2. Зажми левую кнопку мыши и води мышкой - снежок растет.
    3. Отпусти над окном или панелью задач - шар упадет на верхний край.
    4. Следующие шары отпускай над снеговиком - они встанут сверху (всего 3 шара).
    Средняя кнопка по снеговику - дать имя. Правая - убрать. Esc - выйти.

macOS: запуск - python3 snow.pyw (или Snow.command). Снег идёт на основном экране.
Данные (настройки, снеговики, сугробы, логи): Windows - %APPDATA%\\SnowDesktop,
macOS - ~/Library/Application Support/SnowDesktop.
"""
import ctypes
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import traceback
from ctypes import wintypes as wt

# ---------- Настройки ----------
FLAKES = 150               # количество снежинок
FPS = 60 if sys.platform.startswith("win") else 30   # кадров в секунду (если грузит процессор - уменьши)
MIN_SIZE = 1.4             # минимальный размер снежинки
MAX_SIZE = 4.2             # максимальный размер снежинки
FALL_SPEED = 1.0           # множитель скорости падения
WIND_STRENGTH = 1.2        # сила ветра
MOUSE_RADIUS = 140         # радиус, в котором снег реагирует на курсор
MOUSE_FORCE = 1.0          # сила реакции на курсор (0 - выключить)

SNOW_OVER_WINDOWS = False  # True - снег идет и поверх окон
SNOW_ON_WINDOWS = True     # сугробы на верхнем крае окон и панели задач
GARLANDS = True            # гирлянды на окнах
MAX_BALL = 46              # максимальный размер снежного кома при лепке

# --- сугробы ---
SNOW_FLOOR = True          # куча снега на нижнем краю экрана (если нет панели задач)
ACCUMULATE = 1.0           # скорость накопления снега (0 - не копить, 2 - вдвое быстрее)
MAX_DRIFT_WIN = 20         # максимальная высота сугроба на окне, px
MAX_DRIFT_TASK = 30        # ... на панели задач
MAX_DRIFT_FLOOR = 90       # ... на нижнем краю экрана
REPOSE = 1.2               # крутизна откоса сугроба (меньше - более пологий)
EDGE_SLOPE = 0.8           # крутизна у края окна (с него снег сползает)
SWEEP = True               # смахивать сугробы быстрым движением курсора
SWEEP_SPEED = 7.0          # насколько быстро надо вести мышь (px за кадр)
SWEEP_RADIUS = 34          # радиус "метлы" вокруг курсора, px
SHAKE_OFF = True           # быстро таскаешь окно - снег слетает
MAX_CHUNKS = 700           # максимум летящих комьев снега
SYNC_LEAD_MS = 24          # опережение при таскании окна, миллисекунды (убирает отставание
                           # сугробов и гирлянд; 0 - выключить). Подстроить на ходу: Ctrl+Shift+F7 / F8
                           # (на Mac: Ctrl+Shift+] / [)
FULLSCREEN_API = True      # прятать снег, когда Windows сообщает о полноэкранном приложении

# --- снегоуборочная машина ---
PLOW = True                # включить снегоуборщика
PLOW_INTERVAL = 120        # как часто выезжает, секунды
PLOW_FIRST = 20            # первый выезд после запуска, секунды
PLOW_SPEED = 2.4           # скорость, px за кадр
PLOW_VARIETY = True        # разные машины по очереди: грузовичок, трактор, снегоочиститель

# --- погода и гости ---
BLIZZARD_AUTO = True       # метель сама по расписанию
BLIZZARD_INTERVAL = 12     # как часто, минуты
BLIZZARD_LENGTH = 40       # сколько длится, секунды

# --- украшения ---
ICICLES = True             # сосульки под окнами
FROST = True               # иней по краям окон
TREE = True                # ёлка с огнями на панели задач
TREE_POS = 90              # где стоит ёлка, % ширины экрана

# --- прочее ---
TRAILS = True              # следы курсора в сугробах
ECO = True                 # экономия: меньше FPS на батарее и когда ты долго ничего не трогаешь
SAVE_STATE = True          # запоминать снеговиков и сугробы между запусками
# --------------------------------

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
if not (IS_WIN or IS_MAC):
    print("Это приложение работает только в Windows и macOS.")
    sys.exit(1)

if IS_WIN:
    # Qt должен работать в настоящих пикселях экрана, как и системные окна
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
else:                                      # macOS: Qt и системные окна считают в точках
    user32 = dwmapi = None
HERE = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "SnowDesktop"
APP_VERSION = "4.1"
FROZEN = bool(getattr(sys, "frozen", False))       # запущено из .exe / .app (PyInstaller)
if IS_WIN:
    _BASE = os.environ.get("APPDATA") or HERE
else:
    _BASE = os.path.expanduser("~/Library/Application Support")
DATA_DIR = os.path.join(_BASE, APP_NAME)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = HERE
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

# Подписи, зависящие от системы
AUTOSTART_LABEL = "Запускать вместе с Windows" if IS_WIN else "Запускать при входе в macOS"
TRAY_WHERE = "в трее (возле часов)" if IS_WIN else "в строке меню (вверху экрана)"
# Горячие клавиши (всегда Ctrl+Shift+...). На Mac F-клавиши обычно требуют Fn, поэтому там - буквы.
HK = ({"settings": "F1", "plow": "F2", "blizzard": "F3", "throw": "F10", "lead_up": "F7", "lead_dn": "F8"}
      if IS_WIN else
      {"settings": "S", "plow": "B", "blizzard": "W", "throw": "T", "lead_up": "]", "lead_dn": "["})


def msgbox(text, title="Снег", flags=0x40):
    if IS_MAC:
        try:
            esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e",
                            'display dialog "%s" with title "%s" buttons {"OK"} default button "OK"'
                            % (esc(text), esc(title))], timeout=600)
        except Exception:
            print(title + ": " + text)
        return
    try:
        user32.MessageBoxW(0, text, title, flags)
    except Exception:
        pass


def _deps_ok():
    try:
        import PySide6.QtWidgets  # noqa: F401
        if IS_MAC:
            import objc, Quartz, AppKit  # noqa: F401
        return True
    except ImportError:
        return False


def ensure_deps():
    if _deps_ok():
        return
    if IS_MAC:
        # У системного и Homebrew-Python pip часто запрещён, поэтому ставим всё в свой venv
        vdir = os.path.join(DATA_DIR, "venv")
        vpy = os.path.join(vdir, "bin", "python3")
        if os.path.realpath(sys.prefix) == os.path.realpath(vdir):
            msgbox("Не хватает библиотек PySide6 / pyobjc даже в окружении " + vdir +
                   ".\nУдали эту папку и запусти снег снова.", "Снег - ошибка")
            sys.exit(1)
        want = ["PySide6", "pyobjc-framework-Cocoa", "pyobjc-framework-Quartz"]
        try:
            if os.path.exists(vpy) and subprocess.call(
                    [vpy, "-c", "import PySide6.QtWidgets, objc, Quartz, AppKit"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                os.execv(vpy, [vpy, os.path.abspath(__file__)] + sys.argv[1:])
            msgbox("Для работы нужны библиотеки PySide6 и pyobjc.\n\n"
                   "Сейчас они установятся автоматически (нужен интернет, 2-5 минут).\n"
                   "Нажми OK и подожди - потом сам появится снег.")
            if not os.path.exists(vpy):
                subprocess.check_call([sys.executable, "-m", "venv", vdir])
            subprocess.check_call([vpy, "-m", "pip", "install", "--disable-pip-version-check"] + want)
        except Exception:
            msgbox("Не получилось установить библиотеки автоматически.\n\n"
                   "Открой Терминал и выполни:\n"
                   "    python3 -m pip install PySide6 pyobjc-framework-Cocoa pyobjc-framework-Quartz\n"
                   "Потом запусти снег снова:  python3 snow.pyw", "Снег - ошибка")
            sys.exit(1)
        os.execv(vpy, [vpy, os.path.abspath(__file__)] + sys.argv[1:])
        return
    msgbox("Для плавной графики нужна библиотека PySide6.\n\n"
           "Сейчас она установится автоматически (нужен интернет, 1-3 минуты).\n"
           "Нажми OK и подожди - потом сам появится снег.")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "PySide6"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000)
    except Exception:
        msgbox("Не получилось установить PySide6 автоматически.\n\n"
               "Открой командную строку (Win+R, cmd) и выполни:\n"
               "    pip install PySide6\n"
               "Потом запусти snow.pyw снова.", "Снег - ошибка", 0x10)
        sys.exit(1)
    subprocess.Popen([sys.executable, os.path.abspath(__file__)])   # перезапуск
    sys.exit(0)


ensure_deps()

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QFont, QIcon, QImage,  # noqa: E402
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient, QRegion)
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QGridLayout,  # noqa: E402
                               QHBoxLayout, QInputDialog, QLabel, QMenu, QPushButton,
                               QScrollArea, QSlider, QSystemTrayIcon, QTabWidget,
                               QVBoxLayout, QWidget)

FMT = QImage.Format.Format_ARGB32_Premultiplied
TRANSPARENT = Qt.GlobalColor.transparent
NOPEN = Qt.PenStyle.NoPen
NOBRUSH = Qt.BrushStyle.NoBrush
RH = (QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
      | QPainter.RenderHint.TextAntialiasing)

# Геометрия виртуального экрана (все мониторы) и масштаб - заполняются в setup()
VX = VY = 0
VW, VH = 1920, 1080
S = 1.0


def setup(app):
    global VX, VY, VW, VH, S
    global MONS, CW
    scr = app.primaryScreen()
    if IS_MAC:
        # На macOS одно окно не может надёжно перекрывать несколько экранов
        # (у каждого экрана свой "Space"), поэтому снег идёт на основном экране.
        vg = scr.geometry()
        VX, VY, VW, VH = vg.x(), vg.y(), vg.width(), vg.height() - 1
        S = 1.0
        MONS = [(0, 0, vg.width(), vg.height())]
    else:
        vg = scr.virtualGeometry()
        VX, VY, VW, VH = vg.x(), vg.y(), vg.width(), vg.height() - 1   # -1: не "полный экран"
        S = max(1.0, scr.logicalDotsPerInch() / 96.0)
        MONS = []
        for sc in app.screens():
            g = sc.geometry()
            MONS.append((g.x() - VX, g.y() - VY, g.x() - VX + g.width(), g.y() - VY + g.height()))
    CW = 4.0 * S


PLOW_KINDS = ((34.0, 27.0), (46.0, 35.0), (48.0, 37.0))   # (полудлина, вынос отвала), в S
PLOW_SPEED_K = (1.0, 0.85, 0.95)                          # скорость: грузовик, трактор, снегоочиститель

# ---------------------------------------------------------------------------
#  Настройки (окно настроек + файл settings.json)
# ---------------------------------------------------------------------------
# (вкладка, имя, подпись, тип, минимум, максимум, шаг)
SPEC = [
    ("Снег", "FLAKES", "Количество снежинок", "int", 20, 600, 10),
    ("Снег", "FALL_SPEED", "Скорость падения", "float", 0.3, 3.0, 0.1),
    ("Снег", "WIND_STRENGTH", "Сила ветра", "float", 0.0, 4.0, 0.1),
    ("Снег", "MIN_SIZE", "Минимальный размер снежинки", "float", 0.8, 4.0, 0.1),
    ("Снег", "MAX_SIZE", "Максимальный размер снежинки", "float", 2.0, 9.0, 0.2),
    ("Снег", "MOUSE_FORCE", "Реакция снега на курсор", "float", 0.0, 3.0, 0.1),
    ("Снег", "ACCUMULATE", "Скорость роста сугробов", "float", 0.0, 3.0, 0.1),
    ("Снег", "MAX_DRIFT_FLOOR", "Высота сугроба внизу экрана, px", "int", 10, 200, 5),
    ("Снег", "MAX_DRIFT_TASK", "Высота сугроба на панели задач, px", "int", 5, 120, 5),
    ("Снег", "MAX_DRIFT_WIN", "Высота сугроба на окнах, px", "int", 3, 80, 1),
    ("Снег", "SNOW_ON_WINDOWS", "Сугробы на окнах и панели задач", "bool", None, None, None),
    ("Снег", "SNOW_FLOOR", "Сугробы внизу экрана", "bool", None, None, None),
    ("Снег", "SNOW_OVER_WINDOWS", "Снег идёт и поверх окон", "bool", None, None, None),
    ("Снег", "SWEEP", "Смахивать сугробы быстрым курсором", "bool", None, None, None),
    ("Снег", "TRAILS", "Следы курсора в сугробах", "bool", None, None, None),
    ("Снег", "SHAKE_OFF", "Снег слетает, если резко таскать окно", "bool", None, None, None),
    ("Погода и гости", "BLIZZARD_AUTO", "Метель сама по расписанию", "bool", None, None, None),
    ("Погода и гости", "BLIZZARD_INTERVAL", "Метель раз в ... минут", "int", 1, 60, 1),
    ("Погода и гости", "BLIZZARD_LENGTH", "Длительность метели, сек", "int", 10, 180, 5),
    ("Погода и гости", "PLOW", "Снегоуборочная машина", "bool", None, None, None),
    ("Погода и гости", "PLOW_INTERVAL", "Снегоуборщик раз в ... секунд", "int", 20, 600, 10),
    ("Погода и гости", "PLOW_SPEED", "Скорость снегоуборщика", "float", 1.0, 6.0, 0.2),
    ("Погода и гости", "PLOW_VARIETY", "Разные машины по очереди", "bool", None, None, None),
    ("Декор", "GARLANDS", "Гирлянды на окнах", "bool", None, None, None),
    ("Декор", "ICICLES", "Сосульки под окнами", "bool", None, None, None),
    ("Декор", "FROST", "Иней по краям окон", "bool", None, None, None),
    ("Декор", "TREE", "Ёлка с огнями", "bool", None, None, None),
    ("Декор", "TREE_POS", "Где стоит ёлка, % ширины экрана", "int", 3, 97, 1),
    ("Система", "FPS", "Кадров в секунду", "int", 15, 144, 1),
    ("Система", "ECO", "Экономия: меньше FPS на батарее и при простое", "bool", None, None, None),
    ("Система", "SYNC_LEAD_MS", "Опережение при таскании окон, мс", "int", 0, 100, 1),
    ("Система", "FULLSCREEN_API", "Прятать снег при полноэкранных играх и видео", "bool", None, None, None),
    ("Система", "SAVE_STATE", "Запоминать снеговиков и сугробы", "bool", None, None, None),
]
DEFAULTS = {item[1]: globals()[item[1]] for item in SPEC}


def _coerce(kind, lo, hi, v):
    if kind == "bool":
        return bool(v)
    v = max(lo, min(hi, float(v)))
    return int(round(v)) if kind == "int" else round(v, 3)


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return False
    for _tab, key, _lab, kind, lo, hi, _st in SPEC:
        if key in data:
            try:
                globals()[key] = _coerce(kind, lo, hi, data[key])
            except Exception:
                pass
    return True


def save_settings():
    try:
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({item[1]: globals()[item[1]] for item in SPEC}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, SETTINGS_FILE)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  Автозапуск, один экземпляр, питание
# ---------------------------------------------------------------------------
if IS_WIN:
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
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
                return True
        except Exception:
            return False

    def autostart_set(on):
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
            return True
        except Exception:
            return False

    _MUTEX = None

    def single_instance():
        """False, если снег уже запущен (чтобы не получилось два оверлея сразу)."""
        global _MUTEX
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
            _MUTEX = k32.CreateMutexW(None, False, "Local\\SnowDesktopOverlay_v4")
            if ctypes.get_last_error() == 183:          # ERROR_ALREADY_EXISTS
                return False
        except Exception:
            pass
        return True

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", wt.DWORD), ("BatteryFullLifeTime", wt.DWORD)]

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]

    def on_battery():
        try:
            st = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
                return st.ACLineStatus == 0
        except Exception:
            pass
        return False

    def idle_seconds():
        """Сколько секунд пользователь ничего не нажимал и не двигал мышь."""
        try:
            li = LASTINPUTINFO()
            li.cbSize = ctypes.sizeof(li)
            if user32.GetLastInputInfo(ctypes.byref(li)):
                return ((ctypes.windll.kernel32.GetTickCount() - li.dwTime) & 0xFFFFFFFF) / 1000.0
        except Exception:
            pass
        return 0.0
else:
    import Quartz
    LAUNCH_LABEL = "com.snowdesktop.overlay"
    LAUNCH_PLIST = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % LAUNCH_LABEL)

    def autostart_get():
        return os.path.exists(LAUNCH_PLIST)

    def autostart_set(on):
        """Автозапуск при входе: LaunchAgent в ~/Library/LaunchAgents."""
        try:
            if on:
                import plistlib
                args = [sys.executable] if FROZEN else [sys.executable, os.path.abspath(__file__)]
                os.makedirs(os.path.dirname(LAUNCH_PLIST), exist_ok=True)
                with open(LAUNCH_PLIST, "wb") as fh:
                    plistlib.dump({"Label": LAUNCH_LABEL, "ProgramArguments": args,
                                   "RunAtLoad": True, "ProcessType": "Interactive",
                                   "LimitLoadToSessionType": "Aqua"}, fh)
            elif os.path.exists(LAUNCH_PLIST):
                os.remove(LAUNCH_PLIST)
            return True
        except Exception:
            return False

    _LOCK_FH = None

    def single_instance():
        """False, если снег уже запущен (блокировка файла, снимается сама при выходе)."""
        global _LOCK_FH
        try:
            import fcntl
            _LOCK_FH = open(os.path.join(DATA_DIR, "snow.lock"), "w")
        except Exception:
            return True
        try:
            fcntl.flock(_LOCK_FH, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    _BATT = [0.0, False]

    def on_battery():
        now = time.time()
        if now - _BATT[0] > 30.0:                       # pmset - отдельный процесс, не дёргаем часто
            _BATT[0] = now
            try:
                res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=3)
                _BATT[1] = "Battery Power" in res.stdout
            except Exception:
                _BATT[1] = False
        return _BATT[1]

    def idle_seconds():
        try:
            return float(Quartz.CGEventSourceSecondsSinceLastEventType(
                Quartz.kCGEventSourceStateCombinedSessionState, Quartz.kCGAnyInputEventType))
        except Exception:
            return 0.0


# ---------------------------------------------------------------------------
#  Окна и система: Windows (Win32) и macOS (Quartz / AppKit)
# ---------------------------------------------------------------------------
if IS_WIN:
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                    ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    GWL_EXSTYLE = -20
    WS_EX_LAYERED, WS_EX_TRANSPARENT = 0x80000, 0x20
    WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80, 0x08000000

    user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = wt.LONG
    user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, wt.LONG]
    user32.SetWindowLongW.restype = wt.LONG
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsWindow.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsZoomed.argtypes = [wt.HWND]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.InternalGetWindowText.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.InternalGetWindowText.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    user32.MonitorFromWindow.restype = ctypes.c_void_p
    user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MONITORINFO)]
    user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.SetWindowPos.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.UINT]
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]



class Win:
    """Окно в координатах оверлея. kind: win | task | max (развёрнуто) | full (весь монитор)."""
    __slots__ = ("hwnd", "kind", "l", "t", "r", "b", "dx", "dy")

    def __init__(self, hwnd, kind, l, t, r, b):
        self.hwnd, self.kind, self.l, self.t, self.r, self.b = hwnd, kind, l, t, r, b
        self.dx = self.dy = 0.0          # скорость окна, px за 1/60 с


TASKBAR = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd"}
IGNORE = {"Progman", "WorkerW", "Windows.UI.Core.CoreWindow",
          "ApplicationFrameInputSinkWindow", "NotifyIconOverflowWindow",
          "TopLevelWindowForOverflowXamlIsland"}
MY_PID = os.getpid()
MONS = []          # прямоугольники мониторов (l, t, r, b) в координатах оверлея
CW = 4.0           # ширина одной колонки сугроба (px), задаётся в setup()

def visible_segments(w, above):
    """Части верхнего края окна, не закрытые окнами выше."""
    segs = [(max(w.l, 0), min(w.r, VW))]
    for o in above:
        if o.t <= w.t < o.b:
            new = []
            for a, b in segs:
                if o.r <= a or o.l >= b:
                    new.append((a, b))
                    continue
                if o.l > a:
                    new.append((a, o.l))
                if o.r < b:
                    new.append((o.r, b))
            segs = new
    return [(a, b) for a, b in segs if b - a >= 24]


def visible_segments_y(w, above, y, minw=24):
    """Части горизонтального отрезка окна на высоте y, не закрытые окнами выше."""
    segs = [(max(w.l, 0), min(w.r, VW))]
    for o in above:
        if o.t <= y < o.b:
            new = []
            for a, b in segs:
                if o.r <= a or o.l >= b:
                    new.append((a, b))
                    continue
                if o.l > a:
                    new.append((a, o.l))
                if o.r < b:
                    new.append((o.r, b))
            segs = new
    return [(a, b) for a, b in segs if b - a >= minw]


if IS_WIN:
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]


    def scan_windows():
        """Медленный проход (несколько раз в секунду): какие окна вообще нам интересны.
        Порядок - сверху вниз (Z-order). Возвращает [(hwnd, это_панель_задач)]."""
        out = []

        def cb(hwnd, _):
            try:
                if not hwnd or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    return True
                pid = wt.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value == MY_PID:
                    return True
                cloaked = ctypes.c_int(0)
                dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), 4)
                if cloaked.value:
                    return True
                buf = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, buf, 64)
                cls = buf.value
                ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                task = cls in TASKBAR
                if not task:
                    if cls in IGNORE:
                        return True
                    if ex & 0x80 and not ex & 0x40000:
                        return True
                    if ex & 0x08000000:
                        return True
                    if ex & 0x20 and ex & 0x80000:
                        return True
                    # InternalGetWindowText не шлёт сообщение окну, поэтому не может
                    # зависнуть на "залипшем" или полноэкранном приложении
                    tb = ctypes.create_unicode_buffer(4)
                    if user32.InternalGetWindowText(hwnd, tb, 4) == 0:
                        return True
                out.append((int(hwnd), task))
            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        return out


    def refresh_windows(entries):
        """Быстрое обновление (каждый кадр): только положение уже известных окон.
        Благодаря этому сугробы едут вместе с окном без отставания и рывков."""
        out = []
        for hwnd, task in entries:
            try:
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    continue
                r = wt.RECT()
                if task or dwmapi.DwmGetWindowAttribute(
                        hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) != 0:
                    user32.GetWindowRect(hwnd, ctypes.byref(r))
                l, t, rr, b = r.left - VX, r.top - VY, r.right - VX, r.bottom - VY
                if rr <= l or b <= t or l < -20000 or t < -20000:
                    continue
                if task:
                    kind = "task"
                else:
                    if rr - l < 100 or b - t < 40:
                        continue
                    kind = "win"
                    for m in MONS:
                        if l <= m[0] + 4 and t <= m[1] + 4 and rr >= m[2] - 4 and b >= m[3] - 4:
                            kind = "full"
                            break
                    if kind == "win" and user32.IsZoomed(hwnd):
                        kind = "max"
                out.append(Win(hwnd, kind, l, t, rr, b))
            except Exception:
                pass
        return out


    def fullscreen_state():
        """True, если Windows считает, что сейчас работает полноэкранное приложение
        (игра, видео, F11 в браузере, презентация) или экран заблокирован."""
        try:
            st = ctypes.c_int(0)
            if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(st)) == 0:
                return st.value in (1, 2, 3, 4)
        except Exception:
            pass
        return False


    def key_down(vk):
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)



    def plat_apply_window(ov):
        """Прозрачное для мыши окно без фокуса, не в списке окон."""
        ex = user32.GetWindowLongW(ov.hwnd, GWL_EXSTYLE)
        ex |= WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        ex = (ex | WS_EX_TRANSPARENT) if ov.click_through else (ex & ~WS_EX_TRANSPARENT)
        user32.SetWindowLongW(ov.hwnd, GWL_EXSTYLE, ctypes.c_long(ex).value)


    def plat_raise(ov):
        # HWND_TOPMOST, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        user32.SetWindowPos(ov.hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


    def plat_click_through(ov, on):
        ex = user32.GetWindowLongW(ov.hwnd, GWL_EXSTYLE)
        ex = (ex | WS_EX_TRANSPARENT) if on else (ex & ~WS_EX_TRANSPARENT)
        user32.SetWindowLongW(ov.hwnd, GWL_EXSTYLE, ctypes.c_long(ex).value)


    def win_alive(h):
        return bool(user32.IsWindow(h))


    def plat_timer_precision(on):
        try:
            if on:
                ctypes.windll.winmm.timeBeginPeriod(1)    # точный таймер Windows (1 мс)
            else:
                ctypes.windll.winmm.timeEndPeriod(1)
        except Exception:
            pass


    def plat_app_setup(app):
        pass


    def plat_activate():
        pass

else:
    import objc as _objc
    import AppKit as _AppKit

    _MAC_DOCK = None            # прямоугольник Dock (обновляется потоком поиска окон)
    _MAC_IDS = set()
    _MAC_FLAGS = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
    # коды клавиш Windows (как в poll_keys) -> коды клавиш macOS
    _MAC_KEYS = {0x11: (59, 62), 0x10: (56, 60), 0x1B: (53,), 0x51: (12,), 0x50: (35,), 0x59: (16,),
                 0x43: (8,), 0x53: (1,), 0x42: (11,), 0x57: (13,), 0x54: (17,), 0xDB: (33,), 0xDD: (30,)}


    def _mac_windows():
        """Все видимые окна сверху вниз: (id, x, y, w, h, слой, владелец, прозрачность)."""
        out = []
        with _objc.autorelease_pool():
            rows = Quartz.CGWindowListCopyWindowInfo(_MAC_FLAGS, Quartz.kCGNullWindowID) or []
            for w in rows:
                try:
                    if int(w.get("kCGWindowOwnerPID", -1)) == MY_PID:
                        continue
                    b = w["kCGWindowBounds"]
                    out.append((int(w["kCGWindowNumber"]), float(b["X"]), float(b["Y"]),
                                float(b["Width"]), float(b["Height"]), int(w.get("kCGWindowLayer", 0)),
                                str(w.get("kCGWindowOwnerName") or ""), float(w.get("kCGWindowAlpha", 1.0))))
                except Exception:
                    continue
        return out


    def scan_windows():
        """Какие окна нам интересны (раз в доли секунды, в отдельном потоке).
        Возвращает [(id, это_Dock)] сверху вниз. Dock всегда первый."""
        global _MAC_DOCK, _MAC_IDS
        out, dock = [], None
        scr_h = VH + 1
        for wid, x, y, w, h, layer, owner, alpha in _mac_windows():
            if layer == 20 and owner == "Dock":              # окно(а) Dock
                if 20 <= h <= 260 and w >= 120 and y + h >= scr_h - 14 and y <= scr_h:
                    cand = (x - VX, y - VY, x - VX + w, y - VY + h)
                    if dock is None or (cand[2] - cand[0]) < (dock[2] - dock[0]):
                        dock = cand                              # берём самое узкое - саму "плашку" Dock
                continue
            if layer != 0 or alpha < 0.05 or w < 100 or h < 40:  # только обычные окна приложений
                continue
            out.append((wid, False))
        _MAC_DOCK = dock
        out.insert(0, (-1, True))
        _MAC_IDS = {e[0] for e in out}
        return out


    def refresh_windows(entries):
        """Быстрое обновление положения окон каждый кадр."""
        want = {e[0] for e in entries if e[0] != -1}
        info = {}
        for row in _mac_windows():
            if row[0] in want:
                info[row[0]] = row
        prim = QApplication.primaryScreen()
        g, a = prim.geometry(), prim.availableGeometry()
        out = []
        for wid, task in entries:
            if task:                                              # Dock
                r = _MAC_DOCK
                if r is None and a.bottom() < g.bottom() - 4:     # запасной вариант: полоса под рабочей областью
                    r = (g.left() - VX, a.bottom() + 1 - VY, g.right() + 1 - VX, g.bottom() + 1 - VY)
                if r is not None:
                    out.append(Win(-1, "task", r[0], r[1], r[2], r[3]))
                continue
            row = info.get(wid)
            if row is None:
                continue
            l, t, rr, b = row[1] - VX, row[2] - VY, row[1] + row[3] - VX, row[2] + row[4] - VY
            if rr <= 0 or l >= VW or b <= 0 or t >= VH:           # окно на другом мониторе
                continue
            kind = "win"
            for m in MONS:
                if l <= m[0] + 4 and t <= m[1] + 4 and rr >= m[2] - 4 and b >= m[3] - 4:
                    kind = "full"                                 # полноэкранное окно
                    break
            if kind == "win" and (l <= a.left() - VX + 6 and rr >= a.right() + 1 - VX - 6
                                  and t <= a.top() - VY + 6 and b >= a.bottom() + 1 - VY - 6):
                kind = "max"                                      # окно "развёрнуто" (зелёная кнопка)
            out.append(Win(wid, kind, l, t, rr, b))
        return out


    def fullscreen_state():
        return False             # на macOS полный экран определяем по окну на весь монитор


    def key_down(vk):
        for code in _MAC_KEYS.get(vk, ()):
            try:
                if Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateCombinedSessionState, code):
                    return True
            except Exception:
                pass
        return False


    def _ns_window(ov):
        try:
            view = _objc.objc_object(c_void_p=ctypes.c_void_p(int(ov.winId())))
            return view.window()
        except Exception:
            return None


    def plat_apply_window(ov):
        """Окно поверх всего, на всех рабочих столах, не ловит мышь, без тени."""
        w = _ns_window(ov)
        if w is None:
            return
        try:
            w.setLevel_(25)                                   # NSStatusWindowLevel: выше окон, Dock и меню
            w.setCollectionBehavior_(1 | 16 | 64 | 256)       # все Spaces | неподвижное | вне Cmd+` | над полным экраном
            w.setHasShadow_(False)
            w.setOpaque_(False)
            w.setIgnoresMouseEvents_(bool(ov.click_through))
            hs = _AppKit.NSScreen.screens()[0].frame().size.height
            w.setFrame_display_(_AppKit.NSMakeRect(VX, hs - VY - VH, VW, VH), False)
            w.orderFrontRegardless()
        except Exception:
            pass


    def plat_raise(ov):
        w = _ns_window(ov)
        if w is not None:
            try:
                w.orderFrontRegardless()
            except Exception:
                pass


    def plat_click_through(ov, on):
        w = _ns_window(ov)
        if w is not None:
            try:
                w.setIgnoresMouseEvents_(bool(on))
            except Exception:
                pass


    def win_alive(h):
        return h in _MAC_IDS


    def plat_timer_precision(on):
        pass


    def plat_app_setup(app):
        """Убираем значок из Dock: остаётся только значок в строке меню."""
        try:
            _AppKit.NSApplication.sharedApplication().setActivationPolicy_(
                _AppKit.NSApplicationActivationPolicyAccessory)
        except Exception:
            pass


    def plat_activate():
        """Окно настроек и диалоги должны получать фокус, хотя приложения нет в Dock."""
        try:
            _AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass


def whash(n):
    return (int(n) * 2654435761) & 0xFFFFFFFF


# ---------------------------------------------------------------------------
#  Спрайты (рисуются один раз, потом только копируются)
# ---------------------------------------------------------------------------
_SPR = {}
BULB_COLORS = ["#FF4040", "#FFC83A", "#42E86B", "#3DB6FF", "#FF6FD8"]


def new_image(size):
    img = QImage(size, size, FMT)
    img.fill(TRANSPARENT)
    return img


def soft_sprite(r):
    key = ("s", max(1, int(round(r * 2))))
    if key in _SPR:
        return _SPR[key]
    rr = key[1] / 2.0
    half = int(math.ceil(rr * 2.3)) + 2
    img = new_image(half * 2)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(NOPEN)
    g = QRadialGradient(half, half, rr * 2.2)
    g.setColorAt(0.0, QColor(255, 255, 255, 70))
    g.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(half, half), rr * 2.2, rr * 2.2)
    g = QRadialGradient(half, half, rr)
    g.setColorAt(0.0, QColor(255, 255, 255, 255))
    g.setColorAt(0.65, QColor(246, 250, 255, 250))
    g.setColorAt(1.0, QColor(220, 235, 255, 70))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(half, half), rr, rr)
    p.end()
    _SPR[key] = (img, float(half))
    return _SPR[key]


def crystal_sprite(R):
    key = ("c", max(2, int(round(R))))
    if key in _SPR:
        return _SPR[key]
    R = float(key[1])
    half = int(math.ceil(R)) + 3
    img = new_image(half * 2)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(half, half)
    p.setPen(NOPEN)
    g = QRadialGradient(0, 0, R * 1.1)
    g.setColorAt(0.0, QColor(255, 255, 255, 60))
    g.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), R * 1.1, R * 1.1)
    p.setPen(QPen(QColor(255, 255, 255, 240), max(1.0, R * 0.11),
                  Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    for k in range(6):
        p.save()
        p.rotate(k * 60.0)
        p.drawLine(QPointF(0, 0), QPointF(0, -R))
        p.drawLine(QPointF(0, -R * 0.55), QPointF(-R * 0.24, -R * 0.80))
        p.drawLine(QPointF(0, -R * 0.55), QPointF(R * 0.24, -R * 0.80))
        p.restore()
    p.end()
    _SPR[key] = (img, float(half))
    return _SPR[key]


def bulb_sprite(ci):
    key = ("b", ci)
    if key in _SPR:
        return _SPR[key]
    c = QColor(BULB_COLORS[ci])
    R = 8.0 * S
    half = int(R) + 2
    img = new_image(half * 2)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(NOPEN)
    g = QRadialGradient(half, half, R)
    c1, c2 = QColor(c), QColor(c)
    c1.setAlpha(190)
    c2.setAlpha(0)
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(half, half), R, R)
    p.setBrush(QBrush(c.lighter(125)))
    p.drawEllipse(QPointF(half, half), 2.7 * S, 3.2 * S)
    p.setBrush(QBrush(QColor(255, 255, 255, 210)))
    p.drawEllipse(QPointF(half - 0.8 * S, half - 1.0 * S), 0.9 * S, 1.0 * S)
    p.setBrush(QBrush(QColor(30, 60, 40)))
    p.drawRoundedRect(QRectF(half - 1.5 * S, half - 5.6 * S, 3.0 * S, 2.8 * S), 0.8 * S, 0.8 * S)
    p.end()
    _SPR[key] = (img, float(half))
    return _SPR[key]


def make_icon():
    pm = QPixmap(64, 64)
    pm.fill(TRANSPARENT)
    p = QPainter(pm)
    p.setRenderHints(RH)
    g = QLinearGradient(0, 0, 0, 64)
    g.setColorAt(0.0, QColor("#3C78C8"))
    g.setColorAt(1.0, QColor("#1B3A6B"))
    p.setPen(NOPEN)
    p.setBrush(QBrush(g))
    p.drawEllipse(2, 2, 60, 60)
    p.translate(32, 32)
    p.setPen(QPen(QColor("white"), 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for k in range(6):
        p.save()
        p.rotate(k * 60.0)
        p.drawLine(QPointF(0, 0), QPointF(0, -24))
        p.drawLine(QPointF(0, -14), QPointF(-6, -20))
        p.drawLine(QPointF(0, -14), QPointF(6, -20))
        p.restore()
    p.end()
    return QIcon(pm)



def glow_sprite(ci, r):
    """Цветное светящееся пятнышко (огоньки ёлки, искры, подсветка снега)."""
    key = ("g", ci, max(1, int(round(r * 2))))
    if key in _SPR:
        return _SPR[key]
    half = int(math.ceil(r)) + 2
    img = new_image(half * 2)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(NOPEN)
    c = QColor(BULB_COLORS[ci % len(BULB_COLORS)])
    c1, c2 = QColor(c), QColor(c)
    c1.setAlpha(230)
    c2.setAlpha(0)
    g = QRadialGradient(half, half, r)
    g.setColorAt(0.0, QColor(255, 255, 255, 255))
    g.setColorAt(0.25, c1)
    g.setColorAt(1.0, c2)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(half, half), r, r)
    p.end()
    _SPR[key] = (img, float(half))
    return _SPR[key]


def icicle_sprite(length):
    L = max(4, min(70, int(round(length / 2.0)) * 2))
    key = ("ic", L)
    if key in _SPR:
        return _SPR[key]
    wd = max(3.0, L * 0.26)
    W, H = int(wd) + 4, L + 4
    img = QImage(W, H, FMT)
    img.fill(TRANSPARENT)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = W / 2.0
    path = QPainterPath()
    path.moveTo(cx - wd / 2.0, 1.0)
    path.lineTo(cx + wd / 2.0, 1.0)
    path.lineTo(cx, L + 1.0)
    path.closeSubpath()
    g = QLinearGradient(0, 1, 0, L + 1)
    g.setColorAt(0.0, QColor(190, 222, 250, 235))
    g.setColorAt(1.0, QColor(255, 255, 255, 245))
    p.setBrush(QBrush(g))
    p.setPen(QPen(QColor(150, 195, 235, 200), 1.0))
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 255, 255, 210), max(1.0, wd * 0.14), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(cx - wd * 0.14, 2.5), QPointF(cx - wd * 0.03, L * 0.7))
    p.end()
    _SPR[key] = (img, W / 2.0)
    return _SPR[key]


def splat_sprite(r):
    key = ("sp", max(3, int(round(r))))
    if key in _SPR:
        return _SPR[key]
    r = float(key[1])
    half = int(r * 2.0) + 3
    img = new_image(half * 2)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(NOPEN)
    rnd = random.Random(key[1])
    p.setBrush(QBrush(QColor(60, 80, 120, 55)))               # лёгкая тень
    p.drawEllipse(QPointF(half, half + 1.5 * S), r * 0.95, r * 0.9)
    p.setBrush(QBrush(QColor(250, 252, 255, 240)))
    p.drawEllipse(QPointF(half, half), r * 0.85, r * 0.8)
    for k in range(9):
        a = k * 6.2831853 / 9 + rnd.uniform(-0.2, 0.2)
        d = r * rnd.uniform(0.7, 1.2)
        rr = r * rnd.uniform(0.22, 0.38)
        p.drawEllipse(QPointF(half + math.cos(a) * d, half + math.sin(a) * d), rr, rr)
    p.setBrush(QBrush(QColor(238, 245, 255, 235)))
    for k in range(3):
        dx = rnd.uniform(-0.6, 0.6) * r
        p.drawRoundedRect(QRectF(half + dx - 1.2 * S, half, 2.4 * S, r * rnd.uniform(0.9, 1.6)),
                          1.2 * S, 1.2 * S)
    p.end()
    _SPR[key] = (img, float(half))
    return _SPR[key]


def frost_sprite():
    """Морозный узор-папоротник для нижнего левого угла окна."""
    key = ("fr", int(S * 100))
    if key in _SPR:
        return _SPR[key]
    sz = int(46 * S)
    img = new_image(sz)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(240, 248, 255, 175), max(1.0, 1.0 * S), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))

    def branch(x, y, ang, ln, dep):
        if dep <= 0 or ln < 2.5 * S:
            return
        x2, y2 = x + math.cos(ang) * ln, y + math.sin(ang) * ln
        p.drawLine(QPointF(x, y), QPointF(x2, y2))
        branch(x2, y2, ang - 0.6, ln * 0.60, dep - 1)
        branch(x2, y2, ang + 0.6, ln * 0.60, dep - 1)
        branch(x2, y2, ang, ln * 0.72, dep - 1)

    branch(2.0, sz - 2.0, -0.85, 19 * S, 4)
    branch(2.0, sz - 2.0, -0.28, 23 * S, 4)
    branch(2.0, sz - 2.0, -1.40, 15 * S, 3)
    p.end()
    _SPR[key] = (img, sz)
    return _SPR[key]


def tree_sprite():
    """Ёлка: (картинка, ширина, высота, огоньки [(x, y, цвет)], положение звезды)."""
    key = ("tree", int(S * 100))
    if key in _SPR:
        return _SPR[key]
    u = S
    W, H = int(100 * u), int(138 * u)
    img = QImage(W, H, FMT)
    img.fill(TRANSPARENT)
    p = QPainter(img)
    p.setRenderHints(RH)
    cx = W / 2.0
    base = H - 3 * u
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor("#6B4423")))
    p.drawRect(QRectF(cx - 5 * u, base - 14 * u, 10 * u, 14 * u))
    tiers = ((94 * u, base - 12 * u, 52 * u), (74 * u, base - 44 * u, 48 * u),
             (52 * u, base - 76 * u, 44 * u))
    lights, nb = [], len(BULB_COLORS)
    for ti, (tw, by, th) in enumerate(tiers):
        top = by - th
        n = 5
        path = QPainterPath()
        path.moveTo(cx, top)
        path.lineTo(cx + tw / 2, by)
        edge = QPainterPath()
        edge.moveTo(cx + tw / 2, by)
        for i in range(n):
            x1 = cx + tw / 2 - (i + 1) * tw / n
            xm = cx + tw / 2 - (i + 0.5) * tw / n
            path.quadTo(xm, by + 7 * u, x1, by)
            edge.quadTo(xm, by + 7 * u, x1, by)
        path.closeSubpath()
        g = QLinearGradient(0, top, 0, by)
        g.setColorAt(0.0, QColor("#2E9B4E"))
        g.setColorAt(1.0, QColor("#0F5A2A"))
        p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(10, 70, 35, 180), max(1.0, 0.8 * u)))
        p.drawPath(path)
        p.setBrush(NOBRUSH)
        p.setPen(QPen(QColor(255, 255, 255, 235), 3.0 * u, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawPath(edge)
        p.setPen(NOPEN)
        p.setBrush(QBrush(QColor(255, 255, 255, 215)))
        for k in range(3):
            p.drawEllipse(QPointF(cx + (k - 1) * tw * 0.26, top + th * (0.42 + 0.1 * k)),
                          4.5 * u, 1.9 * u)
        for k, (fx, fy) in enumerate(((-0.30, 0.22), (0.05, 0.44), (0.28, 0.28))):
            ox, oy = cx + fx * tw * (1 - fy * 0.6), by - th * fy
            c = QColor(BULB_COLORS[(ti * 3 + k + 2) % nb])
            p.setBrush(QBrush(c))
            p.drawEllipse(QPointF(ox, oy), 3.3 * u, 3.3 * u)
            p.setBrush(QBrush(QColor(255, 255, 255, 190)))
            p.drawEllipse(QPointF(ox - 1.0 * u, oy - 1.1 * u), 0.9 * u, 0.9 * u)
        for j in range(3):
            fy = 0.14 + 0.25 * j
            for side in ((-0.7, 0.7, 0.0) if j == 1 else (-0.7, 0.7)):
                lights.append((cx + side * (tw / 2) * (1 - fy) * 0.85, by - th * fy,
                               len(lights) % nb))
    star_y = base - 76 * u - 44 * u - 2 * u
    star = QPainterPath()
    for i in range(10):
        rr = 8.5 * u if i % 2 == 0 else 3.8 * u
        a = math.radians(-90 + i * 36)
        pt = QPointF(cx + math.cos(a) * rr, star_y + math.sin(a) * rr)
        star.moveTo(pt) if i == 0 else star.lineTo(pt)
    star.closeSubpath()
    g = QRadialGradient(cx, star_y, 9 * u)
    g.setColorAt(0.0, QColor("#FFF6B0"))
    g.setColorAt(1.0, QColor("#FFC83A"))
    p.setBrush(QBrush(g))
    p.setPen(QPen(QColor("#D99A10"), max(1.0, 0.8 * u)))
    p.drawPath(star)
    p.end()
    _SPR[key] = (img, W, H, lights, (cx, star_y))
    return _SPR[key]


# ---------------------------------------------------------------------------
#  Рисование: сугробы, гирлянды, снеговики
# ---------------------------------------------------------------------------
NZ = [0.6 * math.sin(i * 0.45) + 0.4 * math.sin(i * 1.37 + 1.0) for i in range(4096)]


class Surface:
    """Поверхность, на которой копится снег: верхний край окна, панель задач
    или низ экрана. Снег хранится как карта высот по колонкам - в координатах
    самой поверхности, поэтому при перетаскивании окна сугроб едет вместе с ним
    и не \"плывёт\"."""
    __slots__ = ("key", "kind", "l", "t", "r", "b", "cw", "n", "h", "maxh", "segs",
                 "dirty", "seed", "off", "miss")

    def __init__(self, key, kind, l, t, r, b, start):
        self.key, self.kind = key, kind
        self.l, self.t, self.r, self.b = l, t, r, b
        self.cw = CW
        self.n = max(2, int((r - l) / self.cw) + 2)
        self.h = [start] * self.n
        self.maxh = (MAX_DRIFT_FLOOR if kind == "floor" else
                     MAX_DRIFT_TASK if kind == "task" else MAX_DRIFT_WIN) * S
        self.segs = []
        self.dirty = False
        self.miss = 0
        self.seed = whash(key if isinstance(key, int) else 99991 + key[1])
        self.off = self.seed % 4096

    def set_geom(self, l, t, r, b):
        self.l, self.t, self.r, self.b = l, t, r, b
        n = max(2, int((r - l) / self.cw) + 2)
        if n > self.n:
            self.h.extend([0.0] * (n - self.n))
        elif n < self.n:
            del self.h[n:]
        self.n = n

    def vis(self, x):
        for a, b in self.segs:
            if a <= x <= b:
                return True
        return False

    def add(self, x, vol, k):
        """Добавить снег объёмом vol (px^2) вокруг точки x, ширина размаха +-k колонок."""
        ic = int(round((x - self.l) / self.cw))
        wsum = float((k + 1) * (k + 1))
        h, mx, n, cw = self.h, self.maxh, self.n, self.cw
        for j in range(-k, k + 1):
            i = ic + j
            if 0 <= i < n:
                nh = h[i] + vol * (k + 1 - abs(j)) / wsum / cw
                h[i] = nh if nh < mx else mx
        self.dirty = True

    def relax(self, spill):
        """Сугроб оплывает до естественного угла откоса; лишнее на краях сползает вниз."""
        h, n, cw = self.h, self.n, self.cw
        rep = REPOSE * cw
        moved = 0.0
        for i in range(n - 1):
            d = h[i] - h[i + 1]
            if d > rep:
                m = (d - rep) * 0.3
                h[i] -= m
                h[i + 1] += m
                moved += m
            elif d < -rep:
                m = (-d - rep) * 0.3
                h[i] += m
                h[i + 1] -= m
                moved += m
        if self.kind != "floor":
            sl = EDGE_SLOPE * cw
            for i in range(min(n // 2, 40)):
                lim = sl * (i + 1)
                for j in (i, n - 1 - i):
                    if h[j] > lim:
                        ex = h[j] - lim
                        h[j] = lim
                        if ex * cw >= 1.5:
                            spill(self, j, ex * cw)
                        moved += ex
        self.dirty = moved > 0.02


def draw_drift(p, s, a, b):
    """Рисует сугроб на видимом участке [a, b] поверхности s."""
    cw, l, h, n, t = s.cw, s.l, s.h, s.n, s.t
    floor = s.kind == "floor"
    xs = [a]
    x = l + (int((a - l) / cw) + 1) * cw
    while x < b:
        xs.append(x)
        x += cw
    xs.append(b)
    ys = []
    mx = 0.0
    for x in xs:
        f = (x - l) / cw
        i = int(f)
        if i < 0:
            i, f = 0, 0.0
        elif i > n - 2:
            i, f = n - 2, float(n - 1)
        fr = f - i
        hh = h[i] * (1.0 - fr) + h[i + 1] * fr
        if hh > 0.25:
            hh += NZ[(s.off + i) & 4095] * 0.35 * S * min(1.0, hh / (3.0 * S))
            if not floor:
                e = min(1.0, (x - l) / (10 * S), (s.r - x) / (10 * S))
                hh *= 0.2 + 0.8 * max(0.0, e)
        else:
            hh = 0.0
        ys.append(hh)
        if hh > mx:
            mx = hh
    if mx < 0.5:
        return
    path = QPainterPath()
    path.moveTo(a, t + 3.0 * S)
    for x, hh in zip(xs, ys):
        path.lineTo(x, t - hh)
    path.lineTo(b, t + 3.0 * S)
    path.closeSubpath()
    p.setPen(NOPEN)
    p.translate(0, 2.4 * S)
    p.setBrush(QBrush(QColor(90, 120, 170, 70)))
    p.drawPath(path)
    p.translate(0, -2.4 * S)
    g = QLinearGradient(0, t - mx - 2, 0, t + 3.0 * S)
    g.setColorAt(0.0, QColor("#FFFFFF"))
    g.setColorAt(0.55, QColor("#F4F9FF"))
    g.setColorAt(1.0, QColor("#CFE2F7"))
    p.setBrush(QBrush(g))
    p.drawPath(path)


def draw_garland(p, w, a, b, h, bulbs_out, t=0.0, sway=0.0):
    """Гирлянда. sway - размах качания (на ветру и в метель она раскачивается)."""
    Ls, depth = 72.0 * S, 7.0 * S
    top = w.t + 3.0 * S
    k0 = int((a - w.l) // Ls)
    k1 = int((b - w.l) // Ls)
    p.save()
    p.setClipRect(QRectF(a, w.t - 12 * S, b - a, 44 * S), Qt.ClipOperation.IntersectClip)
    p.setBrush(NOBRUSH)
    p.setPen(QPen(QColor(38, 84, 56), max(1.6, 1.7 * S), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    ctrls = {}
    ratio = sway / S if S else 0.0
    for k in range(k0, k1 + 1):
        x0 = w.l + k * Ls
        x1 = x0 + Ls
        ph = k * 1.3 + (h % 7)
        cx = (x0 + x1) / 2.0 + sway * math.sin(t * 0.045 + ph)
        dp = depth * (1.0 + 0.10 * min(ratio, 6.0) * math.sin(t * 0.06 + ph * 0.7))
        cy = top + 2.0 * dp
        ctrls[k] = (x0, x1, cx, cy)
        path = QPainterPath()
        path.moveTo(x0, top)
        path.quadTo(cx, cy, x1, top)
        p.drawPath(path)
    p.restore()
    nb = len(BULB_COLORS)
    for k in range(k0, k1 + 1):
        x0, x1, cx, cy = ctrls[k]
        for j, u in enumerate((1 / 3.0, 2 / 3.0)):
            om = 1.0 - u
            bx = om * om * x0 + 2 * u * om * cx + u * u * x1
            if a + 4 * S <= bx <= b - 4 * S:
                by = om * om * top + 2 * u * om * cy + u * u * top + 4.5 * S
                i = int((bx - w.l) / w.cw)
                gh = w.h[i] if 0 <= i < w.n else 0.0
                bulbs_out.append((bx, by, (k * 2 + j + h) % nb,
                                  ((h + k * 7 + j * 3) % 628) / 100.0, gh))


def draw_snowball(p, cx, cy, r):
    g = QRadialGradient(cx, cy, r, cx - r * 0.35, cy - r * 0.40)
    g.setColorAt(0.0, QColor("#FFFFFF"))
    g.setColorAt(0.55, QColor("#F3F8FF"))
    g.setColorAt(1.0, QColor("#B7D0EA"))
    p.setPen(QPen(QColor(140, 170, 205, 170), max(1.0, r * 0.03)))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy), r, r)


def stack_centers(balls, base):
    cy = base - balls[0]
    out = [cy]
    for i in range(1, len(balls)):
        cy -= 0.82 * (balls[i - 1] + balls[i])
        out.append(cy)
    return out


SCARVES = [("#D93A3A", "#F6F6F6"), ("#2F7FD6", "#F6F6F6"),
           ("#2E9E5B", "#F6F6F6"), ("#8E44AD", "#F6F6F6")]
HATS = ["#C0392B", "#2E86C1", "#27AE60"]


def draw_snowman(p, x, base, balls, seed, t=0.0, wind=0.0, name=""):
    r1 = balls[0]
    cs = stack_centers(balls, base)
    complete = len(balls) >= 3
    p.setPen(NOPEN)
    # тень и сугробик у основания
    p.save()
    p.translate(x, base)
    p.scale(1.0, 0.18)
    g = QRadialGradient(0, 0, r1 * 1.6)
    g.setColorAt(0.0, QColor(30, 50, 90, 80))
    g.setColorAt(1.0, QColor(30, 50, 90, 0))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), r1 * 1.6, r1 * 1.6)
    p.restore()
    g = QLinearGradient(0, base - r1 * 0.2, 0, base + r1 * 0.1)
    g.setColorAt(0.0, QColor("#FFFFFF"))
    g.setColorAt(1.0, QColor("#D3E4F8"))
    p.setBrush(QBrush(g))
    p.drawEllipse(QRectF(x - r1 * 1.0, base - r1 * 0.20, r1 * 2.0, r1 * 0.34))
    # руки-веточки (за шарами)
    if complete:
        mr, my = balls[1], cs[1]
        p.setPen(QPen(QColor("#5E3B1E"), max(2.0, mr * 0.09), Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        wv = 0.17 * math.sin(t * 0.07 + (seed % 17))
        if int(t / 140.0 + seed) % 6 == 0:                  # иногда машет сильнее
            wv = 0.30 * math.sin(t * 0.20 + (seed % 17)) + 0.1
        for sgn, lift in ((-1, 0.25 + 0.05 * math.sin(t * 0.05 + (seed % 11))), (1, 0.65 + wv)):
            x0, y0 = x + sgn * mr * 0.8, my - mr * 0.05
            x1, y1 = x + sgn * mr * 1.95, my - mr * lift
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
            xm, ym = x0 + (x1 - x0) * 0.65, y0 + (y1 - y0) * 0.65
            p.drawLine(QPointF(xm, ym), QPointF(xm + sgn * mr * 0.3, ym - mr * 0.38))
            p.drawLine(QPointF(xm, ym), QPointF(xm + sgn * mr * 0.38, ym + mr * 0.05))
    # шары
    for r, cy in zip(balls, cs):
        draw_snowball(p, x, cy, r)
    p.setPen(NOPEN)
    coal = QColor("#1B1B24")
    if len(balls) >= 2:
        mr, my = balls[1], cs[1]
        p.setBrush(QBrush(coal))
        for dy in (-0.38, 0.0, 0.38):
            p.drawEllipse(QPointF(x, my + mr * dy), max(1.5, mr * 0.075), max(1.5, mr * 0.075))
    if not complete:
        return
    hr, hy = balls[2], cs[2]
    # глаза
    er = max(1.6, hr * 0.095)
    blink = ((int(t) + seed % 233) % 230) < 7                  # моргает
    for sx in (-1, 1):
        if blink:
            p.setPen(QPen(coal, max(1.2, er * 0.55), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x + sx * hr * 0.32 - er, hy - hr * 0.16),
                       QPointF(x + sx * hr * 0.32 + er, hy - hr * 0.16))
            p.setPen(NOPEN)
            continue
        p.setBrush(QBrush(coal))
        p.drawEllipse(QPointF(x + sx * hr * 0.32, hy - hr * 0.16), er, er)
        p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        p.drawEllipse(QPointF(x + sx * hr * 0.32 - er * 0.3, hy - hr * 0.16 - er * 0.3),
                      er * 0.35, er * 0.35)
    # улыбка
    p.setBrush(QBrush(coal))
    for k in range(-2, 3):
        a = k * 0.34
        p.drawEllipse(QPointF(x + math.sin(a) * hr * 0.52,
                              hy + hr * 0.50 - (1 - math.cos(a)) * hr * 0.55),
                      max(1.0, hr * 0.05), max(1.0, hr * 0.05))
    # нос-морковка
    nose = QPainterPath()
    nose.moveTo(x - hr * 0.10, hy - hr * 0.02)
    nose.lineTo(x + hr * 0.80, hy + hr * 0.20)
    nose.lineTo(x - hr * 0.10, hy + hr * 0.24)
    nose.closeSubpath()
    g = QLinearGradient(x, hy, x + hr * 0.8, hy + hr * 0.2)
    g.setColorAt(0.0, QColor("#FFA23A"))
    g.setColorAt(1.0, QColor("#E5600A"))
    p.setBrush(QBrush(g))
    p.drawPath(nose)
    # шарф
    sc_main, sc_stripe = SCARVES[seed % len(SCARVES)]
    ny = hy + hr * 0.86
    sw, sh = hr * 1.55, hr * 0.46
    p.save()
    p.translate(x + hr * 0.52, ny + hr * 0.12)
    p.rotate(9.0)
    p.setBrush(QBrush(QColor(sc_main)))
    p.drawRoundedRect(QRectF(-hr * 0.2, 0, hr * 0.42, hr * 1.0), hr * 0.1, hr * 0.1)
    p.restore()
    p.setBrush(QBrush(QColor(sc_main)))
    p.drawRoundedRect(QRectF(x - sw / 2, ny - sh / 2, sw, sh), sh * 0.45, sh * 0.45)
    p.setPen(QPen(QColor(sc_stripe), max(1.0, hr * 0.07), Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    for k in (-0.5, -0.17, 0.17, 0.5):
        p.drawLine(QPointF(x + sw * k * 0.9, ny - sh * 0.35), QPointF(x + sw * k * 0.9, ny + sh * 0.35))
    p.setPen(NOPEN)
    # шапка (на ветру наклоняется)
    tilt = max(-14.0, min(14.0, wind * 2.6)) + math.sin(t * 0.09 + seed % 9) * 1.2
    p.save()
    p.translate(x, hy - hr * 0.5)
    p.rotate(tilt)
    p.translate(-x, -(hy - hr * 0.5))
    hat = (seed >> 3) % 3
    if hat == 0:                                    # цилиндр
        by = hy - hr * 0.80
        p.setBrush(QBrush(QColor("#22222B")))
        p.drawEllipse(QPointF(x, by), hr * 0.98, hr * 0.22)
        p.drawRoundedRect(QRectF(x - hr * 0.60, by - hr * 1.05, hr * 1.2, hr * 1.05),
                          hr * 0.08, hr * 0.08)
        p.setBrush(QBrush(QColor("#C0392B")))
        p.drawRect(QRectF(x - hr * 0.60, by - hr * 0.32, hr * 1.2, hr * 0.2))
    elif hat == 1:                                  # шапочка с помпоном
        col = QColor(HATS[(seed >> 6) % len(HATS)])
        yb = hy - hr * 0.55
        dome = QPainterPath()
        dome.moveTo(x + hr * 0.92, yb)
        dome.arcTo(QRectF(x - hr * 0.92, yb - hr * 0.95, hr * 1.84, hr * 1.9), 0, 180)
        dome.closeSubpath()
        p.setBrush(QBrush(col))
        p.drawPath(dome)
        p.setBrush(QBrush(QColor("#F6F6F6")))
        p.drawRoundedRect(QRectF(x - hr * 0.97, yb - hr * 0.2, hr * 1.94, hr * 0.34),
                          hr * 0.15, hr * 0.15)
        p.drawEllipse(QPointF(x, yb - hr * 0.97), hr * 0.2, hr * 0.2)
    p.restore()
    if name:                                                   # подпись с именем
        f = QFont("Segoe UI")
        f.setPixelSize(max(9, int(12 * S)))
        f.setBold(True)
        p.setFont(f)
        tw = p.fontMetrics().horizontalAdvance(name) + 14 * S
        ty = hy - hr * 2.9
        rc = QRectF(x - tw / 2, ty, tw, 17 * S)
        p.setPen(NOPEN)
        p.setBrush(QBrush(QColor(15, 30, 55, 190)))
        p.drawRoundedRect(rc, 8 * S, 8 * S)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(rc, Qt.AlignmentFlag.AlignCenter, name)


def draw_plow(p, x, base, d, wheel, t, pile):
    """Маленькая снегоуборочная машина. x - центр, base - уровень земли, d - направление."""
    u = S
    p.save()
    p.setPen(NOPEN)
    # куча снега перед отвалом
    if pile > 2.0:
        pw = min(34.0 * u, 6.0 * u + math.sqrt(pile) * 0.75)
        ph = min(16.0 * u, 2.0 * u + math.sqrt(pile) * 0.38)
        xf = x + d * 27.0 * u
        path = QPainterPath()
        path.moveTo(xf, base + 1.5 * u)
        path.cubicTo(QPointF(xf, base - ph * 1.3), QPointF(xf + d * pw * 0.45, base - ph * 1.1),
                     QPointF(xf + d * pw, base + 1.5 * u))
        path.closeSubpath()
        g = QLinearGradient(0, base - ph, 0, base + 2 * u)
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(1.0, QColor("#CFE2F7"))
        p.setBrush(QBrush(g))
        p.drawPath(path)
    p.translate(x, base)
    if d < 0:
        p.scale(-1.0, 1.0)
    # тень
    p.setBrush(QBrush(QColor(20, 30, 60, 60)))
    p.drawEllipse(QPointF(0, 1.8 * u), 25 * u, 2.2 * u)
    # кузов-бункер
    p.setBrush(QBrush(QColor("#5B6470")))
    p.drawRoundedRect(QRectF(-23 * u, -21 * u, 16 * u, 8 * u), 1.5 * u, 1.5 * u)
    # шасси
    p.setBrush(QBrush(QColor("#F28C1B")))
    p.drawRoundedRect(QRectF(-23 * u, -14 * u, 42 * u, 9 * u), 2.0 * u, 2.0 * u)
    # кабина
    cab = QPainterPath()
    cab.moveTo(-5 * u, -13 * u)
    cab.lineTo(-2 * u, -25 * u)
    cab.lineTo(11 * u, -25 * u)
    cab.lineTo(15 * u, -13 * u)
    cab.closeSubpath()
    p.drawPath(cab)
    p.setBrush(QBrush(QColor("#BFE3FF")))
    win = QPainterPath()
    win.moveTo(-1.5 * u, -14.5 * u)
    win.lineTo(0.5 * u, -23 * u)
    win.lineTo(9.5 * u, -23 * u)
    win.lineTo(12 * u, -14.5 * u)
    win.closeSubpath()
    p.drawPath(win)
    # фара
    p.setBrush(QBrush(QColor("#FFF3B0")))
    p.drawEllipse(QPointF(18.2 * u, -10.5 * u), 1.7 * u, 1.7 * u)
    # рычаг и отвал
    p.setPen(QPen(QColor("#4A525C"), max(1.5, 1.6 * u), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(15 * u, -8 * u), QPointF(23 * u, -8 * u))
    p.setPen(QPen(QColor("#9A7B00"), max(1.0, 0.8 * u)))
    p.setBrush(QBrush(QColor("#FFD21F")))
    blade = QPainterPath()
    blade.moveTo(20 * u, 1.5 * u)
    blade.lineTo(25 * u, 1.5 * u)
    blade.lineTo(29 * u, -15 * u)
    blade.lineTo(24 * u, -15 * u)
    blade.closeSubpath()
    p.drawPath(blade)
    p.setPen(NOPEN)
    # колёса
    for wx in (-13 * u, 11 * u):
        p.save()
        p.translate(wx, -3.2 * u)
        p.setBrush(QBrush(QColor("#22262E")))
        p.drawEllipse(QPointF(0, 0), 5.0 * u, 5.0 * u)
        p.rotate(wheel)
        p.setBrush(QBrush(QColor("#9AA3AE")))
        p.drawEllipse(QPointF(0, 0), 2.1 * u, 2.1 * u)
        p.setPen(QPen(QColor("#22262E"), max(1.0, 0.9 * u)))
        p.drawLine(QPointF(-1.8 * u, 0), QPointF(1.8 * u, 0))
        p.drawLine(QPointF(0, -1.8 * u), QPointF(0, 1.8 * u))
        p.restore()
    # мигалка на крыше
    on = int(t * 0.12) % 2 == 0
    p.setPen(NOPEN)
    _ground_glow(p, 4.0 * u, on, u)
    p.setBrush(QBrush(QColor("#7A4A00")))
    p.drawRect(QRectF(2 * u, -27 * u, 5 * u, 2 * u))
    g = QRadialGradient(4.5 * u, -28.5 * u, 9 * u)
    g.setColorAt(0.0, QColor(255, 170, 30, 210 if on else 40))
    g.setColorAt(1.0, QColor(255, 170, 30, 0))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(4.5 * u, -28.5 * u), 9 * u, 9 * u)
    p.setBrush(QBrush(QColor("#FFC040") if on else QColor("#B07A20")))
    p.drawEllipse(QPointF(4.5 * u, -28.2 * u), 2.2 * u, 2.0 * u)
    p.restore()


def _ground_glow(p, cx, on, u):
    """Оранжевый отсвет мигалки на снегу."""
    if not on:
        return
    p.save()
    p.translate(cx, 0.5 * u)
    p.scale(1.0, 0.18)
    g = QRadialGradient(0, 0, 46 * u)
    g.setColorAt(0.0, QColor(255, 170, 40, 100))
    g.setColorAt(1.0, QColor(255, 170, 40, 0))
    p.setPen(NOPEN)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(0, 0), 46 * u, 46 * u)
    p.restore()


def _wheel(p, cx, cy, r, ang):
    p.save()
    p.translate(cx, cy)
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor("#22262E")))
    p.drawEllipse(QPointF(0, 0), r, r)
    p.rotate(ang)
    p.setBrush(QBrush(QColor("#9AA3AE")))
    p.drawEllipse(QPointF(0, 0), r * 0.45, r * 0.45)
    p.setPen(QPen(QColor("#22262E"), max(1.0, r * 0.12)))
    p.drawLine(QPointF(-r * 0.4, 0), QPointF(r * 0.4, 0))
    p.drawLine(QPointF(0, -r * 0.4), QPointF(0, r * 0.4))
    p.restore()


def _beacon(p, cx, cy, t, u):
    on = int(t * 0.12) % 2 == 0
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor("#7A4A00")))
    p.drawRect(QRectF(cx - 2.5 * u, cy, 5 * u, 2 * u))
    g = QRadialGradient(cx, cy - 1.5 * u, 9 * u)
    g.setColorAt(0.0, QColor(255, 170, 30, 210 if on else 40))
    g.setColorAt(1.0, QColor(255, 170, 30, 0))
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(cx, cy - 1.5 * u), 9 * u, 9 * u)
    p.setBrush(QBrush(QColor("#FFC040") if on else QColor("#B07A20")))
    p.drawEllipse(QPointF(cx, cy - 1.2 * u), 2.2 * u, 2.0 * u)
    return on


def _pile(p, xf, base, d, pile):
    if pile <= 2.0:
        return
    pw = min(34.0 * S, 6.0 * S + math.sqrt(pile) * 0.75)
    ph = min(16.0 * S, 2.0 * S + math.sqrt(pile) * 0.38)
    path = QPainterPath()
    path.moveTo(xf, base + 1.5 * S)
    path.cubicTo(QPointF(xf, base - ph * 1.3), QPointF(xf + d * pw * 0.45, base - ph * 1.1),
                 QPointF(xf + d * pw, base + 1.5 * S))
    path.closeSubpath()
    g = QLinearGradient(0, base - ph, 0, base + 2 * S)
    g.setColorAt(0.0, QColor("#FFFFFF"))
    g.setColorAt(1.0, QColor("#CFE2F7"))
    p.setPen(NOPEN)
    p.setBrush(QBrush(g))
    p.drawPath(path)


def draw_tractor(p, x, base, d, wheel, t, pile):
    """Зелёный трактор с большим отвалом."""
    u = S
    p.save()
    _pile(p, x + d * 35.0 * u, base, d, pile)
    p.translate(x, base)
    if d < 0:
        p.scale(-1.0, 1.0)
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor(20, 30, 60, 60)))
    p.drawEllipse(QPointF(2 * u, 1.8 * u), 30 * u, 2.4 * u)
    _wheel(p, -13 * u, -9.5 * u, 9.5 * u, wheel)
    p.setBrush(QBrush(QColor("#2F8F46")))
    p.drawRoundedRect(QRectF(-18 * u, -17 * u, 40 * u, 8 * u), 2 * u, 2 * u)
    p.setBrush(QBrush(QColor("#3FB45A")))
    p.drawRoundedRect(QRectF(2 * u, -24 * u, 22 * u, 12 * u), 3 * u, 3 * u)
    p.setBrush(QBrush(QColor("#2F8F46")))
    p.drawRoundedRect(QRectF(-19 * u, -36 * u, 17 * u, 20 * u), 2.5 * u, 2.5 * u)
    p.setBrush(QBrush(QColor("#BFE3FF")))
    p.drawRoundedRect(QRectF(-16.5 * u, -33.5 * u, 12 * u, 11 * u), 1.5 * u, 1.5 * u)
    p.setBrush(QBrush(QColor("#1F5E31")))
    p.drawRect(QRectF(-21 * u, -38 * u, 21 * u, 2.5 * u))
    p.setBrush(QBrush(QColor("#555B63")))
    p.drawRect(QRectF(16 * u, -33 * u, 2.2 * u, 10 * u))
    _wheel(p, 16 * u, -5.2 * u, 5.2 * u, wheel * 1.8)
    p.setBrush(QBrush(QColor("#FFF3B0")))
    p.drawEllipse(QPointF(24 * u, -17 * u), 1.8 * u, 1.8 * u)
    p.setPen(QPen(QColor("#3C434B"), max(1.5, 1.8 * u), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(20 * u, -9 * u), QPointF(31 * u, -9 * u))
    p.drawLine(QPointF(20 * u, -12 * u), QPointF(31 * u, -14 * u))
    p.setPen(QPen(QColor("#9A7B00"), max(1.0, 0.8 * u)))
    p.setBrush(QBrush(QColor("#FFD21F")))
    blade = QPainterPath()
    blade.moveTo(30 * u, 1.5 * u)
    blade.lineTo(36 * u, 1.5 * u)
    blade.lineTo(40 * u, -22 * u)
    blade.lineTo(34 * u, -22 * u)
    blade.closeSubpath()
    p.drawPath(blade)
    on = _beacon(p, -10 * u, -41 * u, t, u)
    _ground_glow(p, 0.0, on, u)
    p.restore()


def draw_blower(p, x, base, d, wheel, t, pile):
    """Большой роторный снегоочиститель: шнек спереди, снег летит из трубы."""
    u = S
    p.save()
    p.translate(x, base)
    if d < 0:
        p.scale(-1.0, 1.0)
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor(20, 30, 60, 60)))
    p.drawEllipse(QPointF(2 * u, 1.8 * u), 34 * u, 2.4 * u)
    # гусеницы
    p.setBrush(QBrush(QColor("#2B2F36")))
    p.drawRoundedRect(QRectF(-30 * u, -9 * u, 54 * u, 10.5 * u), 5 * u, 5 * u)
    p.setBrush(QBrush(QColor("#59616C")))
    for cx in (-23, -11, 1, 13, 21):
        p.drawEllipse(QPointF(cx * u, -3.7 * u), 3.4 * u, 3.4 * u)
    off = (wheel * 0.09 * u) % (8 * u)
    p.setBrush(QBrush(QColor("#8A929C")))
    for k in range(8):
        tx = -30 * u + 2 * u + k * 8 * u + off
        if tx < 22 * u:
            p.drawRect(QRectF(tx, 0.4 * u, 2 * u, 1.2 * u))
    # корпус и кабина
    p.setBrush(QBrush(QColor("#E4572E")))
    p.drawRoundedRect(QRectF(-28 * u, -27 * u, 44 * u, 19 * u), 3 * u, 3 * u)
    p.setBrush(QBrush(QColor("#C43F1B")))
    p.drawRect(QRectF(-28 * u, -12 * u, 44 * u, 3 * u))
    p.setBrush(QBrush(QColor("#E4572E")))
    p.drawRoundedRect(QRectF(-25 * u, -42 * u, 18 * u, 17 * u), 3 * u, 3 * u)
    p.setBrush(QBrush(QColor("#BFE3FF")))
    p.drawRoundedRect(QRectF(-22.5 * u, -39.5 * u, 13 * u, 11 * u), 2 * u, 2 * u)
    # шнек
    p.setBrush(QBrush(QColor("#7C858F")))
    p.drawRoundedRect(QRectF(16 * u, -26 * u, 17 * u, 25 * u), 3 * u, 3 * u)
    p.save()
    p.setClipRect(QRectF(16 * u, -26 * u, 17 * u, 25 * u), Qt.ClipOperation.IntersectClip)
    p.setPen(QPen(QColor("#D5DBE1"), max(1.0, 1.3 * u)))
    off2 = (wheel * 0.06) % 6.0
    for k in range(-1, 6):
        yy = -26 * u + (k * 6.0 + off2) * u
        p.drawLine(QPointF(17 * u, yy + 4 * u), QPointF(32 * u, yy))
    p.restore()
    p.setPen(NOPEN)
    p.setBrush(QBrush(QColor("#FFD21F")))
    p.drawRect(QRectF(32 * u, -26 * u, 2.5 * u, 25 * u))
    # труба и козырёк
    p.setBrush(QBrush(QColor("#7C858F")))
    chute = QPainterPath()
    chute.moveTo(21 * u, -26 * u)
    chute.lineTo(28 * u, -26 * u)
    chute.lineTo(30 * u, -46 * u)
    chute.lineTo(24 * u, -48 * u)
    chute.closeSubpath()
    p.drawPath(chute)
    p.setBrush(QBrush(QColor("#FFD21F")))
    cap = QPainterPath()
    cap.moveTo(24 * u, -48 * u)
    cap.lineTo(31 * u, -46 * u)
    cap.lineTo(35 * u, -50 * u)
    cap.lineTo(26 * u, -53 * u)
    cap.closeSubpath()
    p.drawPath(cap)
    p.setBrush(QBrush(QColor("#FFF3B0")))
    p.drawEllipse(QPointF(15.5 * u, -15 * u), 1.7 * u, 1.7 * u)
    on = _beacon(p, -16 * u, -43 * u, t, u)
    _ground_glow(p, 0.0, on, u)
    p.restore()


def draw_vehicle(p, pl, base, t):
    fn = (draw_plow, draw_tractor, draw_blower)[pl["kind"]]
    fn(p, pl["x"], base, pl["d"], pl["wheel"], t, pl["pile"])


def draw_tree(p, x, base, t):
    """Ёлка (x - центр, base - низ ствола), огоньки мигают."""
    img, W, H, lights, star = tree_sprite()
    ox, oy = x - W / 2.0, base - (H - 3 * S)
    p.drawImage(QPointF(ox, oy), img)
    nb = len(BULB_COLORS)
    for i, (lx, ly, ci) in enumerate(lights):
        spr, half = glow_sprite((ci + int(t * 0.025)) % nb, 5.0 * S)
        p.setOpacity(0.5 + 0.5 * max(0.0, math.sin(t * 0.1 + i * 1.7)))
        p.drawImage(QPointF(ox + lx - half, oy + ly - half), spr)
    spr, half = soft_sprite(9.0 * S)
    p.setOpacity(0.55 + 0.45 * math.sin(t * 0.08))
    p.drawImage(QPointF(ox + star[0] - half, oy + star[1] - half), spr)
    p.setOpacity(1.0)


def snowman_rect(x, base, balls):
    cs = stack_centers(balls, base)
    top = cs[-1] - balls[-1] - (balls[-1] * 1.4 if len(balls) >= 3 else 4)
    r = max(balls) + 6
    return QRectF(x - r * 1.9 if len(balls) >= 3 else x - r, top, r * 3.8 if len(balls) >= 3 else r * 2,
                  base - top + 6)


# ---------------------------------------------------------------------------
#  Объекты
# ---------------------------------------------------------------------------
class Flake:
    __slots__ = ("x", "y", "r", "depth", "speed", "amp", "sp", "ph", "wk", "vx", "vy",
                 "op", "crystal", "ang", "spin", "spr", "half")

    def __init__(self, first=False):
        self.reset(first)

    def reset(self, first=False):
        d = random.random() ** 1.5            # больше мелких (дальних) снежинок
        self.depth = d
        self.r = (MIN_SIZE + (MAX_SIZE - MIN_SIZE) * d) * S
        self.x = random.uniform(0, VW)
        self.y = random.uniform(-VH, VH) if first else random.uniform(-60, -8)
        self.speed = (0.7 + d * 2.0) * S
        self.amp = random.uniform(0.25, 1.0) * S
        self.sp = random.uniform(0.012, 0.04)
        self.ph = random.uniform(0, math.tau)
        self.wk = 0.35 + d * 0.9
        self.vx = self.vy = 0.0
        self.op = 0.45 + 0.55 * d
        self.crystal = d > 0.8 and random.random() < 0.75
        self.ang = random.uniform(0, 360)
        self.spin = random.uniform(-1.2, 1.2)
        if self.crystal:
            self.spr, self.half = crystal_sprite(self.r * 1.9)
        else:
            self.spr, self.half = soft_sprite(self.r)


class Snowman:
    __slots__ = ("anchor", "dx", "balls", "seed", "lx", "ly", "name")

    def __init__(self, anchor, dx, r, lx, ly):
        self.anchor, self.dx, self.balls = anchor, dx, [r]
        self.name = ""
        self.seed = random.getrandbits(32)
        self.lx, self.ly = lx, ly


# ---------------------------------------------------------------------------
#  Оверлей
# ---------------------------------------------------------------------------
class Overlay(QWidget):
    def __init__(self, app):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                 Qt.WindowType.WindowDoesNotAcceptFocus)
        if IS_WIN:
            flags |= Qt.WindowType.Tool          # (на Mac Tool-окна прячутся, когда приложение не активно)
        super().__init__(None, flags)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Snow overlay")
        self.setGeometry(VX, VY, VW, VH)

        self.t = 0                       # номер кадра
        self.tf = 0.0                    # время в "кадрах по 1/60 с" (для плавности)
        self.last = time.perf_counter()
        self.paused = False
        self.build = False
        self.hidden = False              # скрыт, пока открыто полноэкранное приложение
        self.click_through = True
        self.hwnd = 0
        self.lock = {}
        self.flakes = [Flake(first=True) for _ in range(FLAKES)]
        self.puffs = []
        self.chunks = []                 # летящие комья снега [x, y, vx, vy, объём]
        self.entries = []
        self.wins, self.by_hwnd, self.segs, self.rects = [], {}, {}, []
        self.surf, self.surfs, self.lands = {}, [], []
        self.blank = []                  # мониторы, закрытые полноэкранным окном
        self.snowmen, self.sm_layout, self.sm_rects = [], [], []
        self.hold = None
        self.drops = []
        self.cur = (0.0, 0.0, 0.0, 0.0)          # x, y, vx, vy курсора
        self.tray = None
        self.wpos = {}                   # недавние положения окон (для скорости и опережения)
        self.lead_ms = float(SYNC_LEAD_MS)
        self.toast = None
        self.fs_flag = False             # Windows сообщает о полноэкранном приложении
        self.beat = 0.0                  # "пульс" для сторожа зависаний
        self.show_votes = 0
        self.err_logged = False
        self.plow = None
        self.plow_next = time.perf_counter() + PLOW_FIRST
        self.plow_dir = 1
        self.plow_mon = 0
        self.plow_count = 0
        self.tracks = []                 # следы колёс [x0, x1, поверхность, возраст]
        # метель
        self.bl = 0.0                    # интенсивность метели 0..1 (плавно меняется)
        self.bl_on = False
        self.bl_end = 0.0
        self.bl_dir = 1
        self.bl_next = time.perf_counter() + BLIZZARD_INTERVAL * 60.0
        self.wind = 0.0
        # сосульки
        self.ice = {}                    # окно -> насколько выросли (0..1)
        self.ice_cache = {}
        self.bsegs = {}                  # видимые части нижнего края окон
        self.shards = []                 # падающие осколки сосулек [x, y, vx, vy, длина]
        # снежки
        self.throw = False
        self.balls = []
        self.decals = []                 # снежные "шлепки" на окнах
        # сохранение
        self.pending_sm = []
        self.pending_t0 = time.perf_counter()
        self.saved_drifts = {}
        self.state_saved_at = time.perf_counter()
        self._save_pending = False
        self.panel = None
        self.naming = False
        pg = app.primaryScreen().geometry()
        self.banner_cx = pg.x() - VX + pg.width() / 2.0
        self.banner_y = pg.y() - VY + 18 * S

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.frame_ms = max(5, int(1000 / FPS))

    # ----- запуск и системные флаги -----
    def start(self):
        self.show()
        self.hwnd = int(self.winId())
        self.apply_exstyle()
        self.raise_topmost()
        threading.Thread(target=self.scan_loop, daemon=True).start()
        threading.Thread(target=self.watchdog, daemon=True).start()
        self.last = time.perf_counter()
        self.timer.start(self.frame_ms)

    def apply_exstyle(self):
        plat_apply_window(self)

    def scan_loop(self):
        """Поиск окон и проверка полноэкранного режима идут в отдельном потоке:
        даже если какое-то приложение не отвечает, снег не зависает."""
        while True:
            try:
                self.entries = scan_windows()
            except Exception:
                pass
            if FULLSCREEN_API:
                try:
                    self.fs_flag = fullscreen_state()
                except Exception:
                    pass
            time.sleep(0.3 if self.hidden else 0.15)

    def watchdog(self):
        """Если снег завис больше чем на 3 секунды - записывает в snow_freeze.log,
        где именно застряла программа (чтобы можно было найти причину)."""
        import faulthandler
        stuck = False
        while True:
            time.sleep(1.0)
            b = self.beat
            if b and time.perf_counter() - b > 3.0:
                if not stuck:
                    stuck = True
                    try:
                        with open(os.path.join(DATA_DIR, "snow_freeze.log"), "a", encoding="utf-8") as fh:
                            fh.write("\n=== зависание, %s ===\n" % time.strftime("%H:%M:%S"))
                            fh.flush()
                            faulthandler.dump_traceback(file=fh, all_threads=True)
                    except Exception:
                        pass
            else:
                stuck = False

    def raise_topmost(self):
        plat_raise(self)

    def set_click_through(self, on):
        if on == self.click_through:
            return
        self.click_through = on
        plat_click_through(self, on)

    # ----- команды -----
    def toggle_pause(self, *_):
        self.paused = not self.paused

    def toggle_build(self, *_):
        self.set_build(not self.build)

    def set_build(self, on):
        self.build = on
        if on:
            self.throw = False
        self.hold = None
        self.set_click_through(not (self.build or self.throw))
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)

    def toggle_throw(self, *_):
        self.set_throw(not self.throw)

    def set_throw(self, on):
        self.throw = on
        if on:
            self.build = False
            self.hold = None
        self.set_click_through(not (self.build or self.throw))
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)

    def clear_snowmen(self, *_):
        self.snowmen = []
        self.drops = []
        self.layout_snowmen()

    def clear_drifts(self, *_):
        """Стряхнуть весь снег с окон и панели задач - он упадёт вниз."""
        for s in list(self.surf.values()):
            self.shed(s, 1.0, 0.0, 0.0, 14)

    def adj_lead(self, delta):
        global SYNC_LEAD_MS
        self.lead_ms = max(0.0, min(100.0, self.lead_ms + delta))
        SYNC_LEAD_MS = int(round(self.lead_ms))
        self.toast = ("Опережение окон: %d мс   (Ctrl+Shift+%s / %s)" % (SYNC_LEAD_MS, HK["lead_up"], HK["lead_dn"]),
                      time.perf_counter() + 2.0)
        self.schedule_save()
        if self.panel is not None:
            self.panel.refresh()

    def call_plow(self, *_):
        if self.plow is None:
            self.plow_next = 0.0

    def on_exit(self, *_):
        try:
            self.save_state()
        except Exception:
            pass
        save_settings()

    def quit(self, *_):
        self.on_exit()
        if self.tray is not None:
            self.tray.hide()
        plat_timer_precision(False)
        self.app.quit()

    # ----- окна -----
    def update_windows(self, now):
        wins = refresh_windows(self.entries)
        # Скорость окна считаем по времени за последние ~3 кадра (так она не дёргается,
        # даже если Windows обновляет положение окна не каждый кадр) и рисуем сугробы
        # с гирляндами чуть впереди: это компенсирует задержку между отрисовкой и показом.
        old, new = self.wpos, {}
        lead = self.lead_ms / 1000.0
        lim = 40.0 * S
        for w in wins:
            hist = old.get(w.hwnd)
            hist = (hist[-3:] if hist else []) + [(now, w.l, w.t)]
            new[w.hwnd] = hist
            vx = vy = 0.0
            if len(hist) >= 2:
                t0, l0, tt0 = hist[0]
                span = now - t0
                if span > 0.004:
                    dxs, dys = w.l - l0, w.t - tt0
                    if abs(dxs) < 600 and abs(dys) < 600:
                        vx, vy = dxs / span, dys / span
            w.dx, w.dy = vx / 60.0, vy / 60.0
            if lead and w.kind == "win" and (vx or vy):
                ox = max(-lim, min(lim, vx * lead))
                oy = max(-lim, min(lim, vy * lead))
                w.l += ox
                w.r += ox
                w.t += oy
                w.b += oy
        self.wpos = new
        self.wins = wins
        self.by_hwnd = {w.hwnd: w for w in wins}
        segs = {}
        for i, w in enumerate(wins):
            if w.kind in ("win", "task"):
                segs[w.hwnd] = visible_segments(w, wins[:i])
        self.segs = segs
        self.rects = [] if SNOW_OVER_WINDOWS else [(w.l, w.t, w.r, w.b) for w in wins]
        if not SNOW_OVER_WINDOWS and self.panel is not None and self.panel.isVisible():
            g = self.panel.frameGeometry()          # снег не падает на окно настроек
            self.rects.append((g.x() - VX, g.y() - VY, g.x() - VX + g.width(),
                               g.y() - VY + g.height()))
        bsegs = {}
        if ICICLES:
            for i, w in enumerate(wins):
                if w.kind == "win" and w.r - w.l >= 160 * S and w.b < VH - 40 * S:
                    bs = visible_segments_y(w, wins[:i], w.b + 3 * S, 14)
                    if bs:
                        bsegs[w.hwnd] = bs
        self.bsegs = bsegs
        # монитор "закрыт", если самое верхнее окно на нём - полноэкранное
        blank, decided = [], set()
        for w in wins:
            if w.kind == "task":
                continue
            cxm, cym = (w.l + w.r) / 2.0, (w.t + w.b) / 2.0
            for mi, m in enumerate(MONS):
                if m[0] <= cxm < m[2] and m[1] <= cym < m[3]:
                    if mi not in decided:
                        decided.add(mi)
                        if w.kind == "full":
                            blank.append(m)
                    break
        self.blank = blank
        self.layout_snowmen()

    def anchor_pos(self, anchor, dx):
        """(x, y поверхности) или None, если поверхность скрыта."""
        if anchor == 0:
            return (float(dx), float(VH))
        w = self.by_hwnd.get(anchor)
        if w is None or w.kind in ("full", "max"):
            return None
        x = w.l + min(dx, max(0, w.r - w.l - 8 * S))
        if not any(a + 6 * S <= x <= b - 6 * S for a, b in self.segs.get(anchor, [])):
            return None
        return (float(x), float(w.t - 1))

    def locate(self, x, y):
        """Куда упадет шар, отпущенный в точке (x, y): (окно, y поверхности, смещение)."""
        wins = self.wins
        for w in wins:                                   # отпустили внутри окна
            if w.l <= x <= w.r and w.t <= y <= w.b:
                if w.kind == "win" and any(a + 6 * S <= x <= b - 6 * S
                                           for a, b in self.segs.get(w.hwnd, [])):
                    return (w.hwnd, w.t, x - w.l)
                break
        best = None                                      # иначе - падает на ближайшую поверхность ниже
        for w in wins:
            if w.kind in ("win", "task") and w.t >= y - 4 * S:
                if any(a + 12 * S <= x <= b - 12 * S for a, b in self.segs.get(w.hwnd, [])):
                    if best is None or w.t < best.t:
                        best = w
        if best is not None:
            return (best.hwnd, best.t, x - best.l)
        return (0, VH, x)

    def layout_snowmen(self):
        lay, rects = [], []
        for sm in self.snowmen:
            if sm.anchor and sm.anchor not in self.by_hwnd and not win_alive(sm.anchor):
                a, _ys, dx = self.locate(sm.lx, sm.ly)   # окно закрыли - падает на то, что под ним
                sm.anchor, sm.dx = a, dx
            pos = self.anchor_pos(sm.anchor, sm.dx)
            if pos is None:
                lay.append((sm, 0.0, 0.0, False))
            else:
                sm.lx, sm.ly = pos
                lay.append((sm, pos[0], pos[1], True))
                rects.append((sm, snowman_rect(pos[0], pos[1], sm.balls)))
        self.sm_layout = lay
        self.sm_rects = rects

    # ----- сугробы -----
    def update_surfaces(self, dt):
        surf = self.surf
        seen = set()
        if SNOW_ON_WINDOWS:
            for w in self.wins:
                if w.kind in ("win", "task") and w.t >= 6:
                    s = surf.get(w.hwnd)
                    if s is None:
                        s = surf[w.hwnd] = Surface(w.hwnd, w.kind, w.l, w.t, w.r, w.b,
                                                   (2.4 if w.kind == "task" else 1.8) * S)
                        self.restore_drift(s)
                    else:
                        if SHAKE_OFF and not self.paused:
                            self.check_shake(s, w, dt)
                        s.set_geom(w.l, w.t, w.r, w.b)
                        s.kind = w.kind
                    s.segs = self.segs.get(w.hwnd, [])
                    s.maxh = (MAX_DRIFT_TASK if w.kind == "task" else MAX_DRIFT_WIN) * S
                    s.miss = 0
                    seen.add(w.hwnd)
        if SNOW_FLOOR:
            for i, m in enumerate(MONS):
                key = ("f", i)
                ft = min(m[3] - 1, VH)
                fl = surf.get(key)
                if fl is None:
                    fl = surf[key] = Surface(key, "floor", m[0], ft, m[2], ft + 1, 0.0)
                    self.restore_drift(fl)
                else:
                    fl.set_geom(m[0], ft, m[2], ft + 1)
                fl.segs = visible_segments(fl, self.wins)
                fl.maxh = MAX_DRIFT_FLOOR * S
                fl.miss = 0
                seen.add(key)
        for key in list(surf):
            if key in seen:
                continue
            s = surf[key]
            s.miss += 1
            s.segs = []
            if s.miss > 20:                      # окно закрыли / свернули - снег осыпается
                self.shed(s, 1.0, 0.0, 0.0, 10)
                del surf[key]
        live = [s for s in surf.values() if s.segs]
        live.sort(key=lambda s: s.t)
        self.surfs = live
        self.lands = [(s.t, s.l, s.r, s) for s in live]

    def check_shake(self, s, w, dt):
        """Окно таскают быстро - снег с него слетает."""
        sp = math.hypot(w.dx, w.dy)
        lim = 12.0 * S
        if sp > lim:
            frac = min(0.7, (sp - lim) / (70.0 * S))
            self.shed(s, frac, -w.dx * 0.35, -w.dy * 0.2, 8)

    def shed(self, s, frac, vx0, vy0, groups):
        """Сбросить долю frac снега с поверхности s: он превращается в падающие комья."""
        h, n, cw = s.h, s.n, s.cw
        acc = {}
        for i in range(n):
            hi = h[i]
            if hi < 0.25:
                continue
            a = hi * frac
            h[i] = hi - a
            vol = a * cw
            g = i * groups // n
            e = acc.get(g)
            if e is None:
                acc[g] = [vol, (s.l + i * cw) * vol, (s.t - hi * 0.6) * vol]
            else:
                e[0] += vol
                e[1] += (s.l + i * cw) * vol
                e[2] += (s.t - hi * 0.6) * vol
        for vol, sx, sy in acc.values():
            if vol >= 1.0:
                self.spawn(sx / vol, sy / vol, vol, vx0, vy0)
        s.dirty = True

    def spawn(self, x, y, vol, vx0, vy0):
        n = min(5, 1 + int(vol / (40.0 * S * S)))
        v = vol / n
        for _ in range(n):
            if len(self.chunks) >= MAX_CHUNKS:
                return
            self.chunks.append([x + random.uniform(-5, 5) * S, y + random.uniform(-3, 2) * S,
                                vx0 + random.uniform(-1.5, 1.5) * S,
                                vy0 + random.uniform(-1.3, 0.5) * S, v])

    def spill(self, s, j, vol):
        left = j < s.n / 2.0
        self.spawn(s.l + j * s.cw, s.t - 1.0, vol,
                   (-1 if left else 1) * random.uniform(0.3, 1.2) * S, 0.0)

    def sweep(self, dt):
        """Быстро провёл курсором через сугроб - снег разлетается и падает вниз."""
        cx, cy, cvx, cvy = self.cur
        sp = math.hypot(cvx, cvy)
        thr = SWEEP_SPEED * S
        if sp < thr:
            return
        R = SWEEP_RADIUS * S
        power = min(1.8, sp / (2.0 * thr)) * min(dt, 2.0)
        vx0 = max(-14 * S, min(14 * S, cvx * 0.6))
        vy0 = max(-10 * S, min(10 * S, cvy * 0.3)) - 1.2 * S
        for s in self.surfs:
            if cx < s.l - R or cx > s.r + R:
                continue
            if cy > s.t + 3 * S or cy < s.t - s.maxh - R:
                continue
            i0 = max(0, int((cx - R - s.l) / s.cw))
            i1 = min(s.n - 1, int((cx + R - s.l) / s.cw) + 1)
            span = i1 - i0 + 1
            acc = {}
            for i in range(i0, i1 + 1):
                hi = s.h[i]
                if hi < 0.3:
                    continue
                x = s.l + i * s.cw
                if abs(x - cx) > R or cy + R < s.t - hi or not s.vis(x):
                    continue
                amt = min(hi, (0.35 * hi + 0.5 * S) * power)
                s.h[i] = hi - amt
                vol = amt * s.cw
                g = (i - i0) * 4 // span
                e = acc.get(g)
                if e is None:
                    acc[g] = [vol, x * vol, (s.t - hi * 0.7) * vol]
                else:
                    e[0] += vol
                    e[1] += x * vol
                    e[2] += (s.t - hi * 0.7) * vol
            if acc:
                s.dirty = True
                for vol, sx, sy in acc.values():
                    if vol >= 0.8:
                        self.spawn(sx / vol, sy / vol, vol, vx0, vy0)

    def step_chunks(self, dt):
        if not self.chunks:
            return
        lands, rects = self.lands, self.rects
        drag = 0.992 ** dt
        g = 0.34 * S * dt
        vmax = 20.0 * S
        keep = []
        for c in self.chunks:
            x, y, vx, vy, vol = c
            py = y
            vy = min(vmax, vy + g)
            vx *= drag
            x += vx * dt
            y += vy * dt
            if y > VH + 30 or x < -40 or x > VW + 40:
                continue
            done = False
            if vy > 0:
                for lt, ll, lr, s in lands:
                    if py <= lt <= y and ll <= x <= lr and s.vis(x):
                        k = max(2, min(8, int(0.5 * math.sqrt(vol) / s.cw) + 2))
                        s.add(x, vol, k)
                        done = True
                        break
            if done:
                continue
            inside = False
            for l, tp, r, b in rects:
                if l <= x <= r and tp <= y <= b:
                    inside = True
                    break
            if inside:
                continue
            c[0], c[1], c[2], c[3] = x, y, vx, vy
            keep.append(c)
        self.chunks = keep

    # ----- снегоуборочная машина -----
    def plow_surface(self, mi):
        """Самая нижняя видимая поверхность на мониторе mi (панель задач или низ экрана)."""
        m = MONS[mi]
        best = None
        for s in self.surf.values():
            if s.kind not in ("task", "floor") or not s.segs:
                continue
            if not (m[0] <= (s.l + s.r) / 2.0 < m[2]) or s.r - s.l < 0.6 * (m[2] - m[0]):
                continue
            if best is None or (s.kind == "task", s.t) > (best.kind == "task", best.t):
                best = s                              # панель задач в приоритете, иначе самый низ
        return best

    def plow_clean_list(self, s, m):
        """Поверхности, с которых снегоуборщик сгребает снег: панель задач и низ экрана."""
        out = [s]
        for o in self.surf.values():
            if (o is not s and o.kind in ("task", "floor") and m[0] <= (o.l + o.r) / 2.0 < m[2]
                    and o.r - o.l >= 0.6 * (m[2] - m[0])):
                out.append(o)
        return out

    def start_plow(self):
        if not MONS:
            return False
        for k in range(len(MONS)):
            mi = (self.plow_mon + k) % len(MONS)
            s = self.plow_surface(mi)
            if s is not None:
                break
        else:
            return False
        self.plow_mon = (mi + 1) % len(MONS)
        d = self.plow_dir
        self.plow_dir = -d
        kind = (self.plow_count % 3) if PLOW_VARIETY else 0
        self.plow_count += 1
        half, fo = PLOW_KINDS[kind]
        m = MONS[mi]
        x = (m[0] - (half + 8.0) * S) if d > 0 else (m[2] + (half + 8.0) * S)
        self.plow = {"mon": mi, "key": s.key, "d": d, "x": x, "pile": 0.0, "wheel": 0.0,
                     "dumped": False, "pxf": x + d * fo * S, "n": 0, "kind": kind,
                     "half": half, "fo": fo, "ltx": x}
        return True

    def end_plow(self):
        self.plow = None
        self.plow_next = time.perf_counter() + PLOW_INTERVAL

    def plow_hit_snowmen(self, s, xf, d):
        """Отвал доехал до снеговика - снеговик разлетается комьями снега."""
        hit = []
        for sm, x, base, vis in self.sm_layout:
            if not vis or abs(base - s.t) > 7.0 * S:
                continue
            r1 = sm.balls[0]
            if d > 0:
                touched = x - r1 * 0.7 <= xf <= x + r1 + 60.0 * S
            else:
                touched = x - r1 - 60.0 * S <= xf <= x + r1 * 0.7
            if touched:
                hit.append((sm, x, base))
        for sm, x, base in hit:
            cs = stack_centers(sm.balls, base)
            for r, cy in zip(sm.balls, cs):
                self.puff(x, cy, 16, 1.6)
                self.spawn(x, cy, math.pi * r * r * 0.8,
                           d * random.uniform(3.0, 6.5) * S, -random.uniform(2.0, 5.0) * S)
            if sm in self.snowmen:
                self.snowmen.remove(sm)
        if hit:
            self.layout_snowmen()

    def step_plow(self, dt):
        pl = self.plow
        s = self.surf.get(pl["key"])
        if s is None or not s.segs:              # поверхность исчезла - уезжаем
            self.end_plow()
            return
        m = MONS[pl["mon"]]
        d, kind, half, S_ = pl["d"], pl["kind"], pl["half"], S
        now = time.perf_counter()
        spd = PLOW_SPEED * PLOW_SPEED_K[kind] * S_ * dt
        pl["x"] += d * spd
        pl["wheel"] += d * spd / (5.0 * S_) * 57.3
        pl["n"] += 1
        xf = pl["x"] + d * pl["fo"] * S_                 # передний край отвала
        lo = min(xf, pl["pxf"]) - 4.0 * S_
        hi = max(xf, pl["pxf"]) + 4.0 * S_
        pl["pxf"] = xf
        removed, keep = 0.0, 0.3 * S_
        for sf in self.plow_clean_list(s, m):            # и панель задач, и самый низ экрана
            if hi >= max(sf.l, m[0]) and lo <= min(sf.r, m[2]):
                i0 = max(0, int((lo - sf.l) / sf.cw))
                i1 = min(sf.n - 1, int((hi - sf.l) / sf.cw) + 1)
                h, cw, got = sf.h, sf.cw, 0.0
                for i in range(i0, i1 + 1):
                    if h[i] > keep:
                        got += (h[i] - keep) * cw
                        h[i] = keep
                if got > 0:
                    sf.dirty = True
                    removed += got
        if removed > 0:
            if kind == 2:                                # снегоочиститель выбрасывает снег из трубы
                for _ in range(min(5, 1 + int(removed / 25.0))):
                    self.puffs.append([pl["x"] + d * 31.0 * S_, s.t - 48.0 * S_,
                                       d * random.uniform(2.5, 5.5) * S_,
                                       -random.uniform(1.5, 4.2) * S_, 0,
                                       random.randint(26, 44), random.uniform(1.8, 3.2) * S_])
            else:
                pl["pile"] = min(1300.0 * S_ * S_, pl["pile"] + removed)
        if removed > 1.0 and kind != 2 and random.random() < 0.7:   # брызги из-под отвала
            self.puffs.append([xf, s.t - 5.0 * S_, d * random.uniform(0.6, 2.2) * S_,
                               -random.uniform(0.7, 2.4) * S_, 0, random.randint(14, 28),
                               random.uniform(1.2, 2.6) * S_])
        if pl["n"] % (7 if kind == 2 else 9) == 0:                   # дымок из трубы
            self.puffs.append([pl["x"] - d * (half - 14.0) * S_, s.t - 26.0 * S_, -d * 0.25 * S_,
                               -0.5 * S_, 0, 30, 2.2 * S_])
        if abs(pl["x"] - pl["ltx"]) >= 8.0 * S_:                     # след колёс
            if m[0] <= pl["x"] <= m[2]:
                self.tracks.append([pl["ltx"], pl["x"], pl["key"], 0.0])
                if len(self.tracks) > 700:
                    del self.tracks[:100]
            pl["ltx"] = pl["x"]
        if self.snowmen:
            self.plow_hit_snowmen(s, xf, d)
        edge = (xf > m[2] - 2) if d > 0 else (xf < m[0] + 2)
        if edge and not pl["dumped"]:                     # у края экрана сбрасывает снег
            pl["dumped"] = True
            if pl["pile"] > 4.0:
                self.spawn(xf, s.t - 8.0 * S_, pl["pile"], d * 3.5 * S_, -3.0 * S_)
            pl["pile"] = 0.0
        if (pl["x"] - (half + 4.0) * S_ > m[2]) if d > 0 else (pl["x"] + (half + 4.0) * S_ < m[0]):
            self.end_plow()

    # ----- метель -----
    def start_blizzard(self):
        now = time.perf_counter()
        self.bl_on = True
        self.bl_end = now + BLIZZARD_LENGTH
        self.bl_dir = random.choice((-1, 1))
        self.toast = ("Метель!", now + 2.0)

    def call_blizzard(self, *_):
        if self.bl_on:
            self.bl_end = 0.0                       # ещё раз - закончить метель
        else:
            self.start_blizzard()

    def step_weather(self, dt, now):
        if self.bl_on and now >= self.bl_end:
            self.bl_on = False
            self.bl_next = now + BLIZZARD_INTERVAL * 60.0 * random.uniform(0.8, 1.2)
        elif (not self.bl_on) and BLIZZARD_AUTO and now >= self.bl_next:
            self.start_blizzard()
        tgt = 1.0 if self.bl_on else 0.0
        self.bl += (tgt - self.bl) * min(1.0, 0.025 * dt)
        if not self.bl_on and self.bl < 0.003:
            self.bl = 0.0
        want = int(FLAKES * (1.0 + 1.8 * self.bl))        # в метель снежинок больше
        fl, n = self.flakes, len(self.flakes)
        if n < want:
            for _ in range(min(6, want - n)):
                fl.append(Flake())
        elif n > want + 3:
            del fl[-min(6, n - want):]

    def step_misc(self, dt):
        if self.decals:
            for dc in self.decals:
                dc["age"] += dt
            self.decals = [dc for dc in self.decals if dc["age"] < dc["life"]]
        if self.tracks:
            for tr in self.tracks:
                tr[3] += dt
            self.tracks = [tr for tr in self.tracks if tr[3] < 1800.0]

    # ----- сосульки -----
    def ice_geom(self, w):
        wd = int(w.r - w.l)
        c = self.ice_cache.get(w.hwnd)
        if c is not None and c[0] == wd:
            return c[1]
        seed = whash(w.hwnd)
        out, x, k = [], 12.0 * S, 0
        while x < wd - 12.0 * S:
            hh = whash(seed + k * 7919)
            L0 = (5 + hh % 17) * S
            if hh % 5 == 0:
                L0 *= 1.5
            out.append((x, L0, ((hh >> 8) % 628) / 100.0))
            x += (11 + (hh >> 4) % 13) * S
            k += 1
        self.ice_cache[w.hwnd] = (wd, out)
        return out

    def update_ice(self, dt):
        ice = self.ice
        for w in self.wins:
            if w.kind != "win":
                continue
            g = ice.get(w.hwnd, 0.15)
            g = min(1.0, g + dt / 3600.0 * (1.0 + 2.0 * self.bl))      # за минуту вырастают
            if g > 0.25 and math.hypot(w.dx, w.dy) > 15.0 * S:         # окно дёрнули - упали
                self.break_icicles(w, g)
                g = 0.1
            ice[w.hwnd] = g
        if self.t % 60 == 0:
            for k in [k for k in ice if k not in self.by_hwnd]:
                del ice[k]
                self.ice_cache.pop(k, None)

    def break_icicles(self, w, g):
        geom = [it for it in self.ice_geom(w) if it[1] * g > 5.0 * S]
        random.shuffle(geom)
        for off, L0, _ph in geom[:8]:
            if len(self.shards) < 40:
                self.shards.append([w.l + off, w.b + 2.0 * S, random.uniform(-0.6, 0.6) * S,
                                    0.5 * S, L0 * g])

    def step_shards(self, dt):
        if not self.shards:
            return
        keep, lands, rects = [], self.lands, self.rects
        for sh in self.shards:
            x, y, vx, vy, L = sh
            py = y
            vy = min(16.0 * S, vy + 0.4 * S * dt)
            x += vx * dt
            y += vy * dt
            if y > VH + 20:
                continue
            hit = False
            for lt, ll, lr, s in lands:
                if py <= lt <= y and ll <= x <= lr and s.vis(x):
                    s.add(x, 5.0 * S * S, 1)
                    self.puff(x, lt, 5, 0.7)
                    hit = True
                    break
            if hit:
                continue
            inside = False
            for l, tp, r, b in rects:
                if l <= x <= r and tp <= y <= b:
                    inside = True
                    break
            if inside:
                self.puff(x, y, 4, 0.6)
                continue
            sh[0], sh[1], sh[2], sh[3] = x, y, vx, vy
            keep.append(sh)
        self.shards = keep

    # ----- следы курсора в сугробах -----
    def carve_trails(self):
        cx, cy, cvx, cvy = self.cur
        sp = math.hypot(cvx, cvy)
        if sp < 0.5 * S or sp >= SWEEP_SPEED * S or self.build or self.throw:
            return
        for s in self.surfs:
            if cx < s.l or cx > s.r or not s.vis(cx):
                continue
            lvl = s.t - cy                            # на какой высоте над поверхностью курсор
            if lvl < 0.0 or lvl > s.maxh + 4 * S:
                continue
            i = int(round((cx - s.l) / s.cw))
            for j in (-1, 0, 1):
                k = i + j
                if 0 <= k < s.n and s.h[k] > lvl + 0.8 * S:
                    s.h[k] = max(0.3 * S, lvl + (s.h[k] - lvl) * 0.5)
                    s.dirty = True
            if random.random() < 0.25:
                self.puffs.append([cx, cy, random.uniform(-0.4, 0.4) * S, -random.uniform(0.2, 0.7) * S,
                                   0, 14, 1.2 * S])

    # ----- снежки -----
    def throw_press(self, ev):
        pos = ev.position()
        tx, ty = pos.x(), pos.y()
        if ev.button() == Qt.MouseButton.RightButton:
            self.set_throw(False)
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        m = MONS[0] if MONS else (0, 0, VW, VH)
        for mm in MONS:
            if mm[0] <= tx < mm[2] and mm[1] <= ty < mm[3]:
                m = mm
                break
        cxm = (m[0] + m[2]) / 2.0
        ox = cxm + (tx - cxm) * 0.25 + random.uniform(-20, 20) * S
        oy = m[3] + 12 * S
        T, g = 26.0, 0.32 * S
        self.balls.append({"x": ox, "y": oy, "vx": (tx - ox) / T, "vy": (ty - oy) / T - 0.5 * g * T,
                           "g": g, "age": 0.0, "T": T, "tx": tx, "ty": ty})
        if len(self.balls) > 12:
            del self.balls[0]

    def step_balls(self, dt):
        keep = []
        for b in self.balls:
            b["age"] += dt
            b["x"] += b["vx"] * dt
            b["y"] += b["vy"] * dt
            b["vy"] += b["g"] * dt
            if random.random() < 0.6:
                self.puffs.append([b["x"], b["y"], 0.0, 0.0, 0, 9, 1.4 * S])
            if b["age"] >= b["T"]:
                self.ball_impact(b["tx"], b["ty"], b["vx"])
            else:
                keep.append(b)
        self.balls = keep

    def ball_impact(self, x, y, vx0):
        for sm, sx, base, vis in self.sm_layout:           # снеговик?
            if not vis:
                continue
            cs = stack_centers(sm.balls, base)
            for idx in range(len(sm.balls) - 1, -1, -1):
                if math.hypot(x - sx, y - cs[idx]) <= sm.balls[idx] + 4 * S:
                    sign = 1.0 if sx > x else -1.0
                    for rr, cy in zip(sm.balls[idx:], cs[idx:]):
                        self.puff(sx, cy, 14, 1.4)
                        self.spawn(sx, cy, math.pi * rr * rr * 0.8, sign * random.uniform(2.0, 5.0) * S,
                                   -random.uniform(2.0, 5.0) * S)
                    del sm.balls[idx:]
                    if not sm.balls and sm in self.snowmen:
                        self.snowmen.remove(sm)
                    self.layout_snowmen()
                    return
        for w in self.wins:                                 # окно?
            if w.kind != "full" and w.l <= x <= w.r and w.t <= y <= w.b:
                self.decals.append({"hwnd": w.hwnd, "dx": x - w.l, "dy": y - w.t,
                                    "r": random.uniform(10, 16) * S, "age": 0.0, "life": 700.0})
                if len(self.decals) > 40:
                    del self.decals[0]
                self.puff(x, y, 10, 1.0)
                return
        self.puff(x, y, 10, 1.0)                            # мимо - снег падает вниз
        self.spawn(x, y, 70.0 * S * S, vx0 * 0.3, -1.0 * S)

    def ask_name(self, sm):
        """Спросить имя снеговика. Пока открыт диалог, оверлей пропускает клики насквозь."""
        self.naming = True
        self.set_click_through(True)
        try:
            plat_activate()
            dlg = QInputDialog(None, Qt.WindowType.WindowStaysOnTopHint)
            dlg.setWindowTitle("Имя снеговика")
            dlg.setLabelText("Как зовут снеговика?")
            dlg.setTextValue(sm.name)
            ok = dlg.exec() == 1
            text = dlg.textValue()
        finally:
            self.naming = False
            self.set_click_through(not (self.build or self.throw))
        if ok:
            sm.name = text.strip()[:18]

    # ----- сохранение и восстановление -----
    def mon_index(self, cx):
        for i, m in enumerate(MONS):
            if m[0] <= cx < m[2]:
                return i
        return 0

    def save_state(self):
        self.state_saved_at = time.perf_counter()
        if not SAVE_STATE:
            return
        data = {"v": 1, "snowmen": [], "drifts": {}}
        for sm in self.snowmen:
            if sm.anchor == 0:
                kind, x = "floor", sm.dx
            else:
                w = self.by_hwnd.get(sm.anchor)
                if w is None or w.kind != "task":
                    continue                              # снеговики на окнах не сохраняем
                kind, x = "task", w.l + sm.dx
            data["snowmen"].append({"kind": kind, "x": round(float(x), 1),
                                    "balls": [round(b, 1) for b in sm.balls],
                                    "seed": sm.seed, "name": sm.name})
        for key, s in self.surf.items():
            if s.kind == "floor":
                name = "f%d" % key[1]
            elif s.kind == "task":
                name = "t%d" % self.mon_index((s.l + s.r) / 2.0)
            else:
                continue
            if max(s.h) > 0.6:
                data["drifts"][name] = [round(v, 1) for v in s.h]
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, STATE_FILE)
        except Exception:
            pass

    def load_state(self):
        self.pending_t0 = time.perf_counter()
        if not SAVE_STATE:
            return
        try:
            with open(STATE_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
            self.saved_drifts = dict(data.get("drifts", {}))
            self.pending_sm = [d for d in data.get("snowmen", []) if isinstance(d, dict)]
        except Exception:
            pass

    def restore_drift(self, s):
        if not self.saved_drifts:
            return
        if s.kind == "floor":
            name = "f%d" % s.key[1]
        elif s.kind == "task":
            name = "t%d" % self.mon_index((s.l + s.r) / 2.0)
        else:
            return
        arr = self.saved_drifts.pop(name, None)
        if arr:
            n = min(len(arr), s.n)
            s.h[:n] = [min(float(v), s.maxh) for v in arr[:n]]
            s.dirty = True

    def process_pending(self, now):
        rest = []
        for it in self.pending_sm:
            try:
                balls = [float(b) for b in it.get("balls", [])][:3]
                if not balls:
                    continue
                x = float(it.get("x", 0.0))
                if it.get("kind") == "floor":
                    anchor, dx = 0, x
                else:
                    w = next((w for w in self.wins if w.kind == "task" and w.l <= x <= w.r), None)
                    if w is None:
                        if now - self.pending_t0 > 8.0:
                            anchor, dx = 0, x
                        else:
                            rest.append(it)
                            continue
                    else:
                        anchor, dx = w.hwnd, x - w.l
                sm = Snowman(anchor, dx, balls[0], x, VH)
                sm.balls = balls
                sm.seed = int(it.get("seed", sm.seed)) & 0xFFFFFFFF
                sm.name = str(it.get("name", ""))[:18]
                self.snowmen.append(sm)
            except Exception:
                continue
        self.pending_sm = rest
        self.layout_snowmen()

    # ----- экономия ресурсов и настройки -----
    def update_eco(self):
        fps = FPS
        if ECO:
            if on_battery():
                fps = min(fps, 30)
            if idle_seconds() > 120.0:
                fps = min(fps, 20)
        ms = max(5, int(1000 / fps))
        if ms != self.frame_ms:
            self.frame_ms = ms
            if not self.hidden:
                self.timer.setInterval(ms)

    def apply_setting(self, key):
        now = time.perf_counter()
        if key == "SYNC_LEAD_MS":
            self.lead_ms = float(SYNC_LEAD_MS)
        elif key in ("FPS", "ECO"):
            self.update_eco()
        elif key == "PLOW_INTERVAL" and self.plow is None:
            self.plow_next = min(self.plow_next, now + PLOW_INTERVAL)
        elif key == "BLIZZARD_INTERVAL" and not self.bl_on:
            self.bl_next = min(self.bl_next, now + BLIZZARD_INTERVAL * 60.0)

    def apply_all(self):
        for item in SPEC:
            self.apply_setting(item[1])

    def schedule_save(self):
        if self._save_pending:
            return
        self._save_pending = True
        QTimer.singleShot(600, self._do_save)

    def _do_save(self):
        self._save_pending = False
        save_settings()

    def open_panel(self, *_):
        if self.panel is None:
            self.panel = SettingsPanel(self)
        self.panel.refresh()
        plat_activate()
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    # ----- мышь (работает только в режиме лепки) -----
    def mousePressEvent(self, ev):
        if self.throw:
            self.throw_press(ev)
            return
        if not self.build:
            return
        pos = ev.position()
        if ev.button() == Qt.MouseButton.MiddleButton:         # средняя кнопка - дать имя
            for sm, rc in reversed(self.sm_rects):
                if rc.contains(pos):
                    self.ask_name(sm)
                    return
            return
        if ev.button() == Qt.MouseButton.LeftButton:
            self.hold = {"x": pos.x(), "y": pos.y(), "r": 8.0 * S}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif ev.button() == Qt.MouseButton.RightButton:
            for sm, rc in reversed(self.sm_rects):
                if rc.contains(pos):
                    if sm in self.snowmen:
                        self.snowmen.remove(sm)
                    self.puff(pos.x(), pos.y(), 16, 1.2)
                    self.layout_snowmen()
                    return
            self.set_build(False)

    def mouseMoveEvent(self, ev):
        h = self.hold
        if h is None:
            return
        pos = ev.position()
        moved = math.hypot(pos.x() - h["x"], pos.y() - h["y"])
        h["x"], h["y"] = pos.x(), pos.y()
        h["r"] = min(MAX_BALL * S, h["r"] + moved * 0.03 * S)
        if moved > 4 * S:
            self.puff(h["x"], h["y"] + h["r"] * 0.8, 1, 0.5)

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton or self.hold is None:
            return
        h, self.hold = self.hold, None
        self.setCursor(Qt.CursorShape.CrossCursor)
        x, y, r = h["x"], h["y"], max(8.0 * S, h["r"])
        best = None
        for sm, sx, base, vis in self.sm_layout:
            if vis and len(sm.balls) < 3 and y < base:
                d = abs(x - sx)
                if d <= sm.balls[-1] + r and (best is None or d < best[0]):
                    best = (d, sm)
        if best is not None:
            sm = best[1]
            r = max(7.0 * S, min(r, sm.balls[-1] * 0.85))
            self.drops.append({"kind": "stack", "sm": sm, "x": x, "y": y, "r": r, "vy": 0.0})
        else:
            anchor, _ys, dx = self.locate(x, y)
            self.drops.append({"kind": "new", "anchor": anchor, "dx": dx,
                               "x": x, "y": y, "r": r, "vy": 0.0})

    # ----- падающие шары -----
    def drop_target(self, d):
        if d["kind"] == "stack":
            for sm, sx, base, vis in self.sm_layout:
                if sm is d["sm"]:
                    if not vis or len(sm.balls) >= 3:
                        return None
                    cy = stack_centers(sm.balls, base)[-1]
                    return sx, cy - 0.82 * (sm.balls[-1] + d["r"])
            return None
        pos = self.anchor_pos(d["anchor"], d["dx"])
        if pos is None:
            return None
        return pos[0], pos[1] - d["r"]

    def step_drops(self, dt):
        k = 1.0 - 0.65 ** dt
        for d in self.drops[:]:
            tg = self.drop_target(d)
            if tg is None:                       # цель пропала - шар рассыпается
                self.puff(d["x"], d["y"], 14, 1.2)
                self.drops.remove(d)
                continue
            tx, ty = tg
            d["x"] += (tx - d["x"]) * k
            if d["y"] < ty:
                d["vy"] += 1.1 * S * dt
                d["y"] = min(ty, d["y"] + d["vy"] * dt)
            else:
                d["y"] += (ty - d["y"]) * k
            if abs(d["x"] - tx) < 1.5 and abs(d["y"] - ty) < 1.5:
                self.land_ball(d, tx, ty)
                self.drops.remove(d)

    def land_ball(self, d, tx, ty):
        if d["kind"] == "stack":
            sm = d["sm"]
            sm.balls.append(d["r"])
            done = len(sm.balls) >= 3
        else:
            pos = self.anchor_pos(d["anchor"], d["dx"]) or (tx, ty + d["r"])
            sm = Snowman(d["anchor"], d["dx"], d["r"], pos[0], pos[1])
            self.snowmen.append(sm)
            done = False
        self.puff(tx, ty + d["r"], 22 if done else 14, 1.4 if done else 1.0)
        self.layout_snowmen()

    def puff(self, x, y, n, power):
        for _ in range(n):
            a = random.uniform(math.pi * 1.05, math.pi * 1.95)
            sp = random.uniform(1.2, 3.8) * power * S
            self.puffs.append([x, y, math.cos(a) * sp, math.sin(a) * sp, 0,
                               random.randint(22, 40), random.uniform(1.4, 3.0) * S])

    # ----- главный цикл -----
    def poll_keys(self):
        if IS_WIN:
            keys = (("q", 0x51, self.quit), ("p", 0x50, self.toggle_pause),
                    ("y", 0x59, self.toggle_build), ("c", 0x43, self.clear_drifts),
                    ("f1", 0x70, self.open_panel), ("f2", 0x71, self.call_plow),
                    ("f3", 0x72, self.call_blizzard), ("f10", 0x79, self.toggle_throw),
                    ("f7", 0x76, lambda: self.adj_lead(4)),
                    ("f8", 0x77, lambda: self.adj_lead(-4)))
        else:                       # на Mac F-клавиши обычно работают через Fn, поэтому - буквы
            keys = (("q", 0x51, self.quit), ("p", 0x50, self.toggle_pause),
                    ("y", 0x59, self.toggle_build), ("c", 0x43, self.clear_drifts),
                    ("s", 0x53, self.open_panel), ("b", 0x42, self.call_plow),
                    ("w", 0x57, self.call_blizzard), ("t", 0x54, self.toggle_throw),
                    ("]", 0xDD, lambda: self.adj_lead(4)),
                    ("[", 0xDB, lambda: self.adj_lead(-4)))
        cs = key_down(0x11) and key_down(0x10)
        for name, vk, action in keys:
            down = cs and key_down(vk)
            if down and not self.lock.get(name):
                self.lock[name] = True
                action()
            elif not down:
                self.lock[name] = False
        esc = key_down(0x1B)
        if esc and (self.build or self.throw) and not self.lock.get("esc"):
            if self.build:
                self.set_build(False)
            else:
                self.set_throw(False)
        self.lock["esc"] = esc

    def tick(self):
        try:
            self.tick_inner()
        except Exception:
            if not self.err_logged:              # ошибку пишем в файл, но снег продолжает идти
                self.err_logged = True
                try:
                    with open(os.path.join(DATA_DIR, "snow_error.log"), "w", encoding="utf-8") as fh:
                        fh.write(traceback.format_exc())
                except Exception:
                    pass

    def tick_inner(self):
        now = time.perf_counter()
        self.beat = now
        # время считаем по часам, а не по числу кадров - так движение ровное,
        # даже если какой-то кадр задержался
        dt = max(0.25, min(4.0, (now - self.last) * 60.0))
        self.last = now
        self.t += 1
        self.tf += dt
        self.poll_keys()
        if self.t % 120 == 1:
            self.update_eco()

        allblank = self.fs_flag or (bool(MONS) and len(self.blank) >= len(MONS))
        if allblank:                             # полный экран - сразу прячем оверлей целиком
            self.show_votes = 0
            if not self.hidden:
                self.hidden = True
                self.hide()
                self.timer.setInterval(100)      # пока спрятан - почти ничего не делаем
        elif self.hidden:
            self.show_votes += 1                 # возвращаем, только когда полный экран точно закончился
            if self.show_votes >= 4:
                self.hidden = False
                self.show_votes = 0
                self.show()
                self.hwnd = int(self.winId())
                self.apply_exstyle()
                self.raise_topmost()
                self.timer.setInterval(self.frame_ms)
                self.last = time.perf_counter()
        if self.hidden:
            try:
                self.update_windows(now)
            except Exception:
                pass
            return
        if self.t % 120 == 0 and not self.naming:
            self.raise_topmost()

        pos = QCursor.pos()
        cx, cy = pos.x() - VX, pos.y() - VY
        ox, oy, ovx, ovy = self.cur
        self.cur = (cx, cy, 0.6 * ovx + 0.4 * (cx - ox) / dt, 0.6 * ovy + 0.4 * (cy - oy) / dt)
        if self.pending_sm:
            self.process_pending(now)
        if SAVE_STATE and now - self.state_saved_at > 60.0:
            self.save_state()

        # --- физика (по положению окон с прошлого кадра - это незаметно) ---
        if not self.paused:
            self.step_weather(dt, now)
            self.step_flakes(dt)
            self.step_chunks(dt)
            if SWEEP:
                self.sweep(dt)
            if TRAILS:
                self.carve_trails()
            if ICICLES or self.ice:
                self.update_ice(dt)
            self.step_shards(dt)
            if self.balls:
                self.step_balls(dt)
            busy = self.build or self.throw
            if PLOW:
                if self.plow is not None:
                    self.step_plow(dt)
                elif now >= self.plow_next and not busy:
                    if not self.start_plow():
                        self.plow_next = now + 10.0      # нет подходящего края - попробуем позже
            self.step_misc(dt)
        if self.t % 2 == 0:
            for s in self.surf.values():
                if s.dirty:
                    s.relax(self.spill)
        for pf in self.puffs[:]:
            pf[0] += pf[2] * dt
            pf[1] += pf[3] * dt
            pf[3] += 0.12 * S * dt
            pf[2] *= 0.97 ** dt
            pf[4] += dt
            if pf[4] >= pf[5]:
                self.puffs.remove(pf)
        if self.hold is not None:
            self.hold["r"] = min(MAX_BALL * S, self.hold["r"] + 0.09 * S * dt)
        if self.drops:
            self.step_drops(dt)

        # --- положение окон читаем В САМОМ КОНЦЕ и сразу рисуем кадр:
        #     так между чтением положения и отрисовкой проходит минимум времени ---
        try:
            self.update_windows(time.perf_counter())
        except Exception:
            pass
        self.update_surfaces(dt)
        self.repaint()

    def step_flakes(self, dt):
        tf = self.tf
        wind = (math.sin(tf * 0.004) + 0.5 * math.sin(tf * 0.011 + 1.3)) * WIND_STRENGTH * S
        bl = self.bl
        if bl > 0.001:                      # метель: ветер сильнее и дует в одну сторону
            wind = wind * (1.0 + 1.5 * bl) + self.bl_dir * 3.4 * bl * S
        self.wind = wind
        fall = FALL_SPEED * (1.0 + 0.5 * bl)
        cx, cy, cvx, cvy = self.cur
        R = MOUSE_RADIUS * S
        R2 = R * R
        force = MOUSE_FORCE
        rects, lands = self.rects, self.lands
        accum = ACCUMULATE * (1.0 + 2.0 * bl)
        fr = 0.93 ** dt
        sin, sqrt = math.sin, math.sqrt
        for f in self.flakes:
            x, y = f.x, f.y
            py = y
            vx, vy = f.vx * fr, f.vy * fr
            if force:
                dx, dy = x - cx, y - cy
                d2 = dx * dx + dy * dy
                if d2 < R2:
                    d = sqrt(d2) or 1.0
                    k = (1.0 - d / R) ** 2 * force * dt
                    vx += dx / d * k * 1.4 * S + cvx * k * 0.30
                    vy += dy / d * k * 1.4 * S + cvy * k * 0.30
                    lim = 14.0 * S
                    vx = max(-lim, min(lim, vx))
                    vy = max(-lim, min(lim, vy))
            f.vx, f.vy = vx, vy
            x += (sin(tf * f.sp + f.ph) * f.amp + wind * f.wk + vx) * dt
            y += (f.speed * fall + vy) * dt
            f.ang += f.spin * dt
            if y > VH + 10 or y < -120 * S:
                f.reset()
                continue
            if x > VW + 10:
                x = -10.0
            elif x < -10:
                x = VW + 10.0
            if accum and lands and y > py:
                hit = False
                for lt, ll, lr, s in lands:
                    if py <= lt <= y and ll <= x <= lr and s.vis(x):
                        s.add(x, 8.0 * f.r * S * accum, 2)
                        hit = True
                        break
                if hit:
                    f.reset()                   # снежинка легла в сугроб
                    continue
            if rects:
                for l, tp, r, b in rects:
                    if l <= x <= r and tp <= y <= b:
                        f.reset()               # упала на окно
                        break
                else:
                    f.x, f.y = x, y
                continue
            f.x, f.y = x, y

    # ----- отрисовка кадра -----
    def tree_pos(self):
        """Где стоит ёлка: (x, y поверхности) или None."""
        if not TREE or not MONS:
            return None
        s = self.plow_surface(0)
        if s is None:
            return None
        m = MONS[0]
        x = m[0] + (m[2] - m[0]) * TREE_POS / 100.0
        if not s.vis(x):
            return None
        return x, s.t

    def draw_tracks(self, p):
        """Следы колёс снегоуборщика на очищенном краю - потом их заметает."""
        if not self.tracks:
            return
        buckets = [QPainterPath(), QPainterPath(), QPainterPath()]
        for x0, x1, key, age in self.tracks:
            s = self.surf.get(key)
            if s is None or not s.segs:
                continue
            bp = buckets[0 if age < 600 else 1 if age < 1200 else 2]
            bp.moveTo(x0, s.t - 0.8 * S)
            bp.lineTo(x1, s.t - 0.8 * S)
        p.setBrush(NOBRUSH)
        for bp, a in zip(buckets, (90, 55, 25)):
            p.setPen(QPen(QColor(70, 90, 130, a), max(1.5, 2.2 * S), Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.FlatCap))
            p.drawPath(bp)

    def draw_frosts(self, p):
        """Иней по краям окон (только на видимых частях окна)."""
        wins, n = self.wins, 0
        for i, w in enumerate(wins):
            if w.kind != "win" or w.r - w.l < 120 * S:
                continue
            reg = QRegion(int(w.l), int(w.t), int(w.r - w.l), int(w.b - w.t))
            for o in wins[:i]:
                reg = reg.subtracted(QRegion(int(o.l), int(o.t), int(o.r - o.l), int(o.b - o.t)))
            if reg.isEmpty():
                continue
            p.save()
            p.setClipRegion(reg, Qt.ClipOperation.IntersectClip)
            fw, h = 10.0 * S, w.b - w.t
            g = QLinearGradient(w.l, 0, w.l + fw, 0)
            g.setColorAt(0.0, QColor(235, 245, 255, 80))
            g.setColorAt(1.0, QColor(235, 245, 255, 0))
            p.fillRect(QRectF(w.l, w.t, fw, h), QBrush(g))
            g = QLinearGradient(w.r, 0, w.r - fw, 0)
            g.setColorAt(0.0, QColor(235, 245, 255, 80))
            g.setColorAt(1.0, QColor(235, 245, 255, 0))
            p.fillRect(QRectF(w.r - fw, w.t, fw, h), QBrush(g))
            g = QLinearGradient(0, w.b, 0, w.b - fw)
            g.setColorAt(0.0, QColor(235, 245, 255, 80))
            g.setColorAt(1.0, QColor(235, 245, 255, 0))
            p.fillRect(QRectF(w.l, w.b - fw, w.r - w.l, fw), QBrush(g))
            spr, sz = frost_sprite()
            p.setOpacity(0.85)
            p.drawImage(QPointF(w.l, w.b - sz), spr)
            p.save()
            p.translate(w.r, 0)
            p.scale(-1.0, 1.0)
            p.drawImage(QPointF(0, w.b - sz), spr)
            p.restore()
            p.setOpacity(1.0)
            p.restore()
            n += 1
            if n >= 8:
                break

    def draw_icicles(self, p, t):
        p.setOpacity(0.92)
        for w in self.wins:
            segs = self.bsegs.get(w.hwnd)
            if not segs:
                continue
            g = self.ice.get(w.hwnd, 0.15)
            for off, L0, ph in self.ice_geom(w):
                x, L = w.l + off, L0 * g
                if L < 3.0 * S:
                    continue
                for a, b in segs:
                    if a <= x <= b:
                        break
                else:
                    continue
                spr, hw = icicle_sprite(L)
                p.drawImage(QPointF(x - hw, w.b - 1.0 * S), spr)
                if math.sin(t * 0.045 + ph * 3.0) > 0.985:        # блестит
                    s2, h2 = soft_sprite(2.4 * S)
                    p.setOpacity(1.0)
                    p.drawImage(QPointF(x - h2, w.b + L - h2), s2)
                    p.setOpacity(0.92)
        for x, y, _vx, _vy, L in self.shards:
            spr, hw = icicle_sprite(L)
            p.drawImage(QPointF(x - hw, y), spr)
        p.setOpacity(1.0)

    def draw_decals(self, p):
        """Снежные шлепки от снежков - прилипают к окну и едут вместе с ним."""
        for dc in self.decals:
            w = self.by_hwnd.get(dc["hwnd"])
            if w is None:
                continue
            fade = min(1.0, (dc["life"] - dc["age"]) / 90.0)
            px, py = w.l + dc["dx"], w.t + dc["dy"]
            covered = False
            for o in self.wins:
                if o is w:
                    break
                if o.l <= px <= o.r and o.t <= py <= o.b:
                    covered = True
                    break
            if covered or fade <= 0:
                continue
            spr, half = splat_sprite(dc["r"])
            p.setOpacity(0.95 * fade)
            p.drawImage(QPointF(px - half, py - half), spr)
        p.setOpacity(1.0)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHints(RH)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), QColor(0, 0, 0, 26) if (self.build or self.throw) else QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.hidden:
            p.end()
            return
        if self.blank:                      # на полноэкранном мониторе ничего не рисуем
            reg = QRegion(0, 0, VW, VH)
            for m in self.blank:
                reg = reg.subtracted(QRegion(int(m[0]), int(m[1]),
                                             int(m[2] - m[0]), int(m[3] - m[1])))
            p.setClipRegion(reg)
        t = self.tf
        bl = self.bl
        if bl > 0.02 and not (self.build or self.throw):          # метель: лёгкая белая дымка
            p.fillRect(self.rect(), QColor(222, 233, 255, int(36 * bl)))
        sway = (0.8 + 4.5 * bl + min(3.0, abs(self.wind)) * 0.5) * S
        self.draw_tracks(p)
        bulbs = []
        for s in self.surfs:
            for a, b in s.segs:
                draw_drift(p, s, a, b)
                if GARLANDS and s.kind == "win" and s.r - s.l >= 160 * S:
                    draw_garland(p, s, a, b, s.seed, bulbs, t, sway)
        if FROST:
            self.draw_frosts(p)
        if ICICLES:
            self.draw_icicles(p, t)
        tp = self.tree_pos()
        if tp is not None:
            draw_tree(p, tp[0], tp[1] - 1.0 * S, t)
        for sm, x, base, vis in self.sm_layout:
            if vis:
                draw_snowman(p, x, base, sm.balls, sm.seed, t, self.wind, sm.name)
        self.draw_decals(p)
        if self.plow is not None:
            ps = self.surf.get(self.plow["key"])
            if ps is not None:
                draw_vehicle(p, self.plow, ps.t + 1.0 * S, t)
        # лампочки гирлянд (плавно мерцают) и их цветной отсвет на сугробах
        for bx, by, ci, ph, gh in bulbs:
            fl = 0.62 + 0.38 * math.sin(t * 0.07 + ph)
            if gh > 2.0 * S:
                gs, gh2 = glow_sprite(ci, 11.0 * S)
                p.setOpacity(0.32 * fl)
                p.drawImage(QPointF(bx - gh2, by - 5.0 * S - gh * 0.6 - gh2), gs)
            spr, half = bulb_sprite(ci)
            p.setOpacity(fl)
            p.drawImage(QPointF(bx - half, by - half), spr)
        # облачка снега
        for x, y, _vx, _vy, age, life, r in self.puffs:
            spr, half = soft_sprite(r)
            p.setOpacity(max(0.0, 1.0 - age / float(life)))
            p.drawImage(QPointF(x - half, y - half), spr)
        # комья снега, летящие с сугробов
        p.setOpacity(0.95)
        for x, y, _vx, _vy, vol in self.chunks:
            spr, half = soft_sprite(max(1.4 * S, min(7.0 * S, 0.55 * math.sqrt(vol))))
            p.drawImage(QPointF(x - half, y - half), spr)
        # снежинки
        for f in self.flakes:
            p.setOpacity(f.op)
            if f.crystal:
                p.save()
                p.translate(f.x, f.y)
                p.rotate(f.ang)
                p.drawImage(QPointF(-f.half, -f.half), f.spr)
                p.restore()
            else:
                p.drawImage(QPointF(f.x - f.half, f.y - f.half), f.spr)
        p.setOpacity(1.0)
        # падающие и лепимый шары, летящие снежки
        for d in self.drops:
            draw_snowball(p, d["x"], d["y"], d["r"])
        if self.hold is not None:
            h = self.hold
            wob = math.sin(t * 0.5) * 0.04
            draw_snowball(p, h["x"], h["y"], h["r"] * (1 + wob))
        for b in self.balls:
            draw_snowball(p, b["x"], b["y"], 9.0 * S * (1.0 - 0.45 * min(1.0, b["age"] / b["T"])))
        if self.build or self.throw:
            self.draw_banner(p)
        if self.toast is not None:
            if time.perf_counter() < self.toast[1]:
                self.draw_toast(p, self.toast[0])
            else:
                self.toast = None
        p.end()

    def draw_toast(self, p, text):
        w, h = 480 * S, 38 * S
        rc = QRectF(self.banner_cx - w / 2, self.banner_y, w, h)
        p.setPen(NOPEN)
        p.setBrush(QBrush(QColor(15, 30, 55, 215)))
        p.drawRoundedRect(rc, 12 * S, 12 * S)
        f = QFont("Segoe UI")
        f.setPixelSize(int(15 * S))
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(rc, Qt.AlignmentFlag.AlignCenter, text)

    def draw_banner(self, p):
        if self.throw:
            lines = ["Режим снежков",
                     "Левая кнопка - снежок летит в эту точку. Попадёшь в снеговика - собьёшь его, в окно - прилипнет.",
                     "Esc или правая кнопка - выйти."]
        else:
            lines = ["Режим лепки снеговика",
                     "Зажми левую кнопку и води мышкой - снежок растёт. Отпусти над окном или снеговиком.",
                     "Средняя кнопка по снеговику - дать имя, правая - убрать.  Esc - выйти."]
        w, h = 760 * S, 78 * S
        rc = QRectF(self.banner_cx - w / 2, self.banner_y, w, h)
        p.setPen(NOPEN)
        p.setBrush(QBrush(QColor(15, 30, 55, 205)))
        p.drawRoundedRect(rc, 14 * S, 14 * S)
        f = QFont("Segoe UI")
        f.setPixelSize(int(17 * S))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(rc.x(), rc.y() + 6 * S, w, 26 * S), Qt.AlignmentFlag.AlignCenter, lines[0])
        f.setBold(False)
        f.setPixelSize(int(13 * S))
        p.setFont(f)
        p.setPen(QColor("#CFE0F5"))
        p.drawText(QRectF(rc.x(), rc.y() + 32 * S, w, 20 * S), Qt.AlignmentFlag.AlignCenter, lines[1])
        p.drawText(QRectF(rc.x(), rc.y() + 51 * S, w, 20 * S), Qt.AlignmentFlag.AlignCenter, lines[2])


# ---------------------------------------------------------------------------
#  Окно настроек
# ---------------------------------------------------------------------------
def panel_css():
    fs, pd, hd = int(13 * S), int(7 * S), int(16 * S)
    return """
        QWidget { background:#17212f; color:#e9f1fb; font-family:'Segoe UI'; font-size:%dpx; }
        QTabWidget::pane { border:1px solid #2b3a50; border-radius:6px; }
        QTabBar::tab { background:#1f2d42; padding:%dpx %dpx; margin-right:2px;
                       border-top-left-radius:6px; border-top-right-radius:6px; }
        QTabBar::tab:selected { background:#2f4b73; }
        QScrollArea { border:none; }
        QSlider::groove:horizontal { height:%dpx; background:#2b3a50; border-radius:3px; }
        QSlider::sub-page:horizontal { background:#4aa3ff; border-radius:3px; }
        QSlider::handle:horizontal { width:%dpx; margin:-%dpx 0; background:#e9f1fb; border-radius:%dpx; }
        QPushButton { background:#2f4b73; border:none; border-radius:6px; padding:%dpx %dpx; }
        QPushButton:hover { background:#3d6199; }
        QCheckBox::indicator { width:%dpx; height:%dpx; }
        QLabel#title { font-size:%dpx; font-weight:bold; }
    """ % (fs, pd, int(12 * S), int(5 * S), hd, int(6 * S), hd // 2, pd, int(10 * S), hd, hd,
           int(18 * S))


class SettingsPanel(QWidget):
    TABS = ("Снег", "Погода и гости", "Декор", "Система")

    def __init__(self, ov):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowTitleHint |
                         Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.ov = ov
        self.widgets = {}
        self.setWindowTitle("Снег на рабочем столе - настройки")
        self.setWindowIcon(make_icon())
        self.setStyleSheet(panel_css())
        mg = int(10 * S)
        root = QVBoxLayout(self)
        root.setContentsMargins(mg, mg, mg, mg)
        title = QLabel("Снег на рабочем столе  v" + APP_VERSION)
        title.setObjectName("title")
        root.addWidget(title)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        pages = {}
        for name in self.TABS:
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setSpacing(int(4 * S))
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setFrameShape(QFrame.Shape.NoFrame)
            sc.setWidget(page)
            tabs.addTab(sc, name)
            pages[name] = lay
        for spec in SPEC:
            self._row(pages[spec[0]], spec)
        cb = QCheckBox(AUTOSTART_LABEL)
        cb.setChecked(autostart_get())
        cb.toggled.connect(lambda v: autostart_set(bool(v)))
        pages["Система"].addWidget(cb)
        self.auto_cb = cb
        for lay in pages.values():
            lay.addStretch(1)
        grid = QGridLayout()
        actions = (("Метель", ov.call_blizzard),
                   ("Снегоуборщик", ov.call_plow), ("Снежки", ov.toggle_throw),
                   ("Лепить снеговика", ov.toggle_build), ("Стряхнуть снег", ov.clear_drifts),
                   ("Убрать снеговиков", ov.clear_snowmen), ("Сбросить настройки", self.reset))
        for i, (text, fn) in enumerate(actions):
            b = QPushButton(text)
            b.clicked.connect(fn)
            grid.addWidget(b, i // 2, i % 2)
        root.addLayout(grid)
        self.resize(int(500 * S), int(720 * S))

    def _row(self, lay, spec):
        _tab, key, label, kind, lo, hi, step = spec
        cur = globals()[key]
        if kind == "bool":
            cb = QCheckBox(label)
            cb.setChecked(bool(cur))
            cb.toggled.connect(lambda v, k=key: self.changed(k, bool(v)))
            lay.addWidget(cb)
            self.widgets[key] = ("bool", cb, None, step)
            return
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, int(2 * S), 0, int(2 * S))
        v.setSpacing(int(2 * S))
        top = QHBoxLayout()
        name = QLabel(label)
        val = QLabel(self._fmt(kind, cur))
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(name, 1)
        top.addWidget(val)
        v.addLayout(top)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(int(round(lo / step)), int(round(hi / step)))
        sl.setValue(int(round(cur / step)))
        sl.valueChanged.connect(lambda i, k=key, kd=kind, st=step, vl=val:
                                self.slider_changed(k, kd, st, vl, i))
        v.addWidget(sl)
        lay.addWidget(box)
        self.widgets[key] = ("num", sl, val, step)

    @staticmethod
    def _fmt(kind, v):
        return str(int(v)) if kind == "int" else "%.1f" % v

    def slider_changed(self, key, kind, step, label, i):
        v = i * step
        v = int(round(v)) if kind == "int" else round(v, 3)
        label.setText(self._fmt(kind, v))
        self.changed(key, v)

    def changed(self, key, val):
        globals()[key] = val
        self.ov.apply_setting(key)
        self.ov.schedule_save()

    def refresh(self):
        """Подтянуть значения ползунков из текущих настроек."""
        for spec in SPEC:
            key, kind, step = spec[1], spec[3], spec[6]
            kindw, w, val, _st = self.widgets[key]
            cur = globals()[key]
            w.blockSignals(True)
            if kindw == "bool":
                w.setChecked(bool(cur))
            else:
                w.setValue(int(round(cur / step)))
                val.setText(self._fmt(kind, cur))
            w.blockSignals(False)
        self.auto_cb.blockSignals(True)
        self.auto_cb.setChecked(autostart_get())
        self.auto_cb.blockSignals(False)

    def reset(self, *_):
        for item in SPEC:
            globals()[item[1]] = DEFAULTS[item[1]]
        self.refresh()
        self.ov.apply_all()
        self.ov.schedule_save()


# ---------------------------------------------------------------------------
def main():
    if not single_instance():
        msgbox("Снег уже запущен - ищи значок снежинки " + TRAY_WHERE + ".")
        return 0
    try:                                   # при "жёстком" падении Python запишет причину в файл
        import faulthandler
        global _CRASH_FH
        _CRASH_FH = open(os.path.join(DATA_DIR, "snow_crash.log"), "a")
        faulthandler.enable(_CRASH_FH)
    except Exception:
        pass
    first_run = not load_settings()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    setup(app)
    plat_timer_precision(True)
    plat_app_setup(app)
    ov = Overlay(app)
    ov.load_state()
    ov.start()
    app.aboutToQuit.connect(ov.on_exit)

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(make_icon(), app)
        tray.setToolTip("Снег  (Ctrl+Shift+" + HK["settings"] + " - настройки)")
        menu = QMenu()
        items = (("Настройки   Ctrl+Shift+" + HK["settings"], ov.open_panel),
                 ("Лепить снеговика   Ctrl+Shift+Y", ov.toggle_build),
                 ("Режим снежков   Ctrl+Shift+" + HK["throw"], ov.toggle_throw),
                 ("Метель вкл/выкл   Ctrl+Shift+" + HK["blizzard"], ov.call_blizzard),
                 ("Вызвать снегоуборщик   Ctrl+Shift+" + HK["plow"], ov.call_plow),
                 ("Стряхнуть снег с окон   Ctrl+Shift+C", ov.clear_drifts),
                 ("Убрать всех снеговиков", ov.clear_snowmen),
                 ("Пауза / продолжить   Ctrl+Shift+P", ov.toggle_pause))
        acts = []
        for text, fn in items:
            a = QAction(text, menu)
            a.triggered.connect(fn)
            menu.addAction(a)
            acts.append(a)
        menu.addSeparator()
        a_auto = QAction(AUTOSTART_LABEL, menu)
        a_auto.setCheckable(True)
        a_auto.setChecked(autostart_get())
        a_auto.toggled.connect(lambda v: autostart_set(bool(v)))

        def sync_auto():
            a_auto.blockSignals(True)
            a_auto.setChecked(autostart_get())
            a_auto.blockSignals(False)

        menu.aboutToShow.connect(sync_auto)
        menu.addAction(a_auto)
        menu.addSeparator()
        a_quit = QAction("Выход   Ctrl+Shift+Q", menu)
        a_quit.triggered.connect(ov.quit)
        menu.addAction(a_quit)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: ov.open_panel()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        tray.show()
        ov.tray = tray
        ov._tray_menu = menu          # держим ссылки, чтобы меню не удалилось
        ov._tray_actions = tuple(acts) + (a_auto, a_quit)
        tray.showMessage("Снег запущен",
                         ("Клик по значку - настройки." if IS_WIN else "Значок в строке меню - все команды.")
                         + "\nCtrl+Shift+Y - лепить снеговика, Ctrl+Shift+Q - выход",
                         QSystemTrayIcon.MessageIcon.Information, 6000)
    if first_run:
        QTimer.singleShot(1500, ov.open_panel)       # при первом запуске сразу показываем настройки
    return app.exec()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        try:
            with open(os.path.join(DATA_DIR, "snow_error.log"), "w", encoding="utf-8") as fh:
                fh.write(err)
        except Exception:
            pass
        msgbox("Снег упал с ошибкой. Подробности в файле snow_error.log в папке данных (" + DATA_DIR + ").\n\n"
               + err[-600:], "Снег - ошибка", 0x10)
