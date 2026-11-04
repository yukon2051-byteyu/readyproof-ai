"""PDF / Word / Excel / テキスト / 貼り付け文 の読込。PowerPoint は pptx.py。"""
from __future__ import annotations

import io

from .common import (IngestError, IngestResult, check_zip_safety, decode_text, looks_garbled,
                     make_segment, split_paragraphs)


# ---------------- PDF ----------------
def _pdf_paragraphs(text: str, max_len: int = 300) -> list[str]:
    """PDF の抽出文は行ごとに改行されるため、文末（。）・空行・長さで段落にまとめる。"""
    out, buf = [], []
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s:
            if buf:
                out.append("".join(buf))
                buf = []
            continue
        buf.append(s)
        if s.endswith(("。", "．", ".")) or sum(len(b) for b in buf) > max_len:
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return out


def read_pdf(data: bytes, limits) -> IngestResult:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    res = IngestResult("pdf")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                pass
            if reader.is_encrypted:
                raise IngestError("パスワード付きPDFは読み込めません。保護を解除したPDFを登録してください。")
        pages = reader.pages
        total = len(pages)
    except PdfReadError as e:
        raise IngestError("PDFを開けませんでした（ファイル破損の可能性）。") from e

    max_pages = min(total, limits.max_pdf_pages)
    skipped, empty_pages, n, chars = [], [], 0, 0
    for i in range(max_pages):
        page_no = i + 1  # ファイル上のページ番号（印刷ページ番号ではない）
        try:
            text = pages[i].extract_text() or ""
        except Exception:
            res.add_warning("page_error", "このページの文字を抽出できませんでした。", f"{page_no}ページ")
            skipped.append(f"{page_no}ページ（抽出失敗）")
            continue
        if not text.strip():
            empty_pages.append(page_no)
            continue
        if looks_garbled(text):
            res.add_warning("garbled", "文字化けの疑いがあります。原本と照合してください。", f"{page_no}ページ")
        for j, para in enumerate(_pdf_paragraphs(text), start=1):
            if chars + len(para) > limits.max_chars_per_source:
                skipped.append(f"{page_no}ページ以降（文字数上限）")
                res.add_warning("truncated", f"文字数上限（{limits.max_chars_per_source:,}字）に達したため以降は未読込です。",
                                f"{page_no}ページ")
                break
            n += 1
            chars += len(para)
            res.segments.append(make_segment(n, {"type": "pdf", "page": page_no, "para": j},
                                             f"{page_no}ページ 第{j}段落", "本文", para, group=f"{page_no}ページ"))
        else:
            continue
        break
    if empty_pages:
        res.add_warning("no_text_pages", "文字情報がないページがあります（画像のみの可能性。OCR非対応）。",
                        "、".join(f"{p}" for p in empty_pages[:30]) + "ページ")
        skipped.extend(f"{p}ページ（文字なし）" for p in empty_pages)
    if total > max_pages:
        skipped.append(f"{max_pages + 1}〜{total}ページ（ページ数上限）")
        res.add_warning("truncated", f"ページ数上限（{limits.max_pdf_pages}）を超えた部分は未読込です。")
    res.coverage = {"unit": "ページ", "total": total, "read": max_pages - len(empty_pages), "skipped": skipped,
                    "notes": "表はテキストとして抽出されるため、列の対応が崩れることがあります。画像内の文字は対象外です。"}
    if any(seg["text"].count("  ") > 5 for seg in res.segments):
        res.add_warning("table_layout", "表の列が崩れている可能性があります。原本の表と照合してください。")
    return res.finalize()


# ---------------- Word ----------------
def read_docx(data: bytes, limits) -> IngestResult:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    res = IngestResult("docx")
    for w in check_zip_safety(data, limits.max_unzipped_mb):
        res.warnings.append(w)
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as e:
        raise IngestError("Word文書を開けませんでした（.docx 形式か確認してください）。") from e

    n, chars, para_no, table_no = 0, 0, 0, 0
    heading = "（見出しなし）"
    skipped = []
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            text = p.text.strip()
            if not text:
                continue
            para_no += 1
            style = (p.style.name if p.style is not None else "") or ""
            if style.lower().startswith("heading") or style.startswith("見出し") or style == "Title":
                heading = text
                kind = "見出し"
            else:
                kind = "本文"
            if chars + len(text) > limits.max_chars_per_source:
                skipped.append(f"段落{para_no}以降（文字数上限）")
                break
            n += 1
            chars += len(text)
            res.segments.append(make_segment(
                n, {"type": "docx", "heading": heading, "para": para_no},
                f"見出し「{heading[:30]}」 段落{para_no}", kind, text, group=heading))
        elif tag == "tbl":
            table_no += 1
            t = Table(child, document)
            for r_idx, row in enumerate(t.rows, start=1):
                cells = []
                for c in row.cells:
                    ct = c.text.strip()
                    if ct and (not cells or cells[-1] != ct):  # 結合セルの重複を除く
                        cells.append(ct)
                if not cells:
                    continue
                text = " | ".join(cells)
                n += 1
                chars += len(text)
                res.segments.append(make_segment(
                    n, {"type": "docx", "heading": heading, "table": table_no, "row": r_idx},
                    f"見出し「{heading[:30]}」 表{table_no} {r_idx}行目", "表", text, group=heading))
    res.coverage = {"unit": "段落", "total": para_no, "read": para_no, "skipped": skipped,
                    "notes": "ヘッダー・フッター・テキストボックス・脚注・コメント・画像は抽出対象外です。"}
    return res.finalize()


