# -*- coding: utf-8 -*-
"""Regression tests for LRAB archive classification (gen_manifest.classify)."""
import sys, os, importlib.util

# load gen_manifest without executing main
_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bench", "lrab", "gen_manifest.py")
_spec = importlib.util.spec_from_file_location("gen_manifest", os.path.normpath(_path))
gm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gm)


class TestManifestClassify:
    def test_eval_canonical_clean(self):
        # clean run-id in eval root -> canonical
        assert gm.classify("hummingbird_WF06_35b_0830_120000", "eval")[0] == "canonical"

    def test_eval_smoke_is_prefix(self):
        assert gm.classify("smoke5_hb_e2b_WF06", "eval")[0] == "pre-fix"
        assert gm.classify("verify_oc_e2b", "eval")[0] == "pre-fix"
        assert gm.classify("m1_opencode_4b_WF06", "eval")[0] == "pre-fix"

    def test_dev_root_always_prefix(self):
        # anything in bench/lrab/results/ is dev-only, never canonical
        assert gm.classify("hummingbird_WF06_35b_0830", "dev")[0] == "pre-fix"
        assert gm.classify("anything_else", "dev")[0] == "pre-fix"

    def test_timestamped_agent_mini_is_prefix(self):
        # old-style timestamped run id is dev data, not canonical
        assert gm.classify("agent-mini_WF-06_20260828_143856", "dev")[0] == "pre-fix"
