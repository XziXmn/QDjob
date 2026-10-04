"""
真实设备数据管理。

- 设备档案保存在工作目录 `devices.json`，可添加多组、自定义命名
- 设备信息与软件版本分离：设备只存硬件/指纹，版本另存 `versions.json`
- 支持从抓包 curl 解析设备参数（解析 ibex 得到真实设备指纹）
- 登录时由 `compose_login_phone()` 把「设备 + 版本」合成为 Login 所需的字典

设备字段说明（对应 Login.init_device_info）：
    brand / model / board / cpu_abi / device_name   -> phone_data
    android_version / build_id                       -> 系统信息
    resolution {width,height}                        -> 分辨率
    qid / qidth                                      -> 设备ID
    phone_security / phone_security_over             -> 设备指纹(qid_36 / qid_36_over)
    ibex_plain                                       -> ibex 明文模板（{TS} 为时间戳占位）
    android_id / jpush_id                            -> 可选
"""

import json
import os
import re

import web_config as wc

DEVICES_FILE = "devices.json"
VERSIONS_FILE = "versions.json"

# 登录所需的最小字段（缺失会给出告警）
REQUIRED_FIELDS = ["brand", "model", "qid", "phone_security"]

DEFAULT_RESOLUTION = {"width": 1080, "height": 2400}
DEFAULT_ANDROID_VERSION = 12
DEFAULT_SDKVERSION = "401"


# ==================== 设备档案存储 ====================
def devices_path():
    return os.path.join(wc.get_workdir(), DEVICES_FILE)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return default
        return json.loads(content)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path, data):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_devices():
    data = _read_json(devices_path(), {"devices": []})
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return []
    return data["devices"]


def save_devices(devices):
    _write_json(devices_path(), {"devices": devices})


def get_device(name):
    for d in load_devices():
        if d.get("name") == name:
            return d
    return None


def upsert_device(name, device, note="", source="manual", version=None):
    """新增或更新设备档案（可附带解析到的软件版本）。返回 (ok, message)。"""
    name = (name or "").strip()
    if not name:
        return False, "设备名称不能为空"
    if len(name) > 40:
        return False, "设备名称过长（最多 40 字符）"
    devices = load_devices()
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    version = _normalize_version(version) if isinstance(version, dict) else None
    existing = get_device(name)
    if existing:
        existing["device"] = device
        existing["note"] = note
        existing["source"] = source
        existing["version"] = version
        existing["updated"] = now
    else:
        devices.append({
            "name": name,
            "note": note,
            "source": source,
            "version": version,
            "created": now,
            "updated": now,
            "device": device,
        })
    save_devices(devices)
    return True, f"设备「{name}」已保存"


def delete_device(name):
    devices = load_devices()
    new = [d for d in devices if d.get("name") != name]
    if len(new) == len(devices):
        return False, f"设备「{name}」不存在"
    save_devices(new)
    return True, f"设备「{name}」已删除"


# ==================== 版本表 ====================
def _versions_candidates():
    candidates = [os.path.join(os.path.dirname(os.path.abspath(__file__)), VERSIONS_FILE)]
    try:
        import sys
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), VERSIONS_FILE))
    except Exception:  # noqa: BLE001
        pass
    candidates.append(os.path.join(wc.get_workdir(), VERSIONS_FILE))
    return candidates


def user_versions_path():
    return os.path.join(wc.get_workdir(), VERSIONS_FILE)


def _normalize_version(v):
    if not isinstance(v, dict):
        return None
    version = str(v.get("version", "")).strip()
    versioncode = str(v.get("versioncode", "")).strip()
    sdkversion = str(v.get("sdkversion", DEFAULT_SDKVERSION)).strip() or DEFAULT_SDKVERSION
    if not version or not versioncode:
        return None
    return {"version": version, "versioncode": versioncode, "sdkversion": sdkversion}


def load_versions():
    """合并读取版本表：内置 versions.json + 工作目录 versions.json（后者覆盖/追加）。"""
    merged = {}
    order = []
    for path in _versions_candidates():
        data = _read_json(path, None)
        if not isinstance(data, dict):
            continue
        for item in data.get("versions", []) or []:
            v = _normalize_version(item)
            if not v:
                continue
            key = (v["version"], v["versioncode"])
            if key not in merged:
                order.append(key)
            merged[key] = v
    return [merged[k] for k in order]


def save_user_versions(versions):
    _write_json(user_versions_path(), {"versions": versions})


def read_user_versions():
    data = _read_json(user_versions_path(), {"versions": []})
    if isinstance(data, dict) and isinstance(data.get("versions"), list):
        return data["versions"]
    return []


def normalize_version(entry):
    """公开接口：规范化单个版本条目，非法返回 None。"""
    return _normalize_version(entry)


