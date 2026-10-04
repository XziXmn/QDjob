"""
WebUI 业务复用层。

把 GUI 中的交互逻辑改写为纯函数：
- 复用 Login / utils（不重写核心逻辑）
- 统一返回 {"ok": bool, "message": str, "data": Any}

验证码采用「两段式」：后端不阻塞等待，而是把 need_captcha 返回给前端，
由浏览器内嵌腾讯验证码拿到 randstr/ticket 后再回传，后端继续完成登录。
"""

import json
import os
import time
from datetime import datetime

import web_config as wc
from app_info import meta_dict  # noqa: F401  (便于其它模块统一引用)

from Login import QDLogin_PhoneCode, QDLogin_Password, get_random_phone
from utils import (
    check_user_status,
    check_login_status,
    check_login_risk,
    refresh_cookies,
    search_books,
    get_chapters,
    readtime_report,
)

from logger import LoggerManager

try:
    logger = LoggerManager().logger
except RuntimeError:
    logger = LoggerManager().setup_basic_logger()

# 兜底 UA（与 GUI 中的默认一致）
FALLBACK_UA = (
    "Mozilla/5.0 (Linux; Android 13; PDEM10 Build/TP1A.220905.001; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/109.0.5414.86 "
    "MQQBrowser/6.2 TBS/047601 Mobile Safari/537.36 QDJSSDK/1.0 QDNightStyle_1 "
    "QDReaderAndroid/7.9.384/1466/1000032/OPPO/QDShowNativeLoading"
)


def _ok(message="", data=None):
    return {"ok": True, "message": message, "data": data}


def _err(message, data=None):
    return {"ok": False, "message": message, "data": data}


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_context(username):
    """
    加载用户的运行上下文：(cfg, user, cookies, user_agent, ibex)
    user 为 None 表示用户不存在。
    """
    cfg = wc.load_config()
    user = wc.get_user(cfg, username)
    cookies = wc.load_cookies(username) or {}
    ua = ""
    ibex = ""
    if user:
        ua = user.get("user_agent") or cfg.get("default_user_agent") or ""
        ibex = user.get("ibex", "")
    if not ua:
        ua = cfg.get("default_user_agent") or FALLBACK_UA
    return cfg, user, cookies, ua, ibex


# ==================== 状态检测 ====================
def do_check_user_status(username):
    """检测 tokenid / usertype 状态。"""
    _, user, _, _, _ = get_context(username)
    if not user:
        return _err(f"用户 '{username}' 不存在")
    tokenid = user.get("tokenid", "")
    usertype = user.get("usertype", "")
    if not tokenid:
        return _err(f"用户 '{username}' 的 tokenid 未配置")
    if not usertype:
        return _err(f"用户 '{username}' 的 usertype 未配置")
    try:
        data = check_user_status(tokenid, usertype)
    except Exception as e:  # noqa: BLE001
        return _err(f"检测用户状态时出错: {e}")
    if not data:
        return _err("tokenid 验证失败，请检查日志")
    expire_time = data.get("expire_time", "")
    remaining_calls = data.get("remaining_calls", "")
    if expire_time == "2099-01-01 00:00:00":
        expire_time = "无限制"
    if remaining_calls == -1:
        remaining_calls = "无限制"
    return _ok("tokenid 验证成功", {"expire_time": expire_time, "remaining_calls": remaining_calls})


def do_check_login_status(username):
    """检测基础登录状态（仅验证 cookies 有效性：用户资料接口）。"""
    _, user, cookies, ua, _ = get_context(username)
    if not user:
        return _err(f"用户 '{username}' 不存在")
    if not cookies:
        return _err(f"用户 '{username}' 的 cookies 未配置")
    try:
        is_logged_in = check_login_status(ua, cookies)
    except Exception as e:  # noqa: BLE001
        return _err(f"检测登录状态时出错: {e}")
    if is_logged_in:
        return _ok("基础 cookies 有效", {
            "level": 0,
            "scope": "basic",
            "message": "仅检测了基础登录状态（用户资料接口返回昵称）。"
                       "如需同时检测福利中心接口与账号风控，请使用「检测账号风险」。",
        })
    return _err("基础 cookies 无效或已过期（用户资料接口未返回昵称）")


# 风控等级说明（BanId）
RISK_LEVELS = {
    1: ("设备风控",
        "检测到设备环境异常（例如 root、模拟器、设备指纹异常等）。"
        "本项目无法自动解决，需要在真实设备上恢复/更换设备环境后重试。"),
    2: ("验证码风控",
        "后续执行任务时可能触发验证码。建议二选一："
        "① 在真实设备上手动通过一次验证码；② 配置 tokenid 让程序自动过验证码。"),
}


