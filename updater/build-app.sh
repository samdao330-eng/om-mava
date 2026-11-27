#!/bin/zsh
# Build "OM MAVA Updater.app" + a drag-to-Applications DMG:  release/updater/build-app.sh  ->  release/mac/OM-MAVA-Updater-<ver>.dmg
# Python 3.12 + Tk come from CHECK VIDEO's vendor folder (packaging/vendor-mac.sh there), so the app needs nothing
# installed. Built in a temp folder (the SAM drive is exFAT: it would sprinkle ._ files into the bundle).
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
VER="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SRC/updater_gui.py")"
VENDOR="${MAVA_QC_VENDOR:-$HOME/.mava-qc-build/vendor-mac}"
ICONPY="${AUTOEDIT_VENV:-$HOME/.auto-edit-venv}/bin/python"      # has Pillow, only to draw the icon
[ -x "$VENDOR/python/bin/python3" ] || { echo "Thiếu $VENDOR — chạy packaging/vendor-mac.sh của CHECK VIDEO trước"; exit 1; }
WORK="$(mktemp -d)"
APP="$WORK/stage/OM MAVA Updater.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app/fonts"

cp "$SRC/update_core.py" "$SRC/updater_gui.py" "$SRC/mark.png" "$APP/Contents/Resources/app/"
cp "$SRC"/fonts/Inter-*.ttf "$SRC/fonts/Inter-LICENSE.txt" "$APP/Contents/Resources/app/fonts/"
# read-only GitHub token shipped inside the app, so editors need not type one. Taken from this machine (the one
# saved in the app's Cài đặt, or MAVA_UPDATER_TOKEN_FILE); never printed, never in git. Share the DMG in-house only.
TOKEN_SRC="${OM_MAVA_UPDATER_TOKEN_FILE:-$HOME/Library/Application Support/OMMavaUpdater/token}"
if [ -s "$TOKEN_SRC" ]; then
  cp "$TOKEN_SRC" "$APP/Contents/Resources/app/bundled_token"
  chmod 644 "$APP/Contents/Resources/app/bundled_token"
  echo "Có token đóng kèm (lấy từ $TOKEN_SRC)"
else
  echo "warning: không có $TOKEN_SRC — app không kèm token, editor phải tự nhập trong Cài đặt"
fi
cp -R "$VENDOR/python" "$APP/Contents/Resources/"
cat > "$APP/Contents/MacOS/om-mava-updater" <<'SH'
#!/bin/zsh
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec "$RES/python/bin/python3" -I -B "$RES/app/updater_gui.py"     # -B: no .pyc cache written into the app (it would break the signature)
SH
chmod +x "$APP/Contents/MacOS/om-mava-updater"

ICONSET="$WORK/AppIcon.iconset"
"$ICONPY" -I "$SRC/make_icon.py" "$ICONSET"
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>OM MAVA Updater</string>
  <key>CFBundleDisplayName</key><string>OM MAVA Updater</string>
  <key>CFBundleIdentifier</key><string>vn.mavamedia.om-updater</string>
  <key>CFBundleVersion</key><string>$VER</string>
  <key>CFBundleShortVersionString</key><string>$VER</string>
  <key>CFBundleExecutable</key><string>om-mava-updater</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
find "$APP" -name '._*' -delete
codesign --force --deep -s - "$APP" 2>/dev/null || true          # ad-hoc: Apple Silicon refuses unsigned code

ln -s /Applications "$WORK/stage/Applications"
mkdir -p "$SRC/../mac"
DMG="$(cd "$SRC/../mac" && pwd)/OM-MAVA-Updater-$VER.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "OM MAVA Updater" -srcfolder "$WORK/stage" -ov -format UDZO "$DMG"
[ -n "$KEEP_APP" ] && { rm -rf "$KEEP_APP/OM MAVA Updater.app"; cp -R "$APP" "$KEEP_APP/"; }
rm -rf "$WORK"
echo "$DMG"
