---
name: office_word
description: Word 文档:生成/读取 .docx(内置解释器,无需装 Office)
---
# Word 文档处理
先 enable_tools 代码类拿到 run_python(内置解释器,无需用户装 Python/Office)。

## 生成 .docx(run_python 抄这个骨架改内容)
```python
import zipfile
CT = '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''
RELS = '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def para(text, bold=False, size=24):   # size=半磅,24=小四附近
    rpr = f'<w:rPr><w:b/><w:sz w:val="{size}"/></w:rPr>' if bold else f'<w:rPr><w:sz w:val="{size}"/></w:rPr>'
    return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>'
body = "".join(para(t) for t in ["第一段正文", "第二段正文"])   # 标题用 para(t, bold=True, size=32)
DOC = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}</w:body></w:document>'
with zipfile.ZipFile("输出.docx", "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS); z.writestr("word/document.xml", DOC)
print("written")
```
## 读取 .docx
```python
import zipfile, re, html
with zipfile.ZipFile("输入.docx") as z:
    xml = z.read("word/document.xml").decode("utf-8")
text = "\n".join(html.unescape(re.sub(r"<[^>]+>", "", p)) for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S))
print(text)
```
要点:长文档分次写段落列表;中文内容直接放 para() 列表;生成后 read_file 无法读 docx,用上面的读取片段自验一遍再交付。
