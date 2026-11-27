#!/usr/bin/env bash
# Cài những gì OpenMontage cần trên máy này (macOS hoặc Ubuntu), chạy trong thư mục OM.
# OM MAVA Updater (nút Cài / Cập nhật / Cài công cụ) và bộ cài 1 file đều gọi script này.
# Không cần quyền quản trị: ffmpeg, Node, uv tải bản dựng sẵn (kiểm SHA-256) vào ~/.openmontage/tools,
# lối gọi đặt ở ~/.local/bin. Máy đã có sẵn (Homebrew, apt…) thì dùng luôn. Chạy lại bao nhiêu lần cũng được.
# Không bao giờ đụng .env đã có, projects/ hay phim.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n==> %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*"; }
OS="$(uname -s)"; ARCH="$(uname -m)"
TOOLS="$HOME/.openmontage/tools"; BIN="$HOME/.local/bin"
mkdir -p "$TOOLS" "$BIN"
export PATH="$BIN:/opt/homebrew/bin:/usr/local/bin:$PATH"
NODE_LINE="22"                                   # Node LTS đi kèm (nodejs.org/dist/latest-v22.x)

sha_of() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
check_sha() { [ "$(sha_of "$1")" = "$2" ] || { rm -f "$1"; echo "Sai mã SHA-256: $1 — bỏ, không cài"; exit 1; }; }
node_major() { local v; v="$(node -v 2>/dev/null)" || { echo 0; return; }; echo "$v" | sed -E 's/^v([0-9]+).*/\1/'; }
link() { ln -sf "$1" "$BIN/$(basename "$1")"; }

ensure_path_line() {   # để Claude/Terminal mở sau này thấy ~/.local/bin
  local line='export PATH="$HOME/.local/bin:$PATH"' f
  for f in "$@"; do
    [ -f "$f" ] && grep -q '\.local/bin' "$f" && continue
    printf '\n# OpenMontage: công cụ cài bởi OM MAVA Updater\n%s\n' "$line" >> "$f"
  done
}

# ---------- Node (nodejs.org) ----------
install_node() {
  local plat
  case "$OS-$ARCH" in
    Darwin-arm64) plat=darwin-arm64;; Darwin-x86_64) plat=darwin-x64;;
    Linux-x86_64) plat=linux-x64;; Linux-aarch64) plat=linux-arm64;;
    *) warn "Không có Node dựng sẵn cho $OS-$ARCH"; return 1;;
  esac
  local base="https://nodejs.org/dist/latest-v$NODE_LINE.x" name sum tmp
  read -r sum name <<<"$(curl -fsSL "$base/SHASUMS256.txt" | grep -E " node-v[0-9.]+-$plat\.tar\.gz$" | head -1)"
  [ -n "$name" ] || { warn "Không đọc được danh sách Node"; return 1; }
  say "Tải Node ${name%.tar.gz}"
  tmp="$(mktemp -d)"
  curl -fL# -o "$tmp/$name" "$base/$name"; check_sha "$tmp/$name" "$sum"
  rm -rf "$TOOLS/node"; mkdir -p "$TOOLS/node"
  tar -xzf "$tmp/$name" -C "$TOOLS/node" --strip-components 1; rm -rf "$tmp"
  for b in node npm npx; do link "$TOOLS/node/bin/$b"; done
}

# ---------- ffmpeg + ffprobe ----------
install_ffmpeg_linux() {   # BtbN static GPL build (libass, freetype, drawtext) — được ffmpeg.org trỏ tới
  local pat
  case "$ARCH" in x86_64) pat=linux64;; aarch64) pat=linuxarm64;; *) warn "Không có ffmpeg dựng sẵn cho $ARCH"; return 1;; esac
  local base="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest" sum name tmp
  read -r sum name <<<"$(curl -fsSL "$base/checksums.sha256" | grep -E " ffmpeg-n[0-9.]+-latest-$pat-gpl-[0-9.]+\.tar\.xz$" | sort -k2 -V | tail -1)"
  [ -n "$name" ] || { warn "Không đọc được danh sách ffmpeg"; return 1; }
  say "Tải ffmpeg ${name%.tar.xz}"
  tmp="$(mktemp -d)"
  curl -fL# -o "$tmp/$name" "$base/$name"; check_sha "$tmp/$name" "$sum"
  rm -rf "$TOOLS/ffmpeg"; mkdir -p "$TOOLS/ffmpeg"
  tar -xJf "$tmp/$name" -C "$TOOLS/ffmpeg" --strip-components 1; rm -rf "$tmp"
  link "$TOOLS/ffmpeg/bin/ffmpeg"; link "$TOOLS/ffmpeg/bin/ffprobe"
}

