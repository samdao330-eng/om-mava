#!/usr/bin/env bash
# OpenMontage — bộ cài 1 file (macOS hoặc Ubuntu 22.04/24.04).
# Cách dùng:   bash <file này> [thư-mục-cài]          (mặc định: ~/OpenMontage)
#   Mac: bấm đúp file cũng được (cài vào ~/OpenMontage).
#   Chỉ giải nén, không cài thư viện:   bash <file này> --extract-only [thư-mục]
# Sau này cập nhật bằng app OM MAVA Updater (Mac) — chọn đúng thư mục này.
set -euo pipefail

EXTRACT_ONLY=0
if [ "${1:-}" = "--extract-only" ]; then EXTRACT_ONLY=1; shift; fi
TARGET="${1:-$HOME/OpenMontage}"

say() { printf '\n==> %s\n' "$*"; }

case "$(uname -s)" in Darwin|Linux) ;; *) echo "Chỉ hỗ trợ macOS và Ubuntu."; exit 1;; esac

say "Giải nén OpenMontage vào: $TARGET"
mkdir -p "$TARGET"
[ -f "$TARGET/.env" ] && cp "$TARGET/.env" "$TARGET/.env.backup-$(date +%Y%m%d%H%M%S)" \
  && echo "Đã có .env — giữ nguyên, kèm bản sao lưu .env.backup-*"
PAYLOAD_LINE=$(awk '/^__OM_PAYLOAD_BELOW__$/ {print NR + 1; exit 0; }' "$0")
tail -n +"$PAYLOAD_LINE" "$0" | tar -xzf - -C "$TARGET"
[ "$(uname -s)" = Darwin ] && xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true
echo "Xong giải nén."

if [ "$EXTRACT_ONLY" = 1 ]; then
  echo "Chỉ giải nén. Cài thư viện sau:  bash \"$TARGET/om-setup.sh\""; exit 0
fi

bash "$TARGET/om-setup.sh"

say "Cài xong! Mở Claude Code trong thư mục OM:"
echo "   cd \"$TARGET\" && claude"
grep -qE '^[A-Z0-9_]+=.+' "$TARGET/.env" 2>/dev/null \
  || echo "Chưa có khoá API: mở Claude Code rồi dán các dòng KEY=giá-trị vào chat, OM sẽ tự cất."
exit 0
__OM_PAYLOAD_BELOW__