def do_check_login_risk(username):
    """检测账号风险状态（基础有效性 + 福利中心接口 + 账号风控 RiskConf）。"""
    _, user, cookies, ua, ibex = get_context(username)
    if not user:
        return _err(f"用户 '{username}' 不存在")
    if not cookies:
        return _err(f"用户 '{username}' 的 cookies 未配置")
    if not ibex:
        return _err(f"用户 '{username}' 的 ibex 未配置")
    try:
        result = check_login_risk(ua, cookies, ibex)
    except Exception as e:  # noqa: BLE001
        return _err(f"检测风险状态时出错: {e}")

    # True  -> Result=0 且无 RiskConf（无风控）
    # dict  -> 返回了 RiskConf（存在风控）
    # False -> 请求失败 / Result 非 0（cookies 可能无效）
    if result is True:
        return _ok("无风控", {
            "level": 0,
            "level_name": "无风控",
            "message": "基础 cookies 有效，福利中心接口正常，未检测到风控。",
            "raw": None,
        })
    if result is False:
        return _err("检测失败：cookies 可能无效或已过期，或接口请求异常（请查看日志）")

    conf = result if isinstance(result, dict) else {}
    ban_raw = conf.get("BanId")
    try:
        ban_id = int(ban_raw)
    except (TypeError, ValueError):
        ban_id = None

    if ban_id in RISK_LEVELS:
        name, advice = RISK_LEVELS[ban_id]
    else:
        name = f"未知风控（BanId={ban_raw}）"
        advice = ("遇到未记录的风控类型。建议把本次检测结果反馈给作者，以便补充处理方案。")

    ban_message = conf.get("BanMessage") or ""
    if ban_message:
        advice = advice + f"（服务端提示：{ban_message}）"

    return _ok(f"检测到风控：{name}", {
        "level": ban_id,
        "level_name": name,
        "message": advice,
        "ban_message": ban_message,
        "captcha_url": conf.get("CaptchaURL") or "",
        "captcha_aid": conf.get("CaptchaAId") or "",
        "captcha_type": conf.get("CaptchaType"),
        "session_key": conf.get("SessionKey") or "",
        "phone_number": conf.get("PhoneNumber") or "",
        "raw": conf,
    })


def do_refresh_cookies(username):
    """刷新 cookies 并写回。"""
    cfg, user, cookies, ua, ibex = get_context(username)
    if not user:
        return _err(f"用户 '{username}' 不存在")
    if not cookies:
        return _err(f"用户 '{username}' 的 cookies 未配置")
    if not ibex:
        return _err(f"用户 '{username}' 的 ibex 未配置")
    try:
        success, cookies_new, message = refresh_cookies(ua, cookies, ibex)
    except Exception as e:  # noqa: BLE001
        return _err(f"刷新 cookies 时出错: {e}")
    if not success:
        return _err(f"刷新失败: {message}")
    wc.save_cookies(username, cookies_new)
    user["last_cookies_refresh_time"] = _now_str()
    user.setdefault("cookies_refresh_interval_days", 20)
    wc.save_config(cfg)
    return _ok("cookies 刷新成功")


# ==================== 用户配置写入 ====================
def upsert_user_credentials(username, ua, ibex):
    """把登录得到的 UA / ibex 写入 config（不存在则创建用户）。"""
    cfg = wc.load_config()
    user = wc.get_user(cfg, username)
    cookies_file = f"cookies/{username}.json"
    if user:
        user.update({"user_agent": ua, "ibex": ibex, "cookies_file": cookies_file})
        user.setdefault("cookies_refresh_interval_days", 20)
        user.setdefault("last_cookies_refresh_time", _now_str())
        user.setdefault("usertype", "captcha")
        user.setdefault("tokenid", "")
        user.setdefault("tasks", wc.default_tasks())
        user.setdefault("push_services", [])
    else:
        if len(cfg.get("users", [])) >= wc.MAX_USERS:
            return _err(f"最多只能添加 {wc.MAX_USERS} 个用户")
        cfg_users = cfg.setdefault("users", [])
        new_user = {
            "username": username,
            "cookies_file": cookies_file,
            "user_agent": ua,
            "ibex": ibex,
            "usertype": "captcha",
            "tokenid": "",
            "cookies_refresh_interval_days": 20,
            "last_cookies_refresh_time": _now_str(),
            "tasks": wc.default_tasks(),
            "push_services": [],
        }
        cfg_users.append(new_user)
    wc.save_config(cfg)
    return _ok()


