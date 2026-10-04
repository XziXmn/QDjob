"""
构建期工具：把 login_data.json 生成为 Python 模块 `_embedded_data.py`。

目的：Nuitka 打包时，敏感数据文件若不嵌入，会在 onefile 运行时被解压成明文文件；
把内容作为 Python 常量编译进二进制后，运行时不再落地明文文件，显著提高逆向成本。

用法（CI 或本地打包前执行）：
    python QDjob_editor/gen_embedded.py
输出：
    QDjob_editor/_embedded_data.py
"""

import json
import os
import sys

# 兼容 Windows CI（stdout 可能是 cp1252）等非 UTF-8 环境：保留原编码，仅避免编码异常
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "login_data.json")
TARGET = os.path.join(HERE, "_embedded_data.py")

HEADER = (
    "# 本文件由 gen_embedded.py 自动生成，请勿手动修改。\n"
    "# 用于在打包时把 login_data.json 编译进二进制，避免运行时落地明文。\n"
    "import json as _json\n\n"
    "_DATA = r'''"
)
FOOTER = "'''\n\nLOGIN_DATA = _json.loads(_DATA)\n"


def generate(source=SOURCE, target=TARGET):
    if not os.path.exists(source):
        print(f"[gen_embedded] source not found: {source}")
        return False
    with open(source, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 用 JSON 字符串嵌入（ensure_ascii=False 保留中文，r'''...''' 包裹）
    payload = json.dumps(data, ensure_ascii=False)
    if "'''" in payload:
        raise ValueError("login_data.json 内容包含 '''，无法安全嵌入")
    content = HEADER + payload + FOOTER
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[gen_embedded] generated: {target} ({len(content)} bytes)")
    return True


if __name__ == "__main__":
    sys.exit(0 if generate() else 1)
