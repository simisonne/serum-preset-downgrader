#!/usr/bin/env bash
# Builds the Windows download: a portable Python runtime plus the tool, in one
# zip. No installer, nothing to configure.
#
#   ./tools/make_windows_release.sh
#
# Output: dist/SerumPresetDowngrader-<version>-Windows.zip
set -euo pipefail

PY_VERSION=3.12.8
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(grep -m1 "^__version__" serum_preset_downgrader.py | cut -d"'" -f2)"
NAME="SerumPresetDowngrader-${VERSION}-Windows"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Building $NAME"

# --- the portable interpreter -------------------------------------------------
EMBED="python-${PY_VERSION}-embed-amd64.zip"
if [ ! -f "cache/$EMBED" ]; then
    mkdir -p cache
    curl -fsSL -o "cache/$EMBED" \
        "https://www.python.org/ftp/python/${PY_VERSION}/${EMBED}"
fi

# --- the one dependency the tool needs ---------------------------------------
WHEEL_DIR="$WORK/wheels"
mkdir -p "$WHEEL_DIR"
python3 - "$WHEEL_DIR" <<'PY'
import json, sys, urllib.request
target = sys.argv[1]
info = json.load(urllib.request.urlopen('https://pypi.org/pypi/zstandard/json'))
version = info['info']['version']
for build in info['releases'][version]:
    name = build['filename']
    if 'cp312' in name and 'win_amd64' in name and name.endswith('.whl'):
        urllib.request.urlretrieve(build['url'], f'{target}/{name}')
        print(f'  fetched {name}')
        break
else:
    sys.exit('no cp312 win_amd64 wheel found')
PY

# --- lay out the folder the user will unzip ----------------------------------
APP="$WORK/$NAME"
mkdir -p "$APP/runtime" "$APP/downgrader" "$APP/runtime/Lib/site-packages"

unzip -q "cache/$EMBED" -d "$APP/runtime"
unzip -q "$WHEEL_DIR"/*.whl -d "$APP/runtime/Lib/site-packages"

# A ._pth file replaces sys.path wholesale, so it has to name site-packages.
cat > "$APP/runtime/python312._pth" <<'PTH'
python312.zip
.
Lib\site-packages
PTH

cp serum_preset_downgrader.py "$APP/downgrader/"

# --- the double clickable launcher (cmd needs CRLF) --------------------------
python3 - "$APP/Downgrade presets.bat" <<'PY'
import sys
bat = '''@echo off
chcp 65001 >nul
setlocal
set "HERE=%~dp0"
if "%~1"=="" goto usage
set PYTHONIOENCODING=utf-8
"%HERE%runtime\\python.exe" "%HERE%downgrader\\serum_preset_downgrader.py" %*
echo.
pause
exit /b
:usage
echo.
echo   Drag one or more Serum 2 preset files onto this file, or drag a folder.
echo   Fixed copies land in a folder called "Serum 2.0.23 versions".
echo.
pause
exit /b
'''
# ASCII only, no BOM: cmd misreads a byte order mark as part of the first
# command on some Windows builds.
open(sys.argv[1], 'w', encoding='ascii', newline='\r\n').write(bat)
PY

python3 - "$APP/HOW TO USE.txt" <<'PY'
import sys
text = '''SERUM 2 PRESET DOWNGRADER
=========================

Some preset packs are saved by a newer Serum 2 than the one you own, and the
older Serum refuses to open them. This fixes that.

HOW TO USE IT
-------------

1. Unzip this folder somewhere, for example your Desktop.
   Keep the files together. Do not move the .bat file out on its own.

2. Find the presets you want to convert.

3. Drag them onto "Downgrade presets.bat".
   You can drag a single preset, several at once, or a whole folder.

4. A black window opens and prints what it is doing. When it says the
   presets are in "Serum 2.0.23 versions", you are done.

5. Open that folder, and copy what is inside it into your Serum 2 preset
   folder. You can find that folder from Serum itself:
   Menu > Open Serum 2 Presets Folder

6. Back in Serum 2, use  Menu > Rescan Folders on Disk  and the presets
   will be there.

Your original files are never changed. The tool only writes new copies.

WHAT IT CANNOT DO
-----------------

This makes presets made in Serum 2.1.5 work in Serum 2.0.23. That pair is
tested. Other versions may work but are not confirmed.

If a preset uses something the older Serum simply does not have, it will
sound slightly different, but it will still open.

Nothing is uploaded anywhere. There is no internet connection involved and
no account of any kind.

If Windows shows a blue "Windows protected your PC" box, click More info and
then Run anyway. That appears for any file downloaded from the internet that
is not signed with a paid certificate.

MORE DETAIL, AND THE SOURCE CODE
--------------------------------
https://github.com/simisonne/serum-preset-downgrader
'''
open(sys.argv[1], 'w', encoding='utf-8-sig', newline='\r\n').write(text)
PY

# --- zip ---------------------------------------------------------------------
mkdir -p dist
rm -f "dist/$NAME.zip"
( cd "$WORK" && zip -qr "$ROOT/dist/$NAME.zip" "$NAME" )
echo
echo "Wrote dist/$NAME.zip ($(du -h "dist/$NAME.zip" | cut -f1))"
