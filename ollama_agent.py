#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自建本地 AI Agent — 小模型特化版
针对本地小模型优化:
- 极简前置开销(SYSTEM ~120 token + 核心工具 ~480 token,共 ~600 token)
- 渐进式披露:核心工具默认就绪,高级工具按需 enable,技能按需 load
- 修复:上下文用量读取(ollama 返回 prompt_eval_count,不是 usage.prompt_tokens)
- 容错:瞬时 API 错误指数退避重试,连续失败则优雅退出
- 会话:JSON + 侧车元数据(供 GUI 浏览/搜索)

环境变量(可被 GUI 设置面板覆盖):
  AGENT_CTX         上下文窗口(默认 16384;本机 32768 会让 ollama 内存打满死锁)
  AGENT_TEMP        温度(默认 0)
  AGENT_NUMPREDICT  输出上限(默认 2048)
  AGENT_THINK=1     开启思考模型 thinking(默认关)
  AGENT_SYSTEM_FILE 自定义系统提示文件路径

用法:
  python ollama_agent.py <model> <taskfile> <workdir> [--session NAME] [--new] [--append]
  python ollama_agent.py <model> --chat <workdir> [--session NAME]  # 交互式
"""
import json, subprocess, os, sys, urllib.request, time, re, asyncio, glob
import appconfig   # 统一配置层:Ollama 地址/路径/环境变量/模型映射,全部可配置

# 强制 UTF-8 输出(GUI 按 UTF-8 读子进程 stdout;PyInstaller 启动默认可能是 GBK → 中文乱码)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AGENT_HOME = os.environ.get("HUMMINGBIRD_HOME") or os.path.expanduser("~/.ollama_agent")
MEMORY_FILE = os.path.join(AGENT_HOME, "memory.json")
SESSIONS_DIR = os.path.join(AGENT_HOME, "sessions")
SKILLS_DIR_HOME = os.path.join(AGENT_HOME, "skills")
MCP_CONFIG = os.path.join(AGENT_HOME, "mcp.json")
for d in (AGENT_HOME, SESSIONS_DIR, SKILLS_DIR_HOME):
    os.makedirs(d, exist_ok=True)
CACHE_DIR = os.path.join(AGENT_HOME, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)
# ---------- 通用磁盘缓存(缓存昂贵操作:网页抓取/搜索/MCP 结果) ----------
# 原则:网络请求/长文本处理代价高,结果按 key 哈希写盘,TTL 内复用。
# 命中 → 直接返回(零网络开销);TTL 过期或 force → 重新计算。harness 层兜底,不依赖模型。
def _cache_key(*parts):
    """把任意字符串拼成缓存 key(sha1 哈希)。"""
    import hashlib
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]

def _cache_get(key, ttl=3600):
    """读缓存文件,返回内容或 None。损坏/缺失/过期返回 None。"""
    try:
        p = os.path.join(CACHE_DIR, key + ".json")
        if os.path.exists(p):
            d = json.load(open(p, encoding="utf-8"))
            if time.time() - float(d.get("ts", 0)) < ttl:
                return d.get("data")
    except Exception:
        pass
    return None

def _cache_set(key, data):
    """写缓存(带时间戳)。失败静默(缓存只是加速,不阻塞)。"""
    try:
        p = os.path.join(CACHE_DIR, key + ".json")
        json.dump({"ts": time.time(), "data": data}, open(p, "w", encoding="utf-8"),
                  ensure_ascii=False)
    except Exception:
        pass

THINK = os.environ.get("AGENT_THINK") == "1"
CTX_BUDGET = int(os.environ.get("AGENT_CTX", "16384"))
TEMP = float(os.environ.get("AGENT_TEMP", "0"))
NUM_PREDICT = int(os.environ.get("AGENT_NUMPREDICT", "2048"))
SYSTEM_FILE = os.environ.get("AGENT_SYSTEM_FILE", "")
STREAM = os.environ.get("AGENT_STREAM") == "1"   # GUI 开流式时置 1

def _stream_tok(tok):
    """把流式 token 打成一行的 @@TOK@@ 前缀,供 GUI 实时渲染(逐 token flush)。"""
    try:
        print("@@TOK@@" + tok, flush=True)
    except Exception:
        pass

def _stream_think(tok):
    try:
        print("@@THINK@@" + tok, flush=True)
    except Exception:
        pass

def _find_ollama_exe():
    """定位 ollama.exe:配置/环境变量指定 > PATH > 常见安装目录。不写死任何用户名/机器信息。"""
    import shutil
    cand = appconfig.ollama_exe()
    if cand and os.path.isfile(cand):
        return cand
    w = shutil.which("ollama")
    if w and os.path.isfile(w):
        return w
    for p in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
              r"C:\Program Files\Ollama\ollama.exe"):
        if p and os.path.isfile(p):
            return p
    return "ollama"

def ensure_ollama(timeout=25):
    """按需启动 ollama:检查 API 是否可达,不可达则拉起 serve 并等就绪。
    地址/可执行文件/额外环境变量均来自配置层,用户按自己机器配置。"""
    import urllib.request as _ur
    host = appconfig.ollama_host()
    try:
        _ur.urlopen(f"{host}/api/tags", timeout=2)
        return True
    except Exception:
        pass
    # 拉起 serve(合并配置里的附加环境变量,如 GPU 加速设置)
    exe = _find_ollama_exe()
    env = dict(os.environ)
    env.update(appconfig.ollama_env())
    try:
        subprocess.Popen([exe, "serve"], cwd=os.path.dirname(exe),
                         env=env,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass
    # 等就绪
    import time as _t
    for _ in range(int(timeout * 2)):
        try:
            _ur.urlopen(f"{host}/api/tags", timeout=1)
            return True
        except Exception:
            _t.sleep(0.5)
    return False

def system_prompt():
    if SYSTEM_FILE and os.path.exists(SYSTEM_FILE):
        return read_text(SYSTEM_FILE)
    return SYSTEM

def restart_ollama(timeout=40):
    """重启 ollama(治本:长运行后的进程级退化,重启即恢复)。
    流程:taskkill ollama → 等 API 死透 → ensure_ollama 拉起 → 等就绪。
    返回 True=重启成功。"""
    import time as _t
    exe = _find_ollama_exe()
    # 1) 杀掉现有 ollama(serve 与 runner 子进程)
    subprocess.run(["taskkill", "/F", "/IM", "ollama.exe"],
                   capture_output=True, shell=False)
    # 2) 等 API 死透(最多 15s)
    import urllib.request as _ur
    host = appconfig.ollama_host()
    for _ in range(30):
        try:
            _ur.urlopen(f"{host}/api/tags", timeout=1)
            _t.sleep(0.5)   # 还活着,再等
        except Exception:
            break
    _t.sleep(2)   # 端口释放
    # 3) 重新拉起(ensure_ollama 检测 API 不可达会启动 serve)
    ok = ensure_ollama(timeout=timeout)
    return ok

# ---------------- 编码兼容 ----------------
def read_text(path):
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return open(path, encoding=enc).read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return open(path, encoding="latin-1", errors="replace").read()

# ---------------- 工具定义(极简 schema:无参数级描述,少 token) ----------------
def _f(name, desc, props, req=None):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props,
                       "required": req or list(props.keys())}}}

P = lambda **kw: kw
# 各工具必备参数(缺参报错时给模型可操作的提示)
_REQ_ARGS = {"create_file":["path","content"],"read_file":["path"],"edit_file":["path","old","new"],
             "list_dir":["path"],"run_bash":["command"],"append_file":["path","content"],
             "delete_file":["path"],"todo":["action"],"skills":["action"],"finish":["summary"]}

CORE_TOOLS = [
 _f("create_file","Create or overwrite a file", P(path={"type":"string"},content={"type":"string"}),["path","content"]),
 _f("read_file","Read a file's content (optional start_line/end_line to read a range)", P(path={"type":"string"},start_line={"type":"number"},end_line={"type":"number"}),["path"]),
 _f("edit_file","Find-and-replace text in a file", P(path={"type":"string"},old={"type":"string"},new={"type":"string"}),["path","old","new"]),
 _f("list_dir","List files in a directory", P(path={"type":"string"}),["path"]),
 _f("run_bash","Run a command (cwd=workspace, no cd /workspace)", P(command={"type":"string"}),["command"]),
 _f("todo","Manage the task plan. action: create(plan), update(item done), list", P(action={"type":"string","enum":["create","update","list"]},items={"type":"array","items":{"type":"string"}},index={"type":"number"},done={"type":"boolean"}),["action"]),
 _f("skills","List available skills, or load one by name to follow its instructions", P(action={"type":"string","enum":["list","load"]},name={"type":"string"}),["action"]),
 _f("enable_tools","Enable advanced tools on demand: append_file, delete_file, search_files, web_search, web_fetch, memory_store, memory_recall, mcp_call", P(tools={"type":"array","items":{"type":"string"}}),["tools"]),
 _f("finish","Declare the task complete with a short summary", P(summary={"type":"string"}),["summary"]),
]
ADVANCED_TOOLS = [
 _f("append_file","Append text to the end of a file", P(path={"type":"string"},content={"type":"string"}),["path","content"]),
 _f("delete_file","Delete a file", P(path={"type":"string"}),["path"]),
 _f("search_files","Grep-like content search in a directory", P(path={"type":"string"},pattern={"type":"string"}),["path","pattern"]),
 _f("web_search","Search the web (Bing/Baidu), return titles+links+snippets", P(query={"type":"string"}),["query"]),
 _f("web_fetch","Fetch a URL: full text saved to sources/, return summary+path", P(url={"type":"string"}),["url"]),
 _f("web_search_multi","Parallel search multiple queries at once (fast)", P(queries={"type":"array","items":{"type":"string"}},max_results={"type":"number"}),["queries"]),
 _f("batch_tools","Batch-run multiple tool calls in parallel (fast): [{tool,args},...], merge results. Reduces round-trips.", P(calls={"type":"array","items":{"type":"object"}}),["calls"]),
 _f("memory_store","Save an important fact to long-term memory", P(text={"type":"string"}),["text"]),
 _f("memory_recall","Retrieve facts from memory relevant to a query", P(query={"type":"string"},limit={"type":"number"}),["query"]),
 _f("mcp_call","Call a tool exposed by an MCP server", P(server={"type":"string"},tool={"type":"string"},args={"type":"object"}),["server","tool"]),
]
TOOLS = CORE_TOOLS  # 默认核心;enable_tools 后追加

SYSTEM = """You are an autonomous AI agent in a workspace directory.
JUDGE INTENT FIRST — 先判断用户意图,再决定怎么做:
- 闲聊/寒暄/介绍自己/一般知识问答(如"你好""你是谁""你能做什么""今天天气如何"):
  【直接用文字回答】,绝不调用任何工具,绝不建 todo,绝不创建文件或跑命令,然后调用 finish。
- 真正要干活的请求(写代码、改/建文件、分析数据、查资料、跑命令、修 bug):
  先调用 todo(action=create) 建编号计划,再逐步用工具执行,边做边更新 todo。
