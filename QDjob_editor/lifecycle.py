"""
生命周期控制：打开浏览器、进程重启、桌面环境判定。

这些能力与运行环境相关（Docker / 无桌面 Linux 不适用），集中在此便于复用。
"""

import os
import platform
import sys
import threading
import time
import webbrowser

_RESTART_ARGS = None


def set_restart_args(args):
    """由入口程序在切换工作目录前设置，用于后续重启进程。"""
    global _RESTART_ARGS
    _RESTART_ARGS = list(args)


def is_docker():
    if os.environ.get("QDJOB_CRON_FILE"):
        return True
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return ("docker" in content) or ("kubepods" in content)
    except OSError:
        return False


def has_display():
    """是否存在可用于图形界面的桌面会话。"""
    if platform.system() != "Linux":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def is_desktop_capable():
    """是否适合打开浏览器 / 显示托盘（容器与无桌面环境返回 False）。"""
    return (not is_docker()) and has_display()


def open_browser(url, delay=1.2):
    """延迟打开默认浏览器（非阻塞）。"""
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_open, daemon=True).start()


def restart_process(delay=0.8):
    """延迟重启当前进程（非阻塞，用原启动参数重新执行）。"""
    def _restart():
        time.sleep(delay)
        try:
            args = _RESTART_ARGS
            if not args:
                # 兜底：源码 sys.argv[0] 为脚本；打包 sys.executable 为可执行文件
                if getattr(sys, "frozen", False):
                    args = [sys.executable] + sys.argv[1:]
                else:
                    args = [sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:]
            os.execv(args[0], args)
        except Exception:  # noqa: BLE001
            os._exit(0)
    threading.Thread(target=_restart, daemon=True).start()
