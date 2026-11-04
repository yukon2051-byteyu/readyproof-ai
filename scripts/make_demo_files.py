"""3件のデモ用の架空資料を生成する（会社・製品・人物・資料・録画はすべて架空）。

実行：.venv\\Scripts\\python scripts\\make_demo_files.py
出力：readyproof/demos/files/
録画（MP4）は Windows の音声合成（System.Speech）で作るため Windows でのみ生成できる。
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "readyproof", "demos", "files")
os.makedirs(OUT, exist_ok=True)


# ============ デモ1：経費精算（PowerPoint ＋ 社内規程Word） ============
def make_demo1():
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    blank = prs.slide_layouts[5]  # タイトルのみ

    def add_slide(title):
        s = prs.slides.add_slide(blank)
        s.shapes.title.text = title
        return s

    def textbox(slide, text, top=1.5, left=0.6, width=8.8, height=1.0, size=16):
        tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tb.text_frame.word_wrap = True
        tb.text_frame.text = text
        for p in tb.text_frame.paragraphs:
            for r in p.runs:
                r.font.size = Pt(size)
        return tb

    # 1 表紙（ノートに社内メモ。初期状態で分析対象外になることを見せる）
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "ケイヒナビ Cloud ご提案資料"
    s.placeholders[1].text = "みらい業務システム株式会社（架空）／株式会社サンプル商事 様向け"
    s.notes_slide.notes_text_frame.text = "営業メモ：値引きは最大15%まで。競合A社との比較表は口頭のみで説明すること。"

    # 2 承認ワークフロー（本文＋表）
    s = add_slide("承認ワークフロー")
    textbox(s, "申請金額に応じて承認ルートを自動で切り替えられます。"
               "金額条件と承認者は管理画面の「承認ルート設定」で設定します（スタンダードプラン以上）。", top=1.4)
    rows = [("金額条件", "承認ルート（設定例）"), ("10,000円未満", "上長"), ("10,000円以上", "上長 → 部長")]
    tbl = s.shapes.add_table(3, 2, Inches(0.8), Inches(3.0), Inches(8.0), Inches(1.5)).table
    for r, (a, b) in enumerate(rows):
        tbl.cell(r, 0).text, tbl.cell(r, 1).text = a, b
    s.notes_slide.notes_text_frame.text = "設定例は初期値ではありません。導入時に設定が必要です。"

    # 3 権限と統制（グループ図形＋画像。自己承認の禁止については記載なし）
    s = add_slide("権限と統制")
    g = s.shapes.add_group_shape()
    for i, t in enumerate(["承認者は申請者の所属部門の上長が自動で設定されます。",
                           "承認・差し戻しの履歴は7年間保存されます。"]):
        tb = g.shapes.add_textbox(Inches(0.6), Inches(1.5 + i * 1.0), Inches(5.5), Inches(0.8))
        tb.text_frame.word_wrap = True
        tb.text_frame.text = t
    png = _diagram_png()
    s.shapes.add_picture(io.BytesIO(png), Inches(6.4), Inches(1.5), Inches(3.0), Inches(2.0))

    # 4 代理承認
    s = add_slide("代理承認")
    textbox(s, "不在期間を登録すると、あらかじめ指定した代理承認者が承認できます。")

    # 5 非表示スライド（旧料金）
    s = add_slide("（旧）料金表 2023年版")
    textbox(s, "スタンダードプラン 月額 450円／人（2023年度価格・現在は無効）")
    s._element.set("show", "0")

    # 6 料金プラン（表）
    s = add_slide("料金プラン")
    rows = [("プラン", "月額（1人あたり）", "主な機能"),
            ("ライト", "300円", "経費申請、単一の承認者"),
            ("スタンダード", "500円", "金額別の承認ルート、代理承認"),
            ("エンタープライズ", "800円", "監査ログの外部出力、IPアドレス制限")]
    tbl = s.shapes.add_table(4, 3, Inches(0.5), Inches(1.6), Inches(9.0), Inches(2.0)).table
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            tbl.cell(r, c).text = v

    # 7 導入効果（「金額」と「承認者」が同じスライドにあるが、金額別承認の根拠ではない）
    s = add_slide("導入効果の例")
    textbox(s, "承認者の確認時間を削減します。")
    textbox(s, "月間の申請金額 1,200万円規模の企業で、締め作業を3日短縮した例があります。", top=2.6)

    prs.save(os.path.join(OUT, "demo1_keihinavi_proposal.pptx"))

    import docx

    d = docx.Document()
    d.add_heading("経費精算規程（抜粋・架空）", level=1)
    d.add_heading("第3条 承認", level=2)
    d.add_paragraph("1. 経費申請の金額が10,000円未満の場合は、申請者の直属の上司が承認する。")
    d.add_paragraph("2. 経費申請の金額が10,000円以上の場合は、直属の上司が承認した後、部長が承認する。")
    d.add_paragraph("3. 申請者本人が自分の申請を承認すること（自己承認）は禁止する。")
    d.add_heading("第4条 代理承認", level=2)
    d.add_paragraph("上司が不在の場合の代理承認の条件は、経理部で検討中であり未確定とする。")
    d.save(os.path.join(OUT, "demo1_expense_rules.docx"))


def _diagram_png() -> bytes:
    """スライドに貼る図（文字を含む画像。アプリは中身を理解しない）。"""
    import zlib
    import struct

    w, h = 120, 80
    raw = b"".join(b"\x00" + bytes([200, 220, 240] * w) for _ in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


# ============ デモ2：生産・在庫管理（PDF ＋ Excel ＋ ベンダー回答） ============
def make_demo2():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    path = os.path.join(OUT, "demo2_tsukurun_overview.pdf")
    c = canvas.Canvas(path)
    pages = [
        ("ツクルン生産管理（架空） 製品説明", [
            "東和ファクトリーソリューションズ株式会社（架空）",
            "",
            "ツクルン生産管理は、中堅製造業向けの生産・在庫管理パッケージです。",
            "製造指図、実績入力、在庫、ロット管理を一つのシステムで扱います。",
        ]),
        ("ロットトレーサビリティ", [
            "製品ロット番号から、製造に使用した原材料ロットを検索できます。",
            "",
            "標準機能では、1つの製造指図に対して原材料ロットを1件登録します。",
            "",
            "1つの製造指図に複数の原材料ロットを投入する場合は、",
            "有償オプション「マルチロット投入」が必要です（1指図あたり最大20ロット）。",
            "",
            "誤って登録したロットは訂正でき、訂正前の内容は履歴として保持されます。",
        ]),
        ("現場端末", [
            "製造現場ではタブレット端末から実績を入力します。",
            "タブレット端末は工場内のWi-Fiに接続して利用します。",
        ]),
    ]
    for title, lines in pages:
        c.setFont("HeiseiKakuGo-W5", 16)
        c.drawString(60, 780, title)
        c.setFont("HeiseiKakuGo-W5", 11)
        y = 740
        for ln in lines:
            c.drawString(60, y, ln)
            y -= 20
        c.showPage()
    c.save()

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "機能一覧"
    ws.append(["No", "機能分類", "機能", "提供", "標準/オプション", "備考"])
    rows = [
        (1, "生産", "製造指図", "○", "標準", ""),
        (2, "生産", "実績入力", "○", "標準", "タブレット対応"),
        (3, "品質", "ロット管理", "○", "標準", ""),
        (4, "品質", "トレーサビリティ", "○", "標準", "製品ロット→原材料ロットの検索"),
        (5, "品質", "マルチロット投入", "○", "オプション", "1指図あたり最大20ロット"),
        (6, "品質", "ロット訂正", "○", "標準", "訂正履歴を保持"),
        (7, "現場", "現場端末（タブレット）", "○", "標準", "Wi-Fi環境が必要"),
    ]
    for r in rows:
        ws.append(list(r))
    memo = wb.create_sheet("社内メモ")
    memo.append(["メモ", "オプション価格は個別見積"])
    memo.sheet_state = "hidden"
    wb.save(os.path.join(OUT, "demo2_feature_list.xlsx"))

    with open(os.path.join(OUT, "demo2_vendor_answers.txt"), "w", encoding="utf-8") as f:
        f.write("ツクルン生産管理（架空） ご質問への回答書（架空） 2026年10月20日\n\n"
                "Q1. 通信が不安定な工程で、オフラインのまま実績を入力できますか。\n"
                "A1. 現行版ではオフラインでの実績入力には対応していません。"
                "通信復旧後に一括登録する機能は次期バージョンで検討中です。\n\n"
                "Q2. マルチロット投入オプションで、誤登録した原材料ロットを訂正した場合、訂正履歴は保持されますか。\n"
                "A2. 保持されます。訂正前のロット番号、訂正者、訂正日時を記録します。\n\n"
                "Q3. オフライン入力を追加開発で対応することは可能ですか。\n"
                "A3. 個別開発としてお見積りが可能です。費用と期間は要件確認後にご提示します。\n")


# ============ デモ3：アカウント管理（Word ＋ 録画 ＋ VTT） ============
DEMO3_TALK = [
    ("自社", "標準プランで、指定日のアカウント停止ができますか？"),
    ("営業", "予約停止は上位プランで対応しています。標準プランは手動操作です。"),
    ("自社", "管理者の操作履歴は、どのくらいの期間保存されますか？"),
    ("営業", "操作履歴の保存期間は、確認して回答します。"),
    ("営業", "なお、来年度には標準プランでも予約停止に対応する予定です。"),
    ("自社", "退職者の停止を、人事システムと連携して自動化できますか？"),
    ("営業", "おそらくCSVの取り込みで対応できると思います。"),
]


def make_demo3():
    import docx

    d = docx.Document()
    d.add_heading("IDガード（架空） 製品概要", level=1)
    d.add_paragraph("ネクストID株式会社（架空）")
    d.add_heading("アカウント管理", level=2)
    d.add_paragraph("利用停止は、管理画面から即時に実行できます。")
    d.add_paragraph("予約停止（指定日にアカウントを自動で停止する機能）は、スタンダードプランから利用できます。")
    d.add_heading("操作ログ", level=2)
    d.add_paragraph("管理者の操作ログを保存します。保存期間はプランによって異なります。")
    d.add_heading("プラン", level=2)
    t = d.add_table(rows=3, cols=2)
    for r, (a, b) in enumerate([("プラン", "主な対象"), ("スタンダード", "従業員300名まで"),
                                ("プレミアム", "従業員300名超・監査対応")]):
        t.cell(r, 0).text, t.cell(r, 1).text = a, b
    d.save(os.path.join(OUT, "demo3_idguard_overview.docx"))
    _make_demo3_recording()


def _tts_wav(text: str, path: str, rate: int, pitch: str) -> bool:
    ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="ja-JP">'
            f'<prosody pitch="{pitch}">{text}</prosody></speak>')
    ps = ("Add-Type -AssemblyName System.Speech;"
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ja-JP' } | Select-Object -First 1;"
          "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
          f"$s.Rate = {rate};"
          "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
          "$s.SetOutputToWaveFile($env:RP_TTS_OUT, $fmt);"
          "$s.SpeakSsml($env:RP_TTS_SSML); $s.Dispose()")
    env = dict(os.environ, RP_TTS_OUT=path, RP_TTS_SSML=ssml)
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, env=env, timeout=60,
                       capture_output=True)
        return os.path.exists(path) and os.path.getsize(path) > 1000
    except Exception as e:  # Windows 以外・音声合成なし
        print("音声合成を利用できません：", e)
        return False


def _make_demo3_recording():
    import numpy as np

    sr = 16000
    tmp = tempfile.mkdtemp(prefix="rp_tts_")
    audio, cues, t = [], [], 1.0
    audio.append(np.zeros(int(sr * 1.0), dtype=np.int16))
    for i, (who, text) in enumerate(DEMO3_TALK):
        p = os.path.join(tmp, f"u{i}.wav")
        ok = _tts_wav(text, p, rate=0 if who == "自社" else 1, pitch="high" if who == "自社" else "low")
        if not ok:
            print("録画の生成をスキップしました。")
            return
        with wave.open(p) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        dur = len(pcm) / sr
        cues.append({"start": round(t, 2), "end": round(t + dur, 2), "speaker": "話者1" if who == "自社" else "話者2",
                     "text": text})
        audio += [pcm, np.zeros(int(sr * 0.8), dtype=np.int16)]
        t += dur + 0.8
    pcm = np.concatenate(audio)
    _write_mp4(pcm, sr, os.path.join(OUT, "demo3_sales_meeting.mp4"))

    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d}.{ms % 1000:03d}"

    with open(os.path.join(OUT, "demo3_sales_meeting.vtt"), "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for c in cues:
            f.write(f"{ts(c['start'])} --> {ts(c['end'])}\n<v {c['speaker']}>{c['text']}</v>\n\n")
    with open(os.path.join(OUT, "demo3_cues.json"), "w", encoding="utf-8") as f:
        json.dump(cues, f, ensure_ascii=False, indent=1)
    print(f"録画 {t:.1f} 秒を生成しました。")


def _write_mp4(pcm, sr: int, path: str):
    """静止画の映像＋AAC音声の MP4 を作る（PyAV）。"""
    import av
    import numpy as np

    container = av.open(path, mode="w")
    v = container.add_stream("mpeg4", rate=2)
    v.width, v.height, v.pix_fmt = 320, 180, "yuv420p"
    a = container.add_stream("aac", rate=sr)
    a.layout = "mono"
    dur = len(pcm) / sr
    img = np.full((180, 320, 3), (31, 58, 95), dtype=np.uint8)
    for i in range(int(dur * 2) + 1):
        frame = av.VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = i
        for packet in v.encode(frame):
            container.mux(packet)
    for packet in v.encode():
        container.mux(packet)
    step = 1024
    for i in range(0, len(pcm), step):
        chunk = pcm[i:i + step]
        if len(chunk) < step:
            chunk = np.pad(chunk, (0, step - len(chunk)))
        frame = av.AudioFrame.from_ndarray(chunk.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = sr
        frame.pts = i
        for packet in a.encode(frame):
            container.mux(packet)
    for packet in a.encode():
        container.mux(packet)
    container.close()


if __name__ == "__main__":
    make_demo1()
    make_demo2()
    make_demo3()
    print("出力先：", OUT)
    for name in sorted(os.listdir(OUT)):
        print(" -", name, os.path.getsize(os.path.join(OUT, name)), "bytes")
    sys.exit(0)