install_ffmpeg_mac() {     # martin-riedl.de: bản arm64/amd64 dựng sẵn, có .sha256 cạnh mỗi file
  local a; case "$ARCH" in arm64) a=arm64;; *) a=amd64;; esac
  local tmp b url; tmp="$(mktemp -d)"
  rm -rf "$TOOLS/ffmpeg"; mkdir -p "$TOOLS/ffmpeg/bin"
  for b in ffmpeg ffprobe; do
    url="$(curl -fsSLI -o /dev/null -w '%{url_effective}' "https://ffmpeg.martin-riedl.de/redirect/latest/macos/$a/release/$b.zip")"
    say "Tải $b (${url##*/download/})"
    curl -fL# -o "$tmp/$b.zip" "$url"
    check_sha "$tmp/$b.zip" "$(curl -fsSL "$url.sha256" | awk '{print $1}')"
    unzip -q -o "$tmp/$b.zip" -d "$TOOLS/ffmpeg/bin"
    chmod +x "$TOOLS/ffmpeg/bin/$b"; xattr -d com.apple.quarantine "$TOOLS/ffmpeg/bin/$b" 2>/dev/null || true
    link "$TOOLS/ffmpeg/bin/$b"
  done
  rm -rf "$tmp"
}

# ---------- Ubuntu: thư viện cho Chrome của Remotion (chỉ cài cái còn thiếu) ----------
linux_libs() {
  command -v dpkg >/dev/null || return 0
  local want=(libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libgbm1 libxrandr2 libxkbcommon0 libxfixes3
              libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2 libsndfile1 fonts-noto-core fonts-noto-cjk)
  if apt-cache show libasound2t64 >/dev/null 2>&1; then want+=(libasound2t64); else want+=(libasound2); fi
  local miss=() p
  for p in "${want[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || miss+=("$p"); done
  [ ${#miss[@]} -eq 0 ] && return 0
  say "Cài thư viện hệ thống còn thiếu: ${miss[*]} (máy sẽ hỏi mật khẩu)"
  local run=sudo; [ "$(id -u)" -eq 0 ] && run=""
  { [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v pkexec >/dev/null && [ "${NONINTERACTIVE:-0}" = 1 ]; } && run=pkexec
  $run apt-get install -y "${miss[@]}" || warn "Chưa cài được ${miss[*]} — Remotion có thể không chạy"
}

case "$OS" in Darwin|Linux) ;; *) echo "Chỉ hỗ trợ macOS và Ubuntu (Windows dùng om-setup.ps1)."; exit 1;; esac

say "Công cụ: ffmpeg, Node, uv"
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  if [ "$OS" = Darwin ]; then
    if command -v brew >/dev/null 2>&1; then brew install ffmpeg; else install_ffmpeg_mac; fi
  else install_ffmpeg_linux; fi
fi
if [ "$(node_major)" -lt 20 ]; then
  if [ "$OS" = Darwin ] && command -v brew >/dev/null 2>&1; then brew install node; else install_node; fi
fi
command -v uv >/dev/null 2>&1 || { say "Cài uv"; curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh; }
[ "$OS" = Linux ] && linux_libs
if [ "$OS" = Darwin ]; then ensure_path_line "$HOME/.zshrc" "$HOME/.zprofile"; else ensure_path_line "$HOME/.profile" "$HOME/.bashrc"; fi
echo "ffmpeg: $(ffmpeg -version | head -1 | cut -d' ' -f3)   Node: $(node -v)   uv: $(uv --version | cut -d' ' -f2)"

# ---- Python 3.12 + thư viện ----
say "Môi trường Python 3.12 + requirements.txt"
uv venv --allow-existing --python 3.12 .venv
uv pip install --python .venv -r requirements.txt \
  || { warn "Tải thư viện lỗi (mạng?) — thử lại sau 5 giây"; sleep 5; uv pip install --python .venv -r requirements.txt; }
say "Tăng tốc GPU nếu máy có card hợp (bỏ qua nếu không)"
.venv/bin/python -m lib.accel_setup --json >/dev/null 2>&1 || warn "accel_setup lỗi — OM vẫn chạy bằng CPU."

[ -f .env ] || cp .env.example .env
chmod 600 .env 2>/dev/null || true

# ---- Remotion ----
say "Remotion (dựng chữ/caption)"
( cd remotion-composer && npm ci --no-audit --no-fund ) || warn "npm ci lỗi — bấm Cài công cụ để thử lại"

# ---- Kiểm tra ----
say "Kiểm tra nhanh"
.venv/bin/python -c "import yaml; print('Python OK')"
.venv/bin/python -m tools list >/dev/null 2>&1 && echo "Công cụ OM: OK" || warn "python -m tools list lỗi"
echo "OM v$(cat VERSION) — cài xong."
