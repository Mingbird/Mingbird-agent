"""多模态输入接线(视觉)测试:read_file 图片分支 + 消息级 images 附载 + 历史剥离。

背景:四个出厂模型 ollama manifest 全部带 vision,但 harness 从未传图
(GAIA 图片/视频题全 0 根因)。本套验证 read_file→pending 队列→images 附载链路。"""
import base64
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ollama_agent as A

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


def _mk_img(tmp_path, name="photo.png"):
    p = tmp_path / name
    p.write_bytes(_PNG_1PX)
    return name


def test_read_file_image_queues_and_attaches(tmp_path):
    name = _mk_img(tmp_path)
    out = A.run_tool("read_file", {"path": name}, str(tmp_path))
    assert "[image attached" in out
    pend = A._pending_images_load(str(tmp_path))
    assert len(pend) == 1
    assert base64.b64decode(pend[0]["b64"]) == _PNG_1PX


def test_read_file_text_still_works(tmp_path):
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    out = A.run_tool("read_file", {"path": "note.txt"}, str(tmp_path))
    assert "hello" in out
    assert A._pending_images_load(str(tmp_path)) == []


def test_attach_puts_images_on_last_tool_message(tmp_path):
    name = _mk_img(tmp_path)
    A.run_tool("read_file", {"path": name}, str(tmp_path))
    msgs = [{"role": "system", "content": "s"},
            {"role": "user", "content": "task"},
            {"role": "tool", "content": "[image attached]"}]
    n = A._attach_pending_images(msgs, str(tmp_path))
    assert n == 1
    assert len(msgs[2]["images"]) == 1
    assert msgs[1].get("images") is None          # 不动更早的消息
    assert A._pending_images_load(str(tmp_path)) == []   # 队列清空


def test_attach_strips_old_images_keeps_recent_two(tmp_path):
    msgs = []
    for i in range(5):
        msgs.append({"role": "tool", "content": f"c{i}", "images": ["x" + str(i)]})
    A._attach_pending_images(msgs, str(tmp_path))
    kept = [m for m in msgs if m.get("images")]
    assert len(kept) == A._IMG_KEEP_MSGS
    assert kept[-1]["images"] == ["x4"]            # 最近的保留


def test_read_file_image_outside_workdir_blocked(tmp_path):
    # 越界图片必须被边界守护拦截(视觉接线不豁免安全门)
    evil = tmp_path.parent / "evil.png"
    evil.write_bytes(_PNG_1PX)
    out = A.run_tool("read_file", {"path": str(evil)}, str(tmp_path))
    assert "blocked" in out or "not found" in out or "越界" in out
    assert A._pending_images_load(str(tmp_path)) == []


def test_read_file_image_queue_limit(tmp_path, monkeypatch):
    for i in range(A._IMG_PER_TURN):
        _mk_img(tmp_path, f"p{i}.png")
    for i in range(A._IMG_PER_TURN):
        A.run_tool("read_file", {"path": f"p{i}.png"}, str(tmp_path))
    _mk_img(tmp_path, "overflow.png")
    out = A.run_tool("read_file", {"path": "overflow.png"}, str(tmp_path))
    assert "queued" in out
    assert len(A._pending_images_load(str(tmp_path))) == A._IMG_PER_TURN


def test_oversize_image_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_IMG_MAX_BYTES", 4)
    _mk_img(tmp_path)
    out = A.run_tool("read_file", {"path": "photo.png"}, str(tmp_path))
    assert "too large" in out
