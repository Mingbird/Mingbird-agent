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

AGENT_HOME = os.path.expanduser("~/.ollama_agent")
MEMORY_FILE = os.path.join(AGENT_HOME, "memory.json")
SESSIONS_DIR = os.path.join(AGENT_HOME, "sessions")
SKILLS_DIR_HOME = os.path.join(AGENT_HOME, "skills")
MCP_CONFIG = os.path.join(AGENT_HOME, "mcp.json")
for d in (AGENT_HOME, SESSIONS_DIR, SKILLS_DIR_HOME):
    os.makedirs(d, exist_ok=True)

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
 _f("read_file","Read a file's content", P(path={"type":"string"}),["path"]),
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
 _f("web_fetch","Fetch a URL and return its plain text", P(url={"type":"string"}),["url"]),
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
    "网络": ["web_search", "web_fetch"],
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
    active_names = {t["function"]["name"] for t in active}
    for n in names:
        if n in avail and n not in active_names:
            active.append(avail[n])
    return [t for t in active if t["function"]["name"] in names]

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
            if out: return "\n".join(out)
        except Exception as e:
            last_err = str(e)[:80]
    return f"[web_search error: {last_err}]"
def web_fetch(url):
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script","style","nav","footer","header","noscript"]): t.decompose()
        return soup.get_text(" ", strip=True)[:6000]
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
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        params = StdioServerParameters(command=cfg["command"], args=cfg.get("args",[]), env=cfg.get("env"))
        async def _run():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    try:
                        res = await session.call_tool(tool, args or {})
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
        return asyncio.run(_run())
    except Exception as e:
        return f"[mcp_call error: {e}]"

# ---------------- 工具执行 ----------------
_active_tools = list(CORE_TOOLS)
def active_tool_defs():
    return list(_active_tools)
def enable_advanced_tools(names):
    avail = {t["function"]["name"]: t for t in ADVANCED_TOOLS}
    added = []
    for n in names:
        if n in avail and n not in [t["function"]["name"] for t in _active_tools]:
            _active_tools.append(avail[n]); added.append(n)
    return f"[enabled tools: {', '.join(added) or '(none)'}. Now available: {', '.join(t['function']['name'] for t in _active_tools)}]"

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

_SYSTEM_DIRS = ("\\windows\\", "\\program files\\", "\\system32\\", "/windows/", "/program files/", "/usr", "/etc/", "/bin/", "/root")
_DANGER_CMD = ("rm -rf", "rm -fr", "format c:", "format c:\\", "del /s /q c:", "rd /s /q c:\\", "diskpart", "mkfs", "shutdown", "taskkill /f /im")

def _gate_check(name, args, workdir):
    """工具安全门:拦截危险操作(删系统/危险命令),来自 V33 Mellum2 验证的安全层。"""
    try:
        if name == "run_bash":
            cmd = str(args.get("command", ""))
            low = cmd.lower()
            if any(d in low for d in _DANGER_CMD):
                return f"[安全门拦截:命令含危险操作,已拒绝执行。原命令: {cmd[:80]}]"
        if name in ("delete_file", "edit_file", "create_file", "append_file"):
            p = (str(args.get("path", "")) + "\\").lower()
            if any(d in p for d in _SYSTEM_DIRS):
                return f"[安全门拦截:目标路径含系统目录,已拒绝。路径: {args.get('path','')[:80]}]"
    except Exception:
        pass
    return None

def run_tool(name, args, workdir):
    try:
        gate = _gate_check(name, args, workdir)
        if gate:
            return gate
        if name=="create_file":
            p=os.path.join(workdir,args["path"]); os.makedirs(os.path.dirname(p),exist_ok=True)
            open(p,"w",encoding="utf-8").write(args["content"])
            fixed = _auto_repair(p)
            tag = "已自动修复转义" if fixed else f"{len(args['content'])} bytes"
            return f"[created {args['path']} ({tag})]"
        if name=="read_file":
            p=os.path.join(workdir,args["path"])
            return read_text(p)[:6000] if os.path.exists(p) else f"[not found: {args['path']}]"
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
        if name=="web_fetch": return web_fetch(args["url"])
        if name=="memory_store": return memory_store(args["text"])
        if name=="memory_recall": return memory_recall(args["query"], int(args.get("limit",3)))
        if name=="todo":
            act = args.get("action","list")
            if act=="create":
                save_todo(workdir,[{"item":i,"done":False} for i in args.get("items",[])])
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
        resp = urllib.request.urlopen(req, timeout=900)
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

