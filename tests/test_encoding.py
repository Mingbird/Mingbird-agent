"""run_bash 读端编码健壮性:非 UTF-8 子进程输出不得炸 reader 线程。

35b GAIA L1-03(timeout)/L1-04/L1-05(no_answer)三格毒杀实证:subprocess.run
text=True 不带 encoding 时继承进程默认(PYTHONUTF8=1 环境=utf-8),中文 Windows
上 cmd 内建命令/非 python 程序输出 GBK 字节(0xb2/0xd5 实锤)→ reader 线程
UnicodeDecodeError 炸死,run_bash 挂掉,模型收不到回执空转到预算烧尽。
修复:读端显式 encoding="utf-8" + errors="replace"(乱码可见,永不崩)。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A


def test_run_bash_survives_raw_gbk_bytes(tmp_path):
    # 子进程往 stdout 写原始 GBK 字节(两格 transcript 实锤的 0xb2 0xd5),
    # 修复前 reader 线程 UnicodeDecodeError 炸死 → subprocess 静默返回空 stdout
    # (回执只剩 STDERR 里的 traceback,模型拿不到任何输出空转)。
    # 修复后:字节被替换符解码,stdout 内容可见。
    payload = tmp_path / "payload.py"
    payload.write_bytes(b"import sys\nsys.stdout.buffer.write(b'\\xb2\\xd5\\xb5\\xc4\\n')\n")
    out = A.run_tool("run_bash", {"command": "python payload.py"}, str(tmp_path))
    assert "[exit 0]" in out
    # stdout 段必须真的有内容(修复前为空);GBK 字节按 utf-8+replace 解出替换符
    stdout_section = out.split("STDOUT:", 1)[1].split("STDERR:", 1)[0]
    assert stdout_section.strip() and "�" in stdout_section


def test_run_bash_normal_utf8_still_clean(tmp_path):
    # 回归:正常 UTF-8 输出路径不受影响
    payload = tmp_path / "ok.py"
    payload.write_text("print('hello 你好')", encoding="utf-8")
    out = A.run_tool("run_bash", {"command": "python ok.py"}, str(tmp_path))
    assert "[exit 0]" in out and "hello 你好" in out
