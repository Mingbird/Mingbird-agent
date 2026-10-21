# -*- coding: utf-8 -*-
"""v3.0.0 review fixes for the local Web UI (webui/server.py).

P0: SSE used a list index as cursor. After EVENTS was truncated to 600,
`idx >= len(EVENTS)` was permanently true and the stream went silent.
P1: @@ASK@@ payloads are JSON-encoded token frames now; the decoder must
accept both the new JSON string frames and legacy raw text.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def test_event_ids_monotonic_and_truncation_does_not_stall():
    import webui.server as S
    saved_events, saved_seq = list(S.EVENTS), S.EVENT_SEQ
    try:
        S.EVENTS.clear()
        S.EVENT_SEQ = 0
        for i in range(700):
            S.push_event({"type": "tok", "data": str(i)})
        assert len(S.EVENTS) == S.EVENTS_MAX == 600
        assert S.EVENTS[-1]["id"] == 700
        ids = [e["id"] for e in S.EVENTS]
        assert ids == sorted(ids) and len(set(ids)) == len(ids)
        # 一个落后 600 条的客户端仍能拿到缓冲区里的新事件(按 id 切片)
        last_id = 100
        new = [e for e in S.EVENTS if e["id"] > last_id]
        assert new and new[-1]["id"] == 700
        assert all(e["id"] > last_id for e in new)
    finally:
        S.EVENTS[:] = saved_events
        S.EVENT_SEQ = saved_seq


def test_session_list_excludes_todo_snapshots():
    src = open(os.path.join(_HERE, "webui", "server.py"), encoding="utf-8").read()
    assert 'f.endswith((".meta.json", ".todo.json"))' in src


def test_decode_frame_json_and_legacy():
    import webui.server as S
    assert S._decode_frame(json.dumps("a\nb", ensure_ascii=False)) == "a\nb"
    assert S._decode_frame("plain legacy") == "plain legacy"
    assert S._decode_frame('"quoted"') == "quoted"


def test_cloud_public_never_leaks_key(monkeypatch):
    import appconfig
    import webui.server as S
    monkeypatch.setattr(appconfig, "load_config", lambda: {
        "cloud": {"enabled": True, "base_url": "https://api.example.com/v1",
                  "model": "demo", "api_key": "sk-secret"}})
    d = S._cloud_public()
    assert d == {"enabled": True, "base_url": "https://api.example.com/v1",
                 "model": "demo", "has_key": True}
    assert "sk-secret" not in json.dumps(d)


def test_session_rows_title_status_and_todo_filter(tmp_path, monkeypatch):
    import appconfig
    import webui.server as S
    sd = tmp_path / "sessions"
    sd.mkdir()
    (sd / "chat_1.json").write_text(
        json.dumps([{"role": "user", "content": "hello world"}]), encoding="utf-8")
    (sd / "chat_1.meta.json").write_text(
        json.dumps({"title": "Greeting", "status": "done"}), encoding="utf-8")
    (sd / "chat_1.todo.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(appconfig, "AGENT_HOME", str(tmp_path))
    rows = S._session_rows()
    assert [r["name"] for r in rows] == ["chat_1"]
    assert rows[0]["title"] == "Greeting"
    assert rows[0]["status"] == "done"
    assert "mtime" in rows[0]


def test_session_rows_falls_back_to_first_user_message(tmp_path, monkeypatch):
    import appconfig
    import webui.server as S
    sd = tmp_path / "sessions"
    sd.mkdir()
    (sd / "chat_2.json").write_text(
        json.dumps([{"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "  整理这个目录  "}]), encoding="utf-8")
    monkeypatch.setattr(appconfig, "AGENT_HOME", str(tmp_path))
    rows = S._session_rows()
    assert rows[0]["title"] == "整理这个目录"