# ---------------- Excel ----------------
def _col_letter(idx: int) -> str:
    s = ""
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


def read_xlsx(data: bytes, limits) -> IngestResult:
    import openpyxl

    res = IngestResult("xlsx")
    for w in check_zip_safety(data, limits.max_unzipped_mb):
        res.warnings.append(w)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        raise IngestError("Excelブックを開けませんでした（.xlsx 形式か確認してください）。") from e

    n, chars, skipped, total_rows = 0, 0, [], 0
    for ws in wb.worksheets:
        hidden = ws.sheet_state != "visible"
        header = None
        rows_read = 0
        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            total_rows += 1
            vals = [("" if v is None else str(v).strip()) for v in row]
            if not any(vals):
                continue
            if rows_read >= limits.max_xlsx_rows_per_sheet:
                skipped.append(f"シート「{ws.title}」{r_idx}行目以降（行数上限）")
                break
            rows_read += 1
            last = max(i for i, v in enumerate(vals) if v) + 1
            first = min(i for i, v in enumerate(vals) if v) + 1
            if header is None:
                header = vals
                text = " | ".join(v for v in vals if v)
                kind = "見出し行"
            else:
                pairs = []
                for i, v in enumerate(vals):
                    if not v:
                        continue
                    h = header[i] if i < len(header) and header[i] else _col_letter(i + 1) + "列"
                    pairs.append(f"{h}: {v}")
                text = " | ".join(pairs)
                kind = "行"
            if chars + len(text) > limits.max_chars_per_source:
                skipped.append(f"シート「{ws.title}」{r_idx}行目以降（文字数上限）")
                break
            n += 1
            chars += len(text)
            rng = f"{_col_letter(first)}{r_idx}:{_col_letter(last)}{r_idx}"
            res.segments.append(make_segment(
                n, {"type": "xlsx", "sheet": ws.title, "row": r_idx, "range": rng},
                f"シート「{ws.title}」 {rng}", kind, text, selected=not hidden, group=ws.title,
                hidden=hidden))
        if hidden:
            res.add_warning("hidden_sheet", "非表示シートです。初期状態では分析対象外にしています。", f"シート「{ws.title}」")
    wb.close()
    res.coverage = {"unit": "行", "total": total_rows, "read": n, "skipped": skipped,
                    "notes": "数式は保存済みの計算結果を読みます。図形・グラフ・コメント・画像は対象外です。結合セルは崩れることがあります。"}
    return res.finalize()


# ---------------- テキスト・貼り付け ----------------
def read_txt(data: bytes, limits) -> IngestResult:
    res = IngestResult("txt")
    text, enc, warns = decode_text(data)
    res.warnings.extend(warns)
    if looks_garbled(text):
        res.add_warning("garbled", "文字化けの疑いがあります。文字コード（UTF-8 / Shift_JIS）を確認してください。")
    lines = text.replace("\r\n", "\n").split("\n")
    n, chars, skipped = 0, 0, []
    block, start = [], None
    for i, line in enumerate(lines + [""], start=1):
        if line.strip():
            if start is None:
                start = i
            block.append(line.rstrip())
            continue
        if block:
            para = "\n".join(block)
            if chars + len(para) > limits.max_chars_per_source:
                skipped.append(f"{start}行目以降（文字数上限）")
                break
            n += 1
            chars += len(para)
            end = i - 1
            label = f"{start}行目" if start == end else f"{start}〜{end}行目"
            res.segments.append(make_segment(n, {"type": "txt", "line_start": start, "line_end": end},
                                             label, "本文", para, group=""))
            block, start = [], None
    res.coverage = {"unit": "行", "total": len(lines), "read": len(lines), "skipped": skipped,
                    "notes": f"文字コード：{enc}"}
    return res.finalize()


def read_pasted(text: str, limits) -> IngestResult:
    res = IngestResult("paste")
    if looks_garbled(text):
        res.add_warning("garbled", "文字化けの疑いがあります。")
    n, chars, skipped = 0, 0, []
    paras = split_paragraphs(text)
    for j, para in enumerate(paras, start=1):
        if chars + len(para) > limits.max_chars_per_source:
            skipped.append(f"第{j}段落以降（文字数上限）")
            break
        n += 1
        chars += len(para)
        res.segments.append(make_segment(n, {"type": "paste", "para": j}, f"貼り付け 第{j}段落", "本文", para))
    res.coverage = {"unit": "段落", "total": len(paras), "read": n, "skipped": skipped, "notes": ""}
    return res.finalize()
