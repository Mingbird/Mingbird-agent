"""触发层测试:TodoProvider 抽象、分类器、安全预检、触发条件 AND 逻辑。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import parallel_todo as PT
from parallel_config import get_parallel_config

GIB = 1024 ** 3


def cfg(**over):
    c = get_parallel_config(config={"parallel": {}})
    c.update(over)
    return c


def write_todo(path, items):
    """items: str 或 (text, done) 或 (text, done, complexity)。"""
    data = []
    for it in items:
        if isinstance(it, str):
            data.append({"item": it, "done": False})
        else:
            d = {"item": it[0], "done": bool(it[1])}
            if len(it) > 2:
                d["complexity"] = it[2]
            data.append(d)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)


class StubProbe:
    def __init__(self, max_parallel=2, reasons=None):
        self.mp = max_parallel
        self.reasons = reasons or []

    def plan_capacity(self, model, cfg):
        return {"max_parallel": self.mp, "reasons": list(self.reasons), "snapshot": {}}


# ---------------- TodoProvider ----------------
class TestTodoProvider:
    def test_read_current_format(self, tmp_path):
        write_todo(tmp_path / "todo.json", ["a", ("b", True)])
        p = PT.JsonTodoProvider(str(tmp_path))
        assert len(p.all_items()) == 2
        assert [i.text for i in p.pending_items()] == ["a"]

    def test_tolerates_item_text_title_and_dict_wrapper(self, tmp_path):
        json.dump({"items": [{"text": "x", "done": False}]},
                  open(tmp_path / "todo.json", "w", encoding="utf-8"))
        assert [i.text for i in PT.JsonTodoProvider(str(tmp_path)).pending_items()] == ["x"]

    def test_mark_done_idempotent_and_no_reorder(self, tmp_path):
        write_todo(tmp_path / "todo.json", ["a", "b", "c"])
        p = PT.JsonTodoProvider(str(tmp_path))
        assert p.mark_done("2") is True
        assert p.mark_done("2") is True          # 幂等
        items = p.all_items()
        assert [i.text for i in items] == ["a", "b", "c"]   # 不重排
        assert [i.done for i in items] == [False, True, False]

    def test_missing_file_is_empty_not_error(self, tmp_path):
        assert PT.JsonTodoProvider(str(tmp_path)).all_items() == []

    def test_complexity_annotation_read(self, tmp_path):
        write_todo(tmp_path / "todo.json", [("x", False, "simple")])
        assert PT.JsonTodoProvider(str(tmp_path)).all_items()[0].complexity == "simple"

    def test_factory_default_provider(self, tmp_path):
        assert isinstance(PT.make_provider(str(tmp_path)), PT.JsonTodoProvider)


# ---------------- 分类器 ----------------
class TestClassify:
    def test_mechanical_single_file(self):
        r = PT.classify_task("把 data.csv 里的列名翻译成中文并另存", cfg())
        assert r.dispatchable

    def test_veto_delete(self):
        assert not PT.classify_task("删除 tmp.log 并统计行数", cfg()).dispatchable

    def test_veto_overwrite(self):
        assert not PT.classify_task("覆盖 config.json 里的字段", cfg()).dispatchable

    def test_veto_network_write(self):
        assert not PT.classify_task("把 result.md 上传到服务器", cfg()).dispatchable

    def test_veto_cross_file(self):
        assert not PT.classify_task("重构 project.py 的所有模块结构", cfg()).dispatchable

    def test_veto_dependency_install(self):
        assert not PT.classify_task("pip install pandas 后生成 out.csv", cfg()).dispatchable

    def test_veto_test_running(self):
        assert not PT.classify_task("运行 test_report.py 验证输出", cfg()).dispatchable

    def test_multi_file_not_dispatchable(self):
        r = PT.classify_task("把 a.csv 和 b.csv 都转成 markdown", cfg())
        assert not r.dispatchable and "files=" in r.reason

    def test_single_file_but_not_mechanical(self):
        r = PT.classify_task("为 report.md 设计一个更好的结构", cfg())
        assert not r.dispatchable

    def test_simple_annotation_escapes_mechanical_requirement(self):
        r = PT.classify_task("[simple] 为 out.md 补一个标题行", cfg())
        assert r.dispatchable

    def test_simple_annotation_cannot_escape_single_file_rule(self):
        assert not PT.classify_task("[simple] 整理所有文件", cfg()).dispatchable

    def test_complex_annotation_always_rejected(self):
        assert not PT.classify_task("[complex] 把 a.csv 转成 b.md", cfg()).dispatchable

    def test_complexity_word_in_text_rejected(self):
        assert not PT.classify_task("转换 main.py,这一步很关键,别搞错", cfg()).dispatchable

    def test_empty_item(self):
        assert not PT.classify_task("", cfg()).dispatchable

    def test_reason_always_explains(self):
        for t in ("删除 x", "把 a.csv 转成 b.md", "随便看看 report.md"):
            assert PT.classify_task(t, cfg()).reason


# ---------------- 安全预检(第二道闸) ----------------
class TestSafetyPrecheck:
    def test_wsl_in_task_text_blocked(self):
        ok, why = PT.safety_precheck("清理 wsl --unregister Ubuntu 的残留", cfg())
        assert not ok and "severe_command" in why

    def test_sensitive_path_in_task_text_blocked(self):
        ok, why = PT.safety_precheck("把结果写到 .env 里", cfg())
        assert not ok and "sensitive_in_task_text" in why

    def test_normal_task_passes(self):
        assert PT.safety_precheck("把 data.csv 转成 markdown 表格", cfg())[0] is True

    def test_precheck_blocks_even_annotated_simple(self):
        assert PT.classify_task("[simple] 删除 old.csv 后生成 new.csv", cfg()).dispatchable is False \
            or not PT.safety_precheck("删除 old.csv", cfg())[0]


# ---------------- 触发条件(全部 AND) ----------------
class TestShouldDispatch:
    def _todo(self, tmp_path, n=6, text="把 data.csv 转成 markdown 表格"):
        write_todo(tmp_path / "todo.json", [text.format(i=i) if "{}" in text else text
                                            for i in range(n)])
        return PT.JsonTodoProvider(str(tmp_path))

    def test_disabled_by_default(self, tmp_path):
        plan = PT.should_dispatch(StubProbe(), self._todo(tmp_path), cfg(), environ={})
        assert not plan.should and "disabled" in plan.reasons[0]

    def test_hard_kill_switch_wins(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        plan = PT.should_dispatch(StubProbe(), self._todo(tmp_path), c,
                                  environ={"AGENT_PARALLEL": "0"})
        assert not plan.should and "hard_kill_switch" in plan.reasons[0]

    def test_depth_limit_blocks_children(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        plan = PT.should_dispatch(StubProbe(), self._todo(tmp_path), c,
                                  environ={"HUMMINGBIRD_DEPTH": "1"})
        assert not plan.should and "depth_limit" in plan.reasons[0]

    def test_no_child_model_means_off(self, tmp_path):
        c = cfg(enabled=True)
        plan = PT.should_dispatch(StubProbe(), self._todo(tmp_path), c, environ={})
        assert not plan.should and "no_child_model" in plan.reasons[0]

    def test_too_few_pending(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        plan = PT.should_dispatch(StubProbe(), self._todo(tmp_path, n=3), c, environ={})
        assert not plan.should and "too_few_pending" in plan.reasons[0]

    def test_too_few_dispatchable(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        write_todo(tmp_path / "todo.json",
                   ["把 data.csv 转成 markdown 表格"] + [f"重构模块{i}" for i in range(5)])
        plan = PT.should_dispatch(StubProbe(), PT.JsonTodoProvider(str(tmp_path)), c, environ={})
        assert not plan.should and "too_few_dispatchable" in plan.reasons[0]

    def test_no_capacity_blocks(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        plan = PT.should_dispatch(StubProbe(max_parallel=0, reasons=["no headroom"]),
                                  self._todo(tmp_path), c, environ={})
        assert not plan.should and "no_capacity" in plan.reasons[0]

    def test_happy_path(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        plan = PT.should_dispatch(StubProbe(max_parallel=2), self._todo(tmp_path), c, environ={})
        assert plan.should and plan.n_items == 6
        assert all(i.done is False for i in plan.items)

    def test_done_items_not_dispatched(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")
        write_todo(tmp_path / "todo.json", [("把 data.csv 转成 markdown 表格", True)] * 6)
        plan = PT.should_dispatch(StubProbe(), PT.JsonTodoProvider(str(tmp_path)), c, environ={})
        assert not plan.should

    def test_skipped_items_carry_reason(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b", min_dispatchable=1,
                min_pending_items=3)
        write_todo(tmp_path / "todo.json",
                   ["把 data.csv 转成 markdown 表格", "删除 old.csv", "重构 core.py"])
        plan = PT.should_dispatch(StubProbe(max_parallel=2), PT.JsonTodoProvider(str(tmp_path)),
                                  c, environ={})
        assert len(plan.items) == 1 and len(plan.skipped) == 2
        assert all(r for _, r in plan.skipped)

    def test_provider_error_is_caught(self, tmp_path):
        c = cfg(enabled=True, child_model="gemma4:e2b")

        class Boom:
            def pending_items(self):
                raise RuntimeError("disk full")

        plan = PT.should_dispatch(StubProbe(), Boom(), c, environ={})
        assert not plan.should and "todo_provider_error" in plan.reasons[0]
