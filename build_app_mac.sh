#!/bin/bash
# Собирает SnowDesktop.app (Python на целевом Mac не нужен).  Результат: dist/SnowDesktop.app
set -e
cd "$(dirname "$0")"
python3 -m venv .buildvenv
source .buildvenv/bin/activate
python -m pip install --upgrade pip pyinstaller PySide6 pyobjc-framework-Cocoa pyobjc-framework-Quartz
[ -f snow.png ] || python make_icon.py
ICON=""
if [ -f snow.png ]; then
  rm -rf snow.iconset && mkdir snow.iconset
  for s in 16 32 128 256; do
    sips -z $s $s snow.png --out snow.iconset/icon_${s}x${s}.png >/dev/null
    sips -z $((s*2)) $((s*2)) snow.png --out snow.iconset/icon_${s}x${s}@2x.png >/dev/null
  done
  iconutil -c icns snow.iconset -o snow.icns && ICON="--icon snow.icns"
fi
python -m PyInstaller --windowed --noconfirm --name SnowDesktop $ICON \
  --osx-bundle-identifier com.snowdesktop.overlay snow.pyw
echo
echo "Готово: dist/SnowDesktop.app"
echo "Первый запуск: правая кнопка -> Открыть (приложение не подписано)."
