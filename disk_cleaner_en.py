# -*- coding: utf-8 -*-
"""
Disk Cleaner (English)
- Analyze cleanable temp files / caches / Recycle Bin, etc.
- Check items then clean (deleted contents go to Recycle Bin, recoverable)
- Dangerous items are unchecked by default
Pure standard library, no third-party dependencies.
"""

import os
import sys
import shutil
import threading
import queue
import time
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox


# ---------------------------------------------------------------- recycle-bin delete
FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_uint),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def send_to_recycle(path):
    """Move path (e.g. C:\\dir\\* for directory contents) to Recycle Bin. Returns (ok, code)"""
    try:
        abspath = os.path.abspath(path)
        buf = ctypes.create_unicode_buffer(abspath + "\0\0")
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = ctypes.cast(buf, wintypes.LPCWSTR)
        op.pTo = None
        op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI
        op.fAnyOperationsAborted = False
        op.hNameMappings = None
        op.lpszProgressTitle = None
        ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return (ret == 0), ret
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def recycle_bin_info():
    """Return (total bytes, item count)"""
    try:
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        ret = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if ret == 0:
            return info.i64Size, info.i64NumItems
    except Exception:  # noqa: BLE001
        pass
    return 0, 0


def empty_recycle_bin():
    SHERB_NOCONFIRMATION = 0x1
    SHERB_NOPROGRESSUI = 0x2
    SHERB_NOSOUND = 0x4
    try:
        ret = ctypes.windll.shell32.SHEmptyRecycleBinW(
            None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        )
        return ret == 0
    except Exception:  # noqa: BLE001
        return False


