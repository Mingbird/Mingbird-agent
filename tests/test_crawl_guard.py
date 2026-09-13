# -*- coding: utf-8 -*-
"""read_file 爬行守卫 v2(字节预算制)单元测试。

v1 致伤复盘(72 格重跑,LH01/4b 撞墙 62 次、WF08/4b 12 次拒绝双超时)锚定的不变量:
1. 预算内读取返回完整请求区间,无任何附加内容;
2. 温和建议只加一行、不改数据,每文件最多 2 次(第 4/10 次读取);
3. 预算耗尽后限速(每次 2000 字符)而非拒绝,且返回的仍是所请求区间的开头;
4. 小文件靠 64KB 下限自由回看(WF08/4b 十几次回读全部放行);
5. batch_tools 子调用与主循环共享同一份计数;
6. 图片在守卫之前豁免。
"""
import importlib.util
import os
import sys

import pytest

_spec = importlib.util.spec_from_file_location(
    "ollama_agent", os.path.join(os.path.dirname(__file__), "..", "ollama_agent.py"))
sys.argv = ["test"]


@pytest.fixture(scope="module")
def oa():
    mod = importlib.util.module_from_spec(_spec)
    try:
        _spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def _mk(tmp_path, name, n_lines=100, pad=""):
    p = tmp_path / name
    p.write_text("".join(f"L{i:03d} {pad}\n" for i in range(1, n_lines + 1)),
                 encoding="utf-8")
    return str(p)


def _read(oa, wd, path, **kw):
    return oa.run_tool("read_file", {"path": path, **kw}, wd, crawl_state={})


# ---- 1. 预算内:完整请求区间、零附加 ----

def test_within_budget_returns_requested_range(oa, tmp_path):
    f = _mk(tmp_path, "data.txt")
    wd = str(tmp_path)
    r1 = _read(oa, wd, "data.txt", start_line=10, end_line=12)
    assert r1.startswith("L010") and "L012" in r1 and "L013" not in r1
    assert "crawl-guard" not in r1 and "[提示" not in r1
    # 连续多次区间读取(远未到 64KB 下限)都完整返回
    r2 = _read(oa, wd, "data.txt", start_line=50, end_line=60)
    assert r2.startswith("L050") and "crawl-guard" not in r2


def test_full_read_within_budget(oa, tmp_path):
    _mk(tmp_path, "small.txt", n_lines=20)
    r = _read(oa, str(tmp_path), "small.txt")
    assert r.startswith("L001") and "L020" in r


# ---- 2. 温和建议:第 4/10 次各一次,只加行不改数据 ----

def test_nudge_at_4th_and_10th_only(oa, tmp_path):
    _mk(tmp_path, "n.txt", n_lines=30)
    wd = str(tmp_path)
    state = {}
    results = [oa.run_tool("read_file", {"path": "n.txt"}, wd, crawl_state=state)
               for _ in range(11)]
    nudged = [i + 1 for i, r in enumerate(results) if "[提示" in r]
    assert nudged == [4, 10]                       # 恰好两次,其余干净
    # 建议只加一行:数据体完整保留在其后
    assert results[3].startswith("[提示")
    assert "L001" in results[3] and "L030" in results[3]
    assert "crawl-guard" not in results[3]


# ---- 3. 预算耗尽:限速而非拒绝,区间仍被尊重 ----