# ==================== 抓包解析 ====================
_PAIR_RE = re.compile(r"""['"]([A-Za-z0-9_\-]+)=([^'"]*)['"]""", re.S)
_OSVER_RE = re.compile(r'Android(\d+)_([\d.]+)_(\d+)')
_WS_RE = re.compile(r'\s+')


def _extract_pairs(text):
    """从 curl 文本提取 `key=value` 参数（兼容 --data-urlencode / -d，单双引号）。"""
    pairs = {}
    for k, v in _PAIR_RE.findall(text or ""):
        v = v.strip()
        if k in ("ibex", "signature", "password", "QDSign"):
            v = _WS_RE.sub("", v)  # base64 可能被换行/空格打断
        pairs[k] = v
    return pairs


def parse_ibex_plain(plain):
    """从 ibex 明文提取设备字段，并生成带 {TS} 占位符的模板。"""
    out = {}
    if not isinstance(plain, str) or not plain.startswith("1|"):
        return out
    parts = plain.split("|")
    if len(parts) < 16:
        return out

    ts = parts[1][:13]
    if ts.isdigit():
        # 把时间戳替换为占位符，保证登录时逐字节还原
        out["ibex_plain"] = plain[:2] + "{TS}" + plain[2 + 13:]

    out["model"] = re.split(r"\s*\(", parts[-12], 1)[0].strip()
    out["brand"] = parts[-11]
    out["board"] = parts[-10]
    out["build_id"] = parts[-8]
    out["cpu_abi"] = parts[-7]
    out["qid"] = parts[-4]
    out["qidth"] = parts[-3]
    # 中段即设备指纹 phone_security（97 字符 / 46 段）
    ps = "|".join([parts[1][13:]] + parts[2:-12] + [""])
    out["phone_security"] = ps
    out["phone_security_over"] = ps
    return out


def _device_from_pairs(pairs):
    """从参数字典提取设备字段，返回 (device, app_version, warnings)。"""
    dev = {}
    app_version = {}
    warnings = []
    if not pairs:
        return dev, app_version, warnings

    if pairs.get("devicename"):
        dev["device_name"] = pairs["devicename"]

    if pairs.get("devicetype"):
        dt = pairs["devicetype"]
        if "_" in dt:
            b, m = dt.split("_", 1)
            dev.setdefault("brand", b)
            dev.setdefault("model", m)
        else:
            dev.setdefault("model", dt)

    # 软件版本（与设备无关，单独返回）
    if pairs.get("osversion"):
        m = _OSVER_RE.search(pairs["osversion"])
        if m:
            dev["android_version"] = int(m.group(1))
            app_version["version"] = m.group(2)
            app_version["versioncode"] = m.group(3)
    if pairs.get("version"):
        app_version["versioncode"] = pairs["version"]
    if pairs.get("sdkversion"):
        app_version["sdkversion"] = pairs["sdkversion"]

    if pairs.get("ibex"):
        try:
            from enctrypt_qidian import decode_ibex
            plain = decode_ibex(_WS_RE.sub("", pairs["ibex"]))
            if isinstance(plain, (bytes, bytearray)):
                plain = plain.decode("utf-8", "replace")
            info = parse_ibex_plain(plain)
            if not info:
                warnings.append("ibex 明文结构无法识别（可能是未知格式）")
            for k, v in info.items():
                if v:
                    dev[k] = v
        except Exception as e:  # noqa: BLE001
            warnings.append(f"ibex 解析失败: {e}")
    else:
        warnings.append("未填写 ibex，无法获取真实设备指纹")

    if not dev.get("qid") and pairs.get("signature"):
        try:
            from enctrypt_qidian import decode_signature
            sig = str(decode_signature(_WS_RE.sub("", pairs["signature"])))
            qid = sig.split("|")[0].strip()
            if qid:
                dev["qid"] = qid
        except Exception as e:  # noqa: BLE001
            warnings.append(f"signature 解析失败: {e}")

    dev = normalize_device(dev)
    for field in REQUIRED_FIELDS:
        if not dev.get(field):
            warnings.append(f"未能提取字段: {field}（可在表单中手动补充）")
    return dev, app_version, warnings


def parse_curl(text):
    """解析抓包 curl，返回 (ok, message, result)。"""
    empty = {"device": {}, "app_version": {}, "warnings": [], "found": []}
    pairs = _extract_pairs(text)
    if not pairs:
        return False, "未解析到任何参数，请确认粘贴的是完整 curl 命令", empty
    dev, app_version, warnings = _device_from_pairs(pairs)
    return True, "解析成功", {"device": dev, "app_version": app_version,
                             "warnings": warnings, "found": sorted(pairs.keys())}


