"""資料の読込と参照位置（必須検証：対応形式・位置追跡・PowerPoint の表/グループ/ノート・画像未理解・異常系）。"""
import io
import zipfile

import pytest

from conftest import read
from readyproof.ingest import IngestError, ingest_bytes, ingest_text


def test_pptx_slides_tables_groups_notes(limits):
    r = ingest_bytes("d.pptx", read("demo1_keihinavi_proposal.pptx"), limits)
    segs = r.segments
    # 表は行単位で、スライド番号・図形番号・行番号を持つ
    row = next(s for s in segs if "10,000円以上" in s["text"])
    assert row["loc"]["slide"] == 2 and row["loc"]["row"] == 3 and row["kind"] == "表"
    assert "金額条件: 10,000円以上" in row["text"]  # 見出しと値の対応を保つ
    # グループ内の図形も再帰的に抽出
    grp = [s for s in segs if s["loc"].get("in_group")]
    assert len(grp) == 2 and all(s["loc"]["slide"] == 3 for s in grp)
    # ノートは抽出するが初期状態で対象外・未確認
    notes = [s for s in segs if s.get("is_note")]
    assert len(notes) == 2 and not any(n["selected"] for n in notes) and not any(n["note_reviewed"] for n in notes)
    assert notes[0]["kind"] == "ノート"
    # 非表示スライドは判別して対象外
    hidden = [s for s in segs if s.get("hidden_slide")]
    assert hidden and not any(s["selected"] for s in hidden)
    # 画像は「理解していない」警告
    assert any(w["code"] == "not_understood" and "画像" in w["message"] for w in r.warnings)
    info = {x["slide"]: x for x in r.coverage["slides"]}
    assert info[5]["hidden"] and info[3]["unknown"] == {"画像": 1}


def test_pdf_page_numbers(limits):
    r = ingest_bytes("a.pdf", read("demo2_tsukurun_overview.pdf"), limits)
    seg = next(s for s in r.segments if "マルチロット投入" in s["text"])
    assert seg["loc"]["page"] == 2 and seg["loc_label"].startswith("2ページ")
    assert r.status == "ok"


def test_xlsx_sheet_row_range_and_hidden_sheet(limits):
    r = ingest_bytes("a.xlsx", read("demo2_feature_list.xlsx"), limits)
    seg = next(s for s in r.segments if "マルチロット投入" in s["text"])
    assert seg["loc"]["sheet"] == "機能一覧" and seg["loc"]["range"] == "A6:F6"
    assert "標準/オプション: オプション" in seg["text"]
    hidden = [s for s in r.segments if s.get("hidden")]
    assert hidden and not hidden[0]["selected"]
    assert any(w["code"] == "hidden_sheet" for w in r.warnings)


def test_docx_heading_paragraph_and_table(limits):
    r = ingest_bytes("a.docx", read("demo3_idguard_overview.docx"), limits)
    seg = next(s for s in r.segments if "予約停止" in s["text"])
    assert seg["loc"]["heading"] == "アカウント管理" and isinstance(seg["loc"]["para"], int)
    tbl = [s for s in r.segments if s["kind"] == "表"]
    assert tbl and tbl[0]["loc"]["table"] == 1


def test_txt_line_numbers_and_cp932(limits):
    data = "一行目\n\n三行目の文章\n四行目".encode("cp932")
    r = ingest_bytes("a.txt", data, limits)
    assert r.segments[1]["loc"] == {"type": "txt", "line_start": 3, "line_end": 4}
    assert r.coverage["notes"] == "文字コード：cp932"


def test_paste_paragraphs(limits):
    r = ingest_text("第一段落\n\n第二段落です", limits)
    assert [s["loc"]["para"] for s in r.segments] == [1, 2]
    with pytest.raises(IngestError):
        ingest_text("   ", limits)


@pytest.mark.parametrize("ext", [".doc", ".xls", ".ppt"])
def test_legacy_formats_guided(limits, ext):
    with pytest.raises(IngestError) as e:
        ingest_bytes("old" + ext, b"\xd0\xcf\x11\xe0" + b"0" * 100, limits)
    assert "変換" in str(e.value) or "保存" in str(e.value)


def test_broken_and_mismatched_files(limits):
    with pytest.raises(IngestError):
        ingest_bytes("x.pptx", b"PK\x03\x04broken", limits)
    with pytest.raises(IngestError):
        ingest_bytes("x.pdf", b"not a pdf", limits)  # 拡張子と中身が不一致
    with pytest.raises(IngestError):
        ingest_bytes("x.docx", b"", limits)
    with pytest.raises(IngestError):
        ingest_bytes("x.exe", b"MZ", limits)


def test_zip_bomb_limit_and_macro_warning(limits):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("big.bin", b"0" * (3 * 1024 * 1024))
    limits.max_unzipped_mb = 1
    with pytest.raises(IngestError) as e:
        ingest_bytes("x.docx", buf.getvalue(), limits)
    assert "展開後" in str(e.value)
    # マクロ・埋め込み・外部リンクは実行せず警告
    from readyproof.ingest.common import check_zip_safety

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/vbaProject.bin", b"x")
        z.writestr("word/embeddings/a.bin", b"x")
        z.writestr("xl/externalLinks/link1.xml", b"x")
    codes = {w["code"] for w in check_zip_safety(buf.getvalue(), 10)}
    assert codes == {"macro", "embedded", "external_link"}


def test_garbled_pdf_detected(limits, tmp_path):
    """フォントに文字対応表がない PDF は抽出結果が化ける → 警告を出し、黙って分析済みにしない。"""
    from readyproof.ingest.common import looks_garbled

    assert looks_garbled("���i���b�g�ԍ�����g�p")
    assert not looks_garbled("製品ロット番号から検索できます。")


def test_image_only_pdf_reported(limits):
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(200, 200)
    buf = io.BytesIO()
    w.write(buf)
    r = ingest_bytes("blank.pdf", buf.getvalue(), limits)
    assert r.status == "empty"
    assert "1ページ（文字なし）" in r.coverage["skipped"]
    assert any("OCR" in w["message"] for w in r.warnings)


def test_char_limit_not_silently_dropped(limits):
    limits.max_chars_per_source = 30
    r = ingest_text("あ" * 20 + "\n\n" + "い" * 20 + "\n\n" + "う" * 5, limits)
    assert r.status == "partial" and r.coverage["skipped"]


def test_slide_limit_reported(limits):
    limits.max_slides = 2
    r = ingest_bytes("d.pptx", read("demo1_keihinavi_proposal.pptx"), limits)
    assert any("スライド3〜7" in s for s in r.coverage["skipped"])
    assert max(s["loc"]["slide"] for s in r.segments) == 2
