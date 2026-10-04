"""
定时调度器（进程内调度）。

设计：定时完全由 WebUI 进程自身负责——
    只要程序在后台运行，就会按计划执行；程序退出即停止。
Windows / Linux / Docker / 源码运行 **行为一致**，不再使用 schtasks / 用户 crontab。

- 时间表达式统一保存在工作目录的 `crontab.txt`
- 支持标准 5 字段 cron：`*`、`a-b`、`a,b`、`*/n`、`a/n`
"""

import datetime
import os
import platform
import threading

import cron_manager
import lifecycle
import run_manager
import web_config as wc

SYSTEM = platform.system()
DISABLE_MARK = ".qdjob_schedule_disabled"
CHECK_INTERVAL = 20  # 秒，检查一次是否到点（保证同一分钟内必被命中）


# ==================== 环境信息（仅用于展示）====================
def detect_environment():
    source = not run_manager.is_compiled()
    docker = lifecycle.is_docker()
    if docker:
        mode, label = "docker", "Docker 容器"
    elif source:
        mode, label = "source", "源码运行"
    elif SYSTEM == "Windows":
        mode, label = "windows", "Windows"
    elif SYSTEM == "Linux":
        mode, label = "linux", "Linux"
    else:
        mode, label = "other", SYSTEM or "未知系统"
    return {"os": SYSTEM, "docker": docker, "source": source, "mode": mode, "label": label}


# ==================== cron 匹配 ====================
def _match_field(field, value, min_v, max_v):
    if field == "*":
        return True
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/", 1)
            if not s.isdigit():
                continue
            step = int(s) or 1
        if part == "*":
            lo, hi = min_v, max_v
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                continue
            lo, hi = int(a), int(b)
        elif part.isdigit():
            lo = hi = int(part)
        else:
            continue
        if lo <= value <= hi and (value - lo) % step == 0:
            return True
    return False


def match_cron(expr, now):
    """判断给定时间是否匹配 cron 表达式（支持 *、a-b、a,b、*/n、a/n）。"""
    parts = (expr or "").split()
    if len(parts) != 5:
        return False
    minute, hour, dom, mon, dow = parts
    cron_dow = (now.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> cron Sun=0..Sat=6
    return (
        _match_field(minute, now.minute, 0, 59)
        and _match_field(hour, now.hour, 0, 23)
        and _match_field(dom, now.day, 1, 31)
        and _match_field(mon, now.month, 1, 12)
        and _match_field(dow, cron_dow, 0, 6)
    )


# ==================== 表达式 / 开关 ====================
def _write_expression(expr):
    with open(cron_manager.crontab_path(), "w", encoding="utf-8", newline="\n") as f:
        f.write(expr.strip() + "\n")


def _disable_mark_path():
    return os.path.join(wc.get_workdir(), DISABLE_MARK)


def is_disabled():
    return os.path.exists(_disable_mark_path())


def _set_disabled(disabled):
    path = _disable_mark_path()
    if disabled:
        with open(path, "w", encoding="utf-8") as f:
            f.write("disabled\n")
    elif os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ==================== 进程内调度器 ====================
class _Scheduler:
    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._last_key = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="qdjob-scheduler", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def is_running(self):
        return bool(self._thread and self._thread.is_alive())

    def _loop(self):
        while not self._stop.is_set():
            try:
                if not is_disabled():
                    expr = cron_manager.read_crontab()
                    now = datetime.datetime.now()
                    key = now.strftime("%Y-%m-%d %H:%M")
                    if key != self._last_key and match_cron(expr, now):
                        self._last_key = key
                        run_manager.run_qdjob_blocking(src="定时")
            except Exception:  # noqa: BLE001
                pass
            self._stop.wait(CHECK_INTERVAL)


SCHEDULER = _Scheduler()


def start_auto_scheduler():
    """启动时调用：启动进程内调度线程。"""
    SCHEDULER.start()
    return detect_environment()


# ==================== 对外接口 ====================
def apply(expr):
    """保存表达式并启用进程内定时。返回 (ok, message)。"""
    ok, result = cron_manager.validate_cron(expr)
    if not ok:
        return False, result
    _write_expression(result)
    _set_disabled(False)
    SCHEDULER.start()
    return True, "定时方案已保存（程序运行期间按计划执行）"


def remove():
    """停止定时执行。返回 (ok, message)。"""
    _set_disabled(True)
    return True, "已停止定时执行"


def status():
    """返回当前环境与定时方案状态（供页面展示）。"""
    env = detect_environment()
    cmd = run_manager.find_qdjob_command()
    info = dict(env)
    info.update({
        "expression": cron_manager.read_crontab(),
        "qdjob_command": run_manager.describe_qdjob_command(cmd),
        "qdjob_found": bool(cmd),
        "workdir": wc.get_workdir(),
        "disabled": is_disabled(),
        "running": SCHEDULER.is_running(),
        "managed": "进程内调度",
        "detail": "只要程序在后台运行就会按计划执行；程序退出则停止",
    })
    return info