RULES:
- 别把"你好/你是干嘛的"当成任务去演示工具——直接回答即可。
- Actually DO the work with tools when it's a real task (write code, run it, fix errors until verified). Never just describe.
- Need web/memory/MCP/append/delete/search? Call enable_tools first, they then become available.
- Work only in the current directory (Windows). Never cd to absolute paths like /workspace — commands already run here; use relative paths.
- Be concise in text; put large content in tool arguments. Call finish only when answered or fully verified done."""

# 问答模式:聊天级 prefill(根治小模型"加戏"死循环)。
# 根因:任务向系统提示+全量工具+Continue 注入,把"你好"逼成工具演示死循环。
# 问答 → 换聊天提示+只读工具,答完即停。
CHAT_SYSTEM = """你是本地 AI 助手 Ant-agent,正在和用户对话。
- 直接、自然、简洁地回答用户的问题。像真人聊天。
- 普通寒暄/问句,直接回答即可,一句话或几句话都行,不要长篇大论。
- 只有需要查资料/读文件/搜索时才用工具,其余情况纯粹用文字回答。
- 回答完就结束,不要重复,不要自我展示,不要说"我能帮你做什么"这类套话。"""

# 问答模式可用工具:只读,绝不包含写文件/跑命令(防加戏)
def _chat_tool_defs():
    avail = {t["function"]["name"]: t for t in CORE_TOOLS + ADVANCED_TOOLS}
    return [avail[n] for n in ("read_file", "list_dir", "web_search", "web_fetch")
            if n in avail]

# ============ 扁平 prefill:按类别按需加载工具(任务域分层) ============
# 基础工具(任何任务都需要):计划/读文件/技能/启用/收尾
_BASE_TOOLS = {"read_file", "list_dir", "todo", "skills", "enable_tools", "finish"}
# 类别 → 该类的工具(只在此类任务才加载)
_CATEGORY_TOOLS = {
    "文件": ["create_file", "edit_file", "append_file", "delete_file", "search_files"],
    "代码": ["run_bash"],
    "网络": ["web_search", "web_fetch", "web_search_multi", "batch_tools"],
    "记忆": ["memory_store", "memory_recall"],
    "MCP":  ["mcp_call"],
}
_CAT_KEYWORDS = {
    "代码": ("写", "代码", "程序", "脚本", "运行", "bash", "python", "编译", "函数", "模块",
             "修复", "重构", "调试", "实现", "测试", "执行", "算法", "计算", "程序", "报错"),
    "文件": ("创建", "建立", "生成", "文档", "文件", "目录", "整理", "改名", "删除",
             "编辑", "新建", "写入", "保存", "重命名", "组织"),
    "网络": ("搜索", "查", "调研", "网络", "网页", "资料", "新闻", "天气", "在线", "下载", "研究"),
    "记忆": ("记住", "回忆", "记忆", "存档", "之前"),
    "MCP":  ("mcp", "外部工具", "工具服务", "插件", "服务器", "api", "数据库"),
}

def route_categories(text):
    """任务描述 → 相关类别集合。分类不确定时加载宽默认(文件+代码+网络),宁可多不可少。"""
    cats = set()
    for cat, kws in _CAT_KEYWORDS.items():
        if any(k in text for k in kws):
            cats.add(cat)
    if "代码" in cats:
        cats.add("文件")   # 写代码必然要建/改文件
    if not cats:
        cats = {"文件", "代码", "网络"}
    return cats

def tools_for_categories(cats, active=None, extra=None):
    """按类别过滤工具定义(只暴露相关工具 → prefill 更小 → 更快)。
    自动启用该类别的工具(替代手动 enable_tools)。extra=模型 enable_tools 补充的工具名。"""
    active = active if active is not None else _active_tools
    avail = {t["function"]["name"]: t for t in CORE_TOOLS + ADVANCED_TOOLS}
    names = set(_BASE_TOOLS)
    for c in cats:
        names.update(_CATEGORY_TOOLS.get(c, []))
    if extra:
        names.update(extra)
    names -= _disabled_tools   # 被禁用的工具不再装配(否则每轮按类别还原)
    active_names = {t["function"]["name"] for t in active}
    for n in names:
        if n in avail and n not in active_names:
            active.append(avail[n])
    result = [t for t in active if t["function"]["name"] in names]
    result += mcp_tool_defs(cats, extra=extra)   # 扁平并入该类别下的 MCP 工具(真实工具,模型直接调用)
    return result

# ---------------- 记忆 ----------------
def load_memory():
    try:
        return json.load(open(MEMORY_FILE, encoding="utf-8"))
    except Exception:
        return []
def save_memory(mem):
    json.dump(mem, open(MEMORY_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
def memory_store(text):
    mem = load_memory()
    mem.append({"text": text, "ts": time.strftime("%Y-%m-%d %H:%M")})
    save_memory(mem)
    return f"[saved {len(mem)} facts]"
def memory_recall(query, limit=3):
    mem = load_memory()
    qw = set(re.findall(r"[\w一-鿿]+", query.lower()))
    scored = []
    for m in mem:
        words = set(re.findall(r"[\w一-鿿]+", m["text"].lower()))
        scored.append((len(qw & words), m["text"], m.get("ts","")))
    scored.sort(reverse=True)
    hits = [f"[{ts}] {t}" for s,t,ts in scored if s>0][:limit] or [m["text"] for m in mem[-3:]]
    return "\n".join(hits) if hits else "(no memory)"

# ---------------- Todo ----------------
def todo_file(workdir):
    return os.path.join(workdir, "todo.json")
def load_todo(workdir):
    try: return json.load(open(todo_file(workdir), encoding="utf-8"))
    except Exception: return []
def save_todo(workdir, t):
    json.dump(t, open(todo_file(workdir),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
def load_todo_str(workdir):
    t=load_todo(workdir)
    if not t: return "(todo list empty)"
    return "\n".join(f"{'[x]' if x['done'] else '[ ]'} {i}. {x['item']}" for i,x in enumerate(t,1))

# ---------------- 网页 ----------------
def web_search(query, max_results=5):
    key = _cache_key("search", query, max_results)
    cached = _cache_get(key)
    if cached:
        return cached
    import requests
    from bs4 import BeautifulSoup
    hd = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    last_err = ""
    for url in ("https://cn.bing.com/search", "https://www.baidu.com/s"):
        try:
            r = requests.get(url, params={"q": query}, headers=hd, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")
            out = []
            lis = soup.select("li.b_algo") if url.startswith("https://cn.bing") else soup.select("div.result.c-container")
            for li in lis[:max_results]:
                a = li.select_one("h2 a") or li.select_one("h3 a")
                if not a: continue
                t = a.get_text(strip=True); h = a.get("href","")
                cap = li.select_one(".b_caption p") or li.select_one("p") or li.select_one(".c-abstract")
                sn = cap.get_text(strip=True)[:200] if cap else ""
                if t: out.append(f"• {t}\n  {h}\n  {sn}")
            if out:
                result = "\n".join(out)
                _cache_set(key, result)
                return result
        except Exception as e:
            last_err = str(e)[:80]
    return f"[web_search error: {last_err}]"
def web_search_multi(queries, max_results=3):
    """并行检索多个查询(线程池),合并结果。独立查询并发执行,显著提速。
    返回: 每个查询的结果块(带查询标签)。单个失败不影响整体。"""
    if not queries:
        return "[web_search_multi: 需提供 queries 数组]"
    import concurrent.futures as _cf
    results = {}
    with _cf.ThreadPoolExecutor(max_workers=min(6, len(queries))) as ex:
        futs = {ex.submit(web_search, q, max_results): q for q in queries}
        for fut in _cf.as_completed(futs):
            q = futs[fut]
            try:
                results[q] = fut.result()
            except Exception as e:
                results[q] = f"[error: {e}]"
    parts = []
    for q in queries:
        parts.append(f"### 查询: {q}\n{results.get(q, '(failed)')}")
    return "\n\n".join(parts)

def batch_tools(calls, workdir):
    """批处理编排:一次执行多个工具调用,合并结果(减少 agent round-trip)。
    输入: [{"tool": "read_file", "args": {...}}, {"tool": "web_search", "args": {...}}, ...]
    - 网络/检索类工具(web_search/web_fetch/web_search_multi/mcp_call)并行执行(提速)
    - 文件/命令类工具串行执行(保依赖,避免 create 后立即 read 的竞态)
    每个子调用仍走 run_tool(含安全门/路径边界),单个失败不影响整体。
    限制: 最多 8 个;禁止嵌套 batch_tools。"""
    if not calls or not isinstance(calls, list):
        return "[batch_tools: 需提供 calls 数组,形如 [{tool, args}, ...]]"
    calls = calls[:8]   # 并发上限
    # 禁止嵌套
    if any(isinstance(c.get("tool"), str) and c.get("tool") == "batch_tools" for c in calls):
        return "[batch_tools: 禁止嵌套 batch_tools]"
    _PARALLEL_SAFE = ("web_search", "web_fetch", "web_search_multi", "mcp_call")
    import concurrent.futures as _cf
    results = {}
    def _one(c):
        try:
            tool = c.get("tool", ""); args = c.get("args", {}) or {}
            r = run_tool(tool, args, workdir)
            return str(r)[:2000]
        except Exception as e:
            return f"[batch error: {e}]"
    # 网络类并行,文件类串行(保依赖)
    parallel = [(i, c) for i, c in enumerate(calls) if c.get("tool") in _PARALLEL_SAFE]
    serial = [(i, c) for i, c in enumerate(calls) if c.get("tool") not in _PARALLEL_SAFE]
    if parallel:
        with _cf.ThreadPoolExecutor(max_workers=min(8, len(parallel))) as ex:
            futs = {ex.submit(_one, c): i for i, c in parallel}
            for fut in _cf.as_completed(futs):
                results[futs[fut]] = fut.result()
    for i, c in serial:
        results[i] = _one(c)
    parts = []
    for i, c in enumerate(calls):
        tool = c.get("tool", "?")
        parts.append(f"### [{i+1}] {tool}\n{results.get(i, '(failed)')}")
    return "\n\n".join(parts)

def web_fetch(url, workdir=None):
    """抓取网页:全量落盘 + 摘要进上下文 + 缓存。
    科研场景要求"读越多原文越好"——不截断丢弃全文,而是:
    1) 全文写入 workdir/sources/<hash>.txt(完整保留,模型可 read_file 精读任意部分)
    2) 返回 800 字摘要 + 文件路径(摘要进上下文,省 token)
    3) 磁盘缓存:同 URL 命中直接返回,不重复网络请求
    返回格式: 摘要文本 + '\n[全文已存: sources/xxx.txt,需要细节用 read_file 读取]'
    """
    key = _cache_key("fetch", url)
    cached = _cache_get(key)
    if cached:
        return cached
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","nav","footer","header","noscript"]): t.decompose()
        full = soup.get_text(" ", strip=True)
        if not full:
            return f"[web_fetch error: 页面无文本内容]"
        # 1) 全量落盘(完整保留,供按需精读)
        src_dir = ""
        if workdir:
            src_dir = os.path.join(workdir, "sources")
            os.makedirs(src_dir, exist_ok=True)
            fname = f"fetch_{key}.txt"
            with open(os.path.join(src_dir, fname), "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n\n{full}")
        # 2) 摘要进上下文(前 800 字,保留关键信息)
        summary = full[:800]
        note = f"\n[全文已存: sources/fetch_{key}.txt ({len(full)} 字符)。需要细节时用 read_file 读取对应部分。]"
        if workdir:
            out = summary + note
        else:
            out = summary[:6000]
        _cache_set(key, out)
        return out
    except Exception as e:
        return f"[web_fetch error: {e}]"

# ---------------- Skills(渐进式披露) ----------------
def _skill_bases(workdir):
    return [os.path.join(workdir,"skills"), SKILLS_DIR_HOME,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")]
def find_skill(name, workdir):
    for base in _skill_bases(workdir):
        for ext in (".md", ".txt", ".py"):
            p = os.path.join(base, name + ext)
            if os.path.exists(p): return p
    return None
def skill_desc(path):
    """从 frontmatter 取 description 一句话(供 list 用,省 token)。"""
    try:
        head = open(path, encoding="utf-8").read(600)
    except Exception:
        try: head = open(path, encoding="gbk").read(600)
        except Exception: return ""
    m = re.search(r"description:\s*(.+)", head)
    if m: return m.group(1).strip().strip('"').strip("'")[:120]
    for line in head.splitlines():
        line = line.strip()
        if line and not line.startswith(("#","-","---")):
            return line[:120]
    return ""
def list_skills(workdir):
    seen = {}
    for base in _skill_bases(workdir):
        if os.path.isdir(base):
            for f in os.listdir(base):
                if f.endswith((".md",".txt",".py")):
                    name = f.rsplit(".",1)[0]
                    if name not in seen:
                        seen[name] = skill_desc(os.path.join(base,f))
    if not seen: return "(none)"
    return "\n".join(f"• {n}: {d}" if d else f"• {n}" for n,d in sorted(seen.items()))
def load_skill(name, workdir):
    p = find_skill(name, workdir)
    if not p:
        return f"[skill '{name}' not found. Available: {list_skills(workdir)}]"
    return f"### SKILL: {name}\n{read_text(p)}"

# ---------------- MCP ----------------
def load_mcp_servers():
    try:
        return json.load(open(MCP_CONFIG, encoding="utf-8"))
    except Exception:
        return {}
def mcp_call(server, tool, args):
    cfg = load_mcp_servers().get(server)
    if not cfg:
        return f"[MCP server '{server}' not configured. Edit {MCP_CONFIG}: {{\"{server}\":{{\"command\":\"...\",\"args\":[...]}}}}]"
    try:
        from mcp import ClientSession
        url = cfg.get("url")
        async def _call(session):
            await session.initialize()
            try:
                # MCP 调用加超时(60s),防止卡死的服务器无限阻塞 agent
                res = await asyncio.wait_for(session.call_tool(tool, args or {}), timeout=60)
            except asyncio.TimeoutError:
                return f"[mcp_call error: 工具 {tool} 调用超时(60s)。服务器可能卡死,请换其他工具或稍后重试。]"
            except Exception as e:
                # 参数校验失败 → 返回该工具期望的参数名,帮模型下次猜对
                try:
                    tools = (await session.list_tools()).tools
                    for t in tools:
                        if t.name == tool:
                            props = t.inputSchema.get("properties", {})
                            names = ", ".join(props.keys())
                            return f"[mcp_call error: {e}] 工具 {tool} 期望参数: {names or '(无参数)'}"
                except Exception:
                    pass
                return f"[mcp_call error: {e}]"
            txt = res.content[0].text if res.content and hasattr(res.content[0],"text") else str(res)
            return txt[:4000]
        async def _run():
            if url:
                from mcp.client.streamable_http import streamablehttp_client
                async with streamablehttp_client(url, headers=cfg.get("headers")) as (read, write, _sid):
                    async with ClientSession(read, write) as session:
                        return await _call(session)
            else:
                from mcp import StdioServerParameters
                from mcp.client.stdio import stdio_client
                params = StdioServerParameters(command=cfg["command"], args=cfg.get("args",[]), env=cfg.get("env"))
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        return await _call(session)
        return asyncio.run(_run())
    except Exception as e:
        return f"[mcp_call error: {e}]"

# ============ MCP 打散重组 + 扁平化(每个工具独立并入类别,模型直接调用) ============
# mcp.json 每个服务器可声明 "categories"(该服务器工具的默认类别);
# "大而全"的服务器可再给每个工具单独打标:
#   "tools": {"read_file":["文件"], "search_web":["网络"], "exec_sql":["代码"]}
# 未声明类别的工具默认归入 "MCP" 类。任务路由到某类别时,该类别下的 MCP 工具
# 以真实工具定义(名称 = "服务器.工具名",带压缩 schema)扁平加载进 prefill,
# 模型原生直接调用;派发器自动路由到对应 MCP 服务器。
_MCP_CACHE = {"t": 0, "data": None}
_MCP_TTL = 300   # 探测结果缓存秒数(探测要拉起 stdio 进程,贵)
_MCP_CACHE_FILE = os.path.join(AGENT_HOME, "mcp_manifest_cache.json")  # 磁盘持久化缓存
# 探测代价高(拉起多个 stdio 进程 ~7s),缓存写盘避免每次 agent 进程都重新探测。
# 通用原则:配置没变 → 直接用缓存;force=True 或 TTL 过期 → 重新探测。不绑定任何服务器。

def _load_mcp_cache_disk():
    """读磁盘缓存。返回 (ts, data) 或 (0, None)。损坏/缺失返回空。"""
    try:
        if os.path.exists(_MCP_CACHE_FILE):
            d = json.load(open(_MCP_CACHE_FILE, encoding="utf-8"))
            return float(d.get("ts", 0)), d.get("data")
    except Exception:
        pass
    return 0, None

def _save_mcp_cache_disk(data):
    """把探测结果写盘(含时间戳)。失败静默(缓存只是加速,不阻塞)。"""
    try:
        os.makedirs(AGENT_HOME, exist_ok=True)
        json.dump({"ts": time.time(), "data": data},
                  open(_MCP_CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:
        pass

def mcp_server_categories(name, cfg):
    cats = cfg.get("categories") if isinstance(cfg, dict) else None
    if not cats:
        return ["MCP"]
    return [str(c) for c in cats if c in _CAT_KEYWORDS or c == "MCP"]

def _compact_schema(js):
    """MCP JSON Schema → 压缩版(只留参数名+类型+必填,省 token)。"""
    if not isinstance(js, dict):
        return {"type": "object", "properties": {}, "required": []}
    props = {}
    for k, v in (js.get("properties") or {}).items():
        t = v.get("type") if isinstance(v, dict) else None
        if t:
            props[k] = {"type": t}
    req = js.get("required") or list(props.keys())
    if len(props) > 8:            # 参数过多只留必填,防 prefill 膨胀
        props = {k: props[k] for k in req if k in props}
    return {"type": "object", "properties": props, "required": req}

def _introspect_mcp_tools(name, cfg):
    """连接 MCP 服务器取 tools/list(名称+描述+输入 schema)。失败返回 []。
    支持本地 stdio(command) 与远程 HTTP(url, 如 tavily)。"""
    try:
        from mcp import ClientSession
        url = cfg.get("url")
        async def _run():
            if url:
                from mcp.client.streamable_http import streamablehttp_client
                async with streamablehttp_client(url, headers=cfg.get("headers")) as (read, write, _sid):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        res = await session.list_tools()
                        return [{"name": t.name, "desc": (t.description or "")[:150],
                                 "schema": _compact_schema(getattr(t, "inputSchema", None) or {})}
                                for t in res.tools]
            else:
                from mcp import StdioServerParameters
                from mcp.client.stdio import stdio_client
                params = StdioServerParameters(command=cfg["command"], args=cfg.get("args", []), env=cfg.get("env"))
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        res = await session.list_tools()
                        return [{"name": t.name, "desc": (t.description or "")[:150],
                                 "schema": _compact_schema(getattr(t, "inputSchema", None) or {})}
                                for t in res.tools]
        return asyncio.run(asyncio.wait_for(_run(), timeout=10))   # 坏服务器最多等 10s,不阻塞任务
    except Exception:
        return []

def _mcp_expose(per_tool, tname, server_expose):
    """解析工具的暴露策略。优先级:工具级 expose > 服务器级 expose > 默认 auto。
    工具级可写 'expose': 'on-demand' 或 'auto' 或 'disabled'。"""
    t = per_tool.get(tname)
    if isinstance(t, dict) and t.get("expose"):
        return t["expose"]
    return server_expose or "auto"

def mcp_manifest(force=False):
    """服务器 → {categories, tools:[{name,desc,schema,categories,expose}]}。缓存(内存+磁盘)。
    expose ∈ {auto, on-demand, disabled}:
      auto      → 随类别默认注入 prefill(轻量高相关)
      on-demand → 默认不注入,模型 enable_tools 显式加载才可用(重量/低频)
      disabled  → 永不自动注入(仅配置声明确认需要时)
    由 mcp.json 配置声明(服务器级 expose 或 tools 里工具级 expose),harness 不特判服务器名。
    探测代价高(拉起 stdio 进程 ~7s),结果写盘缓存;新进程/任务不重复探测,TTL 过期或 force 才重测。"""
    now = time.time()
    # 1) 内存缓存
    if not force and _MCP_CACHE["data"] is not None and now - _MCP_CACHE["t"] < _MCP_TTL:
        return _MCP_CACHE["data"]
    # 2) 磁盘缓存(跨进程):未过期直接用,不重新拉起服务器
    if not force:
        disk_ts, disk_data = _load_mcp_cache_disk()
        if disk_data and now - disk_ts < _MCP_TTL:
            _MCP_CACHE.update({"t": disk_ts, "data": disk_data})
            return disk_data
    servers = load_mcp_servers()
    manifest = {}
    for name, cfg in servers.items():
        if not isinstance(cfg, dict) or not (cfg.get("command") or cfg.get("url")):
            continue
        server_cats = mcp_server_categories(name, cfg)
        server_expose = cfg.get("expose")
        per_tool = cfg.get("tools") if isinstance(cfg.get("tools"), dict) else {}
        raw = _introspect_mcp_tools(name, cfg)
        tools = []
        for t in raw:
            tname = t["name"]
            tools.append({
                "name": tname,
                "desc": t.get("desc", ""),
                "schema": t.get("schema") or {"type": "object", "properties": {}},
                "categories": per_tool.get(tname) if isinstance(per_tool.get(tname), list) else server_cats,
                "expose": _mcp_expose(per_tool, tname, server_expose),
            })
        manifest[name] = {"categories": server_cats, "tools": tools}
    _MCP_CACHE.update({"t": now, "data": manifest})
    _save_mcp_cache_disk(manifest)   # 写盘,下次进程直接用
    return manifest

_BUILTIN_NAMES = {t["function"]["name"] for t in CORE_TOOLS + ADVANCED_TOOLS}
# MCP 文件类工具 → 内置替代(内置更懂工作目录;避免 MCP 沙箱写错位置)
_FILE_DUP = {
    "write_file": "create_file", "create_file": "create_file", "read_file": "read_file",
    "read_text_file": "read_file", "list_directory": "list_dir", "directory_tree": "list_dir",
    "list_allowed_directories": "list_dir", "search_files": "search_files",
    "edit_file": "edit_file", "delete_file": "delete_file", "move_file": "create_file",
    "append_file": "append_file",
}

def mcp_tool_defs(cats, extra=None):
    """按类别返回 MCP 工具定义(扁平化为真实工具,名称="服务器.工具名")。
    分层:expose=auto 的工具随类别默认注入;on-demand/disabled 默认跳过,
    仅当 extra(模型 enable_tools 显式请求的工具名)里出现时才注入。
    跳过与内置工具重复的 MCP 工具:同名,或文件类工具的动词已被内置覆盖
    (内置更懂工作目录;filesystem 等 MCP 写的是自己的沙箱,会写错位置)。"""
    manifest = mcp_manifest()
    extra = extra or set()
    defs = []
    for server, info in manifest.items():
        for t in info["tools"]:
            full = f"{server}.{t['name']}"
            # 类别不匹配且未显式请求 → 跳过
            if not (set(t["categories"]) & set(cats)) and full not in extra:
                continue
            # 分层:auto 随类别;on-demand/disabled 需 extra 显式请求
            if t["expose"] != "auto" and full not in extra:
                continue
            if t["name"] in _BUILTIN_NAMES and full not in extra:
                continue   # 与内置工具同名,跳过(除非显式请求)
            if "文件" in t["categories"] and t["name"] in _FILE_DUP and _FILE_DUP[t["name"]] in _BUILTIN_NAMES and full not in extra:
                continue   # 文件类操作被内置覆盖,跳过(除非显式请求)
            desc = (t["desc"] or "").replace("\n", " ")
            if len(desc) > 60:
                desc = desc[:60] + "…"
            defs.append({"type": "function", "function": {
                "name": full,
                "description": desc or f"{server} 工具",
                "parameters": t["schema"],
            }})
    return defs

def is_mcp_tool(name):
    """是否形如 "服务器.工具名" 且该服务器已配置。"""
    if "." not in name:
        return False
    server, _, tool = name.partition(".")
    return bool(server and tool) and server in load_mcp_servers()

_PRODUCING_PREFIX = ("create_", "write_", "render_", "export_", "update_", "save_",
                     "generate_", "build_", "insert_", "convert_", "import_", "add_")
def _is_mcp_producing(name):
    """MCP 工具是否为产出型(创建/写入/渲染/导出等 → 算做了实际工作)。"""
    tool = name.partition(".")[2]
    return tool.startswith(_PRODUCING_PREFIX)

_PATH_ARGS = ("path", "filepath", "file", "dir", "folder", "filename", "directory",
              "output", "out", "dest", "destination", "doc", "src", "source", "target", "input")
def _is_abs(p):
    return bool(re.match(r"^[A-Za-z]:[\\/]|^[/\\]", p)) or p.startswith(("http://", "https://", "file://", "data:", "C:/", "C:\\"))

def _is_path_key(k):
    kl = k.lower()
    if kl in _PATH_ARGS:
        return True
    # 复合路径名: docx_path / output_file / input_dir / filename ...
    return kl.endswith(("_path", "_file", "_dir", "_folder", "_filename", "_pathname"))

def _resolve_mcp_paths(args, workdir):
    """MCP 工具路径解析:agent 传的相对路径(相对工作目录) → 绝对路径。
    MCP 服务器进程 CWD 与 agent 工作目录不同,相对路径会找不到文件。
    仅解析形如 path/filePath/docx_path/output_file 等路径型参数;URL/绝对路径/命令不动。"""
    if not args:
        return args
    out = dict(args)
    for k, v in list(out.items()):
        if not isinstance(v, str) or not v:
            continue
        if not _is_path_key(k):
            continue
        v = v.strip().strip('"').strip("'")
        if not v or _is_abs(v):
            continue
        if "://" in v or v.lower().startswith(("mailto:", "tel:", "#")):
            continue
        out[k] = os.path.normpath(os.path.join(workdir, v))
    return out

# ---------------- 工具执行 ----------------
_active_tools = list(CORE_TOOLS)
# 被禁用的工具名:tools_for_categories 每轮按类别重新装配,只过滤 _active_tools 的
# "禁用"会被下一轮装配还原(潜伏 bug)——持久禁用必须进本集合,装配与调用双处拦截。
_disabled_tools = set()
def active_tool_defs():
    return list(_active_tools)
def enable_advanced_tools(names):
    avail = {t["function"]["name"]: t for t in ADVANCED_TOOLS}
    added = []
    mcp_added = []
    for n in names:
        if n in avail and n not in [t["function"]["name"] for t in _active_tools]:
            _active_tools.append(avail[n]); added.append(n)
        elif is_mcp_tool(n) and n not in mcp_added:
            # MCP 扁平工具(服务器.工具名):由 agent_loop 的 allowed_extra 负责注入
            mcp_added.append(n)
    note = ""
    if mcp_added:
        note = f" MCP 工具已按需加载: {', '.join(mcp_added)}"
    return f"[enabled tools: {', '.join(added) or '(none)'}. Now available: {', '.join(t['function']['name'] for t in _active_tools)}]{note}"

def _auto_repair(path):
    """写文件后自愈:小模型常把换行/引号转义成字面反斜杠序列(层数不固定),导致 .py 语法错误。
    仅当 .py 语法检查失败时用正则折叠任意层数反斜杠转义;合法文件绝不动;修复无效回退原内容。"""
    if path.endswith(".py"):
        pass
    elif path.endswith((".md", ".txt", ".csv")):
        s = open(path, encoding="utf-8", errors="replace").read()
        if chr(92) in s:
            fixed = re.sub(r"\\+n", "\n", s)
            fixed = re.sub(r"\\+t", "\t", fixed)
            fixed = fixed.rstrip(chr(92))
            if fixed != s:
                open(path, "w", encoding="utf-8").write(fixed)
                return 1
        return 0
    else:
        return 0
    def _compiles():
        import py_compile
        try:
            py_compile.compile(path, doraise=True)
            return True
        except Exception:
            return False
    if _compiles():
        return 0
    s = open(path, encoding="utf-8", errors="replace").read()
    if "\\" not in s:
        return 0
    fixed = re.sub(r"\\+n", "\n", s)
    fixed = re.sub(r"\\+t", "\t", fixed)
    fixed = re.sub(r'\\+"', '"', fixed)
    fixed = re.sub(r"\\+'", "'", fixed)
    fixed = fixed.rstrip(chr(92))      # 文件尾孤立反斜杠
    if fixed == s:
        return 0
    open(path, "w", encoding="utf-8").write(fixed)
    if _compiles():
        return 1
    open(path, "w", encoding="utf-8").write(s)   # 回退原内容
    return 0

# 本轮已获得"允许全部"授权的工具名(GUI 弹窗用户选"允许全部"后,本轮同工具不再确认)
_allow_all = set()
# 本进程可读写的目录白名单(工作目录;可被 AGENT_ALLOW_DIRS 环境变量扩展,冒号分隔)
_allow_dirs = set()

_SYSTEM_DIRS = ("\\windows\\", "\\program files\\", "\\system32\\", "/windows/", "/program files/", "/usr", "/etc/", "/bin/", "/root")
_DANGER_CMD = ("rm -rf", "rm -fr", "format c:", "format c:\\", "del /s /q c:", "rd /s /q c:\\", "diskpart", "mkfs", "shutdown", "taskkill /f /im",
               "curl | bash", "curl | sh", "wget | bash", "powershell -c", "reg add", "reg delete", "netsh", "sc create", "certutil", "del c:\\*",
               "rm -rf /", "rm -fr /", "sudo rm")
# 敏感路径片段(命中即受保护):写一律拒绝,读也需确认。全小写匹配。
_SENSITIVE_PATTERNS = (".ssh\\", ".aws\\", ".gnupg\\", ".env", ".pem", "id_rsa", "id_ed25519",
                       "credentials\\", "\\token", "secrets", ".wav", "gui_prefs.json",
                       "mcp.json", "config.json", "memory.json",
                       "app_lang.txt", "\\program files\\", "\\windows\\", "\\system32\\")
# 注意:.agent_state.json 是蜂鸟自己的运行时检查点(会话历史),模型写它属于正常工作,
# 不能列入敏感模式(否则检查点保存失败,崩溃无法续跑)。真正的隐私文件用上面的列表保护。
# run_bash 里疑似访问工作目录之外的命令模式(全小写匹配;命中→走确认通道)
_BASH_ESCAPE_PATTERNS = (
    r"cd\s+[a-z]:\\\\", r"cd\s+/d\s+[a-z]:", r"del\s+[a-z]:\\", r"type\s+[a-z]:\\",
    r"dir\s+[a-z]:\\", r"copy\s+[a-z]:\\", r"move\s+[a-z]:\\", r"ren\s+[a-z]:\\",
    r"echo\s+.*>\\[a-z]:\\", r"more\s+[a-z]:\\", r"xcopy\s+[a-z]:\\", r"rd\s+[a-z]:\\",
    r"attrib\s+[a-z]:\\", r"cacls\s+[a-z]:\\", r"icacls\s+[a-z]:\\", r"takeown\s+[a-z]:\\",
    r"%userprofile%", r"%appdata%", r"%localappdata%", r"\.ssh", r"\.aws", r"\.env",
    r"c:\\users", r"c:\program", r"d:\\", r"e:\\",
)
_FILE_TOOLS = ("create_file", "read_file", "edit_file", "append_file", "delete_file",
               "list_dir", "search_files")

def _safe_path(workdir, path):
    """解析路径并判断是否在工作目录(或允许目录)内。返回 (real_abs, inside_bool)。
    关键:os.path.join 在 Windows 上遇到绝对路径会直接返回绝对路径本身(绕过 workdir),
    且 `..` 可向上跳转。这里用 abspath 折叠 `..` + commonpath 判定边界。
    _allow_dirs 可由 AGENT_ALLOW_DIRS 环境变量(冒号分隔)扩展,允许 agent 访问额外目录。"""
    try:
        base = os.path.abspath(workdir)
        real = os.path.abspath(os.path.join(workdir, str(path or "")))
        allowed = [os.path.abspath(d) for d in ([base] + sorted(_allow_dirs))]
        for d in allowed:
            try:
                common = os.path.commonpath([os.path.normcase(d), os.path.normcase(real)])
                if common == os.path.normcase(d):
                    return real, True
            except Exception:
                continue
        return real, False
    except Exception:
        return os.path.abspath(os.path.join(workdir, str(path or ""))), False

def _is_sensitive_path(path):
    """路径是否命中敏感模式(含工作目录名本身触发的误报排除:敏感模式用全路径片段匹配)。"""
    p = str(path).lower()
    return any(s in p for s in _SENSITIVE_PATTERNS)

def _ask_user_confirm(name, real_path, workdir, action="访问"):
    """越界操作征求用户同意。GUI 模式(AGENT_STREAM=1):发 @@ASK@@ 到 stdout,阻塞读 stdin 回传。
    CLI/无 stdin 模式:直接拒绝。返回 (allow:bool, allow_all:bool, msg:str)。
    注:用线程带超时读 stdin(Windows console 上 select 不可靠;GUI 提供的是 PIPE 管道)。"""
    try:
        if os.environ.get("AGENT_STREAM") == "1" and sys.stdin and not sys.stdin.closed:
            req = {"tool": name, "path": real_path, "action": action,
                   "workdir": os.path.abspath(workdir)}
            print("@@ASK@@" + json.dumps(req, ensure_ascii=False), flush=True)
            # 线程带超时读一行(120s)
            import threading, queue as _q
            box = _q.Queue()
            def _read():
                try:
                    box.put(sys.stdin.readline().strip())
                except Exception:
                    box.put(None)
            th = threading.Thread(target=_read, daemon=True)
            th.start()
            try:
                line = box.get(timeout=120)
            except Exception:
                line = None
            if line:
                low = line.lower()
                if low in ("@allow", "@allow_all", "allow", "yes", "y"):
                    return True, low in ("@allow_all", "allow_all"), ""
                return False, False, "[安全门:用户拒绝了本次越界访问]"
            return False, False, "[安全门:等待用户确认超时(120s),已按拒绝处理]"
        return False, False, f"[安全门拦截:路径 {real_path} 在工作目录之外。工作目录: {os.path.abspath(workdir)}。已拒绝。CLI 模式不允许越界访问。]"
    except Exception as e:
        return False, False, f"[安全门拦截:越界访问确认失败({e}),已拒绝]"

def _gate_check(name, args, workdir):
    """工具安全门:拦截危险操作(删系统/危险命令) + 工作目录边界 + 敏感路径。
    返回拦截消息(字符串)或 None(放行)。"""
    try:
        if name == "run_bash":
            cmd = str(args.get("command", ""))
            low = cmd.lower()
            # 危险命令无论是否"允许全部"都拦截(不可被用户一次性放行)
            if any(d in low for d in _DANGER_CMD):
                return f"[安全门拦截:命令含危险操作,已拒绝执行。原命令: {cmd[:80]}]"
            # 越界命令模式 → 征求同意(允许全部仅本轮豁免路径确认,不含危险命令)
            if name not in _allow_all:
                for pat in _BASH_ESCAPE_PATTERNS:
                    if re.search(pat, low):
                        allow, allok, msg = _ask_user_confirm(name, f"bash: {cmd[:60]}", workdir, "执行命令")
                        if allow:
                            if allok: _allow_all.add(name)
                            return None
                        return msg or f"[安全门拦截:命令疑似访问工作目录之外,已拒绝。原命令: {cmd[:80]}]"
        # "允许全部"只豁免路径确认,不豁免危险命令(已在上面拦过 run_bash 危险命令)
        if name in _allow_all and name in _FILE_TOOLS:
            return None
        if name in _FILE_TOOLS:
            path = str(args.get("path", "") or args.get("dir", "") or args.get("filepath", "") or "")
            if path:
                real, inside = _safe_path(workdir, path)
                if not inside:
                    allow, allok, msg = _ask_user_confirm(name, real, workdir, "访问")
                    if allow:
                        if allok: _allow_all.add(name)
                        return None
                    return msg or (f"[安全门拦截:路径 {real} 在工作目录之外。工作目录: {os.path.abspath(workdir)}。"
                                   f"已拒绝。若确需访问,请在 GUI 弹窗确认。]")
                if _is_sensitive_path(real):
                    # 敏感路径:写一律拒绝;读也需确认
                    if name in ("create_file", "edit_file", "append_file", "delete_file"):
                        return f"[安全门拦截:路径 {real} 命中敏感模式,写操作一律拒绝。]"
                    allow, allok, msg = _ask_user_confirm(name, real, workdir, "读取敏感文件")
                    if allow:
                        if allok: _allow_all.add(name)
                        return None
                    return msg or f"[安全门拦截:路径 {real} 命中敏感模式,已拒绝读取。]"
        if name in ("delete_file", "edit_file", "create_file", "append_file"):
            p = (str(args.get("path", "")) + "\\").lower()
            if any(d in p for d in _SYSTEM_DIRS):
                return f"[安全门拦截:目标路径含系统目录,已拒绝。路径: {args.get('path','')[:80]}]"
    except Exception:
        pass
    return None

def run_tool(name, args, workdir):
    try:
        # 工具名别名:小模型常输出业界通名(write_file/list_directory 等),
        # 自动映射到蜂鸟内置工具,而非拒绝("工具已禁用"会让小模型陷入死循环)。
        _TOOL_ALIASES = {
            "write_file": "create_file", "save_file": "create_file",
            "read_text_file": "read_file", "cat": "read_file",
            "list_directory": "list_dir", "ls": "list_dir",
            "append_to_file": "append_file", "edit": "edit_file",
            "search_code": "search_files", "grep": "search_files",
            "delete": "delete_file", "bash": "run_bash", "shell": "run_bash",
        }
        if name in _TOOL_ALIASES:
            name = _TOOL_ALIASES[name]
        gate = _gate_check(name, args, workdir)
        if gate:
            return gate
        if is_mcp_tool(name):           # MCP 打散后的扁平工具:"服务器.工具名" → 路由到 mcp_call
            server, _, tool = name.partition(".")
            _args = _resolve_mcp_paths(args or {}, workdir)   # 相对路径→按工作目录解析为绝对路径
            _res = mcp_call(server, tool, _args)
            _low = str(_res).lower()
            if any(k in _low for k in ("access denied", "outside allowed", "not in allowed",
                                       "outside the allowed", "permission denied", "越权", "不在允许")):
                _res += ("\n[提示:这是 MCP 文件服务器自己的沙箱目录。要读写 agent 工作目录的文件,"
                         "请用内置 create_file/read_file/edit_file/list_dir;"
                         "MCP 的文件工具只对它配置的根目录有效。]")
            return _res
        if name=="create_file":
            p=os.path.join(workdir,args["path"]); os.makedirs(os.path.dirname(p),exist_ok=True)
            open(p,"w",encoding="utf-8").write(args["content"])
            fixed = _auto_repair(p)
            tag = "已自动修复转义" if fixed else f"{len(args['content'])} bytes"
            return f"[created {args['path']} ({tag})]"
        if name=="read_file":
            p=os.path.join(workdir,args["path"])
            if not os.path.exists(p):
                return f"[not found: {args['path']}]"
            # 按需精读:start_line/end_line 只读指定行区间(科研场景精读全文落盘文件)
            sl = int(args.get("start_line", 0) or 0)
            el = int(args.get("end_line", 0) or 0)
            lines = read_text(p).splitlines()
            if sl > 0 or el > 0:
                if el <= 0: el = len(lines)
                chunk = lines[max(0, sl-1):el]
                meta = f"\n[文件共 {len(lines)} 行,已读取 {max(0,sl-1)+1}-{min(el,len(lines))} 行。需要其他部分用 read_file(start_line=.., end_line=..)。]"
                return "\n".join(chunk)[:6000] + meta
            return read_text(p)[:6000]
        if name=="edit_file":
            p=os.path.join(workdir,args["path"]); s=read_text(p)
            # 编辑前备份 .bak,模型改坏文件时可回滚
            try:
                if os.path.exists(p):
                    import shutil as _sh
                    _sh.copy2(p, p + ".bak")
            except Exception:
                pass
            old = str(args["old"]).replace("\\n","\n").replace("\\t","\t").replace('\\"','"')
            new = str(args["new"]).replace("\\n","\n").replace("\\t","\t").replace('\\"','"')
            if old not in s:
                preview = s[:200].replace("\n","↵")
                return (f"[edit failed: old text not found. 文件开头预览: {preview}...] "
                        f"请 read_file 查看全文,构造精确匹配的 old 文本,或改用 create_file 整体重写。")
            open(p,"w",encoding="utf-8").write(s.replace(old,new,1))
            fixed = _auto_repair(p)
            tag = "已备份+自动修复转义" if fixed else "已备份"
            return f"[edited {args['path']} ({tag}),.bak 备份可用]"
        if name=="append_file":
            p=os.path.join(workdir,args["path"]); open(p,"a",encoding="utf-8").write(args["content"])
            _auto_repair(p)
            return f"[appended {args['path']}]"
        if name=="delete_file":
            p=os.path.join(workdir,args["path"])
            if os.path.exists(p): os.remove(p); return f"[deleted {args['path']}]"
            return f"[not found: {args['path']}]"
        if name=="list_dir":
            d=os.path.join(workdir,args.get("path","."))
            return "\n".join(sorted(os.listdir(d))) if os.path.isdir(d) else f"[not a dir: {d}]"
        if name=="search_files":
            d=os.path.join(workdir,args["path"]); pat=re.compile(args["pattern"])
            out=[]
            for root,_,files in os.walk(d):
                for f in files[:200]:
                    fp=os.path.join(root,f)
                    try:
                        for i,line in enumerate(open(fp,encoding="utf-8",errors="ignore"),1):
                            if pat.search(line): out.append(f"{os.path.relpath(fp,d)}:{i}: {line.strip()[:100]}")
                            if len(out)>=20: break
                    except Exception: pass
                    if len(out)>=20: break
                if len(out)>=20: break
            return "\n".join(out) or "(no matches)"
        if name=="run_bash":
            cmd = str(args["command"])
            cmd = re.sub(r"\\+n", "\n", cmd)
            cmd = re.sub(r"\\+t", "\t", cmd)
            cmd = re.sub(r'\\+"', '"', cmd)
            cmd = re.sub(r"\\+'", "'", cmd)
            r=subprocess.run(cmd,shell=True,capture_output=True,text=True,timeout=300,cwd=workdir)
            out = f"[exit {r.returncode}]\nSTDOUT:\n{r.stdout[-5000:]}\nSTDERR:\n{r.stderr[-2000:]}"
            # 常见 Linux 绝对路径幻觉(/workspace /data /tmp 等),给提示
            if re.search(r"(^|\s)(cd|mkdir|ls|rm|cat|touch)\s+/(?!Users|home|[A-Za-z]:)", cmd) or "cd /workspace" in cmd:
                out += "\n[提示: 这是 Windows,不要用 /data /tmp /workspace 等 Linux 路径。工作目录已设定,直接用相对路径或本机盘符路径。]"
            # bash 风格 `time cmd` 在 Windows cmd 里不是计时(会提示改系统时间),给提示
            if re.match(r"^\s*time\s+", cmd):
                out += "\n[提示: Windows 无 bash 的 time 命令。请在脚本内用 python time 模块计时,或用 python -c 执行计时。]"
            return out
        if name=="web_search": return web_search(args["query"])
        if name=="web_search_multi": return web_search_multi(args.get("queries", []), int(args.get("max_results", 3)))
        if name=="batch_tools": return batch_tools(args.get("calls", []), workdir)
        if name=="web_fetch": return web_fetch(args["url"], workdir)
        if name=="memory_store": return memory_store(args["text"])
        if name=="memory_recall": return memory_recall(args["query"], int(args.get("limit",3)))
        if name=="todo":
            act = args.get("action","list")
            if act=="create":
                # 参数宽容:小模型常用 plan/steps/items 等别名,或传整个字符串。
                items = args.get("items") or args.get("plan") or args.get("steps") or []
                if isinstance(items, str):
                    items = [ln.strip(" -0123456789.") for ln in items.splitlines() if ln.strip()]
                items = [str(i) for i in items if str(i).strip()]
                if not items:
                    return "[todo create: no items found. Pass items as a list of strings, e.g. items=[\"step 1\", \"step 2\"]]"
                save_todo(workdir,[{"item":i,"done":False} for i in items])
                return load_todo_str(workdir)
            if act=="update":
                t=load_todo(workdir)
                if 1<=int(args.get("index",0))<=len(t):
                    t[int(args["index"])-1]["done"]=bool(args.get("done",True)); save_todo(workdir,t)
                return load_todo_str(workdir)
            return load_todo_str(workdir)
        if name=="skills":
            return list_skills(workdir) if args.get("action","list")=="list" else load_skill(args.get("name",""), workdir)
        if name=="mcp_call": return mcp_call(args["server"], args["tool"], args.get("args",{}))
        if name=="enable_tools": return enable_advanced_tools(args.get("tools",[]))
        if name=="finish": return "[TASK_COMPLETE] " + args.get("summary","")
    except KeyError as e:
        # 缺参数是本地小模型最常见的失败模式,给可操作的提示
        req = _REQ_ARGS.get(name, [])
        got = list(args.keys())
        missing = req if not got else [k for k in req if k not in args]
        return (f"[tool error: {name} 缺少参数 {e}。必须提供参数: {missing or req}。"
                f"你实际传了: {got}。请 read_file 后再用完整参数重试,或改用 create_file 整写。]")
    except Exception as e:
        return f"[tool error: {e}]"
    return "[unknown tool]"

# ---------------- API 调用 ----------------
def call_chat(model, messages, ctx=None, tools=None, stream=False, on_token=None, on_think=None):
    """调用 ollama /api/chat。stream=True 时逐 token 回调(on_token=回答, on_think=思考),
    返回结构与非流式一致(message.content / tool_calls / prompt_eval_count / eval_count)。"""
    ctx = ctx or CTX_BUDGET
    payload = {"model":model,"messages":messages,
               "tools": active_tool_defs() if tools is None else tools,
               "stream":stream, "options":{"num_ctx":ctx,"num_predict":NUM_PREDICT,
                                          "temperature":TEMP}}
    if not THINK: payload["options"]["think"] = False   # 思考模型防空响应死循环
    req = urllib.request.Request(f"{appconfig.ollama_host()}/api/chat",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    if stream:
        parts, thinks, tool_calls = [], [], None
        prompt_ev, eval_ev = None, None
        # 生成超时 240s:正常 35B 生成足够,卡死(模型不吐 token)能兜底退出,避免无限等
        resp = urllib.request.urlopen(req, timeout=240)
        for line in resp:
            line = line.strip()
            if not line: continue
            try: chunk = json.loads(line)
            except Exception: continue
            msg = chunk.get("message", {}) or {}
            c = msg.get("content")
            if c:
                if on_token: on_token(c)
                parts.append(c)
            rc = msg.get("reasoning_content") or msg.get("thinking")
            if rc:
                if on_think: on_think(rc)
                thinks.append(rc)
            if msg.get("tool_calls"):
                tool_calls = msg["tool_calls"]
            if chunk.get("prompt_eval_count") is not None: prompt_ev = chunk["prompt_eval_count"]
            if chunk.get("eval_count") is not None: eval_ev = chunk["eval_count"]
            if chunk.get("done"): break
        content = "".join(parts)
        m = {"role": "assistant", "content": content}
        if tool_calls: m["tool_calls"] = tool_calls
        return {"message": m, "prompt_eval_count": prompt_ev, "eval_count": eval_ev}
    return json.loads(urllib.request.urlopen(req, timeout=900).read())

# ---------------- 上下文事前估算 ----------------
def _estimate_tokens(text):
    """粗略估算文本 token 数(中文≈1字/token,英文≈4字符/token)。
    用于 API 调用前判断是否超限,不等 ollama 返回(500 时拿不到用量)。"""
    try:
        if not text:
            return 0
        # 统计 CJK 字符数
        cjk = sum(1 for ch in text if '一' <= ch <= '鿿' or '㐀' <= ch <= '䶿')
        other = len(text) - cjk
        return cjk + other // 4 + 1
    except Exception:
        return len(str(text)) // 4

def _estimate_messages_tokens(messages, tools=None):
    """估算消息+工具 schema 的总 token 数。"""
    total = 0
    for m in messages or []:
        total += _estimate_tokens(str(m.get("content", "")))
        for tc in (m.get("tool_calls") or []):
            total += _estimate_tokens(str(tc.get("function", {}).get("name", "")))
            total += _estimate_tokens(str(tc.get("function", {}).get("arguments", "")))
    for t in (tools or []):
        total += _estimate_tokens(str(t.get("function", {}).get("name", "")))
        total += _estimate_tokens(str(t.get("function", {}).get("description", "")))
        total += _estimate_tokens(str(t.get("function", {}).get("parameters", {})))
    return total

def compact_history(model, messages, level=3):
    """分层压缩上下文(符合 context-rot 经验:本地模型 ~60% 就开始退化,应分级提前压缩)。

    level 1(轻):  丢弃/精简旧工具输出——把较早 tool 消息的长结果截断为一行标注,
                  保留结构(assistant 的决策/结论),不动 system 和最近轮次。
    level 2(中):  摘要更早的轮次为一段摘要,保留 system + 最近 5 条(比 level3 温和)。
    level 3(重):  全量摘要 + 重建工作集:system + 摘要 + 最近 3 条(原有行为)。

    保留原则(无论哪级):目标、已做决定、当前产物文件、未完成事项;丢弃:旧日志、
    已被替换的计划、已读过的文件全文。"""
    if len(messages) <= 4: return messages
    head = messages[0]
    if level <= 1:
        # level 1:只精简旧 tool 输出(截断长结果),保留所有角色结构
        _MAX_TOOL = 120   # 旧 tool 消息只留前 120 字符
        out = [head]
        keep_tail = messages[-2:]   # 保留最近 2 条(通常是刚发生的 tool+assistant)
        for i, m in enumerate(messages[1:], 1):
            m = dict(m)
            is_recent = any(m is orig for orig in keep_tail)
            if m.get("role") == "tool" and not is_recent:   # 旧 tool 结果截断
                c = str(m.get("content", ""))
                if len(c) > _MAX_TOOL:
                    m["content"] = c[:_MAX_TOOL] + f"…(已截断,原 {len(c)} 字符)"
            out.append(m)
        print(f"[上下文压缩 L1: 截断旧工具输出]", flush=True)
        return out
    if level <= 2:
        # level 2:摘要更早的轮次,保留 system + 最近 5 条
        if len(messages) <= 6: return messages
        tail = messages[-5:]; to_zip = messages[1:-5]
        if not to_zip: return messages
        text = "\n".join(f"[{m.get('role')}]: {str(m.get('content',''))[:400]}" for m in to_zip)
        try:
            req = [{"role":"system","content":"用中文压缩成 ≤150 字摘要,保留目标、关键文件名、已做决定、错误和未完成事项,丢弃旧日志与已读全文。"},
                   {"role":"user","content": text}]
            r = call_chat(model, req, ctx=8000, tools=[])
            summary = r.get("message",{}).get("content","") or "(summary failed)"
            out = [head, {"role":"user","content":"[先前上下文摘要] " + summary}, *tail]
            print(f"[上下文压缩 L2: {len(messages)} → {len(out)} 条消息]", flush=True)
            return out
        except Exception:
            return messages
    # level 3(原有行为):全量摘要 + 重建工作集
    if len(messages) <= 4: return messages
    tail = messages[-3:]; to_zip = messages[1:-3]
    text = "\n".join(f"[{m.get('role')}]: {str(m.get('content',''))[:400]}" for m in to_zip)
    try:
        req = [{"role":"system","content":"用中文把下面这段 agent 对话压缩成 ≤150 字摘要,保留关键文件名、代码决策、错误信息和未完成事项。"},
               {"role":"user","content": text}]
        r = call_chat(model, req, ctx=8000, tools=[])
        summary = r.get("message",{}).get("content","") or "(summary failed)"
        out = [head, {"role":"user","content":"[先前上下文摘要] " + summary}, *tail]
        print(f"[上下文压缩 L3: {len(messages)} → {len(out)} 条消息]", flush=True)
        return out
    except Exception:
        return messages

# ---------------- 会话(JSON + 侧车元数据) ----------------
def load_session(name):
    if not name: return None
    p = os.path.join(SESSIONS_DIR, name + ".json")
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return None
def sanitize_ckpt(msgs):
    """续跑前清理检查点:末尾若为带 tool_calls 但无 tool 结果的悬空 assistant(崩溃点),
    去掉其 tool_calls(保留正文);末尾空内容/损坏内容(response:unknown{...} 等)的
    assistant 直接删。否则模型面对悬空 tool_call 会输出垃圾。"""
    _GARBAGE = ("response:unknown", "<|endoftext|>", "`$`")
    changed = True
    while changed:
        changed = False
        while msgs and msgs[-1].get("role") == "assistant" and msgs[-1].get("tool_calls"):
            last = msgs[-1]; last.pop("tool_calls", None)
            if not str(last.get("content","") or "").strip():
                msgs.pop()
            changed = True
        while msgs and msgs[-1].get("role") == "assistant" \
                and not str(msgs[-1].get("content","") or "").strip():
            msgs.pop(); changed = True
        while msgs and msgs[-1].get("role") == "assistant" and not msgs[-1].get("tool_calls") \
                and any(g in str(msgs[-1].get("content","") or "") for g in _GARBAGE):
            msgs.pop(); changed = True
    return msgs

def save_session(name, msgs):
    if not name: return
    json.dump(msgs, open(os.path.join(SESSIONS_DIR, name + ".json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    try:
        task = next((str(m.get("content","")) for m in msgs if m.get("role")=="user" and not m.get("tool_calls")), "")
        status = "running"
        for m in reversed(msgs):
            c = str(m.get("content",""))
            if "TASK_COMPLETE" in c: status = "done"; break
            if "MAX ITERATIONS" in c: status = "max-iter"; break
            for tc in m.get("tool_calls", []):
                if tc.get("function",{}).get("name") == "finish":
                    status = "done"; break
            if status == "done": break
        meta = {"updated": time.strftime("%Y-%m-%d %H:%M"), "task": task[:200],
                "status": status, "msgs": len(msgs)}
        json.dump(meta, open(os.path.join(SESSIONS_DIR, name + ".meta.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass
    print(f"[session saved: {name}]", flush=True)

# ---------------- 主循环 ----------------
def main():
    args = sys.argv[1:]
    # 守护系统:允许目录白名单(AGENT_ALLOW_DIRS 冒号分隔,追加到工作目录之外)
    global _allow_dirs
    _extra = os.environ.get("AGENT_ALLOW_DIRS", "")
    if _extra:
        _allow_dirs = set(os.path.abspath(d.strip()) for d in _extra.split(";") if d.strip())
    if not ensure_ollama():
        print("⚠️ 未能自动启动 ollama,请手动运行 ollama serve 后重试。", flush=True)
    session = None; interactive = False
    if "--session" in args: session = args[args.index("--session")+1]
    if "--chat" in args: interactive = True
    if "--new" in args and len(args)>=3 and os.path.exists(os.path.join(args[2],".agent_state.json")):
        os.remove(os.path.join(args[2],".agent_state.json"))

    if interactive:
        model = args[0]; workdir = os.path.abspath(args[args.index("--chat")+1])
        os.chdir(workdir)
        msgs = load_session(session) or [{"role":"system","content":system_prompt()}]
        print("[交互模式] 输入 exit 退出。", flush=True)
        while True:
            try: user = input("你> ").strip()
            except EOFError: break
            if user.lower() in ("exit","quit"): break
            msgs.append({"role":"user","content":user})
            msgs = agent_loop(model, msgs, workdir, session)
    else:
        model, taskfile, workdir = args[0], args[1], args[2]
        taskfile = os.path.abspath(taskfile)
        workdir = os.path.abspath(workdir)
        os.makedirs(workdir, exist_ok=True)
        os.chdir(workdir)
        task = read_text(taskfile)
        ckpt = os.path.join(workdir, ".agent_state.json")
        append_text = task if "--append" in sys.argv else None
        if "--new" in sys.argv:
            msgs = [{"role":"system","content":system_prompt()},{"role":"user","content":task}]
        elif append_text:
            # 对话延续:优先已保存会话,其次检查点,都没有则新建;新消息必须追加
            msgs = load_session(session)
            if not msgs and os.path.exists(ckpt):
                msgs = sanitize_ckpt(json.load(open(ckpt, encoding="utf-8")))
            if msgs:
                print(f"[RESUMED: {len(msgs)} msgs + 追加新消息]", flush=True)
                msgs.append({"role":"user","content":append_text})
            else:
                msgs = [{"role":"system","content":system_prompt()},{"role":"user","content":append_text}]
        elif os.path.exists(ckpt):
            msgs = sanitize_ckpt(json.load(open(ckpt, encoding="utf-8")))
            print(f"[RESUMED checkpoint: {len(msgs)} msgs]", flush=True)
        elif session and load_session(session):
            msgs = load_session(session)
            print(f"[RESUMED session: {session} ({len(msgs)} msgs)]", flush=True)
            msgs.append({"role":"user","content":"继续之前的对话,完成或回答当前需求。"})
        else:
            msgs = [{"role":"system","content":system_prompt()},{"role":"user","content":task}]
        agent_loop(model, msgs, workdir, session)

_FAIL_MARKERS = ("[edit failed", "[tool error", "[not found", "[web_search error",
                 "[web_fetch error", "[mcp_call error", "not found in", "error:",
                 "cannot find the path", "no such file", "is not recognized",
                 "command not found", "not recognized as", "access is denied",
                 "did not match", "fatal:", "unknown option")
_TASK_HINTS = ("写","建","改","创建","修改","删","删除","运行","执行","实现","编写","重构","修复",
               "生成","统计","翻译","总结","对比","测试","调试","安装","下载","部署","搭建","配置",
               "启动","停止","整理","转换","爬取","优化","检查","分析","设计","代码","程序","脚本","帮我做",
               # English imperative/task verbs (benchmark + international users)
               "write ", "create ", "build ", "implement", "fix ", "debug", "analyze", "analyse",
               "clean ", "optimize", "optimise", "refactor", "generate", "design ", "audit ",
               "review ", "compute", "convert", "export", "import ", "plot ", "profile ",
               "implement ", "produce ", "research ", "search for", "find all", "list all",
               "step 1", "required steps", "plan at least", "todo(action")
_QA_HINTS = ("什么","怎么","为什么","如何","解释","说明","介绍","区别","原理","能否","可以吗","能不能",
             "吗","呢","?","？","你好","hi","hello","在吗","谢谢","再见","早安","晚安","你是谁",
             # English question patterns
             "what is ", "what are ", "how do i", "how does ", "why is ", "why does ",
             "can you explain", "tell me about", "who is ", "when was ")
_MUTATE = ("create_file","edit_file","append_file","delete_file","run_bash")

def _hint_hit(hint, low):
    """提示词命中:中文/含非 ASCII 用子串;纯 ASCII 用词边界(防 "hi" 命中 "this"、
    "fix" 命中 "prefix" 这类子串误伤)。大小写由调用方统一 lower。"""
    if not hint.isascii():
        return hint in low
    return re.search(r"\b" + re.escape(hint.strip()) + r"\b", low) is not None

def _is_qa(messages):
    """判断最近一条用户消息是"问答"(问句/寒暄)还是"任务"(要动手干活)。
    问答 → 回答一次即收尾,拦写文件/跑命令;任务 → 正常用工具,绝不强制收尾。
    跳过 harness 注入的消息,只认真正的用户输入。大小写不敏感(英文任务常以大写开头)。"""
    for m in reversed(messages):
        if m.get("role") == "user":
            text = str(m.get("content","") or "").strip()
            if not text:
                continue
            if (text.startswith("⚠️") or text.startswith("Continue:") or text.startswith("[已拦截")
                    or "[先前上下文摘要]" in text or "上下文已压缩" in text):
                continue
            low = text.lower()
            # 任务词命中 → 任务(优先,避免把"帮我写代码"当问答)
            if any(_hint_hit(h, low) for h in _TASK_HINTS):
                return False
            # 问句/寒暄命中 → 问答
            if any(_hint_hit(h, low) for h in _QA_HINTS):
                return True
            # 短消息(≤40字)无动作词 → 问答
            if len(text) <= 40:
                return True
            return False
    return False

def _dedupe_trailing_assistant(messages):
    """修复对话结构:删除末尾连续的空 assistant 消息(保留最后一条)。
    连续 assistant(无 tool_calls)会让 ollama 报 400 'Cannot have 2 or more
    assistant messages at the end of the list'。空内容 + 无 tool_calls 的
    assistant 是无效的(模型没输出也没调工具),应被合并掉。"""
    if not messages:
        return messages
    # 只在末尾处理连续 assistant:合并空的无调用 assistant,保留最后一条有内容的
    while len(messages) >= 2 and messages[-1].get("role") == "assistant" and \
          messages[-2].get("role") == "assistant":
        # 若末条为空且无 tool_calls,丢弃它;否则保留末条丢弃前一条空的
        last = messages[-1]; prev = messages[-2]
        last_empty = not (last.get("content") or "").strip() and not last.get("tool_calls")
        prev_empty = not (prev.get("content") or "").strip() and not prev.get("tool_calls")
        if last_empty:
            messages.pop()
        elif prev_empty:
            messages.pop(-2)
        else:
            # 两条都有内容/调用:合并内容到后一条,删前一条
            merged = dict(prev)
            merged["content"] = (prev.get("content") or "") + "\n" + (last.get("content") or "")
            merged["tool_calls"] = last.get("tool_calls") or prev.get("tool_calls")
            messages[-2:] = [merged]
    return messages

def _similar(a, b, thresh=0.75):
    """判断两段文本是否高度相似(用于重复输出死循环检测)。"""
    a = "".join(a.split()); b = "".join(b.split())
    if not a or not b:
        return False
    try:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a[:200], b[:200]).ratio() > thresh
    except Exception:
        return a == b

def _pytest_hint(output):
    """从 pytest 失败输出里提取精确调试信息(失败文件/行号/错误/断言),注入给模型帮它自修。
    治小模型"修自己 bug"弱的问题。"""
    lines = output.splitlines()
    hint = []
    for i, ln in enumerate(lines):
        if ln.startswith("FAILED "):
            hint.append(ln[7:].strip()[:120])
            break
    for ln in lines:
        m = re.search(r'File "([^"]+)", line (\d+)', ln)
        if m:
            hint.append(f"位于 {os.path.basename(m.group(1))}:{m.group(2)}")
            break
    for ln in lines:
        if ln.startswith("E "):
            hint.append(ln[2:].strip()[:160])
            break
    if hint:
        return " | ".join(hint)
    return (lines[-1] if lines else "").strip()[:120]

def _is_tool_error(res):
    r = res[:200].lower()
    return any(m in r for m in _FAIL_MARKERS)

def try_parse_tool_calls(content):
    """小模型常把工具调用写成文本 JSON 而非 tool_call(格式泄漏)。尝试解析成工具调用。
    支持: {"todo": {...}} / {"name":"todo","arguments":{...}} / [{"todo":{...}},...]
    返回 [(name, args), ...] 或 None。"""
    c = content.strip()
    if not c.startswith(("{", "[")):
        return None
    try:
        data = json.loads(c)
    except Exception:
        return None
    items = data if isinstance(data, list) else [data]
    if not isinstance(items, list):
        return None
    calls = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if "name" in it and "arguments" in it:
            calls.append((it["name"], it.get("arguments") or {}))
        elif len(it) == 1:
            name = next(iter(it)); v = it[name]
            if isinstance(v, dict):
                calls.append((name, v))
    return calls or None

_ARTIFACT_EXTS = (".md", ".txt", ".png", ".jpg", ".jpeg", ".csv", ".py", ".json", ".docx",
                  ".xlsx", ".pdf", ".html", ".yaml", ".yml", ".svg", ".tex", ".tsv", ".log")
_FILE_TOKEN = re.compile(r"[A-Za-z0-9_\-一-鿿][A-Za-z0-9_\-一-鿿]*\.[A-Za-z0-9]{2,5}")

def _model_params_b(model):
    """从模型名解析参数量(单位:B): gemma4:e2b→2.0 / qwen3.5:4b→4.0 / ornith-1.5:35b→35.0。
    解析失败返回 None(调用方按大模型处理)。"""
    m = re.search(r"(\d+(?:\.\d+)?)b\b", str(model).lower())
    return float(m.group(1)) if m else None

def _claimed_missing_files(summary, workdir):
    """finish 产物核对:提取 summary 声称的文件名,返回工作目录中不存在的。
    判定存在:按声称路径(相对 workdir)查 → 按文件名递归搜 → 现有文件名是 token
    后缀也算(兼容中文动词前缀粘连,如"生成了温度分布图.png")。"""
    toks = set()
    for m in _FILE_TOKEN.finditer(summary or ""):
        tok = m.group(0).strip()
        if tok.lower().endswith(_ARTIFACT_EXTS):
            toks.add(tok)
    if not toks:
        return []
    all_bn = [os.path.basename(f).lower()
              for f in glob.glob(os.path.join(workdir, "**", "*"), recursive=True)
              if os.path.isfile(f)]
    missing = []
    for tok in sorted(toks):
        rel = tok.replace("\\", "/").lstrip("./")
        if os.path.isfile(os.path.join(workdir, rel)):
            continue
        base = os.path.basename(rel).lower()
        if base in all_bn or any(base.endswith(bn) for bn in all_bn):
            continue
        missing.append(tok)
    return missing


def agent_loop(model, messages, workdir, session):
    global _active_tools
    fails = 0
    fail_count = {}           # 工具名 -> 连续失败次数(同工具无成功则累计)
    redirect_warns = 0
    last_tool = None
    last_sig = None            # 上一次工具调用签名(严格不重复同一命令)
    dup_warns = 0
    tool_streak = 0
    streak_warns = 0
    research_streak = 0     # 连续调研类工具(web_search/web_fetch)计数
    research_warns = 0
    _RESEARCH = ("web_search", "web_fetch")
    todo_streak = 0         # 累计 todo 调用(仅产出型工具清零)
    _PRODUCTIVE = ("create_file", "edit_file", "append_file", "finish", "run_bash")
    productive_used = False  # 是否调用过产出型工具
    fake_finish_warns = 0
    finish_claim_warns = 0   # finish 产物核对拒绝次数(≥2 放行,防死锁)
    bash_teach_warns = 0     # 小模型 run_bash 教学提示次数
    empty_turns = 0          # 连续空文本输出计数
    test_guard_warns = 0
    qa = _is_qa(messages)          # 用户最近消息是"问答"还是"任务"
    casual_warns = 0
    casual_force = False            # 强制收尾标志(问答答完 / 重复死循环)
    last_text = ""                  # 上一次助手文本输出(重复检测)
    repeat_count = 0
    if qa:
        # 问答:换聊天级系统提示(根治:任务向 prefill 是"加戏"死循环的根源)
        messages = [{"role": "system", "content": CHAT_SYSTEM}] + \
                   [m for m in messages if m.get("role") != "system"]
        cats = None
    else:
        # 任务:按类别路由,只暴露相关工具 → prefill 更小更快
        _task_text = next((str(m.get("content","")) for m in reversed(messages)
                           if m.get("role") == "user" and not str(m.get("content","")).startswith(
                               ("⚠️", "Continue:", "[已拦截", "回答已经足够"))), "")
        cats = route_categories(_task_text)
        mcp_manifest()   # 预热 MCP 探测缓存(实际工具由 tools_for_categories 扁平并入)
    # 小模型协议降级(≤4B):edit_file 的 old_text 精确匹配是 2-4B 模型失败重灾区,
    # 直接持久禁用,一律用 create_file 重写;run_bash 报错附教学提示(见错误处理段)。
    # 模型名解析参数量: gemma4:e2b→2 / qwen3.5:4b→4 / ornith-1.5:35b→35;解析失败视为大模型。
    _small_model = (not qa) and ((_model_params_b(model) or 99.0) <= 4.0)
    if _small_model:
        _disabled_tools.add("edit_file")
    allowed_extra = set()   # 模型 enable_tools 补充的工具名
    _compact_lvl = 0        # 已执行的最高压缩级别(避免同级别重复触发)
    _restarts = 0           # ollama 重启次数(单任务上限 3 次,防无限重启)
    for i in range(200):
        if casual_force:
            print("[收尾] 本轮已足够,强制结束(防问答重复/死循环)", flush=True)
            messages.append({"role":"tool","content":"[TASK_COMPLETE] 已回答,结束本轮"})
            break
        try:
            # 修复对话结构:连续 assistant 消息会让 ollama 返回 400
            # (Cannot have 2 or more assistant messages at the end)。
            # 删除末尾连续的空 assistant(保留最后一条),避免"可修复的 400"被误判为致命。
            messages = _dedupe_trailing_assistant(messages)
            if qa:
                ct = _chat_tool_defs()      # 问答:只读工具(根治加戏)
            elif cats:
                ct = tools_for_categories(cats, extra=allowed_extra)   # 任务:按类别加载(扁平 prefill)
            else:
                ct = None                    # 全量(兜底)
            # 上下文事前估算:调用前估算消息+工具 token,超限主动压缩(不等 ollama 返回,
            # 500 时拿不到用量;opencode 同思路——请求前预算检查避免超限/错误)
            _est = _estimate_messages_tokens(messages, ct)
            if _est > CTX_BUDGET * 0.90 and _compact_lvl < 3:
                messages = compact_history(model, messages, level=3); _compact_lvl = 3
                print(f"[{i}] 事前估算 {_est} token 超限,已压缩(L3)", flush=True)
            elif _est > CTX_BUDGET * 0.75 and _compact_lvl < 2:
                messages = compact_history(model, messages, level=2); _compact_lvl = 2
                print(f"[{i}] 事前估算 {_est} token 超限,已压缩(L2)", flush=True)
            elif _est > CTX_BUDGET * 0.60 and _compact_lvl < 1:
                messages = compact_history(model, messages, level=1); _compact_lvl = 1
                print(f"[{i}] 事前估算 {_est} token 超限,已压缩(L1)", flush=True)
            if STREAM:
                r = call_chat(model, messages, tools=ct, stream=True, on_token=_stream_tok, on_think=_stream_think)
            else:
                r = call_chat(model, messages, tools=ct)
            fails = 0
        except Exception as e:
            # verify-before-retry:区分"可修复的 4xx"(对话结构问题→清理后重试)
            # 与"不可修复的 4xx"(模型不存在/参数非法→停止)。
            body = ""
            try:
                import urllib.error as _ue
                if isinstance(e, _ue.HTTPError):
                    body = (e.read().decode("utf-8", "replace") if hasattr(e, "read") else "")[:300]
                    if 400 <= e.code < 500:
                        # 结构类 400(assistant 连续) → sanitize 后重试,不退出
                        if "assistant messages at the end" in body or "consecutive" in body.lower():
                            cleaned = _dedupe_trailing_assistant(messages)
                            if len(cleaned) != len(messages):
                                messages = cleaned
                                print(f"[{i}] 修复对话结构(连续 assistant),已清理重试", flush=True)
                                fails += 1
                                if fails >= 6:
                                    save_session(session, messages); sys.exit(1)
                                time.sleep(1)
                                continue
                        # 其他 4xx(模型/参数) → 不可修复,停止
                        print(f"[{i}] API 4xx 错误(重试无意义,已停止): {e} {body}", flush=True)
                        save_session(session, messages)
                        sys.exit(1)
            except Exception:
                pass
            # 500 降级重试:连续 500(ollama 资源紧张/超限)时,先触发压缩缩小上下文再重试,
            # 而非纯退避等待。这直接缓解 ollama 压力,减少 500 恢复时间。
            _is_500 = False
            try:
                import urllib.error as _ue2
                _is_500 = isinstance(e, _ue2.HTTPError) and e.code == 500
            except Exception:
                pass
            fails += 1
            if _is_500 and fails >= 4 and _restarts < 3:
                # ★ 治本:连续 ≥4 次 500 = ollama 进程级退化(temp=0 下同消息重走同坏路径,
                # 压缩/等待都无法逃逸)。重启 ollama 即恢复;检查点机制保证任务不丢。
                _restarts += 1
                print(f"[{i}] 连续 {fails} 次 500 → 判定 ollama 进程退化,自动重启(第 {_restarts}/3 次)...", flush=True)
                try:
                    ok = restart_ollama()
                    if ok:
                        print(f"[{i}] ✓ ollama 已重启,继续任务", flush=True)
                    else:
                        print(f"[{i}] ⚠ ollama 重启未就绪,仍继续重试", flush=True)
                except Exception as _re:
                    print(f"[{i}] ⚠ ollama 重启异常: {_re}", flush=True)
                fails = 0   # 重启后重置连续错误计数
                time.sleep(3)
                continue
            if _is_500 and fails >= 2:
                # 连续 ≥2 次 500:①压缩缩小上下文;②注入继续提示打破 temp=0 的
                # 同路径死循环(相同 messages 在退化 runner 上必然复现同一坏输出)
                if _compact_lvl < 3:
                    lvl = min(3, _compact_lvl + 1)
                    _compact_lvl = lvl
                    try:
                        messages = compact_history(model, messages, level=lvl)
                        print(f"[{i}] 500 错误,已降级压缩上下文(L{lvl})再重试", flush=True)
                    except Exception:
                        pass
                # 打破路径:若无未答的继续提示,追加一条(user 角色改变消息序列 → 模型换生成路径)
                _last_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
                if not (str(_last_user.get("content", "")).startswith("⚠️") if _last_user else False):
                    messages.append({"role": "user", "content":
                        "⚠️ 系统提示:上一请求遇到服务错误。请基于当前已有进度继续完成任务,"
                        "可以从换一种写法或先做下一步开始。"})
                    print(f"[{i}] 500 错误,已注入继续提示(打破死循环路径)", flush=True)
                time.sleep(2)
                continue
            wait = min(3 * (2 ** (fails - 1)), 60)
            print(f"[{i}] API error: {e} (retry {fails}, wait {wait}s)", flush=True)
            time.sleep(wait)
            if fails >= 8:
                print("===== FAILED: ollama 连续错误(含重启后仍失败),已停止。修复后勾选'续跑'可从中断处继续 =====", flush=True)
                save_session(session, messages)
                sys.exit(1)
            continue
        pt = r.get("prompt_eval_count") or (r.get("usage") or {}).get("prompt_tokens", 0)
        if pt:
            pct = pt * 100 // CTX_BUDGET
            print(f"[ctx: {pt}/{CTX_BUDGET} = {pct}%]", flush=True)
            # 分层压缩(context-rot:本地模型早退化,分级提前压缩)
            # 60% → L1 截断旧工具输出;75% → L2 摘要早轮次;90% → L3 全量重建
            if pt > CTX_BUDGET * 0.90 and _compact_lvl < 3:
                messages = compact_history(model, messages, level=3); _compact_lvl = 3
            elif pt > CTX_BUDGET * 0.75 and _compact_lvl < 2:
                messages = compact_history(model, messages, level=2); _compact_lvl = 2
            elif pt > CTX_BUDGET * 0.60 and _compact_lvl < 1:
                messages = compact_history(model, messages, level=1); _compact_lvl = 1
        msg = r.get("message",{})
        content = msg.get("content","") or ""
        tcs = msg.get("tool_calls")
        if not tcs and not qa:
            # 抢救:模型把工具调用写成文本 JSON 时,尝试解析成真实调用(问答模式禁用,防加戏)
            salvaged = try_parse_tool_calls(content)
            if salvaged:
                tcs = [{"function": {"name": n, "arguments": a}} for n, a in salvaged]
                print(f"[{i}] ⚡ 抢救到文本工具调用: {', '.join(n for n,_ in salvaged)}", flush=True)
        if tcs: messages.append({"role":"assistant","content":content,"tool_calls":tcs})
        else: messages.append({"role":"assistant","content":content})
        json.dump(messages, open(os.path.join(workdir,".agent_state.json"),"w",encoding="utf-8"), ensure_ascii=False)
        if tcs:
            for tc in tcs:
                fn=tc["function"]; name=fn["name"]; args=fn.get("arguments",{})
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except: args={}
                # 禁用工具必须拒绝执行(模型可能幻觉调用已被禁用的工具)
                # MCP 扁平工具("服务器.工具名")不在 _active_tools 里,需放行(run_tool 会路由)
                # 别名优先:write_file/list_directory 等业界通名映射为内置工具,直接放行
                _alias = {"write_file": "create_file", "save_file": "create_file",
                          "read_text_file": "read_file", "cat": "read_file",
                          "list_directory": "list_dir", "ls": "list_dir",
                          "append_to_file": "append_file", "edit": "edit_file",
                          "search_code": "search_files", "grep": "search_files",
                          "delete": "delete_file", "bash": "run_bash", "shell": "run_bash"}
                if name in _alias:
                    print(f"[{i}] ⚡ 别名映射: {name} -> {_alias[name]}", flush=True)
                    name = _alias[name]
                    fn["name"] = name
                if (name in _disabled_tools or name not in [t["function"]["name"] for t in _active_tools]) and not is_mcp_tool(name):
                    res = f"[tool {name} 已被禁用,请改用其他工具;若是搜索/抓取请直接写报告]"
                elif name not in ("finish", "todo") and last_sig == (name, json.dumps(args, sort_keys=True, ensure_ascii=False)) and dup_warns < 3:
                    # 严格不重复同一命令:完全相同签名连续调用 → 拦截并提醒换策略
                    dup_warns += 1
                    res = f"[已拦截:你刚调用过完全相同的 {name}(参数一致),结果不会变。请换策略:read_file 看真实情况/换实现方式。]"
                    print(f"[{i}] ⚠️ 重复调用拦截: {name}({dup_warns})", flush=True)
                    messages.append({"role":"tool","content":res})
                    # 拦截立刻前置提醒:tool 消息对小模型注意力弱,用 user 消息钉住"别原样重试"
                    messages.append({"role":"user","content":
                        "⚠️ 上一次调用被判定为重复(与此前完全一致),结果不会变。"
                        "不要原样重试:先用 read_file/list_dir 确认现状,或换一种实现方式继续推进。"})
                    continue
                elif qa and name in _MUTATE and casual_warns < 3:
                    # 问答守护:用户是问句/寒暄,拦住写文件/跑命令这类"加戏"
                    casual_warns += 1
                    if casual_warns >= 2:
                        casual_force = True   # 已提醒两次,下次迭代强制结束
                    res = f"[已拦截:用户是问答,无需 {name}。请直接用文字回答用户。]"
                    print(f"[{i}] ⚠️ 问答守护:拦截 {name}(问答消息,非任务)", flush=True)
                    messages.append({"role":"tool","content":res})
                    messages.append({"role":"user","content":
                        f"⚠️ 提醒(第 {casual_warns} 次):用户是在问答(问句/寒暄),不是要执行任务。"
                        f"你的文字回答已经足够。请【立即调用 finish(summary=你的回答)】结束本轮。"
                        f"不要重复输出同一段文字,不要调用任何工具。"})
                    continue
                else:
                    res = run_tool(name, args, workdir)
                    last_sig = (name, json.dumps(args, sort_keys=True, ensure_ascii=False))
                if name == "enable_tools":
                    # 记录 enable_tools 请求的工具名 → 下一轮 tools_for_categories 的 extra 里纳入
                    # (修复:此前 enable_advanced_tools 只改 _active_tools,on-demand MCP 工具实际加载不上)
                    for _n in (args.get("tools") or []):
                        allowed_extra.add(str(_n))
                if name in ("create_file", "edit_file", "append_file", "run_bash"):
                    productive_used = True
                elif is_mcp_tool(name) and _is_mcp_producing(name):
                    productive_used = True   # MCP 产出型工具(create_docx/write_*/render_* 等)
                print(f"[{i}] ⚙ {name} {json.dumps(args,ensure_ascii=False)[:60]} -> {res[:90]}", flush=True)
                if name=="finish":
                    # 假完成守护:没做任何实际工作就 finish → 拒绝并强制继续
                    if not productive_used and fake_finish_warns < 2:
                        fake_finish_warns += 1
                        print(f"[{i}] ⚠️ 拒绝假 finish:未使用任何产出型工具(create_file/edit_file/run_bash)", flush=True)
                        messages.append({"role":"user","content":
                            "⚠️ 你的 finish 被拒绝:你还没有做任何实际工作(未创建/修改文件或运行命令)。"
                            "请先真正执行任务(读写文件、运行命令、写报告),完成后再调用 finish。"})
                        messages.append({"role":"tool","content":res})
                        continue
                    # 测试验证守护:目录有 test_*.py 时,harness 亲自跑 pytest,不过则拒绝 finish
                    if glob.glob(os.path.join(workdir, "test_*.py")) and test_guard_warns < 3:
                        test_guard_warns += 1
                        pr = subprocess.run("python -m pytest -q", shell=True,
                                            capture_output=True, text=True, cwd=workdir, timeout=300)
                        ok = pr.returncode == 0
                        tail = ((pr.stdout or "").strip().splitlines() or [""])[-1][:120]
                        if not ok:
                            h = _pytest_hint(pr.stdout or "")
                            bak_hint = ""
                            if "SyntaxError" in h or "IndentationError" in h:
                                baks = glob.glob(os.path.join(workdir, "*.py.bak"))
                                if baks:
                                    bak_hint = (f"检测到语法错误。可用备份回滚:先把对应 .bak 内容恢复"
                                                f"(如 copy {os.path.basename(baks[0])} 覆盖原文件),或重建文件。\n")
                            print(f"[{i}] ⚠️ 测试未通过({pr.returncode}),拒绝 finish", flush=True)
                            messages.append({"role":"user","content":
                                f"⚠️ 你的 finish 被拒绝:测试未通过(pytest exit {pr.returncode})。\n"
                                f"精确失败: {h}\n"
                                + bak_hint +
                                f"请 read_file 查看失败处代码,修复测试与实现使其一致,"
                                f"运行 python -m pytest -q 确认全绿后再 finish。"})
                            messages.append({"role":"tool","content":res})
                            continue
                    # 产物核对门禁:finish summary 声称的产物逐一对照 workdir,缺失则拒绝。
                    # (裸 finish 曾让模型谎报"已写入/已生成"直接收货——谎报是低分直接死因)
                    if not qa and finish_claim_warns < 2:
                        _missing = _claimed_missing_files(str(args.get("summary","")), workdir)
                        if _missing:
                            finish_claim_warns += 1
                            print(f"[{i}] ⚠️ 产物核对:summary 声称但缺失 {_missing},拒绝 finish", flush=True)
                            messages.append({"role":"user","content":
                                "⚠️ 你的 finish 被拒绝:summary 声称的以下产物在工作目录中不存在:\n"
                                + "\n".join("- " + f for f in _missing)
                                + "\n请用 create_file/run_bash 真正生成它们;"
                                "或修改 summary 只声称确实存在的文件,然后重新 finish。"})
                            messages.append({"role":"tool","content":res})
                            continue
                    print("\n===== TASK COMPLETE =====", flush=True); print(res, flush=True)
                    save_session(session, messages)
                    return messages
                # 重复失败检测:同工具连续失败(只有同工具成功才清零)→ 强制换策略/禁用
                if _is_tool_error(res):
                    # 小模型教学:把 Python 代码直接喂给 cmd 是 e2b 的头号浪费
                    # ('import' is not recognized)——首次命中即教正确姿势,最多 2 次
                    if _small_model and name == "run_bash" \
                            and "not recognized" in res.lower() and bash_teach_warns < 2:
                        bash_teach_warns += 1
                        messages.append({"role":"user","content":
                            "提示:run_bash 执行的是 Windows shell 命令(cmd),不能直接运行 Python 代码。"
                            "正确做法:先用 create_file 把代码写入 .py 文件,再用 run_bash 运行:python 文件名.py"})
                    fail_count[name] = fail_count.get(name, 0) + 1
                    if fail_count[name] >= 3:
                        if name == "edit_file":
                            # edit_file 是小模型最易卡死的工具:连续 3 次失败直接禁用,强推 create_file
                            _disabled_tools.add("edit_file")
                            _active_tools = [t for t in _active_tools
                                             if t["function"]["name"] != "edit_file"]
                            messages.append({"role":"user","content":
                                "⚠️ edit_file 已连续 3 次失败,已被禁用。以后一律用 create_file 写入完整文件内容来修改文件。"})
                            fail_count[name] = 0
                        elif redirect_warns < 4:
                            redirect_warns += 1
                            if name == "run_bash":
                                hint = ("不要 cd 到 /workspace 等绝对路径——工作目录已设定,直接运行命令或用相对路径;"
                                        "先用 list_dir 确认目录内容,用 read_file/pwd 确认实际情况。")
                            else:
                                hint = ("先用 list_dir / read_file 确认实际情况,重新构造参数;"
                                        "或换一个实现方式。")
                            messages.append({"role":"user","content":
                                f"⚠️ 你已连续 {fail_count[name]} 次调用 {name} 失败。立刻停止重试,必须换策略:{hint}"})
                            fail_count[name] = 0
                elif fail_count.get(name):
                    fail_count[name] = 0   # 仅同工具成功清零
                # 重复成功检测:同一工具连续调用过多次(如 web_search 反复搜)→ 提示推进
                if name == last_tool:
                    tool_streak += 1
                else:
                    last_tool = name; tool_streak = 1
                if tool_streak >= 5 and streak_warns < 3:
                    streak_warns += 1
                    messages.append({"role":"user","content":
                        f"⚠️ 你已连续 {tool_streak} 次调用 {name}。若结果类似或没有新进展,停止重复:"
                        f"综合已有结果推进到下一步(写文件 / 换其他工具 / 调用 finish)。"})
                    tool_streak = 1
                if tool_streak >= 8 and name != "finish":
                    # 强升级:任何工具连续 8 次 → 临时禁用,强制推进(todo/搜索/只读循环都适用)
                    _disabled_tools.add(name)
                    _active_tools = [t for t in _active_tools
                                     if t["function"]["name"] != name]
                    messages.append({"role":"user","content":
                        f"⚠️ {name} 已连续调用 {tool_streak} 次,现被禁用。停止重复它,直接推进实际工作(写文件/执行/调用 finish)。"})
                    tool_streak = 1
                # 调研类工具组合检测:web_search/web_fetch 累计 ≥6 次仍无产出(产出型工具才会清零)→ 禁用并强制推进
                if name in _RESEARCH:
                    research_streak += 1
                    if research_streak >= 6 and research_warns < 3:
                        research_warns += 1
                        _disabled_tools.update(_RESEARCH)
                        _active_tools = [t for t in _active_tools
                                         if t["function"]["name"] not in _RESEARCH]
                        messages.append({"role":"user","content":
                            f"⚠️ 你已连续 {research_streak} 次使用网络工具且尚未产出任何文件。web_search/web_fetch 已被禁用:"
                            f"立即综合已有搜索结果,用 create_file 写报告/文件,然后调用 finish。"})
                        research_streak = 0
                elif name in ("create_file", "edit_file", "append_file", "finish", "run_bash"):
                    research_streak = 0   # 仅产出型工具清零;todo/skills/enable 等 meta 工具不影响
                # todo 循环检测:累计 todo 调用 ≥6 次仍无产出 → 禁用 todo,强制干正事
                if name == "todo":
                    todo_streak += 1
                    if todo_streak >= 6:
                        _disabled_tools.add("todo")
                        _active_tools = [t for t in _active_tools
                                         if t["function"]["name"] != "todo"]
                        messages.append({"role":"user","content":
                            f"⚠️ 你已调用 todo 达 {todo_streak} 次但没做实际工作。todo 已被禁用:"
                            f"立即用 edit_file/create_file 修改 app.py 修复漏洞,用 run_bash 跑测试。"})
                        todo_streak = 0
                elif name in _PRODUCTIVE:
                    todo_streak = 0   # 产出型工具清零 todo 计数
                messages.append({"role":"tool","content":res})
        else:
            if not STREAM:   # 流式时 token 已逐字上屏,不再整段打印
                print(f"[{i}] ✍ {content[:2000]}", flush=True)
            if not content.strip():
                empty_turns += 1
                if empty_turns >= 3:
                    empty_turns = 0
                    messages.append({"role":"user","content":
                        "⚠️ 你连续输出了空文本。立即调用工具做实际工作:"
                        "read_file 读文件 / run_bash 运行命令 / create_file 写文件。不要输出空文本。"})
                    continue
            else:
                empty_turns = 0
                if last_text and _similar(last_text, content):
                    # 重复输出死循环(问答或任务都可能):同段文字重复 ≥2 次 → 强制收尾
                    repeat_count += 1
                    print(f"[{i}] ⚠️ 检测到重复输出({repeat_count})", flush=True)
                    if repeat_count >= 2:
                        casual_force = True
                        messages.append({"role":"user","content":
                            "⚠️ 你重复输出了几乎相同的内容,判定为死循环。立即调用 finish 结束本轮,不要重复。"})
                    else:
                        messages.append({"role":"user","content":"Continue: keep making real progress with tools, or call finish only when fully verified/answered."})
                else:
                    last_text = content
                    repeat_count = 0
                    if qa:
                        # 问答:一次文字回答已足够,立即收尾,绝不再 push 继续
                        casual_force = True
                        messages.append({"role":"user","content":
                            "回答已经足够,用户是在问答。立即调用 finish 结束本轮,不要重复输出。"})
                    else:
                        messages.append({"role":"user","content":"Continue: keep making real progress with tools, or call finish only when fully verified/answered."})
    print("===== MAX ITERATIONS =====", flush=True)
    save_session(session, messages)
    return messages

if __name__ == "__main__":
    main()