# ==================== 设备信息 ====================
def do_get_device(username=None):
    """生成随机设备信息；传入 username 时同时落盘保存。"""
    device = get_random_phone()
    if not device:
        return _err("生成设备信息失败，请检查 login_data.json 是否存在")
    if username:
        wc.save_device(username, device)
    return _ok("设备信息已生成", device)


def do_load_device(username):
    device = wc.load_device(username)
    if not device:
        return _err("暂无已保存的设备信息，请先使用手机验证码登录")
    return _ok("", device)


def do_save_device(username, device):
    """保存（编辑后的）设备信息。"""
    if not isinstance(device, dict):
        return _err("设备信息必须是 JSON 对象")
    if not wc.get_user(wc.load_config(), username):
        return _err(f"用户 '{username}' 不存在")
    try:
        wc.save_device(username, device)
    except Exception as e:  # noqa: BLE001
        return _err(f"保存设备信息失败: {e}")
    return _ok("设备信息已保存")


# ==================== 手机验证码登录（两段式）====================
def do_phone_sendcode(username, phone, device, session_key="", randstr="", ticket=""):
    """发送手机验证码。返回 status=sent / captcha。"""
    if not phone:
        return _err("请输入手机号")
    if not isinstance(device, dict):
        return _err("设备信息缺失，请先获取随机设备信息")
    inst = QDLogin_PhoneCode(phonenum=phone)
    if not inst.init_device_info(device):
        return _err("设备信息初始化失败")
    status, data = inst.send_phonecode(session_key, randstr, ticket)
    if status == "captcha":
        return _ok("需要图形验证码", {"status": "captcha", "session_key": data})
    if status in (True, "True"):
        return _ok("验证码已发送", {"status": "sent", "session_key": data})
    return _err(f"验证码发送失败: {data}")


def do_phone_verify(username, phone, device, session_key, code):
    """校验手机验证码并完成登录，写入 cookies/UA/ibex。"""
    if not phone or not code:
        return _err("手机号和验证码不能为空")
    if not isinstance(device, dict):
        return _err("设备信息缺失，请先获取随机设备信息")
    inst = QDLogin_PhoneCode(phonenum=phone)
    if not inst.init_device_info(device):
        return _err("设备信息初始化失败")
    try:
        if not inst.check_phonecode(session_key, code):
            return _err("手机验证码验证失败")
        if not inst.login_druidv6():
            return _err("登录 druidv6.if.qidian.com 失败")
    except Exception as e:  # noqa: BLE001
        return _err(f"登录过程中出错: {e}")
    cookies = inst.cookies
    inst.gener_user_agent()
    ua = inst.user_agent
    ibex = inst.gener_ibex_over(str(int(time.time() * 1000)))
    wc.save_cookies(username, cookies)
    wc.save_device(username, device)
    res = upsert_user_credentials(username, ua, ibex)
    if not res["ok"]:
        return res
    return _ok("登录成功", {"cookies": cookies, "user_agent": ua, "ibex": ibex})


# ==================== 账号密码登录（两段式）====================
def do_password_login(username, account, password, session_key="", randstr="", ticket=""):
    """账号密码登录；需要图形验证码时返回 status=captcha。"""
    if not account or not password:
        return _err("账号和密码不能为空")
    device = wc.load_device(username)
    if not device:
        return _err("设备信息不存在，请先使用手机验证码登录成功后再使用密码登录")
    inst = QDLogin_Password(account=account, password=password)
    if not inst.init_device_info(device):
        return _err("设备信息初始化失败")
    try:
        if session_key and randstr and ticket:
            if not inst.login_with_captcha(session_key, randstr, ticket):
                return _err("图形验证码校验失败")
        else:
            status, data = inst.static_login()
            if status == "captcha":
                return _ok("需要图形验证码", {"status": "captcha", "session_key": data})
            if status not in (True, "True"):
                return _err(f"登录失败: {data}")
        if not inst.login_druidv6():
            return _err("登录 druidv6.if.qidian.com 失败")
    except Exception as e:  # noqa: BLE001
        return _err(f"登录过程中出错: {e}")
    cookies = inst.cookies
    inst.gener_user_agent()
    ua = inst.user_agent
    ibex = inst.gener_ibex_over(str(int(time.time() * 1000)))
    wc.save_cookies(username, cookies)
    res = upsert_user_credentials(username, ua, ibex)
    if not res["ok"]:
        return res
    return _ok("登录成功", {"cookies": cookies, "user_agent": ua, "ibex": ibex})


