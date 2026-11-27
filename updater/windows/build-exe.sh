#!/bin/zsh
# Build the Windows installer on this Mac:  release/updater/windows/build-exe.sh  ->  release/windows/OM-MAVA-Updater-Setup-<ver>.exe
# Needs NSIS (brew install makensis) and CHECK VIDEO's Windows Python (packaging/vendor-win.sh there).
# The installer is unsigned: Windows SmartScreen asks "Run anyway" once.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/.." && pwd)"                        # release/updater
VER="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SRC/updater_gui.py")"
VENDOR="${MAVA_QC_VENDOR_WIN:-$HOME/.mava-qc-build/vendor-win}"
[ -f "$VENDOR/python/pythonw.exe" ] || { echo "Thiếu $VENDOR — chạy packaging/vendor-win.sh của CHECK VIDEO trước"; exit 1; }
command -v makensis >/dev/null || { echo "Cần NSIS: brew install makensis"; exit 1; }
OUTDIR="$(cd "$SRC/.." && pwd)/windows"; mkdir -p "$OUTDIR"
OUT="$OUTDIR/OM-MAVA-Updater-Setup-$VER.exe"

WORK="$(mktemp -d)"; STAGE="$WORK/stage"
mkdir -p "$STAGE/app/fonts"
cp "$SRC/update_core.py" "$SRC/updater_gui.py" "$SRC/mark.png" "$STAGE/app/"
cp "$SRC"/fonts/Inter-*.ttf "$SRC/fonts/Inter-LICENSE.txt" "$STAGE/app/fonts/"
TOKEN_SRC="${OM_MAVA_UPDATER_TOKEN_FILE:-$HOME/Library/Application Support/OMMavaUpdater/token}"
if [ -s "$TOKEN_SRC" ]; then cp "$TOKEN_SRC" "$STAGE/app/bundled_token"; echo "Có token đóng kèm"
else echo "warning: không có $TOKEN_SRC — app không kèm token, editor phải tự nhập trong Cài đặt"; fi
rsync -a --exclude '._*' --exclude '__pycache__' "$VENDOR/python" "$STAGE/"
cp "$HERE/om-mava-updater.ico" "$STAGE/"
# VBScript reads Unicode only as UTF-16 little-endian with its BOM, CRLF lines
{ printf '\xff\xfe'; sed 's/$/\r/' "$HERE/launch.vbs" | iconv -f UTF-8 -t UTF-16LE; } > "$STAGE/launch.vbs"
find "$STAGE" -name '._*' -delete

LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 makensis -INPUTCHARSET UTF8 -V2 -DVER="$VER" -DSTAGE="$STAGE" -DOUT="$OUT" "$HERE/om-mava-updater.nsi"
rm -rf "$WORK"
echo "$OUT"
