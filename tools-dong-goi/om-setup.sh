#!/usr/bin/env bash
# Cài những gì OpenMontage cần trên máy này (macOS hoặc Ubuntu), chạy trong thư mục OM.
# Bộ cài 1 file và OM MAVA Updater đều gọi script này sau khi chép file. Chạy lại bao nhiêu lần cũng được:
# thứ đã có thì bỏ qua. Không bao giờ đụng .env đã có, projects/ hay phim.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n==> %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*"; }
OS="$(uname -s)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

node_major() { local v; v="$(node -v 2>/dev/null)" || { echo 0; return; }; echo "$v" | sed -E 's/^v([0-9]+).*/\1/'; }

if [ "$OS" = "Darwin" ]; then
  # ---- macOS: Homebrew, ffmpeg, Node ----
  if ! command -v brew >/dev/null 2>&1; then
    say "Cài Homebrew (sẽ hỏi mật khẩu máy Mac)"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
  fi
  command -v ffmpeg >/dev/null 2>&1 || { say "Cài ffmpeg"; brew install ffmpeg; }
  [ "$(node_major)" -ge 20 ] || { say "Cài Node.js"; brew install node; }
  command -v uv >/dev/null 2>&1 || { say "Cài uv"; brew install uv; }
elif [ "$OS" = "Linux" ]; then
  # ---- Ubuntu: apt, Node 20 (NodeSource), thư viện cho Chrome của Remotion ----
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  say "Cài gói hệ thống (ffmpeg, font, build tools)"
  $SUDO apt-get update -y
  $SUDO apt-get install -y ffmpeg curl ca-certificates git build-essential xz-utils unzip \
    fonts-noto fonts-noto-cjk fonts-dejavu-core
  # Tên gói khác nhau giữa 22.04 và 24.04: gói nào không có thì bỏ qua.
  for pkg in libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libgbm1 libxrandr2 libxkbcommon0 \
             libxfixes3 libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2 \
             libasound2t64 libasound2 libsndfile1; do
    $SUDO apt-get install -y "$pkg" >/dev/null 2>&1 || true
  done
  if [ "$(node_major)" -lt 20 ]; then
    say "Cài Node.js 20"
    curl -fsSL https://deb.nodesource.com/setup_20.x | $SUDO -E bash -
    $SUDO apt-get install -y nodejs
  fi
  command -v uv >/dev/null 2>&1 || { say "Cài uv"; curl -LsSf https://astral.sh/uv/install.sh | sh; }
else
  echo "Chỉ hỗ trợ macOS và Ubuntu."; exit 1
fi
echo "ffmpeg: $(ffmpeg -version | head -1 | cut -d' ' -f3)   Node: $(node -v)"

# ---- Python 3.12 + thư viện ----
say "Môi trường Python 3.12 + requirements.txt"
uv venv --allow-existing --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
say "Tăng tốc GPU nếu máy có card hợp (bỏ qua nếu không)"
.venv/bin/python -m lib.accel_setup --json >/dev/null 2>&1 || warn "accel_setup lỗi — OM vẫn chạy bằng CPU."

[ -f .env ] || cp .env.example .env
chmod 600 .env 2>/dev/null || true

# ---- Remotion ----
say "Remotion (dựng chữ/caption)"
( cd remotion-composer && npm ci --no-audit --no-fund ) || warn "npm ci lỗi — chạy lại: cd remotion-composer && npm ci"

# ---- Kiểm tra ----
say "Kiểm tra nhanh"
.venv/bin/python -c "import yaml; print('Python OK')"
.venv/bin/python -m tools list >/dev/null 2>&1 && echo "Công cụ OM: OK" || warn "python -m tools list lỗi"
echo "OM v$(cat VERSION) — cài xong."
