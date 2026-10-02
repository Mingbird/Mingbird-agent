# -*- coding: utf-8 -*-
"""issue #1:自动启动 ollama serve 时继承 Ollama GUI 的自定义模型目录。

Ollama 0.3x GUI 把模型目录存在 %LOCALAPPDATA%\\Ollama\\db.sqlite 的 settings.models,
不写用户环境变量;我们 spawn 的 serve 需显式带上 OLLAMA_MODELS。
优先级:用户环境变量/配置层 > GUI 设置;无 GUI 设置时行为不变。
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ollama_agent as A


def _fabricate_db(dirpath, models_value):
    os.makedirs(os.path.join(dirpath, "Ollama"), exist_ok=True)
    db = os.path.join(dirpath, "Ollama", "db.sqlite")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, models TEXT)")
    con.execute("INSERT INTO settings (models) VALUES (?)", (models_value,))
    con.commit()
    con.close()
    return db


class TestOllamaAppModelsDir(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_reads_models_column(self):
        if sys.platform != "win32":
            self.skipTest("Ollama app settings DB is Windows-specific")
        _fabricate_db(self.tmp, "E:\\Ollama_Models")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp}):
            self.assertEqual(A._ollama_app_models_dir(), "E:\\Ollama_Models")

    def test_blank_value_returns_none(self):
        if sys.platform != "win32":
            self.skipTest("Ollama app settings DB is Windows-specific")
        _fabricate_db(self.tmp, "   ")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp}):
            self.assertIsNone(A._ollama_app_models_dir())

    def test_missing_db_returns_none(self):
        if sys.platform != "win32":
            self.skipTest("Ollama app settings DB is Windows-specific")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp}):
            self.assertIsNone(A._ollama_app_models_dir())

    def test_corrupt_db_returns_none(self):
        if sys.platform != "win32":
            self.skipTest("Ollama app settings DB is Windows-specific")
        os.makedirs(os.path.join(self.tmp, "Ollama"), exist_ok=True)
        with open(os.path.join(self.tmp, "Ollama", "db.sqlite"), "wb") as f:
            f.write(b"not a sqlite file at all")
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp}):
            self.assertIsNone(A._ollama_app_models_dir())

    def test_empty_settings_table_returns_none(self):
        if sys.platform != "win32":
            self.skipTest("Ollama app settings DB is Windows-specific")
        os.makedirs(os.path.join(self.tmp, "Ollama"), exist_ok=True)
        con = sqlite3.connect(os.path.join(self.tmp, "Ollama", "db.sqlite"))
        con.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, models TEXT)")
        con.commit()
        con.close()
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": self.tmp}):
            self.assertIsNone(A._ollama_app_models_dir())

    def test_non_windows_returns_none(self):
        with mock.patch.object(A.sys, "platform", "linux"):
            self.assertIsNone(A._ollama_app_models_dir())


class TestEnsureOllamaEnv(unittest.TestCase):
    """ensure_ollama spawn serve 时传给子进程的环境变量(不起真进程/不连网)。"""

    def _run_ensure(self, pop_models=True):
        cfg = mock.MagicMock()
        cfg.ollama_host.return_value = "http://127.0.0.1:59999"
        cfg.ollama_env.return_value = {}
        popen = mock.MagicMock()
        ctx = mock.patch.dict(os.environ)
        with ctx:
            if pop_models:
                os.environ.pop("OLLAMA_MODELS", None)
            with mock.patch.object(A, "appconfig", cfg), \
                 mock.patch.object(A, "subprocess", popen), \
                 mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
                ok = A.ensure_ollama(timeout=0.1)
        return ok, popen

    def test_gui_dir_passed_to_serve(self):
        with mock.patch.object(A, "_ollama_app_models_dir", return_value="E:\\Ollama_Models"):
            ok, popen = self._run_ensure()
        self.assertFalse(ok)  # urlopen 一直失败 → 等待超时,但进程已按正确 env 拉起
        popen.Popen.assert_called_once()
        kwargs = popen.Popen.call_args.kwargs
        self.assertEqual(kwargs["env"]["OLLAMA_MODELS"], "E:\\Ollama_Models")

    def test_user_env_var_wins_over_gui(self):
        with mock.patch.dict(os.environ, {"OLLAMA_MODELS": "D:\\mine"}), \
             mock.patch.object(A, "_ollama_app_models_dir", return_value="E:\\Ollama_Models"):
            ok, popen = self._run_ensure(pop_models=False)
        kwargs = popen.Popen.call_args.kwargs
        self.assertEqual(kwargs["env"]["OLLAMA_MODELS"], "D:\\mine")

    def test_config_layer_wins_over_gui(self):
        cfg = mock.MagicMock()
        cfg.ollama_host.return_value = "http://127.0.0.1:59999"
        cfg.ollama_env.return_value = {"OLLAMA_MODELS": "D:\\from-config"}
        popen = mock.MagicMock()
        with mock.patch.dict(os.environ):
            os.environ.pop("OLLAMA_MODELS", None)
            with mock.patch.object(A, "appconfig", cfg), \
                 mock.patch.object(A, "subprocess", popen), \
                 mock.patch("urllib.request.urlopen", side_effect=OSError("down")), \
                 mock.patch.object(A, "_ollama_app_models_dir",
                                   return_value="E:\\Ollama_Models") as helper:
                A.ensure_ollama(timeout=0.1)
        kwargs = popen.Popen.call_args.kwargs
        self.assertEqual(kwargs["env"]["OLLAMA_MODELS"], "D:\\from-config")
        helper.assert_not_called()

    def test_no_gui_dir_no_env_key(self):
        with mock.patch.object(A, "_ollama_app_models_dir", return_value=None):
            ok, popen = self._run_ensure()
        kwargs = popen.Popen.call_args.kwargs
        self.assertNotIn("OLLAMA_MODELS", kwargs["env"])


if __name__ == "__main__":
    unittest.main()