def open_recycle_bin():
    """Open the system Recycle Bin window so the user can restore deleted files"""
    try:
        ctypes.windll.shell32.ShellExecuteW(
            None, "open", "::{645FF040-5081-101B-9F08-00AA002F954E}", None, None, 1
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------- utils
def env(name, fallback=""):
    v = os.environ.get(name)
    return v if v else fallback


def app_dir():
    """Directory of the program (works for both frozen exe and source)"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


USERPROFILE = env("USERPROFILE", "C:\\")
LOCALAPPDATA = env("LOCALAPPDATA", os.path.join(USERPROFILE, "AppData", "Local"))
APPDATA = env("APPDATA", os.path.join(USERPROFILE, "AppData", "Roaming"))
TEMP = env("TEMP", os.path.join(LOCALAPPDATA, "Temp"))
WINDIR = env("WINDIR", "C:\\Windows")


def fmt_size(n):
    if n < 1024:
        return "%d B" % n
    if n < 1024 ** 2:
        return "%.1f KB" % (n / 1024)
    if n < 1024 ** 3:
        return "%.1f MB" % (n / 1024 ** 2)
    return "%.2f GB" % (n / 1024 ** 3)


def scan_dir(path):
    """Compute directory total size and file count, ignoring permission/lock errors."""
    if not os.path.isdir(path):
        return 0, 0
    total = 0
    count = 0
    for root, dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
                count += 1
            except OSError:
                pass
    return total, count


def firefox_cache_paths():
    paths = []
    base = os.path.join(APPDATA, "Mozilla", "Firefox", "Profiles")
    if os.path.isdir(base):
        for d in os.listdir(base):
            c = os.path.join(base, d, "cache2")
            if os.path.isdir(c):
                paths.append(c)
    return paths


def build_items():
    chrome = os.path.join(LOCALAPPDATA, "Google", "Chrome", "User Data")
    edge = os.path.join(LOCALAPPDATA, "Microsoft", "Edge", "User Data")
    chrome_paths = []
    edge_paths = []
    for profile in ("Default", "System Profile", "Profile 1"):
        for sub in ("Cache", "Code Cache", "GPUCache"):
            chrome_paths.append(os.path.join(chrome, profile, sub))
            edge_paths.append(os.path.join(edge, profile, sub))

    return [
        {"id": "user_temp", "name": "User Temp Files", "safe": True, "default": True,
         "paths": [TEMP, os.path.join(LOCALAPPDATA, "Temp")],
         "desc": "Temporary files from applications"},
        {"id": "win_temp", "name": "Windows Temp Files", "safe": True, "default": True,
         "paths": [os.path.join(WINDIR, "Temp")],
         "desc": "System temp files (admin required)"},
        {"id": "chrome_cache", "name": "Chrome Cache", "safe": True, "default": True,
         "paths": chrome_paths, "desc": "Browser web cache"},
        {"id": "edge_cache", "name": "Edge Cache", "safe": True, "default": True,
         "paths": edge_paths, "desc": "Browser web cache"},
        {"id": "firefox_cache", "name": "Firefox Cache", "safe": True, "default": True,
         "paths": firefox_cache_paths(), "desc": "Browser web cache"},
        {"id": "thumb_cache", "name": "Thumbnail Cache", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "Explorer")],
         "desc": "Explorer thumbnails"},
        {"id": "inet_cache", "name": "IE/System Network Cache", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "INetCache")],
         "desc": "Legacy browser cache"},
        {"id": "pip_cache", "name": "pip Cache", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "pip", "cache")],
         "desc": "Python package download cache"},
        {"id": "npm_cache", "name": "npm Cache", "safe": True, "default": True,
         "paths": [os.path.join(APPDATA, "npm-cache"), os.path.join(LOCALAPPDATA, "npm-cache")],
         "desc": "Node package download cache"},
        {"id": "yarn_cache", "name": "yarn Cache", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "Yarn", "Cache")],
         "desc": "Node package download cache"},
        {"id": "dot_cache", "name": "User .cache", "safe": True, "default": True,
         "paths": [os.path.join(USERPROFILE, ".cache")],
         "desc": "Cache directories of various tools"},
        {"id": "win_update", "name": "Windows Update Cache", "safe": True, "default": True,
         "paths": [os.path.join(WINDIR, "SoftwareDistribution", "Download")],
         "desc": "Leftover downloads of installed updates (admin required)"},
        {"id": "recycle_bin", "name": "Recycle Bin", "safe": False, "default": False,
         "paths": [], "special": "recycle_bin",
         "desc": "Empty the Recycle Bin (irreversible)"},
        {"id": "downloads", "name": "Downloads Folder", "safe": False, "default": False,
         "paths": [os.path.join(USERPROFILE, "Downloads")],
         "desc": "WARNING: deletes ALL contents of Downloads (moved to Recycle Bin). Use with caution"},
    ]


# ---------------------------------------------------------------- application
class CleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Disk Cleaner")
        self.root.geometry("920x620")
        self.root.minsize(760, 480)

        self.items = build_items()
        self.results = {}   # id -> {"size":int,"count":int}
        self.checked = {}   # id -> bool
        for it in self.items:
            self.checked[it["id"]] = it["default"]

        self.msg_queue = queue.Queue()
        self.busy = False
        self.history_path = os.path.join(app_dir(), "clean_history.log")

        self._setup_style()
        self._build_ui()
        self._update_disk()
        self.root.after(100, self._poll_queue)
        self.start_scan()

    # ------------------------------------------------------------ style
    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.C_PRIMARY = "#2E7CF6"
        self.C_PRIMARY_DARK = "#1B5FC4"
        self.C_BG = "#F0F2F5"
        self.C_CARD = "#FFFFFF"
        self.C_DANGER = "#E5484D"
        self.C_TEXT = "#1F2329"
        self.C_MUTED = "#8A9099"

        self.root.configure(bg=self.C_BG)

        fb = ("Microsoft YaHei UI", 9)
        fbold = ("Microsoft YaHei UI", 9, "bold")

        style.configure("TFrame", background=self.C_BG)
        style.configure("Card.TFrame", background=self.C_CARD)
        style.configure("Header.TFrame", background=self.C_PRIMARY)

        style.configure("TLabel", background=self.C_BG, foreground=self.C_TEXT, font=fb)
        style.configure("HeaderTitle.TLabel", background=self.C_PRIMARY, foreground="#FFFFFF",
                        font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("HeaderSub.TLabel", background=self.C_PRIMARY, foreground="#D6E4FF",
                        font=("Microsoft YaHei UI", 9))
        style.configure("Card.TLabel", background=self.C_CARD, foreground=self.C_TEXT, font=fb)
        style.configure("CardTitle.TLabel", background=self.C_CARD, foreground=self.C_TEXT,
                        font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Muted.TLabel", background=self.C_CARD, foreground=self.C_MUTED,
                        font=("Microsoft YaHei UI", 8))

        style.configure("TButton", font=fb, padding=(12, 7), background="#FFFFFF", borderwidth=0)
        style.map("TButton", background=[("active", "#E7EDF5")])

        style.configure("Accent.TButton", background=self.C_PRIMARY, foreground="#FFFFFF",
                        font=fbold, padding=(18, 8), borderwidth=0)
        style.map("Accent.TButton",
                  background=[("active", self.C_PRIMARY_DARK), ("disabled", "#B9CBE8")],
                  foreground=[("disabled", "#FFFFFF")])

        style.configure("Treeview", font=fb, rowheight=32, background=self.C_CARD,
                        fieldbackground=self.C_CARD, foreground=self.C_TEXT, borderwidth=0)
        style.configure("Treeview.Heading", font=fbold, background="#E8EDF3",
                        foreground=self.C_TEXT, relief="flat")
        style.map("Treeview",
                  background=[("selected", "#D6E6FF")],
                  foreground=[("selected", self.C_TEXT)])
        style.map("Treeview.Heading", background=[("active", "#DDE4ED")])

        style.configure("Disk.Horizontal.TProgressbar", troughcolor="#E3E8EF",
                        background=self.C_PRIMARY, thickness=16, borderwidth=0)
        style.configure("TProgressbar", troughcolor="#E3E8EF", background=self.C_PRIMARY,
                        thickness=10, borderwidth=0)

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        pad = 12

        # header banner
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Disk Cleaner", style="HeaderTitle.TLabel").pack(anchor="w", padx=20, pady=(16, 2))
        ttk.Label(header, text="Safely clean C: temp files & caches · deleted items are recoverable", style="HeaderSub.TLabel").pack(anchor="w", padx=20, pady=(0, 16))

        # disk space card
        disk_card = ttk.Frame(self.root, style="Card.TFrame")
        disk_card.pack(fill="x", padx=pad, pady=(pad, 6))
        self.disk_label = ttk.Label(disk_card, text="Reading disk info...", style="Card.TLabel",
                                    font=("Microsoft YaHei UI", 11, "bold"))
        self.disk_label.pack(anchor="w", padx=14, pady=(12, 8))
        self.disk_bar = ttk.Progressbar(disk_card, style="Disk.Horizontal.TProgressbar", maximum=100)
        self.disk_bar.pack(fill="x", padx=14, pady=(0, 6))
        self.admin_label = ttk.Label(disk_card, text="", style="Muted.TLabel")
        self.admin_label.pack(anchor="w", padx=14, pady=(0, 10))

        # list card
        list_card = ttk.Frame(self.root, style="Card.TFrame")
        list_card.pack(fill="both", expand=True, padx=pad, pady=6)
        cols = ("check", "name", "size", "count", "desc")
        self.tree = ttk.Treeview(list_card, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("check", text="")
        self.tree.heading("name", text="Item")
        self.tree.heading("size", text="Size")
        self.tree.heading("count", text="Files")
        self.tree.heading("desc", text="Description")
        self.tree.column("check", width=44, anchor="center", stretch=False)
        self.tree.column("name", width=165, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("count", width=80, anchor="e")
        self.tree.column("desc", width=430, anchor="w")
        self.tree.tag_configure("danger", foreground=self.C_DANGER)
        vsb = ttk.Scrollbar(list_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        vsb.pack(side="right", fill="y", padx=(0, 6), pady=10)
        self.tree.bind("<Button-1>", self._on_click)

        # bottom action bar
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=pad, pady=(6, pad))
        self.selected_label = ttk.Label(bottom, text="Selected: 0 B", font=("Microsoft YaHei UI", 10, "bold"))
        self.selected_label.pack(side="left")
        ttk.Button(bottom, text="Select All", command=lambda: self._set_all(True)).pack(side="right", padx=3)
        ttk.Button(bottom, text="Select None", command=lambda: self._set_all(False)).pack(side="right", padx=3)
        ttk.Button(bottom, text="Analyze", command=self.start_scan).pack(side="right", padx=3)
        ttk.Button(bottom, text="Open Recycle Bin", command=self._open_recycle).pack(side="right", padx=3)
        self.clean_btn = ttk.Button(bottom, text="Clean Selected", style="Accent.TButton", command=self.start_clean)
        self.clean_btn.pack(side="right", padx=(3, 0))

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=pad)

        # log
        logf = ttk.LabelFrame(self.root, text="Log")
        logf.pack(fill="x", padx=pad, pady=(6, 0))
        self.log = tk.Text(logf, height=5, state="disabled", wrap="word", relief="flat",
                           bg="#FAFBFC", fg=self.C_TEXT, font=("Microsoft YaHei UI", 9))
        lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True, padx=4, pady=4)
        lsb.pack(side="right", fill="y")

    def _update_disk(self):
        try:
            total, used, free = shutil.disk_usage("C:\\")
            pct = used / total * 100
            self.disk_label.config(
                text="C: Total %s / Used %s / Free %s (%.0f%% used)"
                % (fmt_size(total), fmt_size(used), fmt_size(free), pct)
            )
            self.disk_bar.config(value=pct)
            self.admin_label.config(
                text="Running as administrator" if is_admin() else "Not running as admin; Windows/update caches may fail to clean"
            )
        except OSError:
            self.disk_label.config(text="Failed to read C: drive space")

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        try:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.history_path, "a", encoding="utf-8") as f:
                f.write("[%s] %s\n" % (stamp, text))
        except OSError:
            pass

    # ------------------------------------------------------------ interaction
    def _on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if row and col == "#1":
            iid = row
            self.checked[iid] = not self.checked.get(iid, False)
            self._refresh_row(iid)
            self._update_selected()

    def _is_safe(self, iid):
        for it in self.items:
            if it["id"] == iid:
                return it.get("safe", True)
        return True

    def _refresh_row(self, iid):
        mark = "☑" if self.checked.get(iid) else "☐"
        r = self.results.get(iid, {})
        size = fmt_size(r.get("size", 0))
        count = str(r.get("count", 0))
        tags = () if self._is_safe(iid) else ("danger",)
        self.tree.item(iid, values=(mark, self._name_of(iid), size, count, self._desc_of(iid)), tags=tags)

    def _name_of(self, iid):
        for it in self.items:
            if it["id"] == iid:
                return it["name"]
        return iid

    def _desc_of(self, iid):
        for it in self.items:
            if it["id"] == iid:
                return it["desc"]
        return ""

    def _set_all(self, val):
        for iid in self.tree.get_children():
            self.checked[iid] = val
            self._refresh_row(iid)
        self._update_selected()

    def _update_selected(self):
        total = 0
        for it in self.items:
            if self.checked.get(it["id"]):
                total += self.results.get(it["id"], {}).get("size", 0)
        self.selected_label.config(text="Selected: %s" % fmt_size(total))

    def _open_recycle(self):
        if open_recycle_bin():
            self._log("Recycle Bin opened. Right-click items there to restore deleted files.")
        else:
            self._log("Failed to open Recycle Bin")

    # ------------------------------------------------------------ scan
    def start_scan(self):
        if self.busy:
            return
        self.busy = True
        self._log("Analyzing...")
        self.tree.delete(*self.tree.get_children())
        for it in self.items:
            tags = () if it.get("safe", True) else ("danger",)
            self.tree.insert("", "end", iid=it["id"],
                             values=("☐" if not self.checked[it["id"]] else "☑",
                                     it["name"], "Scanning...", "-", it["desc"]), tags=tags)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        for it in self.items:
            if it.get("special") == "recycle_bin":
                size, count = recycle_bin_info()
            else:
                size = 0
                count = 0
                for p in it["paths"]:
                    s, c = scan_dir(p)
                    size += s
                    count += c
            self.msg_queue.put(("scan_done", it["id"], size, count))
        self.msg_queue.put(("scan_finish",))

    # ------------------------------------------------------------ clean
    def start_clean(self):
        if self.busy:
            return
        selected = [it for it in self.items if self.checked.get(it["id"])]
        if not selected:
            messagebox.showinfo("Notice", "Please select items to clean first")
            return
        total = sum(self.results.get(it["id"], {}).get("size", 0) for it in selected)
        if total <= 0:
            messagebox.showinfo("Notice", "The selected items have nothing to clean")
            return
        if not messagebox.askyesno(
            "Confirm Cleaning",
            "Will clean %d item(s), totaling %s.\n\n"
            "Temp files / caches are moved to the Recycle Bin (recoverable);\n"
            "the \"Recycle Bin\" item is emptied permanently (irreversible).\n\nContinue?" % (len(selected), fmt_size(total)),
        ):
            return
        self.busy = True
        self.clean_btn.config(state="disabled")
        self.progress.config(maximum=len(selected), value=0)
        self._log("Cleaning...")
        threading.Thread(target=self._clean_worker, args=(selected,), daemon=True).start()

    def _clean_worker(self, selected):
        for idx, it in enumerate(selected):
            self.msg_queue.put(("clean_item", it["id"], idx))
            if it.get("special") == "recycle_bin":
                ok = empty_recycle_bin()
                self.msg_queue.put(("log", "Recycle Bin: %s" % ("emptied" if ok else "failed to empty")))
            else:
                cleaned_any = False
                for p in it["paths"]:
                    if not os.path.isdir(p):
                        continue
                    ok, err = send_to_recycle(os.path.join(p, "*"))
                    cleaned_any = cleaned_any or ok
                    if ok:
                        self.msg_queue.put(("log", "  Cleaned: %s" % p))
                    else:
                        self.msg_queue.put(("log", "  Failed (skipped): %s  [%s]" % (p, err)))
                if not cleaned_any:
                    self.msg_queue.put(("log", "  %s: nothing to clean or all failed" % it["name"]))
            self.msg_queue.put(("clean_done", it["id"]))
        self.msg_queue.put(("clean_finish",))

    # ------------------------------------------------------------ queue polling
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "scan_done":
                    _, iid, size, count = msg
                    self.results[iid] = {"size": size, "count": count}
                    self._refresh_row(iid)
                    self._update_selected()
                elif kind == "scan_finish":
                    self.busy = False
                    self._update_disk()
                    self._log("Analysis complete.")
                elif kind == "clean_item":
                    self.progress.config(value=msg[2])
                elif kind == "clean_done":
                    pass
                elif kind == "log":
                    self._log(msg[1])
                elif kind == "clean_finish":
                    self.busy = False
                    self.clean_btn.config(state="normal")
                    self.progress.config(value=self.progress["maximum"])
                    self._update_disk()
                    self._log("Cleaning complete. Files moved to Recycle Bin; click \"Open Recycle Bin\" to restore. Re-analyzing...")
                    # re-scan after cleaning to refresh sizes
                    self.start_scan()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    CleanerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
