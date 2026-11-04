"""資料読込の共通処理。

読込結果（IngestResult）は「抽出した箇所（segments）」「警告」「読めた範囲」を持つ。
取得できない位置情報は作らない。読めなかった部分は coverage.skipped に必ず残す。
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field


class IngestError(Exception):
    """利用者に表示できる読込エラー。"""


@dataclass
class IngestResult:
    file_type: str
    segments: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    status: str = "ok"  # ok / partial / empty / failed

    def add_warning(self, code: str, message: str, where: str = "") -> None:
        self.warnings.append({"code": code, "message": message, "where": where})

    def finalize(self) -> "IngestResult":
        if not self.segments:
            self.status = "empty" if self.status != "failed" else "failed"
            if self.status == "empty":
                self.add_warning("empty", "文字情報を抽出できませんでした。画像のみの資料はOCR非対応です。")
        elif self.coverage.get("skipped"):
            self.status = "partial"
        return self

    def to_dict(self) -> dict:
        return {"file_type": self.file_type, "segments": self.segments, "warnings": self.warnings,
                "coverage": self.coverage, "status": self.status}


def make_segment(n: int, loc: dict, loc_label: str, kind: str, text: str,
                 selected: bool = True, group: str = "", **extra) -> dict:
    seg = {
        "seg_id": f"S{n:04d}",
        "loc": loc,
        "loc_label": loc_label,
        "kind": kind,
        "text": text,
        "selected": selected,
        "group": group,
    }
    seg.update(extra)
    return seg


_MOJIBAKE_PATTERNS = re.compile(r"(Ã.|â€|ç¤¾|ã‚|ã€|ï¼|�)")


def looks_garbled(text: str) -> bool:
    """文字化けの疑い（UTF-8 を別の文字コードで読んだ時の典型パターン等）。"""
    if not text:
        return False
    hits = len(_MOJIBAKE_PATTERNS.findall(text))
    private = sum(1 for ch in text if 0xE000 <= ord(ch) <= 0xF8FF)
    ctrl = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
    return hits >= 3 or (private + ctrl) > max(5, len(text) * 0.02)


def decode_text(data: bytes) -> tuple[str, str, list]:
    """テキストの文字コード判定。戻り値：(文字列, 使った文字コード, 警告)"""
    warnings = []
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16"), "utf-16", warnings
    for enc in ("utf-8-sig", "cp932"):
        try:
            return data.decode(enc), enc, warnings
        except UnicodeDecodeError:
            continue
    warnings.append({"code": "encoding", "message": "文字コードを判定できず、一部の文字を置き換えて読み込みました。",
                     "where": ""})
    return data.decode("utf-8", errors="replace"), "utf-8(置換あり)", warnings


def check_zip_safety(data: bytes, max_unzipped_mb: int) -> list:
    """Office 形式（ZIP）を開く前に、展開後サイズ・マクロ・埋込・外部リンクを確認する。

    マクロや埋込ファイルは実行・展開しない。警告として返すだけ。
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise IngestError("ファイルが壊れているか、Office の新形式ではありません。") from e
    total = sum(i.file_size for i in zf.infolist())
    if total > max_unzipped_mb * 1024 * 1024:
        raise IngestError(
            f"展開後のサイズが上限（{max_unzipped_mb}MB）を超えるため読み込みませんでした。資料を分割してください。")
    warnings = []
    names = [i.filename.lower() for i in zf.infolist()]
    if any("vbaproject.bin" in n for n in names):
        warnings.append({"code": "macro", "message": "マクロを含みます。マクロは実行していません。", "where": ""})
    if any("/embeddings/" in n for n in names):
        warnings.append({"code": "embedded", "message": "埋め込みファイルを含みます。埋め込み内容は読み込んでいません。",
                         "where": ""})
    if any("externallink" in n for n in names):
        warnings.append({"code": "external_link", "message": "外部リンクを含みます。リンク先は参照していません。",
                         "where": ""})
    return warnings


LEGACY_FORMATS = {
    ".doc": "Word の旧形式（.doc）は読み込めません。Word で開き「名前を付けて保存」→「Word 文書（.docx）」または PDF に変換してください。",
    ".xls": "Excel の旧形式（.xls）は読み込めません。Excel で開き「Excel ブック（.xlsx）」で保存し直してください。",
    ".ppt": "PowerPoint の旧形式（.ppt）は読み込めません。PowerPoint で開き「PowerPoint プレゼンテーション（.pptx）」または PDF で保存してください。",
}

SUPPORTED = {".pdf", ".docx", ".xlsx", ".pptx", ".txt"}


def split_paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    return [p.strip() for p in parts if p.strip()]
