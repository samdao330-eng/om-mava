"""OM MAVA Updater core: list OpenMontage releases on GitHub, download one, check it, install it into the
editor's OpenMontage folder, keep the last few versions on the machine for rollback. Standard library only
(the app ships Python without extra packages).

Release format (made by `release/tools-dong-goi/dong_goi.py phat-hanh` on the master OM): tag `v<VERSION>`, asset
`om-mava-<VERSION>.zip` (OM without keys, films, logs), its SHA-256 in the asset's `digest` field or as a `sha256: <hex>` line in the
release notes. A download whose hash does not match is thrown away, never installed.

Runs on macOS, Windows and Ubuntu. Machine files (macOS ~/Library/Application Support/OMMavaUpdater,
Windows %APPDATA%/OMMavaUpdater, Linux ~/.config/om-mava-updater):
  config.json   install folder, how many versions to keep, cached release list
  token         GitHub token typed in Cài đặt, read-only on the repo (file mode 600). Without it the app uses
                the token build-app.sh put inside the app (bundled_token) — never in git
  versions/<v>  unpacked versions kept for rollback        logs/updater.log
Install folder: `.om_mava_updater.json` = the version installed + its file list, so the next update can remove
files that a newer version dropped. Files the release does not carry (whisper model, logchat.md, the venv
outside) are never touched.
"""
import datetime, hashlib, json, os, re, shutil, subprocess, sys, tempfile, threading, urllib.error
import urllib.parse, urllib.request, zipfile

REPO = "samdao330-eng/om-mava"
API = "https://api.github.com"
IS_WIN, IS_MAC = sys.platform == "win32", sys.platform == "darwin"
if IS_MAC:
    HOME = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "OMMavaUpdater")
elif IS_WIN:
    HOME = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "OMMavaUpdater")
else:
    HOME = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "om-mava-updater")
CONFIG = os.path.join(HOME, "config.json")
TOKEN_FILE = os.path.join(HOME, "token")
BUNDLED_TOKEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundled_token")
VERSIONS = os.path.join(HOME, "versions")
LOG = os.path.join(HOME, "logs", "updater.log")
STATE_NAME = ".om_mava_updater.json"
DEFAULT_INSTALL = os.path.join(os.path.expanduser("~"), "OpenMontage")   # first install goes here; Đổi thư mục to move
_lock = threading.Lock()


class UpdateError(Exception):
    """A failure to show the editor as is (already in Vietnamese)."""


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with _lock, open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")


# ---------- config / token ----------

