"""
QDjob 配置编辑器 WebUI 启动入口。

用法（开发直跑 / 打包后均可）：
    python webui.py --host 0.0.0.0 --port 33989 --workdir /app --password xxxx

参数优先级：命令行 > 环境变量 > 默认值
环境变量：
    QDJOB_WORKDIR          工作目录（config.json / cookies / logs 所在目录）
    QDJOB_WEBUI_PASSWORD   访问口令
    QDJOB_HOST / QDJOB_PORT

特性：
    - 启动后自动打开默认浏览器（容器/无桌面环境自动跳过）
    - 打包版在桌面环境显示系统托盘图标（右键：打开界面 / 退出）
    - 默认端口 33989（备选 42062）
"""

import argparse
import os
import sys
import threading

import web_config as wc

# 兼容非 UTF-8 控制台（如英文 Windows 的 cp1252）：保留原编码，仅避免编码异常
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace", line_buffering=True)
    except Exception:  # noqa: BLE001
        pass

DEFAULT_PORT = 33989


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="QDjob 配置编辑器 WebUI")
    parser.add_argument("--host", default=os.environ.get("QDJOB_HOST", "127.0.0.1"),
                        help="监听地址（容器内建议 0.0.0.0）")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("QDJOB_PORT", str(DEFAULT_PORT))),
                        help=f"监听端口（默认 {DEFAULT_PORT}）")
    parser.add_argument("--workdir", default=os.environ.get("QDJOB_WORKDIR", ""),
                        help="工作目录（config.json / cookies / logs 所在目录）")
    parser.add_argument("--password", default=os.environ.get("QDJOB_WEBUI_PASSWORD", ""),
                        help="访问口令（为空则使用已保存口令或不校验）")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    parser.add_argument("--no-tray", action="store_true", help="不启用系统托盘图标")
    parser.add_argument("--debug", action="store_true", help="使用 Flask 调试服务器（开发用）")
    return parser.parse_args(argv)


def _browse_host(host):
    return "127.0.0.1" if host in ("0.0.0.0", "", "::") else host


def main(argv=None):
    args = parse_args(argv)

    import lifecycle
    import run_manager

    # 记录重启参数（在 chdir 之前，确保脚本路径有效）
    if run_manager.is_compiled():
        lifecycle.set_restart_args([sys.executable] + sys.argv[1:])
    else:
        lifecycle.set_restart_args([sys.executable, os.path.abspath(sys.argv[0])] + sys.argv[1:])

    workdir = os.path.abspath(args.workdir) if args.workdir else os.getcwd()
    os.makedirs(workdir, exist_ok=True)
    os.chdir(workdir)
    wc.set_workdir(workdir)
    wc.ensure_dirs()

    # 在切换工作目录之后再导入应用，确保日志/配置路径基于 workdir
    from web_editor import create_app
    app = create_app(workdir=workdir, password=args.password)

    import app_info
    auth_source = app.config.get("AUTH_SOURCE", "none")
    url = f"http://{_browse_host(args.host)}:{args.port}"

    print("=" * 60)
    print(f" QDjob 配置编辑器 WebUI  {app_info.VERSION}")
    print(f" 作者: {app_info.AUTHOR}    项目: {app_info.PROJECT}")
    print(f" 工作目录: {workdir}")
    print(f" 访问地址: {url}")
    print(f" 访问口令: {'已启用' if auth_source != 'none' else '未设置'}")
    print(f" QDjob: {run_manager.describe_qdjob_command() or '未找到（手动执行功能不可用）'}")
    print("=" * 60)

    desktop = lifecycle.is_desktop_capable()
    if desktop and not args.no_browser:
        lifecycle.open_browser(url)

    def _serve():
        if args.debug:
            app.run(host=args.host, port=args.port, debug=True, use_reloader=False)
            return
        try:
            from waitress import serve
        except ImportError:
            print("[警告] 未安装 waitress，回退到 Flask 内置服务器")
            app.run(host=args.host, port=args.port, use_reloader=False)
            return
        serve(app, host=args.host, port=args.port, threads=8)

    # 托盘仅在“打包 + 桌面环境”下启用；否则前台阻塞运行
    use_tray = (not args.no_tray) and run_manager.is_compiled() and desktop
    if use_tray:
        import tray
        server_thread = threading.Thread(target=_serve, name="qdjob-webui", daemon=True)
        server_thread.start()
        if not tray.run_tray(f"{app_info.PROJECT} 配置编辑器", url):
            server_thread.join()
    else:
        _serve()


if __name__ == "__main__":
    sys.exit(main())
