---
name: image_batch
description: 图片批处理:批量改名/缩放/转格式/拼图(内置 PIL)
---
# 图片批处理
先 enable_tools 代码类拿到 run_python(内置解释器带 PIL,无需用户装 Python)。

1. 盘点:run_python 列出图片清单(名称/尺寸/大小):
```python
from PIL import Image
import os
fs = [f for f in os.listdir(".") if f.lower().endswith((".jpg",".jpeg",".png",".webp",".bmp"))]
for f in fs[:50]:
    with Image.open(f) as im: print(f, im.size, os.path.getsize(f)//1024, "KB")
print("total", len(fs))
```
2. 批量缩放(保持比例,长边限 1280 为例):先建 out/ 目录,输出一律写 out/,不动原图:
```python
from PIL import Image
import os
os.makedirs("out", exist_ok=True)
for f in fs:
    with Image.open(f) as im:
        im.thumbnail((1280, 1280))
        im.convert("RGB").save(os.path.join("out", os.path.splitext(f)[0] + ".jpg"), quality=88)
print("done", len(fs))
```
3. 批量重命名:统一规则(序号/日期/前缀),先打印 旧名→新名 清单,用户确认后再 os.rename。
4. 拼接长图/网格:新建画布 Image.new("RGB", (W, H)) 逐张 paste。
5. 交付:finish 报处理张数、输出目录、失败清单及原因。
红线:绝不覆盖原图(输出进 out/);重命名/删除需用户确认;一次处理超过 500 张分批报进度。
