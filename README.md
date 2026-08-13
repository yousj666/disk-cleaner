# C盘清理工具 / Disk Cleaner

一个简单、安全、免费的 Windows C 盘清理工具。纯 Python 标准库开发，无第三方依赖；打包成单文件 exe，**无需安装 Python 即可使用**。

A simple, safe, free Windows disk cleaner. Pure Python standard library, no third-party dependencies; packaged as single-file executables — **no Python installation required**.

[中文说明](#中文) · [English](#english)

---

## 中文

### ✨ 功能特性

- 🔍 一键分析 C 盘可清理空间，按类别展示大小和文件数
- ☑️ 可视化勾选要清理的项目，底部实时显示"已选可释放"空间
- 🗑️ 安全删除：临时文件 / 缓存均移入回收站，可随时还原
- 🔄 一键打开回收站 + 自动记录清理历史日志，误删可追溯
- ⚠️ 危险项（清空回收站、下载文件夹）默认不勾选，需手动确认
- 🛡️ 清理前二次确认，被占用的文件自动跳过、不卡死、不误删

### 📦 使用方法

**方式一：直接下载 exe（推荐）**

到 [Releases](../../releases) 下载最新版：
- `DiskCleaner.exe` —— 中文界面
- `DiskCleaner-EN.exe` —— English UI

双击运行即可，无需安装任何环境。

> 首次运行会稍慢几秒（单文件自解压），属正常现象。
> 若提示"未以管理员运行"，部分系统目录（Windows 临时文件、更新缓存）可能无法清理，右键"以管理员身份运行"可解决。

**方式二：从源码运行**

需要 Python 3.8+（自带 tkinter）：

```bash
python disk_cleaner.py      # 中文
python disk_cleaner_en.py   # English
```

### 🔨 自行打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DiskCleaner disk_cleaner.py
pyinstaller --onefile --windowed --name DiskCleaner-EN disk_cleaner_en.py
```

### 🛡️ 安全说明

- 删除操作使用 Windows 回收站机制（`SHFileOperationW` + `FOF_ALLOWUNDO`），临时文件 / 缓存均可从回收站还原
- 仅"清空回收站"为不可逆操作，且默认不勾选、单独警告
- 工具只清理临时文件与缓存，不会删除任何系统关键文件

---

## English

### ✨ Features

- 🔍 Analyze cleanable space on C: in one click, showing size and file count per category
- ☑️ Visually check items to clean, with a real-time "Selected" space total
- 🗑️ Safe deletion: temp files / caches are moved to the Recycle Bin, recoverable anytime
- 🔄 One-click open Recycle Bin + automatic clean history log, traceable
- ⚠️ Dangerous items (empty Recycle Bin, Downloads folder) are unchecked by default
- 🛡️ Confirmation before cleaning; locked files are skipped automatically

### 📦 Usage

**Option 1: download the exe (recommended)**

Go to [Releases](../../releases) and download the latest:
- `DiskCleaner.exe` — Chinese UI
- `DiskCleaner-EN.exe` — English UI

Double-click to run — no environment needed.

> First launch takes a few extra seconds (single-file self-extraction); this is normal.
> If it says "Not running as admin", some system directories (Windows temp files, update cache) may fail to clean — right-click and choose "Run as administrator".

**Option 2: run from source**

Requires Python 3.8+ (with tkinter):

```bash
python disk_cleaner.py      # Chinese
python disk_cleaner_en.py   # English
```

### 🔨 Build from source

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name DiskCleaner disk_cleaner.py
pyinstaller --onefile --windowed --name DiskCleaner-EN disk_cleaner_en.py
```

### 🛡️ Safety

- Deletion uses the Windows Recycle Bin mechanism (`SHFileOperationW` + `FOF_ALLOWUNDO`), so temp files / caches can be restored from the Recycle Bin
- Only "Empty Recycle Bin" is irreversible, and it is unchecked by default with a separate warning
- The tool only cleans temp files and caches, never any critical system files

### 📄 License

[MIT License](LICENSE)
