"""
访问口令的存储与校验。

- 口令以 Werkzeug 哈希形式保存在工作目录的 `.webui_auth.json`
- 优先级（由 web_editor 决定）：启动参数 > 环境变量 > 本文件
"""

import json
import os

from werkzeug.security import generate_password_hash, check_password_hash

import web_config as wc

AUTH_FILE = ".webui_auth.json"
MIN_LENGTH = 4


def auth_path():
    return os.path.join(wc.get_workdir(), AUTH_FILE)


def load_auth():
    try:
        with open(auth_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("hash"):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def has_password():
    return bool(load_auth().get("hash"))


def set_password(password):
    if not password or len(password) < MIN_LENGTH:
        raise ValueError(f"口令长度至少为 {MIN_LENGTH} 位")
    data = {"hash": generate_password_hash(password)}
    path = auth_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def clear_password():
    path = auth_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def verify(password):
    data = load_auth()
    if not data.get("hash"):
        return False
    try:
        return check_password_hash(data["hash"], password or "")
    except Exception:  # noqa: BLE001
        return False
