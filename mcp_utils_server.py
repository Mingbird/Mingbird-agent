# -*- coding: utf-8 -*-
"""本地工具 MCP server:当前时间 / 安全计算 / SHA256 哈希
给小模型提供无法自知的确定性信息与可信计算。
参数名在 schema 中声明了多个别名(小模型常猜错参数名),任意一个都能用。
运行: python mcp_utils_server.py
"""
import datetime, hashlib, re
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local_utils")

@mcp.tool()
def current_time() -> str:
    """返回当前本地日期与时间(精确到秒)。模型无法自行得知,必须调用此工具。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f" (weekday {datetime.datetime.now().strftime('%A')})"

@mcp.tool()
def calculate(expression: str = "", expr: str = "") -> str:
    """安全计算一个数学表达式(支持 + - * / () **)。参数名可用 expression 或 expr。"""
    s = (expression or expr or "").strip().replace(" ", "")
    if not s:
        return "error: 缺少表达式参数"
    if not re.fullmatch(r"[0-9+\-*/().**]+", s):
        return "error: 表达式含非法字符"
    try:
        return str(eval(s, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"error: {e}"

@mcp.tool()
def sha256(text: str = "", input: str = "", data: str = "") -> str:
    """返回字符串的 SHA256 十六进制哈希。参数名可用 text 或 input 或 data。"""
    t = (text or input or data or "").strip()
    if not t:
        return "error: 缺少待哈希文本"
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

if __name__ == "__main__":
    mcp.run()
