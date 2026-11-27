#!/bin/zsh
# Build the Ubuntu app installer on this Mac:  release/updater/linux/build-run.sh  ->  release/ubuntu/OM-MAVA-Updater-<ver>.run
# Uses Ubuntu's own python3 (+ python3-tk), so only the app's files ship.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/.." && pwd)"
VER="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SRC/updater_gui.py")"
OUTDIR="$(cd "$SRC/.." && pwd)/ubuntu"; mkdir -p "$OUTDIR"
OUT="$OUTDIR/OM-MAVA-Updater-$VER.run"
WORK="$(mktemp -d)"; S="$WORK/app"; mkdir -p "$S/fonts"
cp "$SRC/update_core.py" "$SRC/updater_gui.py" "$SRC/mark.png" "$HERE/om-mava-updater.png" "$S/"
cp "$SRC"/fonts/Inter-*.ttf "$SRC/fonts/Inter-LICENSE.txt" "$S/fonts/"
TOKEN_SRC="${OM_MAVA_UPDATER_TOKEN_FILE:-$HOME/Library/Application Support/OMMavaUpdater/token}"
if [ -s "$TOKEN_SRC" ]; then cp "$TOKEN_SRC" "$S/bundled_token"; echo "Có token đóng kèm"
else echo "warning: không có $TOKEN_SRC — app không kèm token, editor phải tự nhập trong Cài đặt"; fi
COPYFILE_DISABLE=1 tar --no-xattrs -czf "$WORK/p.tgz" -C "$S" .
cat "$HERE/header-linux.sh" "$WORK/p.tgz" > "$OUT"; chmod +x "$OUT"
rm -rf "$WORK"
echo "$OUT"
