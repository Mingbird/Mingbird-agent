---
name: office_excel
description: 表格处理:CSV/Excel 清洗、统计、汇总(内置 pandas)
---
# 表格处理(Excel/CSV)
先 enable_tools 代码类拿到 run_python(内置解释器带 pandas/numpy,无需用户装 Python)。

1. 看数据:run_python 用 pandas 读前几行摸结构:
```python
import pandas as pd
df = pd.read_csv("数据.csv")            # Excel 用 pd.read_excel("数据.xlsx")
print(df.shape); print(df.head(8).to_string()); print(df.dtypes)
```
2. 常见清洗(按需):去重 df.drop_duplicates();空值 df.dropna() 或填 df.fillna("");列名规范 df.columns=[c.strip() for c in df.columns]。
3. 统计/汇总:describe()、groupby + agg、pivot_table;数字结论必须来自代码输出,不心算。
4. 产出:处理结果存新文件(不要覆盖原文件):
```python
df.to_csv("结果.csv", index=False, encoding="utf-8-sig")   # utf-8-sig=Excel 打开不乱码
df.to_excel("结果.xlsx", index=False)
```
5. 交付:finish 里报行数变化(原始 N 行 → 结果 M 行)、做了什么处理、结果文件名。
注意:大文件(>10 万行)分块处理并报进度;删除行/改值类操作,先报影响行数再执行;编码读错时试 encoding="gbk"。