def load_config():
    cfg = {"install_dir": DEFAULT_INSTALL, "keep_versions": 3, "releases_cache": []}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    os.makedirs(HOME, exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    os.replace(tmp, CONFIG)


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def token_source():
    """"user" (typed on this machine), "bundled" (shipped inside the app) or None."""
    return "user" if _read(TOKEN_FILE) else "bundled" if _read(BUNDLED_TOKEN) else None


def token():
    return _read(TOKEN_FILE) or _read(BUNDLED_TOKEN)


def save_token(t):
    os.makedirs(HOME, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(t.strip())
    os.chmod(TOKEN_FILE, 0o600)


# ---------- GitHub ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Asset downloads redirect to a signed storage URL that rejects our Authorization header: follow by hand."""
    def redirect_request(self, *a, **k):
        return None


def clear_token():
    """Drop the token typed on this machine, so the app uses the one built into it again."""
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass


def _request(url, accept="application/vnd.github+json", auth=True, timeout=15, use_bundled=False):
    headers = {"Accept": accept, "User-Agent": "om-mava-updater", "X-GitHub-Api-Version": "2022-11-28"}
    tok = _read(BUNDLED_TOKEN) if use_bundled else token()
    if auth:
        if not tok:
            raise UpdateError("Chưa có token GitHub — bấm Cài đặt để nhập")
        headers["Authorization"] = f"Bearer {tok}"
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        return opener.open(urllib.request.Request(url, headers=headers), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
            return _request(e.headers["Location"], accept="*/*", auth=False, timeout=timeout)
        if e.code in (401, 403, 404) and auth and not use_bundled and token_source() == "user" \
                and _read(BUNDLED_TOKEN):
            # The token typed in Cài đặt is wrong or lacks access: forget it and use the app's own one.
            log(f"typed token refused ({e.code}); falling back to the bundled token")
            clear_token()
            return _request(url, accept=accept, auth=auth, timeout=timeout, use_bundled=True)
        if e.code in (401, 403):
            if use_bundled or token_source() == "bundled":
                raise UpdateError("Token có sẵn trong app đã hết hạn / bị thu hồi — xin bản OM MAVA Updater mới")
            raise UpdateError("Token GitHub sai, hết hạn hoặc không có quyền đọc repo")
        if e.code == 404:
            raise UpdateError("Không thấy repo / bản phát hành (token có quyền repo này chưa?)")
        raise UpdateError(f"GitHub trả lỗi {e.code}")
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"Không kết nối được GitHub ({getattr(e, 'reason', e)})")


def fetch_releases():
    """Releases newest first: [{id, version, date, notes, size, sha256, url}]. Drafts and releases without a
    zip are skipped."""
    with _request(f"{API}/repos/{REPO}/releases?per_page=30") as r:
        data = json.load(r)
    out = []
    for rel in data:
        if rel.get("draft"):
            continue
        asset = next((a for a in rel.get("assets", []) if a["name"].endswith(".zip")), None)
        if not asset:
            continue
        body = rel.get("body") or ""
        digest = (asset.get("digest") or "").removeprefix("sha256:")
        m = re.search(r"sha256:\s*([0-9a-fA-F]{64})", body)
        notes = next((l.strip() for l in body.splitlines() if l.strip() and not l.lower().startswith("sha256")), "")
        out.append({"id": rel["id"], "version": rel["tag_name"].lstrip("v"), "date": rel.get("published_at", "")[:10],
                    "notes": notes, "size": asset["size"], "url": asset["url"],
                    "sha256": (digest or (m.group(1) if m else "")).lower()})
    out.sort(key=lambda x: version_key(x["version"]), reverse=True)
    return out


def version_key(v):
    return tuple(int(x) for x in re.findall(r"\d+", v))


# ---------- local versions ----------

def local_versions():
    try:
        return sorted((d for d in os.listdir(VERSIONS) if os.path.isfile(os.path.join(VERSIONS, d, "VERSION"))),
                      key=version_key, reverse=True)
    except OSError:
        return []


def read_state(install_dir):
    try:
        with open(os.path.join(install_dir, STATE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def installed_version(install_dir):
    """The version in use: the updater's state file, else the folder's own VERSION file (a manual copy)."""
    st = read_state(install_dir)
    if st.get("version"):
        return st["version"]
    try:
        with open(os.path.join(install_dir, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def download(rel, progress=None):
    """Download + verify + unpack into versions/<v>. Returns the folder. progress(done_bytes, total_bytes)."""
    dest = os.path.join(VERSIONS, rel["version"])
    if os.path.isfile(os.path.join(dest, "VERSION")):
        return dest
    if not re.fullmatch(r"[0-9a-f]{64}", rel.get("sha256") or ""):
        raise UpdateError(f"Bản {rel['version']} không có mã SHA-256 — không cài")
    os.makedirs(VERSIONS, exist_ok=True)
    h = hashlib.sha256()
    with tempfile.TemporaryDirectory(dir=VERSIONS) as tmp:
        zpath = os.path.join(tmp, "release.zip")
        with _request(rel["url"], accept="application/octet-stream", timeout=60) as r, open(zpath, "wb") as f:
            total, done = int(r.headers.get("Content-Length") or rel["size"] or 0), 0
            while chunk := r.read(1 << 16):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
        if h.hexdigest() != rel["sha256"]:
            raise UpdateError(f"File tải về sai mã SHA-256 — bỏ, không cài bản {rel['version']}")
        unpack = os.path.join(tmp, "unpacked")
        _safe_extract(zpath, unpack)
        root = _single_root(unpack)
        if not all(os.path.isfile(os.path.join(root, f)) for f in ("VERSION", "AGENTS.md", "om-setup.sh")):
            raise UpdateError("File tải về không phải OpenMontage (thiếu VERSION / AGENTS.md / om-setup.sh)")
        os.replace(root, dest)
    log(f"downloaded {rel['version']} ({h.hexdigest()[:12]})")
    return dest


def _safe_extract(zpath, out):
    """Unzip refusing absolute paths and '..' (zip-slip); keep the executable bit from the zip."""
    base = os.path.realpath(out)
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            target = os.path.realpath(os.path.join(out, info.filename))
            if not (target == base or target.startswith(base + os.sep)):
                raise UpdateError(f"File zip có đường dẫn lạ: {info.filename}")
            z.extract(info, out)
            mode = (info.external_attr >> 16) & 0o777
            if mode and not info.is_dir():
                os.chmod(target, mode)


def _single_root(d):
    items = [x for x in os.listdir(d) if not x.startswith(".")]
    return os.path.join(d, items[0]) if len(items) == 1 and os.path.isdir(os.path.join(d, items[0])) else d


def prune(keep, protect=()):
    """Keep the newest `keep` versions on the machine, plus any in `protect` (the one in use)."""
    for i, v in enumerate(local_versions()):
        if i >= keep and v not in protect:
            shutil.rmtree(os.path.join(VERSIONS, v), ignore_errors=True)
            log(f"pruned {v}")


# ---------- install ----------

def _files(root):
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            if f.startswith("._") or f == ".DS_Store":
                continue
            out.append(os.path.relpath(os.path.join(d, f), root))
    return sorted(out)


def check_install_dir(install_dir):
    if not install_dir:
        raise UpdateError("Chưa chọn thư mục OpenMontage")
    if os.path.isdir(os.path.join(install_dir, ".git")):
        raise UpdateError("Đây là thư mục gốc (có .git) — không ghi đè bằng bản phát hành")
    if os.path.isdir(os.path.join(install_dir, "release", "tools-dong-goi")):
        raise UpdateError("Đây là OM gốc dùng để phát hành — không ghi đè")
    parent = os.path.dirname(install_dir.rstrip("/")) or "/"
    if not os.path.isdir(parent):
        raise UpdateError(f"Không thấy {parent} (ổ chứa thư mục chưa cắm?)")


def install(version, install_dir, on_line=None):
    """Make install_dir hold exactly `version`'s files (files the release does not carry are kept), record
    the state, then run om-setup.sh so the libraries match the new version."""
    say = on_line or (lambda s: None)
    check_install_dir(install_dir)
    src = os.path.join(VERSIONS, version)
    if not os.path.isfile(os.path.join(src, "VERSION")):
        raise UpdateError(f"Bản {version} chưa có trên máy")
    new_files = _files(src)
    old_files = set(read_state(install_dir).get("files", []))
    os.makedirs(install_dir, exist_ok=True)
    for rel in new_files:
        a, b = os.path.join(src, rel), os.path.join(install_dir, rel)
        os.makedirs(os.path.dirname(b), exist_ok=True)
        tmp = b + ".om-mava-new"
        shutil.copy2(a, tmp)
        with open(tmp, "rb") as f:                 # scripts (#!) runnable: exFAT drives drop the exec bit
            if f.read(2) == b"#!":
                os.chmod(tmp, os.stat(tmp).st_mode | 0o755)
        os.replace(tmp, b)
    removed = 0
    for rel in old_files - set(new_files):
        p = os.path.join(install_dir, rel)
        if os.path.isfile(p):
            os.remove(p)
            removed += 1
    state = {"version": version, "applied_at": datetime.datetime.now().isoformat(timespec="seconds"),
             "files": new_files}
    with open(os.path.join(install_dir, STATE_NAME), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    log(f"installed {version} -> {install_dir} ({len(new_files)} files, {removed} removed)")
    say(f"Đã chép {len(new_files)} file{f', xoá {removed} file cũ' if removed else ''}")
    run_setup(install_dir, say)


TOOLS = os.path.join(os.path.expanduser("~"), ".openmontage", "tools")


def tool_paths():
    """Where om-setup puts or finds ffmpeg / Node / uv, so the app sees them even before a new shell."""
    home = os.path.expanduser("~")
    extra = [os.path.join(TOOLS, "ffmpeg", "bin"), os.path.join(TOOLS, "node"), os.path.join(home, ".local", "bin")]
    if not IS_WIN:
        extra += [os.path.join(TOOLS, "node", "bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                  "/usr/sbin", "/sbin"]
    return os.pathsep.join(extra + [os.environ.get("PATH", "")])


def tool_status(install_dir):
    """[(name, ok)] for the tool card: what this machine has for OM in install_dir."""
    path = tool_paths()
    venv_py = os.path.join(install_dir or "", ".venv", "Scripts" if IS_WIN else "bin",
                           "python.exe" if IS_WIN else "python")
    remotion = os.path.join(install_dir or "", "remotion-composer", "node_modules", "remotion")
    return [("ffmpeg", bool(shutil.which("ffmpeg", path=path))),
            ("Node", bool(shutil.which("node", path=path))),
            ("Python", bool(install_dir) and os.path.isfile(venv_py)),
            ("Remotion", bool(install_dir) and os.path.isdir(remotion))]


def run_setup(install_dir, say):
    """om-setup.sh (macOS/Ubuntu) or om-setup.ps1 (Windows): ffmpeg, Node, uv, Python libraries, Remotion.
    Needs no admin rights; safe to run again (the Cài công cụ button)."""
    check_install_dir(install_dir)
    say("Cài công cụ và thư viện (om-setup) …")
    env = dict(os.environ, PATH=tool_paths(), NONINTERACTIVE="1", PYTHONIOENCODING="utf-8")
    if IS_WIN:
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               os.path.join(install_dir, "om-setup.ps1")]
        flags = 0x08000000                         # CREATE_NO_WINDOW: no console flashing up
    else:
        cmd, flags = ["/bin/bash", os.path.join(install_dir, "om-setup.sh")], 0
    if not os.path.isfile(cmd[-1]):
        raise UpdateError("Thư mục này chưa có OM (thiếu om-setup) — bấm Cài trước")
    try:
        p = subprocess.Popen(cmd, cwd=install_dir, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                             creationflags=flags)
    except OSError as e:
        raise UpdateError(f"Không chạy được om-setup: {e}")
    for line in p.stdout:
        log(f"setup: {line.rstrip()}")
        if line.strip():
            say(line.strip()[:110])
    if p.wait() != 0:
        raise UpdateError("Cài công cụ lỗi — bấm Log để xem, rồi bấm Cài công cụ để thử lại")


def open_path(path):
    """Show a file or folder with the system's own app."""
    if IS_WIN:
        os.startfile(path)
    else:
        subprocess.Popen(["open" if IS_MAC else "xdg-open", path])


def _claude_cli():
    home = os.path.expanduser("~")
    return shutil.which("claude", path=os.pathsep.join(
        [os.path.join(home, ".local", "bin"), os.path.join(home, ".claude", "local"), "/opt/homebrew/bin",
         "/usr/local/bin", os.path.join(os.environ.get("APPDATA", ""), "npm"), os.environ.get("PATH", "")]))


def open_claude(install_dir):
    """Claude Code in the OpenMontage folder: a new Code session of the Claude app on that folder (its
    claude://code/new?folder= link) where the app exists; else the claude CLI in a terminal window."""
    url = "claude://code/new?folder=" + urllib.parse.quote(install_dir, safe="") + "&source=services"
    if IS_MAC and (os.path.isdir("/Applications/Claude.app")
                   or os.path.isdir(os.path.expanduser("~/Applications/Claude.app"))):
        subprocess.Popen(["open", url])
        return
    if IS_WIN and os.path.isdir(os.path.join(os.environ.get("LOCALAPPDATA", ""), "AnthropicClaude")):
        os.startfile(url)
        return
    cli = _claude_cli()
    if not cli:
        raise UpdateError("Máy chưa có Claude — cài app Claude (claude.ai/download) hoặc Claude Code trước")
    if IS_MAC:
        cmd = f"cd {_q(install_dir)} && {_q(cli)}"
        script = f'tell application "Terminal" to do script "{cmd}"'
        subprocess.Popen(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'])
    elif IS_WIN:
        subprocess.Popen(["cmd.exe", "/c", "start", "OpenMontage", "cmd.exe", "/k", cli], cwd=install_dir)
    else:
        for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["konsole", "-e"], ["xterm", "-e"]):
            if shutil.which(term[0]):
                subprocess.Popen(term + ["bash", "-lc", f"cd {_q(install_dir)} && {_q(cli)}; exec bash"])
                return
        raise UpdateError("Không tìm thấy cửa sổ Terminal để mở Claude")


def _q(s):
    """Shell-quote for a command that also sits inside an AppleScript string."""
    return "'" + s.replace("'", "'\\''").replace("\\", "\\\\").replace('"', '\\"') + "'"


if __name__ == "__main__":       # quick terminal use:  python update_core.py list | install <ver> <folder>
    try:
        if sys.argv[1:2] == ["list"]:
            for r in fetch_releases():
                print(r["version"], r["date"], r["sha256"][:12], r["notes"])
        elif sys.argv[1:2] == ["install"] and len(sys.argv) == 4:
            rel = next(r for r in fetch_releases() if r["version"] == sys.argv[2])
            download(rel)
            install(sys.argv[2], sys.argv[3], print)
        else:
            print(__doc__)
    except UpdateError as e:
        sys.exit(f"LỖI: {e}")
