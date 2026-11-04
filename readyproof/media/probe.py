"""録画ファイルの検証と音声抽出（PyAV 使用。外部コマンドは実行しない）。

- 拡張子だけで判断せず、コンテナ・音声トラック・コーデックを実際に開いて確認する
- 一時ファイルはランダム名で作成し、処理後に必ず削除する（利用者のファイル名をパスに使わない）
"""
from __future__ import annotations

import io
import os
import tempfile
import wave
from contextlib import contextmanager

ALLOWED_EXT = {".mp4", ".webm", ".mov", ".m4a", ".mp3", ".wav"}
# 文字起こしに回せる音声コーデック（PyAV/FFmpeg でデコードできるもの）
KNOWN_AUDIO_CODECS = {"aac", "opus", "vorbis", "mp3", "pcm_s16le", "pcm_s24le", "pcm_f32le", "flac", "alac", "mp3float"}


class MediaError(Exception):
    """利用者に表示できる録画処理エラー（代替手段の案内を含む）。"""


ALTERNATIVES = ("代替方法：会議ツールの文字起こし（.vtt / .srt / テキスト）を読み込むか、"
                "録画を MP4（音声 AAC）で書き出し直してください。")


@contextmanager
def temp_media_file(data: bytes, ext: str):
    """利用者のファイル名は使わず、ランダム名の一時ファイルに書き出す。"""
    ext = ext if ext in ALLOWED_EXT else ".bin"
    fd, path = tempfile.mkstemp(prefix="rp_media_", suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def probe_media(data: bytes, filename: str, limits) -> dict:
    """長さ・容量・音声トラック・コーデックを確認する。"""
    import av

    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXT:
        raise MediaError(f"この形式（{ext or '拡張子なし'}）の録画には対応していません。対応：MP4 / WebM / MOV（音声 .m4a/.mp3/.wav も可）。"
                         + ALTERNATIVES)
    size_mb = len(data) / 1024 / 1024
    if size_mb > limits.max_media_mb:
        raise MediaError(f"ファイルサイズ {size_mb:.0f}MB が上限（{limits.max_media_mb}MB）を超えています。"
                         "会議ツールで音声のみを書き出すか、必要な時間だけ切り出してください。")
    try:
        container = av.open(io.BytesIO(data), mode="r")
    except Exception as e:  # av.error.InvalidDataError など
        raise MediaError("録画ファイルを開けませんでした（破損、または未対応の形式）。" + ALTERNATIVES) from e
    try:
        fmt = container.format.name
        duration = container.duration / 1_000_000 if container.duration else None
        audio = [s for s in container.streams if s.type == "audio"]
        video = [s for s in container.streams if s.type == "video"]
        info = {
            "file_name": filename,
            "size_mb": round(size_mb, 2),
            "container": fmt,
            "duration_sec": round(duration, 1) if duration else None,
            "video_streams": [{"codec": s.codec_context.name} for s in video],
            "audio_streams": [{"codec": s.codec_context.name, "sample_rate": s.codec_context.sample_rate,
                               "channels": s.codec_context.channels} for s in audio],
            "issues": [],
        }
    finally:
        container.close()
    if not audio:
        raise MediaError("音声トラックがありません。音声付きで録画・書き出しされているか確認してください。" + ALTERNATIVES)
    codec = info["audio_streams"][0]["codec"]
    if codec not in KNOWN_AUDIO_CODECS:
        info["issues"].append(f"音声コーデック {codec} は動作未確認です。失敗した場合は AAC で書き出し直してください。")
    if duration is None:
        info["issues"].append("録画の長さを取得できませんでした。処理範囲を手入力してください。")
    elif duration / 60 > limits.max_media_minutes:
        info["issues"].append(f"録画の長さ（{duration/60:.0f}分）が上限（{limits.max_media_minutes}分）を超えています。"
                              "時間範囲を指定して分割処理してください。")
    return info


def extract_audio_wav(data: bytes, filename: str, start_sec: float = 0.0, end_sec: float | None = None,
                      sample_rate: int = 16000) -> bytes:
    """指定範囲の音声を 16kHz モノラル WAV に変換して返す（メモリ上）。"""
    import av
    import numpy as np

    try:
        container = av.open(io.BytesIO(data), mode="r")
    except Exception as e:
        raise MediaError("録画ファイルを開けませんでした。" + ALTERNATIVES) from e
    try:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise MediaError("音声トラックがありません。" + ALTERNATIVES)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        chunks = []
        if start_sec > 0:
            container.seek(int(start_sec * 1_000_000), any_frame=False, backward=True)
        for frame in container.decode(stream):
            t = float(frame.time) if frame.time is not None else 0.0
            if t + (frame.samples / frame.sample_rate) < start_sec:
                continue
            if end_sec is not None and t > end_sec:
                break
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    except MediaError:
        raise
    except Exception as e:
        raise MediaError("音声を取り出せませんでした（コーデック未対応または破損）。" + ALTERNATIVES) from e
    finally:
        container.close()
    if not chunks:
        raise MediaError("指定範囲に音声がありません。時間範囲を確認してください。")
    # 開始位置の誤差は音声フレーム1つ分（数十ミリ秒）以内
    pcm = np.concatenate(chunks).astype("int16")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
