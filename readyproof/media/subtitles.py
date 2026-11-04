"""会議ツールの文字起こし・SRT・VTT・時刻付き文章の読込。

時刻や話者が書かれていない場合は作らない（None のまま）。
"""
from __future__ import annotations

import re

_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?"
_CUE = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")
_VTT_VOICE = re.compile(r"<v(?:\.[^ >]+)?\s+([^>]+)>(.*?)(?:</v>|$)", re.S)
_LEAD_TS = re.compile(rf"^\s*\[?{_TS}\]?(?:\s+-\s*|\s+|\]\s*)(.*)$")
_SPEAKER = re.compile(r"^([^:：\s][^:：]{0,30})[:：]\s*(.+)$", re.S)
_TAG = re.compile(r"<[^>]+>")


def _sec(h, m, s, ms) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + (int((ms or "0").ljust(3, "0")) / 1000)


def fmt_ts(sec: float | None) -> str:
    if sec is None:
        return "時刻なし"
    sec = int(round(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _split_speaker(text: str):
    m = _VTT_VOICE.search(text)
    if m:
        return m.group(1).strip(), _TAG.sub("", m.group(2)).strip()
    text = _TAG.sub("", text).strip()
    m = _SPEAKER.match(text)
    if m and len(m.group(1)) <= 20:
        return m.group(1).strip(), m.group(2).strip()
    return None, text


def parse_cues(text: str) -> list[dict]:
    """SRT / VTT（Teams・Zoom 等の VTT を含む）を解析する。"""
    lines = text.replace("\r\n", "\n").replace("﻿", "").split("\n")
    cues, i = [], 0
    while i < len(lines):
        m = _CUE.match(lines[i])
        if not m:
            i += 1
            continue
        g = m.groups()
        start, end = _sec(*g[0:4]), _sec(*g[4:8])
        i += 1
        body = []
        while i < len(lines) and lines[i].strip() and not _CUE.match(lines[i]):
            body.append(lines[i])
            i += 1
        speaker, content = _split_speaker("\n".join(body).strip())
        if content:
            cues.append({"start": start, "end": end, "speaker_label": speaker, "text": content})
    return cues


def parse_timestamped_text(text: str) -> list[dict]:
    """「00:01:23 山田: 発言」や「[01:23] 発言」形式の貼り付け文。時刻がない行は時刻なしで扱う。"""
    out = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _LEAD_TS.match(line)
        start = None
        rest = line
        if m and m.group(5) is not None:
            start = _sec(*m.groups()[0:4])
            rest = m.group(5)
        speaker, content = _split_speaker(rest)
        if not content:
            continue
        if start is None and out and out[-1]["start"] is None and speaker is None:
            out[-1]["text"] += "\n" + content  # 時刻も話者もない継続行
            continue
        out.append({"start": start, "end": None, "speaker_label": speaker, "text": content})
    # 次の発言の開始を終了時刻にする（開始時刻がそろっている場合のみ）
    for a, b in zip(out, out[1:]):
        if a["start"] is not None and b["start"] is not None and b["start"] >= a["start"]:
            a["end"] = b["start"]
    return out


def parse_transcript(filename: str, text: str) -> tuple[list[dict], str]:
    name = (filename or "").lower()
    if name.endswith(".vtt") or text.lstrip("﻿").startswith("WEBVTT"):
        return parse_cues(text), "VTT"
    if name.endswith(".srt") or _CUE.search(text.split("\n\n")[0] if text else ""):
        cues = parse_cues(text)
        if cues:
            return cues, "SRT"
    return parse_timestamped_text(text), "時刻付き文章"