def test_throttle_respects_requested_range(oa, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "_CRAWL_BUDGET_MULT", 1, raising=False)
    monkeypatch.setattr(oa, "_CRAWL_BUDGET_FLOOR", 1024, raising=False)
    _mk(tmp_path, "big.txt", n_lines=200, pad="x" * 40)   # ~9KB/200 行
    wd = str(tmp_path)
    state = {}
    # 预算 = 1×8.8KB;两次全读(各截 6000)累计 12000 字符 > 8800 → 第二次起越限
    r1 = oa.run_tool("read_file", {"path": "big.txt"}, wd, crawl_state=state)
    assert "crawl-guard" not in r1
    r2 = oa.run_tool("read_file", {"path": "big.txt"}, wd, crawl_state=state)
    assert "读取不会被拒绝" in r2                     # 首次限速给完整出路说明
    assert "run_bash" in r2 and "python" in r2          # 说明含可照抄的脚本出路
    # 越限后的区间读取:返回的仍是所请求区间的开头,不是文件头
    r3 = oa.run_tool("read_file",
                     {"path": "big.txt", "start_line": 150, "end_line": 200},
                     wd, crawl_state=state)
    assert "限速中" in r3                              # 后续限速为短提示
    assert r3.splitlines()[1].startswith("L150")
    assert "L001" not in r3.split("限速中", 1)[1]
    body3 = r3.split("]\n", 1)[1]
    assert len(body3.split("\n[文件共")[0]) <= oa._CRAWL_THROTTLE


def test_throttle_never_denies_outright(oa, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "_CRAWL_BUDGET_FLOOR", 200, raising=False)
    _mk(tmp_path, "d.txt", n_lines=60, pad="y" * 30)
    wd = str(tmp_path)
    state = {}
    for i in range(8):
        r = oa.run_tool("read_file", {"path": "d.txt"}, wd, crawl_state=state)
        # 每一次都必须包含真实文件内容——不存在只回拒绝文本的死墙
        assert "L001" in r or "L0" in r


# ---- 4. 小文件回看不触限(WF08/4b 回归锚) ----

def test_small_file_many_reads_still_full(oa, tmp_path):
    p = tmp_path / "app.py"
    p.write_text("def run():\n    return 42\n" * 20, encoding="utf-8")  # ~440B
    wd = str(tmp_path)
    state = {}
    for _ in range(15):
        r = oa.run_tool("read_file", {"path": "app.py"}, wd, crawl_state=state)
        assert "def run():" in r                      # 15 次回读数据始终完整
        assert "crawl-guard" not in r                 # 小文件下限兜底,永不限速


# ---- 5. 状态隔离与 batch_tools 共享 ----

def test_state_isolation_between_tasks(oa, tmp_path, monkeypatch):
    monkeypatch.setattr(oa, "_CRAWL_BUDGET_FLOOR", 1024, raising=False)
    _mk(tmp_path, "s.txt", n_lines=100, pad="z" * 30)
    wd = str(tmp_path)
    s1, s2 = {}, {}
    for _ in range(4):
        oa.run_tool("read_file", {"path": "s.txt"}, wd, crawl_state=s1)
    r_new_task = oa.run_tool("read_file", {"path": "s.txt"}, wd, crawl_state=s2)
    assert "crawl-guard" not in r_new_task           # 新任务计数从零开始


def test_batch_tools_shares_crawl_accounting(oa, tmp_path):
    _mk(tmp_path, "b.txt", n_lines=30)
    wd = str(tmp_path)
    state = {}
    out = oa.run_tool("batch_tools",
                      {"calls": [{"tool": "read_file", "args": {"path": "b.txt"}}]},
                      wd, crawl_state=state)
    key = os.path.normcase(os.path.normpath(str(tmp_path / "b.txt")))
    assert key in state                                # 子调用记入同一份计数
    assert state[key][0] == 1
    assert "L001" in out


# ---- 6. 图片豁免在守卫之前 ----

def test_images_exempt_from_crawl_guard(oa, tmp_path):
    (tmp_path / "fig.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    wd = str(tmp_path)
    state = {}
    for _ in range(8):
        r = oa.run_tool("read_file", {"path": "fig.png"}, wd, crawl_state=state)
        assert "[image attached" in r or "[image queued" in r or "[image too large" in r
    key = os.path.normcase(os.path.normpath(str(tmp_path / "fig.png")))
    assert key not in state                            # 图片不进爬行计数
