"""OM MAVA Updater window (Tkinter): the look of CHECK VIDEO (charcoal / orange, light + dark, Inter), the layout
of the OpenMontage updater: version in use, newer version, OpenMontage folder, version history with
download / rollback, footer with last check + log. Network and installs run in a worker thread; the window
only reads results from a queue.
"""
import ctypes, glob, os, queue, subprocess, sys, threading, time, tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import update_core as core

APP_VERSION = "1.0.0"
THEMES = {   # same values as CHECK VIDEO (engine/qc_gui.py)
    "dark": dict(BG="#0f0f10", PANEL="#18181b", LINE="#2a2a2e", TEXT="#ececee", MUTED="#8b8b93", ORANGE="#f26b1d",
                 ORANGE_DARK="#c4530f", INK="#1b1b1b", GREEN="#3ecf8e", AMBER="#f5a524", RED="#ff5a4e",
                 BTN="#26262b", BTN_HOVER="#323238", BTN_LINE="#2f2f35", FOOT="#141416",
                 TAG_NEW=("#4a2611", "#f5a524"), TAG_USE=("#123524", "#3ecf8e"), TAG_LOCAL=("#1d2333", "#9db4ff")),
    "light": dict(BG="#f4f5f7", PANEL="#ffffff", LINE="#e1e4e9", TEXT="#1b1e23", MUTED="#6b7280", ORANGE="#e8590c",
                  ORANGE_DARK="#c2410c", INK="#fffffe", GREEN="#17a76b", AMBER="#b26a00", RED="#d92d20",
                  BTN="#fffffc", BTN_HOVER="#eef0f4", BTN_LINE="#d3d8e0", FOOT="#eceef2",
                  TAG_NEW=("#fde6d6", "#b54708"), TAG_USE=("#dcf5e8", "#117a4f"), TAG_LOCAL=("#e3e9fb", "#3a56b0")),
}
C = dict(THEMES["dark"])
HAND = "pointinghand" if sys.platform == "darwin" else "hand2"


def load_fonts():
    """Bundled Inter (fonts/) for this process only; else the system UI font."""
    files = glob.glob(os.path.join(HERE, "fonts", "Inter-*.ttf"))
    if sys.platform == "darwin" and files:
        try:
            cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            ct = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long,
                                                                   ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
            for f in files:
                b = f.encode()
                ct.CTFontManagerRegisterFontsForURL(cf.CFURLCreateFromFileSystemRepresentation(None, b, len(b), False),
                                                    1, None)
            return "Inter"
        except (OSError, AttributeError):
            pass
    if sys.platform == "win32" and files:
        try:                                         # FR_PRIVATE: this process only, nothing installed
            for f in files:
                ctypes.windll.gdi32.AddFontResourceExW(f, 0x10, 0)
            return "Inter"
        except (OSError, AttributeError):
            pass
    return {"darwin": "Helvetica Neue", "win32": "Segoe UI"}.get(sys.platform, "DejaVu Sans")


def rounded(cv, x0, y0, x1, y1, r, **kw):
    """Rounded rectangle on a canvas (Tk on macOS antialiases canvas shapes)."""
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r,
           x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


