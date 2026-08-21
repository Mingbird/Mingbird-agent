# -*- coding: utf-8 -*-
"""测量当前 agent 的前置 token 开销(system prompt + 工具 schema)。"""
import json, urllib.request, sys
sys.path.insert(0, ".")
import ollama_agent as A

def tokens(text):
    # 用 ollama tokenize? 直接发一次 api/chat num_predict=1 读 usage.prompt_tokens
    payload = {"model":"gemma4:e4b",
               "messages":[{"role":"system","content":A.SYSTEM},
                           {"role":"user","content":"hi"}],
               "tools":A.active_tool_defs(),
               "stream":False,"options":{"num_ctx":2048,"num_predict":1}}
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    return r["usage"]["prompt_tokens"]

# 分开测:system 单独,工具单独
import copy
sys_only = copy.deepcopy({"model":"gemma4:e4b",
    "messages":[{"role":"system","content":A.SYSTEM},{"role":"user","content":"hi"}],
    "tools":[],"stream":False,"options":{"num_ctx":2048,"num_predict":1}})
req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
    data=json.dumps(sys_only).encode(), headers={"Content-Type":"application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=300).read())
sys_tok = r["usage"]["prompt_tokens"] - 2  # minus "hi"/user tokens roughly

# 工具部分:system+user 短,加工具
tools_only = copy.deepcopy({"model":"gemma4:e4b",
    "messages":[{"role":"system","content":"x"},{"role":"user","content":"hi"}],
    "tools":A.active_tool_defs(),"stream":False,"options":{"num_ctx":2048,"num_predict":1}})
req = urllib.request.Request("http://127.0.0.1:11434/api/chat",
    data=json.dumps(tools_only).encode(), headers={"Content-Type":"application/json"})
r = json.loads(urllib.request.urlopen(req, timeout=300).read())
tools_tok = r["usage"]["prompt_tokens"] - 2 - 2  # "x" system + "hi" user

print(f"SYSTEM prompt        : {sys_tok} tokens")
print(f"CORE tools schema    : {tools_tok} tokens")
print(f"总前置开销            : {sys_tok + tools_tok} tokens")
print(f"core 工具数           : {len(A.CORE_TOOLS)}")
