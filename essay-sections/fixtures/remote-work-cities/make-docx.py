#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""由 v1.md 现造一份 v1.docx，用来演示 Word 稿导入时「未纳入分段」长什么样。

只用标准库的 zipfile 拼一个最小但合法的 .docx：一个标题、八个正文段落，外加一张
两行两列的小表。表格里的字**不会**参与分段——脚本把它渲到正文之后的附录区，
再逐条列进 `split-report.md` 的「未纳入分段」。文本框同理（这里没造，行为一样）。

用法：`python3 make-docx.py`（在本目录下跑，产物覆盖同目录的 v1.docx）。
稿件全部是合成的，跟任何真实文档无关。
"""

import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "v1.md")
OUT = os.path.join(HERE, "v1.docx")

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = ("http://schemas.openxmlformats.org/officeDocument/2006/"
           "relationships/officeDocument")

# 作者贴在稿子旁边的一张小表：只是自己算账用的草稿，不属于任何一段正文
TABLE = [["一次性支出", "摊到十二个月"],
         ["押金 + 中介 + 搬家", "把「便宜一半」拉回到「便宜三成」"]]


def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def para(text, style=None):
    pr = '<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % style if style else ""
    return "<w:p>%s<w:r><w:t xml:space=\"preserve\">%s</w:t></w:r></w:p>" % (pr, esc(text))


def cell(text):
    return ("<w:tc><w:tcPr><w:tcW w:w=\"4400\" w:type=\"dxa\"/></w:tcPr>%s</w:tc>"
            % para(text))


def table(rows):
    body = "".join("<w:tr>%s</w:tr>" % "".join(cell(c) for c in row) for row in rows)
    return ("<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/></w:tblPr>"
            "<w:tblGrid><w:gridCol w:w=\"4400\"/><w:gridCol w:w=\"4400\"/></w:tblGrid>"
            "%s</w:tbl>" % body)


def blocks_of(markdown):
    """按空行切段；开头的 `# ` 标题单独拎出来。"""
    chunks = [c.strip() for c in re.split(r"\n[ \t]*\n", markdown) if c.strip()]
    head = chunks[0].lstrip("# ").strip() if chunks and chunks[0].startswith("#") else ""
    body = chunks[1:] if head else chunks
    return head, body


def main():
    with open(SRC, "r", encoding="utf-8") as f:
        head, body = blocks_of(f.read())

    parts = [para(head, style="Heading1")]
    parts += [para(text) for text in body]
    parts.append(table(TABLE))
    parts.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>')

    document = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
                "<w:document xmlns:w=\"%s\"><w:body>%s</w:body></w:document>"
                % (W, "".join(parts)))
    types = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
             "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
             "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-"
             "package.relationships+xml\"/>"
             "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
             "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd."
             "openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
             "</Types>")
    rels = ("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n"
            "<Relationships xmlns=\"%s\"><Relationship Id=\"rId1\" Type=\"%s\" "
            "Target=\"word/document.xml\"/></Relationships>" % (PKG_REL, DOC_REL))

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as pack:
        pack.writestr("[Content_Types].xml", types)
        pack.writestr("_rels/.rels", rels)
        pack.writestr("word/document.xml", document)
    print("已写出 %s（%d 段正文 + 1 张表）" % (os.path.basename(OUT), len(body)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