class Button(tk.Canvas):
    def __init__(self, parent, text, command, primary=False, width=None):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0, cursor=HAND)
        self.text, self.command, self.primary, self.fixed = text, command, primary, width
        self.enabled, self.hover = True, False
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.bind("<Enter>", lambda e: self._hover(True))
        self.bind("<Leave>", lambda e: self._hover(False))
        self.draw()

    def draw(self):
        f = tkfont.Font(family=FONT, size=11, weight="bold" if self.primary else "normal")
        w, h = self.fixed or f.measure(self.text) + 32, 32
        self.config(width=w, height=h, bg=self.master.cget("bg"))
        self.delete("all")
        if self.primary:
            fill, line, fg = (C["ORANGE_DARK"] if self.hover else C["ORANGE"]), "", C["INK"]
        else:
            fill, line, fg = (C["BTN_HOVER"] if self.hover else C["BTN"]), C["BTN_LINE"], C["TEXT"]
        if not self.enabled:
            fg = C["MUTED"]
        rounded(self, 1, 1, w - 1, h - 1, 7, fill=fill, outline=line or fill)
        self.create_text(w // 2, h // 2, text=self.text, fill=fg, font=f)

    def _hover(self, on):
        self.hover = on and self.enabled
        self.draw()

    def enable(self, on):
        self.enabled = on
        self.config(cursor=HAND if on else "arrow")
        self.draw()


class Card(tk.Canvas):
    """Rounded panel holding `body`, repainted to its size."""
    def __init__(self, parent):
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.body = tk.Frame(self, bg=C["PANEL"])
        self.win = self.create_window(18, 16, window=self.body, anchor="nw")
        self.bind("<Configure>", self._paint)
        self.body.bind("<Configure>", lambda e: self.config(height=e.height + 32))

    def _paint(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("bg")
        rounded(self, 1, 1, w - 1, h - 1, 10, fill=C["PANEL"], outline=C["LINE"], tags="bg")
        self.tag_lower("bg")
        self.itemconfig(self.win, width=max(w - 36, 1))


def ddmmyyyy(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso) >= 10 else iso


def tag(parent, text, colors):
    """Status pill: at least 96 wide (rows line up), wider when the text needs it."""
    bg, fg = colors
    f = tkfont.Font(family=FONT, size=10)
    w = max(96, f.measure(text) + 24)
    cv = tk.Canvas(parent, width=w, height=22, bg=parent.cget("bg"), highlightthickness=0, bd=0)
    rounded(cv, 1, 1, w - 1, 21, 10, fill=bg, outline=bg)
    cv.create_text(w // 2, 11, text=text, fill=fg, font=f)
    return cv


class App:
    def __init__(self, root):
        self.root, self.q = root, queue.Queue()
        self.cfg = core.load_config()
        self.theme = self.cfg.get("theme", "dark")
        C.update(THEMES[self.theme])
        self.releases, self.busy, self.checked_at, self.message = self.cfg.get("releases_cache", []), False, None, None
        root.title("OM MAVA Updater")
        root.geometry(self.cfg.get("geometry", "820x820"))
        root.minsize(640, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.build()
        root.after(100, self.poll)
        self.refresh()

    # ---------- layout ----------
    def build(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=C["BG"])
        install = self.cfg.get("install_dir") or ""
        current = core.installed_version(install) if install else None

        head = tk.Frame(self.root, bg=C["BG"])
        head.pack(fill="x", padx=20, pady=16)
        self.draw_mark(head, 36).pack(side="left", padx=(0, 12))
        titles = tk.Frame(head, bg=C["BG"])
        titles.pack(side="left", fill="x", expand=True)
        name = tk.Frame(titles, bg=C["BG"])
        name.pack(anchor="w")
        tk.Label(name, text="MAVA", bg=C["BG"], fg=C["ORANGE"], font=(FONT, 15, "bold")).pack(side="left")
        tk.Label(name, text="OPENMONTAGE", bg=C["BG"], fg=C["TEXT"], font=(FONT, 15, "bold")).pack(side="left",
                                                                                                   padx=(5, 0))
        tk.Label(titles, text=f"Updater · đang dùng {('v' + current) if current else '—'}", bg=C["BG"], fg=C["MUTED"],
                 font=(FONT, 11)).pack(anchor="w", pady=(2, 0))
        Button(head, "Cài đặt", self.settings).pack(side="right")
        src = core.token_source()
        tag(head, {"user": "Token riêng", "bundled": "Đã kết nối"}.get(src, "Chưa có token"),
            C["TAG_USE"] if src else C["TAG_NEW"]).pack(side="right", padx=8)
        tk.Frame(self.root, bg=C["LINE"], height=1).pack(fill="x")

        foot = tk.Frame(self.root, bg=C["FOOT"])
        foot.pack(side="bottom", fill="x")
        tk.Frame(self.root, bg=C["LINE"], height=1).pack(side="bottom", fill="x")
        color = C["RED"] if self.message and self.message[0] == "err" else C["GREEN"]
        text = self.message[1] if self.message else (
            f"Đã kiểm tra bản mới lúc {self.checked_at}" if self.checked_at else "Chưa kiểm tra")
        self.status = tk.Label(foot, text=text, bg=C["FOOT"], fg=color, font=(FONT, 11), anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=20, pady=8)
        for label, cmd in (("Sáng" if self.theme == "dark" else "Tối", self.toggle_theme),
                           ("Log", self.open_log),
                           (f"v{APP_VERSION}", None)):
            l = tk.Label(foot, text=label, bg=C["FOOT"], fg=C["MUTED"], font=(FONT, 11),
                         cursor=HAND if cmd else "arrow")
            l.pack(side="right", padx=(0, 16))
            if cmd:
                l.bind("<Button-1>", lambda e, c=cmd: c())

        body = tk.Frame(self.root, bg=C["BG"])
        body.pack(fill="both", expand=True, padx=20, pady=16)
        newest = self.releases[0] if self.releases else None

        # 1. newest version
        c1 = Card(body)
        c1.pack(fill="x")
        b = c1.body
        if newest and current and core.version_key(newest["version"]) > core.version_key(current):
            t, sub = f"Có bản mới: v{newest['version']}", " · ".join(x for x in (newest["notes"], ddmmyyyy(newest["date"])) if x)
            Button(b, "Cập nhật", lambda: self.apply(newest), primary=True).pack(side="right")
        elif newest and current:
            t, sub = "Bạn đang dùng bản mới nhất", f"v{current}"
        elif newest:
            t, sub = f"Bản mới nhất: v{newest['version']}", "Chọn thư mục OpenMontage rồi bấm Cài"
            if install:
                Button(b, "Cài", lambda: self.apply(newest), primary=True).pack(side="right")
        else:
            t, sub = "Chưa có danh sách phiên bản", "Nhập token GitHub trong Cài đặt rồi bấm Làm mới"
        left = tk.Frame(b, bg=C["PANEL"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=t, bg=C["PANEL"], fg=C["TEXT"], font=(FONT, 13, "bold"), anchor="w").pack(fill="x")
        tk.Label(left, text=sub, bg=C["PANEL"], fg=C["MUTED"], font=(FONT, 11), anchor="w").pack(fill="x", pady=(4, 0))

        # 2. install folder
        c2 = Card(body)
        c2.pack(fill="x", pady=(12, 0))
        b = c2.body
        claude = Button(b, "Mở Claude", lambda: self.open_claude(install))
        claude.pack(side="right")
        claude.enable(bool(install) and os.path.isdir(install))
        Button(b, "Đổi thư mục", self.choose_dir).pack(side="right", padx=8)
        left = tk.Frame(b, bg=C["PANEL"], width=1)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Thư mục OpenMontage", bg=C["PANEL"], fg=C["TEXT"], font=(FONT, 13, "bold"),
                 anchor="w").pack(fill="x")
        path = install or "Chưa chọn — bấm Đổi thư mục"
        tk.Label(left, text=path if len(path) <= 60 else "…" + path[-59:], bg=C["PANEL"], fg=C["MUTED"],
                 font=(FONT, 11), anchor="w").pack(fill="x", pady=(4, 0))

        # 3. tools (ffmpeg, Node, Python, Remotion) — installed by om-setup, no admin rights
        c4 = Card(body)
        c4.pack(fill="x", pady=(12, 0))
        b = c4.body
        has_om = bool(install) and os.path.isfile(os.path.join(install, "AGENTS.md"))
        status = core.tool_status(install) if has_om else []
        missing = [n for n, ok in status if not ok]
        self.tools_btn = Button(b, "Cài công cụ" if missing or not status else "Cài lại công cụ", self.install_tools,
                                primary=bool(missing))
        self.tools_btn.pack(side="right")
        self.tools_btn.enable(has_om)
        left = tk.Frame(b, bg=C["PANEL"], width=1)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Công cụ", bg=C["PANEL"], fg=C["TEXT"], font=(FONT, 13, "bold"), anchor="w").pack(fill="x")
        row = tk.Frame(left, bg=C["PANEL"])
        row.pack(fill="x", pady=(6, 0))
        if status:
            for n, ok in status:
                tag(row, f"{n} {'✓' if ok else '—'}", C["TAG_USE"] if ok else C["TAG_NEW"]).pack(side="left", padx=(0, 6))
        else:
            tk.Label(row, text="Cài OM trước, rồi app tự cài ffmpeg, Node, Python, Remotion", bg=C["PANEL"],
                     fg=C["MUTED"], font=(FONT, 11), anchor="w").pack(fill="x")

        # 4. history
        c3 = Card(body)
        c3.pack(fill="x", pady=(12, 0))
        b = c3.body
        top = tk.Frame(b, bg=C["PANEL"])
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="Lịch sử phiên bản", bg=C["PANEL"], fg=C["TEXT"], font=(FONT, 13, "bold")).pack(side="left")
        self.refresh_btn = Button(top, "Làm mới", self.refresh)
        self.refresh_btn.pack(side="right")
        local = set(core.local_versions())
        rows = self.releases[:8]
        for rel in rows:
            v = rel["version"]
            tk.Frame(b, bg=C["LINE"], height=1).pack(fill="x")
            row = tk.Frame(b, bg=C["PANEL"])
            row.pack(fill="x", pady=8)
            row.columnconfigure(0, weight=1)
            row.columnconfigure(2, minsize=124)            # pills of different widths, same column
            tk.Label(row, text=f"v{v}", bg=C["PANEL"], fg=C["TEXT"], font=(FONT, 11), anchor="w").grid(row=0, column=0,
                                                                                                      sticky="w")
            tk.Label(row, text=ddmmyyyy(rel["date"]), bg=C["PANEL"],
                     fg=C["MUTED"], font=(FONT, 11), width=10).grid(row=0, column=1, padx=8)
            if v == current:
                tag(row, "Đang dùng", C["TAG_USE"]).grid(row=0, column=2, padx=8)
                tk.Frame(row, bg=C["PANEL"], width=112, height=30).grid(row=0, column=3)
            elif v in local:
                tag(row, "Có trong máy", C["TAG_LOCAL"]).grid(row=0, column=2, padx=8)
                Button(row, "Rollback" if current and core.version_key(v) < core.version_key(current) else "Dùng bản này",
                       lambda r=rel: self.apply(r), width=112).grid(row=0, column=3)
            else:
                tag(row, "Chưa tải", C["TAG_NEW"]).grid(row=0, column=2, padx=8)
                newer = not current or core.version_key(v) > core.version_key(current)
                Button(row, "Cập nhật" if newer else "Tải & rollback", lambda r=rel: self.apply(r), primary=newer,
                       width=112).grid(row=0, column=3)
        if not rows:
            tk.Label(b, text="Chưa có bản nào", bg=C["PANEL"], fg=C["MUTED"], font=(FONT, 11)).pack(anchor="w")
        tk.Label(b, text=f"Giữ tối đa {self.cfg['keep_versions']} phiên bản gần nhất trên máy", bg=C["PANEL"],
                 fg=C["MUTED"], font=(FONT, 11)).pack(anchor="w", pady=(8, 0))
        self.set_busy(self.busy)

    def draw_mark(self, parent, size):
        """The app icon (mark.png, drawn by make_icon.py) shown at `size` points."""
        try:
            if not hasattr(self, "_mark"):
                self._mark = tk.PhotoImage(file=os.path.join(HERE, "mark.png"))
                f = max(1, self._mark.width() // size)
                self._mark_small = self._mark.subsample(f) if f > 1 else self._mark
            return tk.Label(parent, image=self._mark_small, bg=C["BG"], bd=0)
        except tk.TclError:
            return tk.Frame(parent, bg=C["BG"], width=size, height=size)

    # ---------- actions ----------
    def set_busy(self, on):
        self.busy = on
        if hasattr(self, "refresh_btn"):
            self.refresh_btn.enable(not on)
        if hasattr(self, "tools_btn") and on:
            self.tools_btn.enable(False)

    def say(self, text, kind="ok"):
        self.message = (kind, text)
        self.status.config(text=text, fg=C["RED"] if kind == "err" else C["GREEN"])

    def work(self, fn, done=None):
        """Run fn() in a thread; its UI updates go through the queue."""
        if self.busy:
            return
        self.set_busy(True)

        def run():
            try:
                res = fn()
                self.q.put(("done", done, res))
            except core.UpdateError as e:
                self.q.put(("err", str(e)))
            except Exception as e:                     # unexpected: keep the window alive, log it
                core.log(f"error: {e!r}")
                self.q.put(("err", f"Lỗi: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "line":
                    self.say(item[1])
                elif item[0] == "err":
                    self.set_busy(False)
                    self.build()
                    self.say(item[1], "err")
                elif item[0] == "done":
                    self.set_busy(False)
                    if item[1]:
                        item[1](item[2])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def refresh(self):
        def got(rels):
            self.releases = rels
            self.cfg["releases_cache"] = rels
            core.save_config(self.cfg)
            self.checked_at = time.strftime("%H:%M")
            self.message = None
            self.build()
        if core.token():
            self.say("Đang kiểm tra bản mới…")
            self.work(core.fetch_releases, got)

    def apply(self, rel):
        install = self.cfg.get("install_dir")
        try:
            core.check_install_dir(install)
        except core.UpdateError as e:
            return self.say(str(e), "err")
        current = core.installed_version(install)
        verb = "Cập nhật lên" if not current or core.version_key(rel["version"]) > core.version_key(current) \
            else "Rollback về"
        if not messagebox.askyesno("OM MAVA Updater", f"{verb} v{rel['version']}?\n\nThư mục: {install}\n"
                                   "Đang làm phim nào thì chờ xong bước đang chạy rồi hãy cập nhật.\nKhoá API và phim không bị đụng tới."):
            return
        line = lambda s: self.q.put(("line", s))

        def go():
            line(f"Đang tải v{rel['version']}…")
            core.download(rel, lambda d, t: line(f"Đang tải v{rel['version']}… {d * 100 // t if t else 0}%"))
            core.install(rel["version"], install, line)
            core.prune(self.cfg["keep_versions"], protect={rel["version"]})
            return rel["version"]

        def done(v):
            self.message = ("ok", f"Đã cài v{v}")
            self.build()
        self.work(go, done)

    def install_tools(self):
        install = self.cfg.get("install_dir")
        line = lambda s: self.q.put(("line", s))

        def done(_):
            self.message = ("ok", "Đã cài xong công cụ")
            self.build()
        self.work(lambda: core.run_setup(install, line), done)

    def open_claude(self, install):
        try:
            core.open_claude(install)
        except core.UpdateError as e:
            messagebox.showerror("OM MAVA Updater", str(e), parent=self.root)

    def choose_dir(self):
        d = filedialog.askdirectory(title="Chọn thư mục OpenMontage", initialdir=self.cfg.get("install_dir") or os.path.expanduser("~"))
        if not d:
            return
        if not os.path.isfile(os.path.join(d, "AGENTS.md")) and os.listdir(d):
            if not messagebox.askyesno("OM MAVA Updater", "Thư mục này không có OpenMontage và không trống.\n"
                                       "Vẫn cài vào đây?"):
                return
        self.cfg["install_dir"] = d
        core.save_config(self.cfg)
        self.build()

    def settings(self):
        win = tk.Toplevel(self.root, bg=C["BG"], padx=20, pady=16)
        win.title("Cài đặt")
        win.transient(self.root)
        tk.Label(win, text="Token GitHub (chỉ đọc repo om-mava)", bg=C["BG"], fg=C["TEXT"],
                 font=(FONT, 13, "bold")).pack(anchor="w")
        tk.Label(win, text="Không bắt buộc: app đã có sẵn token. Nhập để dùng token riêng; để trống = giữ như cũ.", bg=C["BG"], fg=C["MUTED"],
                 font=(FONT, 11)).pack(anchor="w", pady=(2, 8))
        ent = tk.Entry(win, show="•", width=48, bg=C["PANEL"], fg=C["TEXT"], insertbackground=C["TEXT"],
                       relief="flat", highlightthickness=1, highlightbackground=C["LINE"], font=(FONT, 11))
        ent.pack(fill="x", ipady=6)
        tk.Label(win, text="Số phiên bản giữ trên máy", bg=C["BG"], fg=C["TEXT"], font=(FONT, 13, "bold")).pack(
            anchor="w", pady=(16, 6))
        keep = tk.Spinbox(win, from_=1, to=10, width=4, font=(FONT, 11))
        keep.delete(0, "end")
        keep.insert(0, str(self.cfg["keep_versions"]))
        keep.pack(anchor="w")

        def save():
            if ent.get().strip():
                core.save_token(ent.get())
            try:
                self.cfg["keep_versions"] = max(1, min(10, int(keep.get())))
            except ValueError:
                pass
            core.save_config(self.cfg)
            win.destroy()
            self.build()
            self.refresh()
        row = tk.Frame(win, bg=C["BG"])
        row.pack(fill="x", pady=(16, 0))
        Button(row, "Lưu", save, primary=True).pack(side="right")
        Button(row, "Huỷ", win.destroy).pack(side="right", padx=8)

    def open_log(self):
        os.makedirs(core.HOME, exist_ok=True)
        core.open_path(core.LOG if os.path.exists(core.LOG) else core.HOME)

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        C.update(THEMES[self.theme])
        self.cfg["theme"] = self.theme
        core.save_config(self.cfg)
        self.build()

    def close(self):
        self.cfg["geometry"] = self.root.geometry()
        core.save_config(self.cfg)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    FONT = load_fonts()
    App(root)
    root.mainloop()
