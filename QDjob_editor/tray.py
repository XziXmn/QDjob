"""
系统托盘图标（主要用于 Windows 打包版）。

- 右键菜单：打开界面 / 退出
- 双击图标：打开界面
- 若运行环境不支持（无 pystray/Pillow、无桌面会话、容器），run_tray 返回 False，
  调用方可回退为普通前台运行。
"""

import os
import webbrowser


def _make_image(size=64):
    """运行时生成一个简单图标，避免额外携带图标资源。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 圆角背景（起点红）
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=int(size * 0.22),
                           fill=(217, 58, 43, 255))
    # 尝试绘制 “QD” 文字
    text = "QD"
    font = None
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(name, int(size * 0.42))
            break
        except Exception:  # noqa: BLE001
            font = None
    if font is not None:
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
                      text, font=font, fill=(255, 255, 255, 255))
            return img
        except Exception:  # noqa: BLE001
            pass
    # 兜底：白色圆点
    r = size * 0.16
    draw.ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r],
                 fill=(255, 255, 255, 255))
    return img


def run_tray(title, url, on_exit=None):
    """
    启动托盘并阻塞。成功启动并退出返回 True；环境不支持返回 False。
    on_exit 在用户选择“退出”时调用。
    """
    try:
        import pystray
    except Exception:  # noqa: BLE001
        return False
    try:
        image = _make_image()
    except Exception:  # noqa: BLE001
        return False

    def _open(icon=None, item=None):
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    def _quit(icon, item):
        try:
            icon.stop()
        finally:
            if on_exit:
                try:
                    on_exit()
                except Exception:  # noqa: BLE001
                    pass
            os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("打开界面", _open, default=True),
        pystray.MenuItem("退出", _quit),
    )
    icon = pystray.Icon("QDjob", image, title, menu)
    try:
        icon.run()
    except Exception:  # noqa: BLE001
        return False
    return True