def parse_fields(fields):
    """从「逐个填入的抓包参数」解析设备，返回 (ok, message, result)。"""
    empty = {"device": {}, "app_version": {}, "warnings": [], "found": []}
    if not isinstance(fields, dict):
        return False, "参数格式错误", empty
    pairs = {k: v for k, v in fields.items() if isinstance(v, str) and v.strip()}
    if not pairs:
        return False, "请至少填写 ibex（或其它抓包参数）", empty
    dev, app_version, warnings = _device_from_pairs(pairs)
    return True, "解析成功", {"device": dev, "app_version": app_version,
                             "warnings": warnings, "found": sorted(pairs.keys())}


# ==================== 规范化 / 合成 ====================
def normalize_device(dev):
    """把设备字段补齐/规范为可用的结构。"""
    if not isinstance(dev, dict):
        return {}
    out = dict(dev)

    def s(key):
        return str(out.get(key) or "").strip()

    out["brand"] = s("brand")
    out["model"] = s("model")
    out["board"] = s("board")
    out["cpu_abi"] = s("cpu_abi") or "arm64-v8a"
    out["device_name"] = s("device_name")
    out["build_id"] = s("build_id")
    out["qid"] = s("qid")
    out["qidth"] = s("qidth") or out["qid"]
    out["phone_security"] = str(out.get("phone_security") or "")
    out["phone_security_over"] = str(out.get("phone_security_over") or "") or out["phone_security"]
    out["ibex_plain"] = str(out.get("ibex_plain") or "")
    out["android_id"] = s("android_id")
    out["jpush_id"] = s("jpush_id")

    try:
        out["android_version"] = int(out.get("android_version") or DEFAULT_ANDROID_VERSION)
    except (ValueError, TypeError):
        out["android_version"] = DEFAULT_ANDROID_VERSION

    res = out.get("resolution")
    if not isinstance(res, dict):
        res = dict(DEFAULT_RESOLUTION)
    try:
        res = {"width": int(res.get("width") or DEFAULT_RESOLUTION["width"]),
               "height": int(res.get("height") or DEFAULT_RESOLUTION["height"])}
    except (ValueError, TypeError):
        res = dict(DEFAULT_RESOLUTION)
    out["resolution"] = res
    return out


def device_warnings(dev):
    """返回设备档案的完整性告警列表。"""
    warns = []
    dev = dev or {}
    for field in REQUIRED_FIELDS:
        if not dev.get(field):
            warns.append(f"缺少必要字段: {field}")
    if not dev.get("ibex_plain"):
        warns.append("缺少 ibex 设备指纹（建议通过抓包 curl 导入以获得真实指纹）")
    if not dev.get("device_name"):
        warns.append("缺少设备名称 device_name")
    return warns


def compose_login_phone(device, version):
    """
    把「设备档案 + 软件版本」合成为 Login.init_device_info 需要的字典。
    version: {version, versioncode, sdkversion}；为空时抛 ValueError。
    """
    if not isinstance(device, dict):
        raise ValueError("设备数据无效")
    if not isinstance(version, dict) or not version.get("version") or not version.get("versioncode"):
        raise ValueError("请先选择软件版本（version / versioncode）")

    dev = normalize_device(device)
    qid = dev["qid"]
    ps = dev["phone_security"]
    return {
        "app_data": {
            "version": str(version["version"]),
            "versioncode": str(version["versioncode"]),
            "sdkversion": str(version.get("sdkversion") or DEFAULT_SDKVERSION),
        },
        "resolution": dev["resolution"],
        "qid": qid,
        "qidth": dev["qidth"] or qid,
        "android_version": dev["android_version"],
        "build_id": dev["build_id"],
        "phone_data": {
            "model": dev["model"],
            "brand": dev["brand"],
            "board": dev["board"],
            "cpu_abi": dev["cpu_abi"],
            "device_name": dev["device_name"],
        },
        "phone_security": {
            "qidnum": len(qid) or 36,
            "qid_36": ps,
            "qid_36_over": dev["phone_security_over"] or ps,
        },
        "android_id": dev.get("android_id", ""),
        "jpush_id": dev.get("jpush_id", ""),
        # 供 Login.gener_ibex 使用：逐字节还原真实设备指纹
        "ibex_plain": dev.get("ibex_plain", ""),
    }


def list_device_summaries():
    """设备列表摘要（供页面展示）。"""
    out = []
    for d in load_devices():
        dev = normalize_device(d.get("device") or {})
        out.append({
            "name": d.get("name", ""),
            "note": d.get("note", ""),
            "source": d.get("source", ""),
            "created": d.get("created", ""),
            "updated": d.get("updated", ""),
            "brand": dev.get("brand", ""),
            "model": dev.get("model", ""),
            "device_name": dev.get("device_name", ""),
            "android_version": dev.get("android_version", ""),
            "has_ibex": bool(dev.get("ibex_plain")),
            "version": d.get("version") or None,
            "warnings": device_warnings(dev),
        })
    return out


