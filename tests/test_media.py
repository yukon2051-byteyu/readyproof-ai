"""録画・文字起こし（必須検証：音声なし・破損・形式、時刻と話者の保持、原文と修正）。"""
import io
import os
import wave

import pytest

from conftest import read
from readyproof.logic.recordings import (apply_speaker_map, build_utterances, edit_utterance_text,
                                         find_reusable_transcript, suggest_type)
from readyproof.media.probe import MediaError, extract_audio_wav, probe_media
from readyproof.media.subtitles import fmt_ts, parse_transcript


def test_probe_demo_video(limits):
    info = probe_media(read("demo3_sales_meeting.mp4"), "m.mp4", limits)
    assert info["audio_streams"][0]["codec"] == "aac" and 39 < info["duration_sec"] < 42


def test_extract_range(limits):
    wav = extract_audio_wav(read("demo3_sales_meeting.mp4"), "m.mp4", 5, 15)
    with wave.open(io.BytesIO(wav)) as w:
        sec = w.getnframes() / w.getframerate()
        assert w.getframerate() == 16000 and w.getnchannels() == 1
    assert 9.5 < sec < 10.8  # 指定範囲だけを取り出す（フレーム境界の誤差あり）


def _video_only_mp4() -> bytes:
    import av
    import numpy as np

    buf = io.BytesIO()
    c = av.open(buf, mode="w", format="mp4")
    s = c.add_stream("mpeg4", rate=2)
    s.width, s.height, s.pix_fmt = 64, 64, "yuv420p"
    for i in range(4):
        f = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
        f.pts = i
        for pk in s.encode(f):
            c.mux(pk)
    for pk in s.encode():
        c.mux(pk)
    c.close()
    return buf.getvalue()


def test_no_audio_track(limits):
    with pytest.raises(MediaError) as e:
        probe_media(_video_only_mp4(), "v.mp4", limits)
    assert "音声トラックがありません" in str(e.value) and "代替方法" in str(e.value)


def test_corrupted_and_unsupported(limits):
    with pytest.raises(MediaError) as e:
        probe_media(os.urandom(5000), "x.mp4", limits)
    assert "代替方法" in str(e.value)
    with pytest.raises(MediaError):
        probe_media(b"abc", "x.avi", limits)
    limits.max_media_mb = 0
    with pytest.raises(MediaError):
        probe_media(read("demo3_sales_meeting.mp4"), "m.mp4", limits)


def test_vtt_with_speakers():
    cues, kind = parse_transcript("a.vtt", read("demo3_sales_meeting.vtt").decode("utf-8"))
    assert kind == "VTT" and len(cues) == 7
    assert cues[1]["speaker_label"] == "話者2" and cues[1]["start"] == pytest.approx(6.31, abs=0.01)


def test_srt_and_text_without_time_not_fabricated():
    srt = "1\n00:00:01,000 --> 00:00:03,500\n鈴木: こんにちは\n\n2\n00:00:04,000 --> 00:00:05,000\nよろしく\n"
    cues, kind = parse_transcript("a.srt", srt)
    assert kind == "SRT" and cues[0]["speaker_label"] == "鈴木" and cues[1]["speaker_label"] is None
    cues, kind = parse_transcript("a.txt", "山田: 時刻なしの発言\n[00:01:05] 鈴木: 時刻ありの発言")
    assert cues[0]["start"] is None and cues[0]["end"] is None  # 時刻を作らない
    assert cues[1]["start"] == 65 and fmt_ts(None) == "時刻なし"
    cues, _ = parse_transcript("a.txt", "10:00に開始します")
    assert cues[0]["start"] is None  # 文中の時刻を発言時刻と誤認しない


def test_original_kept_and_history():
    utts = build_utterances([{"start": 1.0, "end": 2.0, "speaker_label": "話者A", "text": "指定費の停止ができます"}])
    u = utts[0]
    u["review_status"] = "確認済み"
    edit_utterance_text(u, "指定日の停止ができます", "確認者")
    assert u["raw_text"] == "指定費の停止ができます" and u["edited_text"] == "指定日の停止ができます"
    assert u["history"][0]["from"] == "指定費の停止ができます" and u["review_status"] == "未確認"


def test_speaker_not_decided_automatically():
    rec = {"utterances": build_utterances([{"start": 0, "end": 1, "speaker_label": "話者A", "text": "はい"},
                                           {"start": 1, "end": 2, "speaker_label": "話者B", "text": "いいえ"}])}
    assert all(u["speaker_role"] == "未分類" and not u["speaker_confirmed"] for u in rec["utterances"])
    assert apply_speaker_map(rec, "話者A", "営業担当者", "鈴木", True, "x") == 1
    assert rec["utterances"][1]["speaker_role"] == "未分類"


@pytest.mark.parametrize("text,expected", [
    ("標準プランで、指定日のアカウント停止ができますか？", "質問"),
    ("操作履歴の保存期間は、確認して回答します。", "未回答・調査中"),
    ("来年度には標準プランでも対応する予定です。", "将来予定"),
    ("おそらくCSVで対応できると思います。", "推測・未確定"),
    ("オフラインでの入力はできません。", "回答（不可）"),
    ("予約停止は上位プランで対応しています。", "回答（条件付き）"),
])
def test_utterance_type_suggestions(text, expected):
    assert suggest_type(text) == expected


def test_reuse_existing_transcript():
    p = {"recordings": [{"file_sha256": "abc", "range": {"start": 0.0, "end": 60.0}, "utterances": [{"id": "U001"}]}]}
    assert find_reusable_transcript(p, "abc", 0.0, 60.0)
    assert find_reusable_transcript(p, "abc", 0.0, 30.0) is None


@pytest.mark.skipif(os.environ.get("RP_RUN_SLOW") != "1", reason="ローカル文字起こしは RP_RUN_SLOW=1 のときだけ実行")
def test_local_whisper_real_audio():
    from readyproof.media.transcribe import transcribe_local

    wav = extract_audio_wav(read("demo3_sales_meeting.mp4"), "m.mp4")
    segs = transcribe_local(wav, os.environ.get("RP_WHISPER_MODEL", "small"))
    text = "".join(s["text"] for s in segs)
    assert "上位プラン" in text and all(s["start"] is not None for s in segs)
    assert all(s["speaker_label"] is None for s in segs)  # 話者は自動で決めない
