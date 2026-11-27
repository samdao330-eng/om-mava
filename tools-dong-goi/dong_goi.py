#!/usr/bin/env python3
"""Đóng gói OpenMontage để phát cho mọi người.

  python3 release/tools-dong-goi/dong_goi.py cai [mac|ubuntu|all] [--co-khoa]
      Bộ cài 1 file -> release/mac/om-mac-v<bản>.command, release/ubuntu/om-ubuntu-v<bản>.run
      --co-khoa: mang theo .env (khoá API) của máy này -> release/ca-nhan-co-khoa/ (chỉ cho máy của mình)

  python3 release/tools-dong-goi/dong_goi.py phat-hanh --notes "có gì mới" [--yes]
      Zip om-mava-<bản>.zip + 2 bộ cài -> GitHub Release v<bản> trên samdao330-eng/om-mava,
      nơi OM MAVA Updater đọc. Hỏi trước khi đẩy (trừ khi có --yes).

<bản> = giờ đóng gói YYYY.MM.DD.HHMM; file VERSION trong gói mang đúng số đó. Bản OM gốc ghi trong ghi chú.
Gói chung không bao giờ mang khoá, phim, log, kế hoạch hay trí nhớ máy này: xem SHARED_EXCLUDE.
Chỉ dùng thư viện chuẩn của Python.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent                     # thư mục OM
REL = SRC / "release"
REPO = "samdao330-eng/om-mava"
SETUPS = ("om-setup.sh", "om-setup.ps1")    # thêm vào gốc gói, từ tools-dong-goi/ (Mac+Ubuntu, Windows)

# Không bao giờ vào gói nào: phim, thư viện đã cài (khác máy), cache, chính thư mục release.
ALWAYS_EXCLUDE_TOP = {"projects", "release", "release-ubuntu", ".venv", ".cache", "dist", "scratch", "output"}
ALWAYS_EXCLUDE_PATHS = {"remotion-composer/out", ".backlot/thumbs"}
ALWAYS_EXCLUDE_ANY_DIR = {"node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
ALWAYS_EXCLUDE_NAMES = ["._*", ".DS_Store", "*.pyc", "*.pyo"]

# Thêm cho gói chung (phát cho người khác): đồ riêng của máy này.
SHARED_EXCLUDE_TOP = {"plans", ".backlot"}
SHARED_EXCLUDE_PATHS = {".claude/agent-memory", ".claude/memory", ".claude/settings.local.json",
                        "config.local.yaml", "logchat.md", ".om_updater.json", ".om_mava_updater.json",
                        "DIEN-KEY-VAO-DAY.txt"}
SECRET_NAMES = [".env", ".env.*", "*.pem", "*.key", "*.p12", "id_rsa*", "gcp-*.json", "*service-account*.json",
                "service_account*.json", ".youtube-token.json", "token", "bundled_token"]
SECRET_ALLOWED = {".env.example"}


def _match(name: str, patterns) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def is_secret(name: str) -> bool:
    return name not in SECRET_ALLOWED and _match(name, SECRET_NAMES)


def collect(with_keys: bool) -> list[str]:
    """Đường dẫn tương đối (posix) của mọi file sẽ vào gói."""
    out = []
    for d, dirs, files in os.walk(SRC):
        rel_d = Path(d).relative_to(SRC).as_posix()
        rel_d = "" if rel_d == "." else rel_d
        keep = []
        for x in dirs:
            r = f"{rel_d}/{x}" if rel_d else x
            if x in ALWAYS_EXCLUDE_ANY_DIR or x.startswith("._") or r in ALWAYS_EXCLUDE_PATHS:
                continue
            if not rel_d and x in ALWAYS_EXCLUDE_TOP:
                continue
            if not with_keys and ((not rel_d and x in SHARED_EXCLUDE_TOP) or r in SHARED_EXCLUDE_PATHS):
                continue
            keep.append(x)
        dirs[:] = sorted(keep)
        for f in sorted(files):
            r = f"{rel_d}/{f}" if rel_d else f
            if _match(f, ALWAYS_EXCLUDE_NAMES) or r in SETUPS or os.path.islink(os.path.join(d, f)):
                continue
            if not with_keys and (r in SHARED_EXCLUDE_PATHS or is_secret(f)):
                continue
            if with_keys and is_secret(f) and r != ".env":
                continue                      # gói có khoá chỉ mang .env gốc, không mang file bí mật khác
            out.append(r)
    if not with_keys:
        leaked = [r for r in out if is_secret(r.rsplit("/", 1)[-1])]
        if leaked:
            sys.exit("Dừng: gói chung lọt file bí mật:\n  " + "\n  ".join(leaked))
    return out


def _mode(path: Path) -> int:
    m = path.stat().st_mode & 0o777
    with open(path, "rb") as fh:              # ổ exFAT làm mất bit chạy: file có #! thì cho chạy được
        if fh.read(2) == b"#!":
            m |= 0o755
    return m | 0o644


def _entries(files, stamp):
    """(tên trong gói, bytes, mode): file OM + om-setup.sh + VERSION = stamp."""
    for r in files:
        p = SRC / r
        if r == "VERSION":
            continue
        yield r, p.read_bytes(), _mode(p)
    yield "om-setup.sh", (HERE / "om-setup.sh").read_bytes(), 0o755
    ps1 = (HERE / "om-setup.ps1").read_bytes()          # PowerShell 5 đọc tiếng Việt đúng chỉ khi có BOM
    yield "om-setup.ps1", (ps1 if ps1.startswith(b"\xef\xbb\xbf") else b"\xef\xbb\xbf" + ps1), 0o644
    yield "VERSION", f"{stamp}\n".encode(), 0o644


def make_tgz(files, stamp) -> bytes:
    buf = io.BytesIO()
    now = time.time()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=6) as tar:
        for name, data, mode in _entries(files, stamp):
            ti = tarfile.TarInfo(name)
            ti.size, ti.mode, ti.mtime = len(data), mode, now
            ti.uname = ti.gname = ""
            tar.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def make_zip(files, stamp, path: Path, prefix="om-mava/"):
    dt = datetime.now().timetuple()[:6]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data, mode in _entries(files, stamp):
            info = zipfile.ZipInfo(prefix + name, date_time=dt)
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)


def build_installers(which, with_keys, stamp) -> list[Path]:
    files = collect(with_keys)
    payload = make_tgz(files, stamp)
    header = (HERE / "header-cai.sh").read_bytes()
    outs = []
    for os_name, sub, ext in (("mac", "mac", "command"), ("ubuntu", "ubuntu", "run")):
        if which not in (os_name, "all"):
            continue
        folder = REL / ("ca-nhan-co-khoa" if with_keys else sub)
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"om-{os_name}-v{stamp}{'-co-khoa' if with_keys else ''}.{ext}"
        out.write_bytes(header + payload)
        out.chmod(0o755)
        outs.append(out)
        print(f"{out}  ({out.stat().st_size / 1e6:.0f} MB, {len(files)} file)")
    return outs


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def publish(notes: str, yes: bool):
    if not shutil.which("gh"):
        sys.exit("Cần gh: brew install gh && gh auth login")
    stamp = datetime.now().strftime("%Y.%m.%d.%H%M")
    tag = f"v{stamp}"
    if subprocess.run(["gh", "release", "view", tag, "--repo", REPO], capture_output=True).returncode == 0:
        sys.exit(f"Đã có {tag} — đợi 1 phút rồi chạy lại.")
    base = (SRC / "VERSION").read_text().strip()
    files = collect(with_keys=False)
    tmp = Path(tempfile.mkdtemp())
    zpath = tmp / f"om-mava-{stamp}.zip"
    make_zip(files, stamp, zpath)
    digest = sha256(zpath)
    installers = build_installers("all", False, stamp)
    body = f"{notes}\n\nOM gốc: {base}\n\nsha256: {digest}"
    print(f"\nBản {tag} — zip {zpath.stat().st_size / 1e6:.0f} MB, {len(files)} file, sha256 {digest[:12]}…")
    print(f"Ghi chú: {notes}")
    if not yes:
        ok = input(f"Đẩy lên GitHub ({REPO}) cho mọi người? [y/N] ").strip().lower()
        if ok != "y":
            sys.exit("Huỷ — chưa đẩy gì.")
    subprocess.run(["gh", "release", "create", tag, str(zpath), *map(str, installers), "--repo", REPO,
                    "--title", tag, "--notes", body], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Xong: OM MAVA Updater sẽ thấy {tag}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cai")
    c.add_argument("which", nargs="?", default="all", choices=["mac", "ubuntu", "all"])
    c.add_argument("--co-khoa", action="store_true")
    p = sub.add_parser("phat-hanh")
    p.add_argument("--notes", required=True)
    p.add_argument("--yes", action="store_true")
    sub.add_parser("liet-ke")                 # in danh sách file gói chung, để soát
    a = ap.parse_args()
    if a.cmd == "cai":
        build_installers(a.which, a.co_khoa, datetime.now().strftime("%Y.%m.%d.%H%M"))
    elif a.cmd == "phat-hanh":
        publish(a.notes, a.yes)
    else:
        print("\n".join(collect(with_keys=False)))


if __name__ == "__main__":
    main()
