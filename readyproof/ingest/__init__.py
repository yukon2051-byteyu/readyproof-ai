"""資料読込の入口。拡張子で振り分けるが、中身も検証する（壊れたファイルは IngestError）。"""
from __future__ import annotations

import os

from .common import LEGACY_FORMATS, SUPPORTED, IngestError, IngestResult
from .formats import read_docx, read_pasted, read_pdf, read_txt, read_xlsx
from .pptx import read_pptx

__all__ = ["ingest_bytes", "ingest_text", "IngestError", "IngestResult", "SUPPORTED"]

_READERS = {".pdf": read_pdf, ".docx": read_docx, ".xlsx": read_xlsx, ".pptx": read_pptx, ".txt": read_txt}

_MAGIC = {".pdf": b"%PDF", ".docx": b"PK", ".xlsx": b"PK", ".pptx": b"PK"}


def ingest_bytes(filename: str, data: bytes, limits) -> IngestResult:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in LEGACY_FORMATS:
        raise IngestError(LEGACY_FORMATS[ext])
    if ext not in SUPPORTED:
        raise IngestError(f"この形式（{ext or '拡張子なし'}）には対応していません。対応形式：PDF / .docx / .xlsx / .pptx / .txt")
    if len(data) > limits.max_file_mb * 1024 * 1024:
        raise IngestError(f"ファイルサイズが上限（{limits.max_file_mb}MB）を超えています。")
    if not data:
        raise IngestError("ファイルが空です。")
    magic = _MAGIC.get(ext)
    if magic and not data.startswith(magic):
        raise IngestError("拡張子と中身の形式が一致しません。ファイルが壊れているか、別形式の可能性があります。")
    return _READERS[ext](data, limits)


def ingest_text(text: str, limits) -> IngestResult:
    if not text or not text.strip():
        raise IngestError("貼り付けた文章が空です。")
    return read_pasted(text, limits)
