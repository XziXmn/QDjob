"""
定时表达式工具：保存 / 读取 / 校验 / 生成。

时间表达式统一保存在工作目录的 `crontab.txt`（第一行）。
调度实际由 `scheduler.py` 的进程内线程负责，这里只负责表达式本身。
"""

import os
import re

import web_config as wc

DEFAULT_CRON = "0 12 * * *"

# cron 字段允许的字符
_CRON_RE = re.compile(r'^[\d\*,\-/A-Za-z\s]+$')


def crontab_path():
    return os.path.join(wc.get_workdir(), "crontab.txt")


def read_crontab():
    """读取 crontab.txt 中的时间表达式（首个非空非注释行）。"""
    path = crontab_path()
    if not os.path.exists(path):
        return DEFAULT_CRON
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    return line
    except OSError:
        pass
    return DEFAULT_CRON


def write_expression(expr):
    with open(crontab_path(), "w", encoding="utf-8", newline="\n") as f:
        f.write((expr or DEFAULT_CRON).strip() + "\n")


def validate_cron(expr):
    """校验 cron 表达式（5 个字段）。返回 (ok, message_or_normalized)。"""
    if not expr or not expr.strip():
        return False, "cron 表达式不能为空"
    expr = " ".join(expr.split())
    parts = expr.split(" ")
    if len(parts) != 5:
        return False, "cron 表达式必须为 5 个字段：分 时 日 月 周"
    if not _CRON_RE.match(expr):
        return False, "cron 表达式包含非法字符"
    return True, expr


def build_cron(kind, hour=12, minute=0, weekday=1, value=1):
    """
    图形化配置 -> cron 表达式。

    kind:
        daily         每天 HH:MM
        weekly        每周 周X HH:MM
        monthly       每月 1 号 HH:MM
        every_minutes 每隔 N 分钟
        every_hours   每隔 N 小时（在第 M 分）
    """
    try:
        hour = int(hour)
        minute = int(minute)
        weekday = int(weekday)
        value = max(1, int(value))
    except (ValueError, TypeError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    if kind == "daily":
        return f"{minute} {hour} * * *"
    if kind == "weekly":
        if not (0 <= weekday <= 6):
            weekday = 1
        return f"{minute} {hour} * * {weekday}"
    if kind == "monthly":
        return f"{minute} {hour} 1 * *"
    if kind == "every_hours":
        if value > 23:
            value = 23
        return f"{minute} */{value} * * *"
    if kind == "every_minutes":
        if value > 59:
            value = 59
        return f"*/{value} * * * *"
    return None
