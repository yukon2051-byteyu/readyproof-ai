"""文字起こしエンジン。

採用：ローカル処理（faster-whisper）。音声を外部に送信しない。API料金は不要だが CPU とメモリを使う。
話者の自動区別（話者分離）は行わない。話者は人が区間ごとに指定する。
外部API方式の比較は docs/transcription_options.md を参照（未実装・未契約）。
"""
from __future__ import annotations

import io

ENGINES = {
    "local_whisper": {
        "label": "ローカル文字起こし（faster-whisper）",
        "destination": "外部送信なし（このアプリが動いているサーバー内で処理）",
        "diarization": "なし（話者は人が指定）",
        "cost": "API料金 0円（サーバーのCPU時間を使用）",
    },
}

LOW_CONFIDENCE_LOGPROB = -1.0
NO_SPEECH_PROB = 0.6


def local_whisper_available() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401
        return True, ""
    except Exception:
        return False, ("faster-whisper がインストールされていません。"
                       "手元のPCで `pip install -r requirements-local.txt` 後に再起動してください。公開環境では、会議ツールの文字起こし（VTT/SRT）を読み込んでください。")


_MODEL_CACHE: dict = {}


def _model(size: str):
    from faster_whisper import WhisperModel

    if size not in _MODEL_CACHE:
        _MODEL_CACHE.clear()  # メモリ節約のため1モデルだけ保持
        _MODEL_CACHE[size] = WhisperModel(size, device="cpu", compute_type="int8")
    return _MODEL_CACHE[size]


def transcribe_local(wav_bytes: bytes, model_size: str = "small", offset_sec: float = 0.0,
                     progress=None) -> list[dict]:
    """WAV（16kHz モノラル）を文字起こしし、録画全体の時刻に合わせた区間を返す。"""
    import wave

    import numpy as np

    model = _model(model_size)
    # faster-whisper 内部のファイル読込は PyAV 19 と互換性がないため、数値配列（16kHz）で直接渡す
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1:
            raise ValueError("16kHz モノラルの WAV が必要です。")
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segments, info = model.transcribe(audio, language="ja", vad_filter=True,
                                      beam_size=5, condition_on_previous_text=False)
    out = []
    total = info.duration or 1
    for seg in segments:
        flags = []
        if seg.avg_logprob is not None and seg.avg_logprob < LOW_CONFIDENCE_LOGPROB:
            flags.append("聞き取り不能あり")
        if seg.no_speech_prob is not None and seg.no_speech_prob > NO_SPEECH_PROB:
            flags.append("聞き取り不能あり")
        out.append({
            "start": round(seg.start + offset_sec, 2),
            "end": round(seg.end + offset_sec, 2),
            "speaker_label": None,
            "text": seg.text.strip(),
            "flags": sorted(set(flags)),
            "confidence": round(seg.avg_logprob, 3) if seg.avg_logprob is not None else None,
        })
        if progress:
            progress(min(seg.end / total, 1.0))
    return out
