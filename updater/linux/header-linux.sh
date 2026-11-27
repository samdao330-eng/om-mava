#!/usr/bin/env bash
# OM MAVA Updater cho Ubuntu — bộ cài 1 file: bash OM-MAVA-Updater-<ver>.run
# Cài app vào ~/.local/share/om-mava-updater, thêm vào menu ứng dụng (và Desktop). Không cần quyền admin,
# trừ khi máy thiếu python3-tk (hỏi mật khẩu một lần).
set -euo pipefail
APP="$HOME/.local/share/om-mava-updater"
echo "==> Cài OM MAVA Updater vào $APP"
rm -rf "$APP"; mkdir -p "$APP"
LINE=$(awk '/^__OM_PAYLOAD_BELOW__$/ {print NR + 1; exit 0; }' "$0")
tail -n +"$LINE" "$0" | tar -xzf - -C "$APP"

if ! python3 -c "import tkinter" 2>/dev/null; then
  echo "==> Cài python3-tk (giao diện của app) — máy sẽ hỏi mật khẩu"
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v pkexec >/dev/null; then
    pkexec apt-get install -y python3-tk
  else
    sudo apt-get install -y python3-tk
  fi
fi

mkdir -p "$HOME/.local/share/applications"
DESK="$HOME/.local/share/applications/om-mava-updater.desktop"
cat > "$DESK" <<EOF
[Desktop Entry]
Type=Application
Name=OM MAVA Updater
Comment=Cài và cập nhật OpenMontage
Exec=python3 -I -B "$APP/updater_gui.py"
Icon=$APP/om-mava-updater.png
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESK"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP_DIR" ]; then
  cp "$DESK" "$DESKTOP_DIR/"; chmod +x "$DESKTOP_DIR/om-mava-updater.desktop"
  gio set "$DESKTOP_DIR/om-mava-updater.desktop" metadata::trusted true 2>/dev/null || true
fi
echo "==> Xong. Mở 'OM MAVA Updater' trong menu ứng dụng (hoặc trên Desktop)."
nohup python3 -I -B "$APP/updater_gui.py" >/dev/null 2>&1 &
exit 0
__OM_PAYLOAD_BELOW__