# ==================== 手动填写 cookies ====================
def do_manual_save(username, ua, ibex, cookies):
    """手动保存 cookies / UA / ibex。"""
    ok, msg = wc.validate_username(username)
    if not ok:
        return _err(msg)
    if not (ua or "").strip():
        return _err("User Agent 为必填项")
    if not (ibex or "").strip():
        return _err("ibex 为必填项")

    if not isinstance(cookies, dict):
        return _err("cookies 必须是 JSON 对象")
    wc.save_cookies(username, cookies)
    res = upsert_user_credentials(username, ua or "", ibex or "")
    if not res["ok"]:
        return res
    return _ok("Cookies 保存成功")


# ==================== 阅读时长上报 ====================
def do_search_books(username, keyword):
    """搜索书籍。"""
    if not keyword:
        return _err("请输入搜索关键词")
    _, user, cookies, ua, ibex = get_context(username)
    if not user:
        return _err(f"用户 '{username}' 不存在")
    if not cookies:
        return _err(f"用户 '{username}' 的 cookies 未配置")
    if not ibex:
        return _err(f"用户 '{username}' 的 ibex 未配置")
    try:
        books = search_books(ua, cookies, ibex, keyword)
    except Exception as e:  # noqa: BLE001
        return _err(f"搜索书籍时出错: {e}")
    if not books:
        return _err("未找到相关书籍")
    return _ok(f"找到 {len(books)} 本书", books)


def do_get_chapters(bookid):
    """获取章节列表（走微信接口，无需登录态）。"""
    if not bookid:
        return _err("请输入书籍ID")
    try:
        chapters = get_chapters(bookid)
    except Exception as e:  # noqa: BLE001
        return _err(f"获取章节列表时出错: {e}")
    if not chapters:
        return _err("获取章节列表失败")
    return _ok(f"获取到 {len(chapters)} 个章节", chapters)


def _parse_final_end(final_end_str):
    try:
        dt = datetime.strptime(final_end_str, "%Y-%m-%d %H:%M:%S")
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def do_build_records(bookid, chapter_ids, min_dur, max_dur, final_end_str):
    """
    按 GUI 的算法批量生成阅读记录。
    chapter_ids: 已选章节ID列表（按列表顺序）
    """
    import random

    if not bookid:
        return _err("请先填写书籍ID")
    if not chapter_ids:
        return _err("请先选择要上报的章节")
    try:
        min_dur = int(min_dur)
        max_dur = int(max_dur)
    except (ValueError, TypeError):
        return _err("阅读时长范围必须是整数分钟")
    if min_dur > max_dur:
        return _err("最小时长不能大于最大时长")
    final_ts = _parse_final_end(final_end_str)
    if final_ts is None:
        return _err("最终结束时间格式错误，应为 YYYY-MM-DD HH:MM:SS")

    chapters = list(reversed(chapter_ids))
    current_end = final_ts
    records = []
    for ch_id in chapters:
        minutes = random.randint(min_dur, max_dur)
        read_ms = minutes * 60 * 1000
        start_ts = current_end - read_ms
        records.append({
            "bookid": str(bookid),
            "chapterid": str(ch_id),
            "read_ms": read_ms,
            "start_ts": start_ts,
            "end_ts": current_end,
        })
        gap_ms = random.randint(1000, 3000)
        current_end = start_ts - gap_ms
    records.reverse()
    return _ok(f"已生成 {len(records)} 条阅读记录", records)


def do_readtime_report(username, records):
    """提交阅读记录上报。records 为 do_build_records 产出的列表。"""
    cfg, user, cookies, ua, ibex = get_context(username)
    if not user:
        return _err(f"用户 '{username}' 不存在")
    if not cookies:
        return _err(f"用户 '{username}' 的 cookies 未配置")
    if not ibex:
        return _err(f"用户 '{username}' 的 ibex 未配置")
    if not records:
        return _err("记录列表为空，请先添加记录")

    chapter_info_list = []
    try:
        for rec in records:
            read_data = {
                "readTime": int(rec["read_ms"]),
                "bookId": int(rec["bookid"]),
                "chapterId": int(rec["chapterid"]),
                "startTime": int(rec["start_ts"]),
                "endTime": int(rec["end_ts"]),
                "bookType": 1,
                "chapterVip": 1,
                "scrollMode": 1,
                "unlockStatus": -100,
                "unlockReason": -100,
                "sp": "",
            }
            chapter_info_list.append(read_data)
    except (KeyError, ValueError, TypeError) as e:
        return _err(f"记录数据格式错误: {e}")

    try:
        success = readtime_report(ua, cookies, ibex, chapter_info_list)
    except Exception as e:  # noqa: BLE001
        return _err(f"上报过程中出错: {e}")
    if not success:
        return _err("上报失败，请检查日志或网络")
    return _ok(f"成功上报 {len(chapter_info_list)} 条阅读记录")