def compact_history(model, messages):
    """超预算时把较早历史压成摘要,保留 system + 最近3条。"""
    if len(messages) <= 4: return messages
    head = messages[0]; tail = messages[-3:]; to_zip = messages[1:-3]
    text = "\n".join(f"[{m.get('role')}]: {str(m.get('content',''))[:400]}" for m in to_zip)
    try:
        req = [{"role":"system","content":"用中文把下面这段 agent 对话压缩成 ≤150 字摘要,保留关键文件名、代码决策、错误信息和未完成事项。"},
               {"role":"user","content": text}]
        r = call_chat(model, req, ctx=8000, tools=[])
        summary = r.get("message",{}).get("content","") or "(summary failed)"
        out = [head, {"role":"user","content":"[先前上下文摘要] " + summary}, *tail]
        print(f"[上下文已压缩: {len(messages)} → {len(out)} 条消息]", flush=True)
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
               "启动","停止","整理","转换","爬取","优化","检查","分析","设计","代码","程序","脚本","帮我做")
_QA_HINTS = ("什么","怎么","为什么","如何","解释","说明","介绍","区别","原理","能否","可以吗","能不能",
             "吗","呢","?","？","你好","hi","hello","在吗","谢谢","再见","早安","晚安","你是谁")
_MUTATE = ("create_file","edit_file","append_file","delete_file","run_bash")

def _is_qa(messages):
    """判断最近一条用户消息是"问答"(问句/寒暄)还是"任务"(要动手干活)。
    问答 → 回答一次即收尾,拦写文件/跑命令;任务 → 正常用工具,绝不强制收尾。
    跳过 harness 注入的消息,只认真正的用户输入。"""
    for m in reversed(messages):
        if m.get("role") == "user":
            text = str(m.get("content","") or "").strip()
            if not text:
                continue
            if (text.startswith("⚠️") or text.startswith("Continue:") or text.startswith("[已拦截")
                    or "[先前上下文摘要]" in text or "上下文已压缩" in text):
                continue
            # 任务词命中 → 任务(优先,避免把"帮我写代码"当问答)
            if any(h in text for h in _TASK_HINTS):
                return False
            # 问句/寒暄命中 → 问答
            if any(h in text for h in _QA_HINTS):
                return True
            # 短消息(≤40字)无动作词 → 问答
            if len(text) <= 40:
                return True
            return False
    return False

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
    allowed_extra = set()   # 模型 enable_tools 补充的工具名
    for i in range(200):
        if casual_force:
            print("[收尾] 本轮已足够,强制结束(防问答重复/死循环)", flush=True)
            messages.append({"role":"tool","content":"[TASK_COMPLETE] 已回答,结束本轮"})
            break
        try:
            if qa:
                ct = _chat_tool_defs()      # 问答:只读工具(根治加戏)
            elif cats:
                ct = tools_for_categories(cats, extra=allowed_extra)   # 任务:按类别加载(扁平 prefill)
            else:
                ct = None                    # 全量(兜底)
            if STREAM:
                r = call_chat(model, messages, tools=ct, stream=True, on_token=_stream_tok, on_think=_stream_think)
            else:
                r = call_chat(model, messages, tools=ct)
            fails = 0
        except Exception as e:
            fails += 1; wait = min(3 * (2 ** (fails - 1)), 60)
            print(f"[{i}] API error: {e} (retry {fails}, wait {wait}s)", flush=True)
            time.sleep(wait)
            if fails >= 6:
                print("===== FAILED: ollama 连续错误,已停止。修复后勾选'续跑'可从中断处继续 =====", flush=True)
                save_session(session, messages)
                sys.exit(1)
            continue
        pt = r.get("prompt_eval_count") or (r.get("usage") or {}).get("prompt_tokens", 0)
        if pt:
            pct = pt * 100 // CTX_BUDGET
            print(f"[ctx: {pt}/{CTX_BUDGET} = {pct}%]", flush=True)
            if pt > CTX_BUDGET * 0.90:
                messages = compact_history(model, messages)
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
                if name not in [t["function"]["name"] for t in _active_tools]:
                    res = f"[tool {name} 已被禁用,请改用其他工具;若是搜索/抓取请直接写报告]"
                elif name not in ("finish", "todo") and last_sig == (name, json.dumps(args, sort_keys=True, ensure_ascii=False)) and dup_warns < 3:
                    # 严格不重复同一命令:完全相同签名连续调用 → 拦截并提醒换策略
                    dup_warns += 1
                    res = f"[已拦截:你刚调用过完全相同的 {name}(参数一致),结果不会变。请换策略:read_file 看真实情况/换实现方式。]"
                    print(f"[{i}] ⚠️ 重复调用拦截: {name}({dup_warns})", flush=True)
                    messages.append({"role":"tool","content":res})
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
                if name in ("create_file", "edit_file", "append_file", "run_bash"):
                    productive_used = True
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
                    print("\n===== TASK COMPLETE =====", flush=True); print(res, flush=True)
                    save_session(session, messages)
                    return messages
                # 重复失败检测:同工具连续失败(只有同工具成功才清零)→ 强制换策略/禁用
                if _is_tool_error(res):
                    fail_count[name] = fail_count.get(name, 0) + 1
                    if fail_count[name] >= 3:
                        if name == "edit_file":
                            # edit_file 是小模型最易卡死的工具:连续 3 次失败直接禁用,强推 create_file
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
