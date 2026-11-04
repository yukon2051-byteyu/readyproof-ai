"""PowerPoint（.pptx）読込。

- スライド番号・タイトル・テキストボックス・表（行列）・グループ内図形（再帰）を抽出
- 発表者ノートは抽出するが、初期状態で分析・AI送信の対象外（selected=False）
- 画像・グラフ・SmartArt・図形の位置関係・矢印は「理解していない要素」として警告に残す
"""
from __future__ import annotations

import io

from .common import IngestError, IngestResult, check_zip_safety, make_segment

_SMARTART_URI = "http://schemas.openxmlformats.org/drawingml/2006/diagram"


def _shape_kind_flags(shape) -> str | None:
    """文字抽出だけでは意味を理解できない要素の種類を返す。"""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    try:
        st = shape.shape_type
    except NotImplementedError:
        st = None
    if st == MSO_SHAPE_TYPE.PICTURE:
        return "画像"
    if getattr(shape, "has_chart", False) and shape.has_chart:
        return "グラフ"
    el = shape._element
    if el.tag.endswith("graphicFrame"):
        gd = el.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}graphicData")
        if gd is not None and gd.get("uri") == _SMARTART_URI:
            return "SmartArt"
    if el.tag.endswith("cxnSp"):
        return "矢印・コネクタ"
    if st == MSO_SHAPE_TYPE.MEDIA:
        return "動画・音声"
    return None


def _walk(shapes, path=""):
    """グループ図形を再帰的にたどり、(図形, 階層パス) を返す。"""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    for shape in shapes:
        sid = f"{path}{shape.shape_id}"
        try:
            is_group = shape.shape_type == MSO_SHAPE_TYPE.GROUP
        except NotImplementedError:
            is_group = False
        if is_group:
            yield from _walk(shape.shapes, path=f"{sid}/")
        else:
            yield shape, sid, bool(path)


def read_pptx(data: bytes, limits) -> IngestResult:
    from pptx import Presentation

    res = IngestResult("pptx")
    for w in check_zip_safety(data, limits.max_unzipped_mb):
        res.warnings.append(w)
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as e:
        raise IngestError("PowerPointを開けませんでした（.pptx 形式か確認してください）。") from e

    slides = list(prs.slides)
    total = len(slides)
    max_slides = min(total, limits.max_slides)
    n, chars, skipped = 0, 0, []
    slide_info = []
    for idx in range(max_slides):
        slide = slides[idx]
        no = idx + 1
        hidden = slide._element.get("show") == "0"
        title = ""
        try:
            if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
                title = slide.shapes.title.text_frame.text.strip()
        except Exception:
            title = ""
        title_label = title or "（タイトルなし）"
        unknown = {}
        seg_count = 0
        for shape, sid, in_group in _walk(slide.shapes):
            flag = _shape_kind_flags(shape)
            if flag:
                unknown[flag] = unknown.get(flag, 0) + 1
            base = {"type": "pptx", "slide": no, "slide_title": title_label, "shape_id": sid,
                    "in_group": in_group}
            if getattr(shape, "has_table", False) and shape.has_table:
                # 表は行単位で抽出（行の意味＝条件と結果の対応を保つ）。列番号は cols に保持
                header = None
                for r, row in enumerate(shape.table.rows, start=1):
                    cells = [c.text.strip() for c in row.cells]
                    if not any(cells):
                        continue
                    if header is None:
                        header = cells
                        text = " | ".join(cells)
                    else:
                        text = " | ".join(
                            (f"{header[i]}: {v}" if i < len(header) and header[i] else v)
                            for i, v in enumerate(cells) if v)
                    n += 1
                    seg_count += 1
                    chars += len(text)
                    res.segments.append(make_segment(
                        n, {**base, "part": "表", "row": r, "cols": len(cells)},
                        f"スライド{no}「{title_label[:24]}」 図形{sid} 表{r}行目", "表", text,
                        selected=not hidden, group=f"スライド{no}", hidden_slide=hidden))
                continue
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                text = shape.text_frame.text.strip()
                if not text:
                    continue
                is_title = (title and text == title and getattr(shape, "is_placeholder", False))
                if chars + len(text) > limits.max_chars_per_source:
                    skipped.append(f"スライド{no}以降（文字数上限）")
                    break
                n += 1
                seg_count += 1
                chars += len(text)
                kind = "タイトル" if is_title else "本文"
                label = f"スライド{no}「{title_label[:24]}」 図形{sid}" + ("（グループ内）" if in_group else "")
                res.segments.append(make_segment(
                    n, {**base, "part": kind}, label, kind, text,
                    selected=not hidden, group=f"スライド{no}", hidden_slide=hidden))
        # 発表者ノート：本文だけを取り出す（ノートページのスライド画像や番号のプレースホルダーは除く）
        note_text = ""
        if slide.has_notes_slide:
            tf = slide.notes_slide.notes_text_frame
            note_text = tf.text.strip() if tf is not None else ""
        if note_text:
            n += 1
            res.segments.append(make_segment(
                n, {"type": "pptx", "slide": no, "slide_title": title_label, "part": "ノート"},
                f"スライド{no}「{title_label[:24]}」 発表者ノート", "ノート", note_text,
                selected=False, group=f"スライド{no}", hidden_slide=hidden, is_note=True,
                note_reviewed=False))
        if unknown:
            desc = "、".join(f"{k}{v}件" for k, v in unknown.items())
            res.add_warning("not_understood",
                            f"{desc}を含みます。文字以外の内容（図の意味・位置関係・グラフの値）は理解していません。",
                            f"スライド{no}")
        if hidden:
            res.add_warning("hidden_slide", "非表示スライドです。初期状態では分析対象外です。", f"スライド{no}")
        if seg_count == 0 and not note_text:
            res.add_warning("no_text", "文字情報がないスライドです（画像のみの可能性）。", f"スライド{no}")
        slide_info.append({"slide": no, "title": title_label, "hidden": hidden, "unknown": unknown,
                           "has_note": bool(note_text), "segments": seg_count})
    if total > max_slides:
        skipped.append(f"スライド{max_slides + 1}〜{total}（スライド数上限）")
        res.add_warning("truncated", f"スライド数上限（{limits.max_slides}）を超えた部分は未読込です。")
    res.coverage = {"unit": "スライド", "total": total, "read": max_slides, "skipped": skipped,
                    "slides": slide_info,
                    "notes": "画像内の文字、矢印・図形の位置関係、グラフ、SmartArt、アニメーションは理解していません。"}
    return res.finalize()
