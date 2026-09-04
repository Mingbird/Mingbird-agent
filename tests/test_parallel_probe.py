"""硬件探测与容量公式测试(全部注入假读数器,不打真机器)。"""
import json
import os
import sys
import urllib.request

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import parallel_probe as PP
from parallel_config import get_parallel_config

GIB = 1024 ** 3


def cfg(**over):
    c = get_parallel_config(config={"parallel": {}})
    c.update(over)
    return c


def probe(available_gib=20.0, total_gib=32.0, loaded=(), models_ok=True):
    return PP.ResourceProbe(
        mem_reader=lambda: (total_gib * GIB, available_gib * GIB),
        models_reader=lambda: (list(loaded) if models_ok else None))


class TestEstimate:
    def test_e2b_8k_conservative(self):
        cost, br = PP.estimate_child_cost("gemma4:e2b", cfg())
        assert 3.0 * GIB < cost < 5.0 * GIB          # 设计表 ~4.0GB
        assert br["params_b"] == 2.0 and br["ctx"] == 8192

    def test_4b_8k_bigger_than_e2b(self):
        c2, _ = PP.estimate_child_cost("gemma4:e2b", cfg())
        c4, _ = PP.estimate_child_cost("qwen3.5:4b", cfg())
        assert c4 > c2 * 1.5

    def test_larger_ctx_costs_more(self):
        c8, _ = PP.estimate_child_cost("gemma4:e2b", cfg(child_ctx=8192))
        c32, _ = PP.estimate_child_cost("gemma4:e2b", cfg(child_ctx=32768))
        assert c32 > c8

    def test_too_large_model_rejected(self):
        cost, br = PP.estimate_child_cost("ornith-1.5:35b", cfg())
        assert cost is None and br["reason"] == "child_model_too_large"

    def test_unparsable_model_treated_as_large(self):
        cost, br = PP.estimate_child_cost("some-model", cfg())
        assert cost is None

    def test_loaded_size_preferred_over_estimate(self):
        cost, br = PP.estimate_child_cost("gemma4:e2b", cfg(), loaded_size=1.4 * GIB)
        assert br["weights_bytes"] == pytest.approx(1.4 * GIB)


class TestCapacity:
    def test_two_e2b_on_20gb_free(self):
        plan = probe(available_gib=20.0).plan_capacity("gemma4:e2b", cfg())
        assert plan["max_parallel"] == 2     # floor(12.5/4.0)=3 → clamp hard_cap 2
        assert any("clamped_to_hard_cap" in r for r in plan["reasons"])

    def test_budget_zero_means_no_dispatch(self):
        plan = probe(available_gib=1.0).plan_capacity("gemma4:e2b", cfg())
        assert plan["max_parallel"] == 0
        assert any("no_headroom" in r for r in plan["reasons"])

    def test_hard_cap_respected(self):
        plan = probe(available_gib=31.0).plan_capacity("gemma4:e2b", cfg(hard_cap=2))
        assert plan["max_parallel"] <= 2

    def test_memory_probe_failure_conservative(self):
        p = PP.ResourceProbe(mem_reader=lambda: None,
                             models_reader=lambda: [])
        plan = p.plan_capacity("gemma4:e2b", cfg())
        assert plan["max_parallel"] == 0 and "memory_probe_failed" in plan["reasons"][0]

    def test_ollama_ps_unreachable_conservative(self):
        p = PP.ResourceProbe(mem_reader=lambda: (32 * GIB, 20 * GIB),
                             models_reader=lambda: None)
        plan = p.plan_capacity("gemma4:e2b", cfg())
        assert plan["max_parallel"] == 0
        assert any("ollama_ps_unreachable" in r for r in plan["reasons"])

    def test_parent_model_eviction_forbidden_by_default(self):
        p = probe(available_gib=20.0,
                  loaded=[{"model": "ornith-1.5:35b", "size": 20 * GIB, "size_vram": 18 * GIB}])
        plan = p.plan_capacity("gemma4:e2b", cfg())
        assert plan["max_parallel"] == 0
        assert any("parent_model_would_be_evicted" in r for r in plan["reasons"])

    def test_parent_eviction_allowed_unlocks(self):
        p = probe(available_gib=20.0,
                  loaded=[{"model": "ornith-1.5:35b", "size": 20 * GIB, "size_vram": 18 * GIB}])
        plan = p.plan_capacity("gemma4:e2b", cfg(allow_parent_eviction=True))
        assert plan["max_parallel"] >= 1

    def test_same_model_as_parent_still_counts_full_cost(self):
        p = probe(available_gib=20.0,
                  loaded=[{"model": "gemma4:e2b", "size": 2 * GIB, "size_vram": 2 * GIB}])
        plan = p.plan_capacity("gemma4:e2b", cfg())
        assert plan["max_parallel"] == 2      # 不做同模型折扣(高估方向)

    def test_reasons_are_human_readable(self):
        plan = probe(available_gib=20.0).plan_capacity("gemma4:e2b", cfg())
        assert any("budget=" in r for r in plan["reasons"])
        assert any("per_child=" in r for r in plan["reasons"])

    def test_capacity_table_renders(self):
        plan = probe(available_gib=20.0).plan_capacity("gemma4:e2b", cfg())
        text = PP.format_capacity_table(plan, cfg())
        assert "max_parallel = 2" in text


class TestPsParsing:
    def test_read_loaded_models_parses_size_and_size_vram(self, monkeypatch):
        payload = json.dumps({"models": [
            {"model": "gemma4:e2b", "size": 2147483648, "size_vram": 2000000000}]}).encode()

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R())
        out = PP.read_loaded_models("http://127.0.0.1:11434")
        assert out[0]["model"] == "gemma4:e2b"
        assert out[0]["size"] == 2147483648 and out[0]["size_vram"] == 2000000000

    def test_read_loaded_models_none_on_error(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("refused")

        monkeypatch.setattr(urllib.request, "urlopen", boom)
        assert PP.read_loaded_models("http://127.0.0.1:11434") is None


class TestMemReaders:
    def test_read_system_memory_uses_psutil_here(self):
        r = PP.read_system_memory()
        assert r and r[0] > 0 and r[1] > 0 and r[1] <= r[0]
