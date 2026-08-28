# -*- coding: utf-8 -*-
"""统一配置层:所有机器相关、环境相关的设置都从这里读取。
用户配置放在 ~/.ollama_agent/config.json;环境变量可覆盖。绝不硬编码个人/本机信息。
隔离/便携模式:设 HUMMINGBIRD_HOME 环境变量可将配置/技能/会话整体搬到独立目录
(多实例、基准评测隔离、便携安装),互不影响。
"""
import json, os

AGENT_HOME = os.environ.get("HUMMINGBIRD_HOME") or os.path.expanduser("~/.ollama_agent")
CONFIG_FILE = os.path.join(AGENT_HOME, "config.json")

# 默认值:只含通用默认,不含任何个人/机器特定内容
DEFAULTS = {
    "ollama_host": "http://127.0.0.1:11434",  # Ollama API 地址
    "ollama_exe": "",                          # ollama.exe 路径(留空=自动检测)
    "ollama_env": {},                          # 启动 ollama 时的额外环境变量(如 GPU 加速设置)
    "models": {},                              # 模型显示名→tag 映射(可选,便于给模型起友好名)
}

_cache = None

def load_config():
    """读取配置(config.json + 环境变量覆盖),带缓存。"""
    global _cache
    if _cache is None:
        cfg = dict(DEFAULTS)
        try:
            if os.path.exists(CONFIG_FILE):
                d = json.load(open(CONFIG_FILE, encoding="utf-8"))
                for k in DEFAULTS:
                    if k in d:
                        cfg[k] = d[k]
        except Exception:
            pass
        _cache = cfg
    return _cache

def save_config(cfg):
    """写回配置。"""
    global _cache
    try:
        os.makedirs(AGENT_HOME, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        _cache = cfg
        return True
    except Exception:
        return False

def ollama_host():
    """Ollama API 地址:环境变量 OLLAMA_HOST > config.json > 默认。"""
    return os.environ.get("OLLAMA_HOST") or load_config().get("ollama_host") or DEFAULTS["ollama_host"]

def ollama_exe():
    """ollama 可执行文件:环境变量 OLLAMA_BIN > config.json > 自动检测。"""
    env = os.environ.get("OLLAMA_BIN")
    if env:
        return env
    return load_config().get("ollama_exe") or ""

def ollama_env():
    """启动 ollama 时附加的环境变量(用户按自己机器配置,如 GPU 加速)。"""
    return load_config().get("ollama_env") or {}

def model_map():
    """模型显示名→tag 映射(用户自定义,可选)。"""
    return load_config().get("models") or {}

def config_path():
    return CONFIG_FILE
