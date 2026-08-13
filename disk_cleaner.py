# -*- coding: utf-8 -*-
"""
C盘清理工具
- 分析可清理的临时文件 / 缓存 / 回收站等
- 勾选后清理（删除内容移入回收站，可恢复）
- 危险项默认不勾选
纯标准库实现，无需安装任何依赖。
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


# ---------------------------------------------------------------- 回收站删除
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
    """把 path（可为 C:\\dir\\* 表示目录内容）移入回收站。返回 (成功, 错误码)"""
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
    """返回 (总字节数, 条目数)"""
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
    """打开系统回收站窗口，供用户还原已删除文件"""
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


# ---------------------------------------------------------------- 工具函数
def env(name, fallback=""):
    v = os.environ.get(name)
    return v if v else fallback


def app_dir():
    """程序所在目录（兼容打包后的 exe 与源码运行）"""
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
    """统计目录总大小和文件数，忽略无权限/占用错误。返回 (bytes, count)"""
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
        {"id": "user_temp", "name": "用户临时文件", "safe": True, "default": True,
         "paths": [TEMP, os.path.join(LOCALAPPDATA, "Temp")],
         "desc": "软件运行产生的临时文件"},
        {"id": "win_temp", "name": "Windows 临时文件", "safe": True, "default": True,
         "paths": [os.path.join(WINDIR, "Temp")],
         "desc": "系统临时文件（需管理员权限）"},
        {"id": "chrome_cache", "name": "Chrome 缓存", "safe": True, "default": True,
         "paths": chrome_paths, "desc": "浏览器网页缓存"},
        {"id": "edge_cache", "name": "Edge 缓存", "safe": True, "default": True,
         "paths": edge_paths, "desc": "浏览器网页缓存"},
        {"id": "firefox_cache", "name": "Firefox 缓存", "safe": True, "default": True,
         "paths": firefox_cache_paths(), "desc": "浏览器网页缓存"},
        {"id": "thumb_cache", "name": "缩略图缓存", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "Explorer")],
         "desc": "资源管理器缩略图"},
        {"id": "inet_cache", "name": "IE/系统网络缓存", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "Microsoft", "Windows", "INetCache")],
         "desc": "旧版浏览器缓存"},
        {"id": "pip_cache", "name": "pip 缓存", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "pip", "cache")],
         "desc": "Python 包下载缓存"},
        {"id": "npm_cache", "name": "npm 缓存", "safe": True, "default": True,
         "paths": [os.path.join(APPDATA, "npm-cache"), os.path.join(LOCALAPPDATA, "npm-cache")],
         "desc": "Node 包下载缓存"},
        {"id": "yarn_cache", "name": "yarn 缓存", "safe": True, "default": True,
         "paths": [os.path.join(LOCALAPPDATA, "Yarn", "Cache")],
         "desc": "Node 包下载缓存"},
        {"id": "dot_cache", "name": "用户 .cache", "safe": True, "default": True,
         "paths": [os.path.join(USERPROFILE, ".cache")],
         "desc": "各类工具的缓存目录"},
        {"id": "win_update", "name": "Windows 更新缓存", "safe": True, "default": True,
         "paths": [os.path.join(WINDIR, "SoftwareDistribution", "Download")],
         "desc": "已安装更新的下载残留（需管理员权限）"},
        {"id": "recycle_bin", "name": "回收站", "safe": False, "default": False,
         "paths": [], "special": "recycle_bin",
         "desc": "清空回收站，删除后不可恢复"},
        {"id": "downloads", "name": "下载文件夹", "safe": False, "default": False,
         "paths": [os.path.join(USERPROFILE, "Downloads")],
         "desc": "⚠ 删除下载文件夹全部内容（移入回收站），请谨慎"},
    ]


# ---------------------------------------------------------------- 应用
class CleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("C盘清理工具")
        self.root.geometry("920x620")
        self.root.minsize(760, 480)

        self.items = build_items()
        self.results = {}   # id -> {"size":int,"count":int}
        self.checked = {}   # id -> bool
        for it in self.items:
            self.checked[it["id"]] = it["default"]

        self.msg_queue = queue.Queue()
        self.busy = False
        self.history_path = os.path.join(app_dir(), "清理历史.log")

        self._setup_style()
        self._build_ui()
        self._update_disk()
        self.root.after(100, self._poll_queue)
        self.start_scan()

    # ------------------------------------------------------------ 样式
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

        # 头部 banner
        header = ttk.Frame(self.root, style="Header.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="磁盘清理工具", style="HeaderTitle.TLabel").pack(anchor="w", padx=20, pady=(16, 2))
        ttk.Label(header, text="安全清理 C 盘临时文件与缓存 · 删除内容可还原", style="HeaderSub.TLabel").pack(anchor="w", padx=20, pady=(0, 16))

        # 磁盘空间卡片
        disk_card = ttk.Frame(self.root, style="Card.TFrame")
        disk_card.pack(fill="x", padx=pad, pady=(pad, 6))
        self.disk_label = ttk.Label(disk_card, text="正在读取磁盘信息…", style="Card.TLabel",
                                    font=("Microsoft YaHei UI", 11, "bold"))
        self.disk_label.pack(anchor="w", padx=14, pady=(12, 8))
        self.disk_bar = ttk.Progressbar(disk_card, style="Disk.Horizontal.TProgressbar", maximum=100)
        self.disk_bar.pack(fill="x", padx=14, pady=(0, 6))
        self.admin_label = ttk.Label(disk_card, text="", style="Muted.TLabel")
        self.admin_label.pack(anchor="w", padx=14, pady=(0, 10))

        # 列表卡片
        list_card = ttk.Frame(self.root, style="Card.TFrame")
        list_card.pack(fill="both", expand=True, padx=pad, pady=6)
        cols = ("check", "name", "size", "count", "desc")
        self.tree = ttk.Treeview(list_card, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("check", text="")
        self.tree.heading("name", text="项目")
        self.tree.heading("size", text="大小")
        self.tree.heading("count", text="文件数")
        self.tree.heading("desc", text="说明")
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

        # 底部操作栏
        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=pad, pady=(6, pad))
        self.selected_label = ttk.Label(bottom, text="已选可释放：0 B", font=("Microsoft YaHei UI", 10, "bold"))
        self.selected_label.pack(side="left")
        ttk.Button(bottom, text="全选", command=lambda: self._set_all(True)).pack(side="right", padx=3)
        ttk.Button(bottom, text="全不选", command=lambda: self._set_all(False)).pack(side="right", padx=3)
        ttk.Button(bottom, text="分析", command=self.start_scan).pack(side="right", padx=3)
        ttk.Button(bottom, text="打开回收站", command=self._open_recycle).pack(side="right", padx=3)
        self.clean_btn = ttk.Button(bottom, text="清理选中项", style="Accent.TButton", command=self.start_clean)
        self.clean_btn.pack(side="right", padx=(3, 0))

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=pad)

        # 日志
        logf = ttk.LabelFrame(self.root, text="日志")
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
                text="C盘：总 %s / 已用 %s / 剩余 %s（%.0f%% 已用）"
                % (fmt_size(total), fmt_size(used), fmt_size(free), pct)
            )
            self.disk_bar.config(value=pct)
            self.admin_label.config(
                text="已获得管理员权限" if is_admin() else "未以管理员运行，Windows/更新缓存可能无法清理"
            )
        except OSError:
            self.disk_label.config(text="C盘空间读取失败")

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

    # ------------------------------------------------------------ 交互
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
        self.selected_label.config(text="已选可释放：%s" % fmt_size(total))

    def _open_recycle(self):
        if open_recycle_bin():
            self._log("已打开回收站，可在其中右键“还原”已删除的文件")
        else:
            self._log("打开回收站失败")

    # ------------------------------------------------------------ 扫描
    def start_scan(self):
        if self.busy:
            return
        self.busy = True
        self._log("开始分析…")
        self.tree.delete(*self.tree.get_children())
        for it in self.items:
            tags = () if it.get("safe", True) else ("danger",)
            self.tree.insert("", "end", iid=it["id"],
                             values=("☐" if not self.checked[it["id"]] else "☑",
                                     it["name"], "扫描中…", "-", it["desc"]), tags=tags)
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

    # ------------------------------------------------------------ 清理
    def start_clean(self):
        if self.busy:
            return
        selected = [it for it in self.items if self.checked.get(it["id"])]
        if not selected:
            messagebox.showinfo("提示", "请先勾选要清理的项目")
            return
        total = sum(self.results.get(it["id"], {}).get("size", 0) for it in selected)
        if total <= 0:
            messagebox.showinfo("提示", "选中的项目没有可清理的内容")
            return
        if not messagebox.askyesno(
            "确认清理",
            "将清理 %d 个项目，共 %s。\n\n"
            "临时文件/缓存会被移入回收站（可恢复）；\n"
            "“回收站”项会被彻底清空（不可恢复）。\n\n确定继续吗？" % (len(selected), fmt_size(total)),
        ):
            return
        self.busy = True
        self.clean_btn.config(state="disabled")
        self.progress.config(maximum=len(selected), value=0)
        self._log("开始清理…")
        threading.Thread(target=self._clean_worker, args=(selected,), daemon=True).start()

    def _clean_worker(self, selected):
        for idx, it in enumerate(selected):
            self.msg_queue.put(("clean_item", it["id"], idx))
            if it.get("special") == "recycle_bin":
                ok = empty_recycle_bin()
                self.msg_queue.put(("log", "回收站：%s" % ("已清空" if ok else "清空失败")))
            else:
                cleaned_any = False
                for p in it["paths"]:
                    if not os.path.isdir(p):
                        continue
                    ok, err = send_to_recycle(os.path.join(p, "*"))
                    cleaned_any = cleaned_any or ok
                    if ok:
                        self.msg_queue.put(("log", "  已清理：%s" % p))
                    else:
                        self.msg_queue.put(("log", "  失败(跳过)：%s  [%s]" % (p, err)))
                if not cleaned_any:
                    self.msg_queue.put(("log", "  %s：无内容或全部失败" % it["name"]))
            self.msg_queue.put(("clean_done", it["id"]))
        self.msg_queue.put(("clean_finish",))

    # ------------------------------------------------------------ 队列轮询
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
                    self._log("分析完成。")
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
                    self._log("清理完成。文件已移入回收站，可点“打开回收站”还原。正在重新分析…")
                    # 清理后重新扫描，刷新大小
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
