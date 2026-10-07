# -*- coding: utf-8 -*-
"""v1.9.1 通用能力测试:run_python 冻结解释器、双语 STT 辅助、通用 skill 清单。"""
import io as _io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ollama_agent as A
import voice_input as V


class TestRunPythonTool(unittest.TestCase):
    def test_tool_def_and_category(self):
        names = [t["function"]["name"] for t in A.ADVANCED_TOOLS] + \
                [t["function"]["name"] for t in A.CORE_TOOLS]
        self.assertIn("run_python", names)
        self.assertIn("run_python", A._CATEGORY_TOOLS["代码"])
        self.assertIn("run_python", A._REQ_ARGS)
        # prefill 红线:run_python 绝不能进基础工具(出厂 prefill 零增量)
        self.assertNotIn("run_python", A._BASE_TOOLS)

    def test_prefill_budget_unchanged(self):
        msgs = [{"role": "system", "content": A.SYSTEM}]
        self.assertEqual(A._estimate_messages_tokens(msgs, A.CORE_TOOLS), 851)  # v2.0.3: 846+5(todo schema 标 1-based)

    def test_hook_cmd_shape(self):
        cmd = A._python_hook_cmd("x.py")
        self.assertIn("--run-py", cmd)
        self.assertEqual(cmd[-1], "x.py")

    def test_run_python_executes(self):
        # 纯 stdlib 脚本(CI 最小依赖环境也能跑);顺带验证 cwd=workdir
        with tempfile.TemporaryDirectory() as d:
            out = A.run_tool("run_python",
                             {"code": "print(6*7)\nopen('ok.txt','w').write('x')"},
                             d)
            self.assertIn("42", out)
            self.assertTrue(os.path.exists(os.path.join(d, "ok.txt")))

    def test_run_python_danger_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            out = A.run_tool("run_python", {"code": "import os; os.system('format c:')"}, d)
            self.assertIn("安全门", out)

    def test_run_python_missing_args_hint(self):
        with tempfile.TemporaryDirectory() as d:
            out = A.run_tool("run_python", {}, d)
            self.assertIn("缺少参数", out)


class TestBilingualSTT(unittest.TestCase):
    # stt 模型是 gitignored 的分发资产:开发机/打包机上有,CI checkout 没有。
    # 这里只测"有模型时能解析";打包完整性由冻结包自检(selftest + 目录清单)保证。
    SIX = ["file_organizer", "web_research", "doc_digest",
           "office_word", "office_excel", "image_batch"]

    def test_both_languages_resolve_model_dir(self):
        if V._stt_model_dir("zh") is None and V._stt_model_dir("en") is None:
            self.skipTest("stt models not present (gitignored assets)")
        for lang in ("zh", "en"):
            d = V._stt_model_dir(lang)
            self.assertIsNotNone(d, f"{lang} 模型目录未找到")
            f = V._stt_files(d)
            self.assertIsNotNone(f, f"{lang} int8 三件套不全")
            for k in ("encoder", "decoder", "joiner"):
                self.assertIn("int8", os.path.basename(f[k]))
            self.assertTrue(os.path.exists(f["tokens"]))

    def test_stt_dirs_only_int8(self):
        if V._stt_model_dir("zh") is None and V._stt_model_dir("en") is None:
            self.skipTest("stt models not present (gitignored assets)")
        # 体积纪律:内置模型目录不允许再带 float32 权重(安装包瘦身承诺)
        for lang in ("zh", "en"):
            d = V._stt_model_dir(lang)
            if d is None:
                continue
            floats = [x for x in os.listdir(d)
                      if x.endswith(".onnx") and "int8" not in x]
            self.assertEqual(floats, [], f"{lang} 目录残留 float 权重: {floats}")


class TestUniversalSkills(unittest.TestCase):
    SIX = ["file_organizer", "web_research", "doc_digest",
           "office_word", "office_excel", "image_batch"]

    def test_six_universal_skills_listed(self):
        with tempfile.TemporaryDirectory() as d:
            listing = A.list_skills(d)
            for s in self.SIX:
                self.assertIn(s, listing)

    def test_skill_format_frontmatter(self):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
        for s in self.SIX:
            head = _io.open(os.path.join(base, s + ".md"), encoding="utf-8").read(400)
            self.assertIn("name:", head)
            self.assertIn("description:", head)

    def test_skills_readme_documents_install(self):
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skills")
        rd = _io.open(os.path.join(base, "README.md"), encoding="utf-8").read()
        self.assertIn(".ollama_agent", rd)      # 自装技能路径说明
        self.assertIn("mcp.json", rd)           # MCP 配置说明


if __name__ == "__main__":
    unittest.main()
