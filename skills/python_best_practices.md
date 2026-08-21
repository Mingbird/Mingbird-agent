---
name: python_best_practices
description: Python 规范:类型注解/pathlib/异常/风格
---
# Python 编码规范
1. 类型注解:def f(x: int) -> str
2. 用 pathlib.Path 处理路径,不用字符串拼接
3. 捕获具体异常,避免裸 except
4. 命名 snake_case,清晰表达意图
5. 用 with 管理文件/资源
6. 完成后 python -m py_compile 验证语法
