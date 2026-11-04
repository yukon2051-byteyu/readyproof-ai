"""Excel 出力（適合性・導入確認レポート／質問書／依頼書）。

- 数式注入対策：= + - @ タブ 改行 で始まる文字列は先頭に ' を付けて文字として扱う
- 日本語が読めるよう列幅・折り返し・見出し固定を設定する
- 名称・ID・版・出力日時・下書き／確定を明示する
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..config import APP_NAME_EN, APP_NAME_JA
from ..core import find, now_iso, primary_product
from ..logic import metrics as M
from ..logic.evidence import evidence_label
from ..logic.rules import current_diagnosis, latest_run
from ..logic.stale import decision_changed_since

HEAD_FILL = PatternFill("solid", fgColor="1F3A5F")
HEAD_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(size=14, bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Side(style="thin", color="B7C2D0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
INPUT_FILL = PatternFill("solid", fgColor="FFF8DC")
_DANGER = ("=", "+", "-", "@", "\t", "\r", "\n")


def safe(v):
    """セル値の数式注入対策。"""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = "\n".join(str(x) for x in v)
    if isinstance(v, bool):
        return "はい" if v else "いいえ"
    if isinstance(v, (int, float)):
        return v
    s = str(v)
    if s.startswith(_DANGER):
        return "'" + s
    return s


def _header_block(ws, title: str, project: dict, status_note: str = "") -> int:
    prod = primary_product(project) or {}
    ws["A1"] = f"{APP_NAME_EN}（{APP_NAME_JA}）｜{title}"
    ws["A1"].font = TITLE_FONT
    rows = [("案件", f"{project['project']['id']} {project['project']['name']}"),
            ("製品・プラン", f"{prod.get('name', '未登録')}／{prod.get('vendor', '')}／{prod.get('plan', '')} {prod.get('edition', '')}"),
            ("出力日時", now_iso())]
    if project["project"].get("demo_id"):
        rows.append(("注意", "架空のデモデータです。AI結果は「準備済みのデモ結果」です。"))
    if status_note:
        rows.append(("状態", status_note))
    for i, (k, v) in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=safe(k)).font = Font(bold=True)
        ws.cell(row=i, column=2, value=safe(v))
    return len(rows) + 3


def _table(ws, start_row: int, headers: list[str], rows: list[list], widths: list[int]) -> int:
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=start_row, column=c, value=safe(h))
        cell.fill, cell.font, cell.alignment, cell.border = HEAD_FILL, HEAD_FONT, WRAP, BORDER
    for r, row in enumerate(rows, start=start_row + 1):
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=safe(v))
            cell.alignment, cell.border = WRAP, BORDER
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(headers))}{start_row + len(rows)}"
    else:
        ws.cell(row=start_row + 1, column=1, value="（該当なし）")
    return start_row + len(rows) + 2


def _evs(project, evs) -> str:
    return "\n".join(f"・[{ev.get('kind', '')}] {evidence_label(project, ev)}" for ev in evs or []) or "根拠なし"


def report_workbook(project: dict) -> bytes:
    wb = Workbook()
    m = M.compute(project)

    # 概要
    ws = wb.active
    ws.title = "概要"
    r = _header_block(ws, "適合性・導入確認レポート", project)
    p = project["project"]
    info = [["対象業務", p["target_business"]], ["導入目的", p["purpose"]], ["担当部門", p["department"]],
            ["制約条件", p["constraints"]], ["導入判断", project["decision"]["value"]]]
    r = _table(ws, r, ["項目", "内容"], info, [22, 90])
    counts = [[k, v] for k, v in m["by_category"].items()]
    counts += [["診断なし", m["no_diagnosis"]], ["診断の人による確認", m["diag_reviewed"]["text"]],
               ["必須要件：資料・説明上の見込みなし", len(m["must_unresolved"])],
               ["必須要件：実機で合格未確認", len(m["must_not_verified"])],
               ["テスト：合格（最新・合否判定済みが分母）", m["pass_rate"]["text"]],
               ["テスト：実施済み（全テストが分母）", m["executed_rate"]["text"]],
               ["不合格", len(m["failed"])], ["未実施", len(m["not_run"])], ["実施不能", len(m["blocked"])],
               ["未回答の質問", len(m["unanswered"])], ["未確定の依頼書", len(m["cr_draft"])],
               ["対応中の依頼", len(m["cr_active"])], ["再確認が必要", len(m["stale"])]]
    _table(ws, r, ["集計項目（資料上の見込みと実機結果は別物です）", "件数・割合"], counts, [44, 30])

    # 資料と録画・分析範囲
    ws = wb.create_sheet("資料と録画")
    r = _header_block(ws, "資料と録画・分析範囲", project)
    rows = []
    for s in project["sources"]:
        cov = s.get("coverage", {})
        sel = sum(1 for g in s["segments"] if g.get("selected"))
        rows.append([s["id"], s.get("version"), s["name"], s["owner"], s["kind"], s["status"], s["file_type"],
                     f"{cov.get('read', '')}/{cov.get('total', '')} {cov.get('unit', '')}",
                     f"{sel}/{len(s['segments'])}", "\n".join(cov.get("skipped", [])) or "なし",
                     "\n".join(f"{w.get('where', '')} {w['message']}" for w in s.get("warnings", [])) or "なし"])
    r = _table(ws, r, ["資料ID", "版", "名称", "区分", "種類", "状態", "形式", "読込範囲", "分析対象の箇所数",
                       "未読込・対象外", "警告"], rows, [10, 5, 28, 7, 12, 7, 7, 14, 12, 30, 50])
    rows = []
    for rec in project["recordings"]:
        rng = rec.get("range") or {}
        utts = rec.get("utterances", [])
        rows.append([rec["id"], rec.get("version"), rec.get("meeting_name"), rec.get("file_name"), rec.get("held_on"),
                     rec.get("duration_sec"), f"{rng.get('start', 0)}秒〜{rng.get('end', '末尾')}秒",
                     rec.get("method"), rec.get("processed_at"),
                     f"{sum(1 for u in utts if u.get('speaker_confirmed') and u.get('review_status') == '確認済み')}/{len(utts)}",
                     "保持していません（ファイル名と時刻のみ）"])
    _table(ws, r, ["録画ID", "版", "ミーティング名", "ファイル名", "開催日", "長さ(秒)", "処理対象時間", "処理方法",
                   "処理日時", "話者・内容確認済み/発言数", "動画本体"], rows, [10, 5, 24, 22, 12, 8, 18, 22, 18, 14, 22])

    # 自社要件
    ws = wb.create_sheet("自社要件")
    r = _header_block(ws, "自社の仕事・ルール", project)
    rows = [[q["id"], q["version"], q["status"], q["priority"], q["business"], q["workflow"], q["role"], q["rules"],
             q["exceptions"], q["reason"], q["open_issues"], q["original_text"], q["origin"],
             q.get("confirmed_by", "")] for q in project["requirements"]]
    _table(ws, r, ["要件ID", "版", "状態", "重要度", "業務名", "作業内容", "役割", "ルール・条件", "例外", "理由",
                   "未確定事項", "元の文章", "作成", "確定者（自己申告）"],
           rows, [9, 5, 7, 8, 16, 30, 12, 36, 24, 20, 24, 36, 10, 12])

    # 診断と根拠
    ws = wb.create_sheet("診断と根拠")
    r = _header_block(ws, "自社に合うかの診断（資料・説明上の見込み。実機確認ではありません）", project)
    rows = []
    for q in project["requirements"]:
        dg = current_diagnosis(project, q["id"])
        if not dg:
            rows.append([q["id"], q["version"], "診断なし", "", "", "", "", "", "", "", ""])
            continue
        rows.append([q["id"], dg["req_version"], dg["category"], dg["reason"], dg["met_conditions"],
                     dg["remaining_conditions"], _evs(project, dg["evidence"]), dg["plan_conditions"],
                     dg["next_check"], f"{dg['review_status']}（{dg['origin']}）", dg.get("reviewed_by", "")])
    _table(ws, r, ["要件ID", "要件の版", "診断区分", "理由", "満たす条件", "残る条件", "根拠（資料名・位置・発言時刻・引用・確認状態）",
                   "プラン等の条件", "次に確認すること", "レビュー状態", "確認者（自己申告）"],
           rows, [9, 6, 18, 36, 26, 26, 60, 22, 26, 16, 12])

    # 質問と回答
    ws = wb.create_sheet("質問と回答")
    r = _header_block(ws, "不明点・矛盾・回答", project)
    rows = [[q["id"], ",".join(q["req_ids"]), q["status"], q["background"], q["question"], q["points"],
             q["answer_source"], q["answer_date"], q["answer_text"], q.get("answer_reviewed_by", "")]
            for q in project["questions"]]
    _table(ws, r, ["質問ID", "関連要件", "状態", "背景", "質問", "回答してほしい点", "回答元", "回答日", "回答本文",
                   "回答確認者"], rows, [8, 10, 10, 36, 36, 28, 12, 11, 40, 12])

    # 対応と依頼
    ws = wb.create_sheet("対応と依頼")
    r = _header_block(ws, "合わない部分への対応と依頼状況", project)
    rows = [[a["id"], a["req_id"], a["type"], a["status"], a["reason"], a["unknowns"], a["decided_by"],
             a["decision_reason"]] for a in project["actions"]]
    r = _table(ws, r, ["対応ID", "要件", "対応方法", "判断", "理由", "不明点", "判断者", "判断理由"],
               rows, [8, 9, 18, 8, 36, 30, 10, 30])
    rows = []
    for c in project["requests"]:
        v = c["vendor"]
        cost = "未回答" if v["cost_amount"] is None else f"{v['cost_amount']:,} {v['cost_currency']}"
        eff = "未回答" if v["effort"] is None else f"{v['effort']} {v['effort_unit']}"
        rows.append([c["id"], c["version"], c["title"], c["kind"], c["phase"], c["status"], ",".join(c["req_ids"]),
                     v.get("answer", ""), cost, eff, v.get("planned_date", ""),
                     "相手完了の連絡あり" if v.get("vendor_done") else "",
                     ("人が確認して完了" + ("（残件あり：" + c["completion"]["reason"] + "）" if c["completion"]["with_remaining"] else ""))
                     if c["completion"]["human_confirmed"] else ""])
    _table(ws, r, ["依頼ID", "版", "件名", "区分", "段階", "状態", "関連要件", "相手の回答", "見積費用", "工数", "予定日",
                   "相手の対応", "人の確認"], rows, [8, 5, 28, 12, 16, 10, 10, 30, 14, 10, 11, 14, 22])

    # テスト・結果
    ws = wb.create_sheet("テストと結果")
    r = _header_block(ws, "試すこと・実際の結果（実機で人が確認した結果）", project)
    rows = []
    for t in project["tests"]:
        lr = latest_run(project, t["id"])
        rows.append([t["id"], t["version"], t["status"], ",".join(t["req_ids"]), t["title"], t["viewpoint"],
                     t["steps"], t["expected"], "確定" if t.get("expected_confirmed") else "未確定", t["importance"],
                     lr["id"] if lr else "", lr["status"] if lr else "未実施", lr["result"] if lr else "",
                     lr["actual"] if lr else "", lr["test_version"] if lr else ""])
    r = _table(ws, r, ["テストID", "版", "状態", "要件", "名称", "観点", "手順", "期待結果", "期待結果の確定", "重要度",
                       "最新の実施ID", "実施状態", "合否", "実際の結果", "実施時のテスト版"],
               rows, [8, 5, 7, 9, 24, 12, 36, 32, 9, 6, 9, 9, 7, 32, 8])
    rows = [[x["id"], x["test_id"], x["test_version"], x["tester"], x["executed_at"], x["product_version"],
             x["plan"], x["environment"], x["status"], x["result"], x["actual"], x["evidence_memo"], x["defect"],
             "再テスト" if x["is_retest"] else "初回"] for x in project["runs"]]
    _table(ws, r, ["実施ID", "テスト", "テスト版", "実施者（自己申告）", "日時", "製品版", "プラン", "環境", "状態", "合否",
                   "実際の結果", "証拠メモ", "不具合", "区分"], rows, [8, 8, 6, 12, 18, 10, 10, 12, 9, 7, 32, 24, 24, 8])

    # 残件
    ws = wb.create_sheet("残件")
    r = _header_block(ws, "残った問題", project)
    issues = M.remaining_issues(project, m)
    _table(ws, r, ["種類", "ID", "内容", "次の操作"], [[i["種類"], i["ID"], i["内容"], i["次の操作"]] for i in issues],
           [26, 10, 60, 20])

    # 導入判断
    ws = wb.create_sheet("導入判断")
    d = project["decision"]
    r = _header_block(ws, "人の導入判断", project,
                      "判断後に関連情報が更新されています。再確認してください。" if decision_changed_since(project) else "")
    _table(ws, r, ["項目", "内容"], [["判断", d["value"]], ["判断者（自己申告・正式承認ではありません）", d["by"]],
                                   ["日付", d["date"]], ["理由", d["reason"]], ["条件", d["conditions"]],
                                   ["判断時点の残件数", len(issues)]], [36, 80])
    return _save(wb)


def questionnaire_workbook(project: dict, question_ids: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "質問書"
    qs = [q for q in project["questions"] if (question_ids is None or q["id"] in question_ids)
          and q["status"] != "取り下げ"]
    draft = any(q["status"] == "下書き" for q in qs)
    r = _header_block(ws, "ベンダーへの質問書", project,
                      "下書きを含みます（社内確認用）" if draft else "確定済みの質問")
    rows = []
    for q in qs:
        reqs = [find(project, "requirements", rid) for rid in q["req_ids"]]
        req_text = "\n".join(f"{x['id']} 第{x['version']}版：{x['business']}／{x['rules']}" for x in reqs if x)
        rows.append([q["id"], q["status"], req_text, q["background"], q["question"], q["points"], "", "", ""])
    _table(ws, r, ["質問ID", "状態", "関連する要件", "背景", "質問", "回答してほしい点", "ご回答（記入欄）", "回答者", "回答日"],
           rows, [8, 8, 30, 36, 40, 30, 44, 12, 11])
    for row in range(r + 1, r + 1 + len(rows)):
        for col in (7, 8, 9):
            ws.cell(row=row, column=col).fill = INPUT_FILL
    return _save(wb)


def request_workbook(project: dict, request_id: str) -> bytes:
    """依頼書1件。アプリがなくても必要な動きと受入条件が分かる構成。"""
    c = find(project, "requests", request_id)
    wb = Workbook()
    ws = wb.active
    ws.title = c["id"]
    state = "下書き（未確定）" if c["status"] == "下書き" else f"{c['status']}（第{c['version']}版）"
    r = _header_block(ws, f"改修・設定変更等の依頼書 {c['id']} 第{c['version']}版", project, state)
    reqs = [find(project, "requirements", x) for x in c["req_ids"]]
    runs = [find(project, "runs", x) for x in c.get("run_ids", [])]
    v = c["vendor"]
    rows = [
        ["件名", c["title"]], ["依頼ID・版", f"{c['id']} 第{c['version']}版"], ["状態", state],
        ["依頼先", c["to"]], ["区分", c["kind"]], ["段階", c["phase"]],
        ["背景", c["background"]], ["目的", c["purpose"]],
        ["関連要件", "\n".join(f"{x['id']} 第{x['version']}版 {x['business']}：{x['rules']}" for x in reqs if x)],
        ["関連テスト・実施", "\n".join(f"{x['id']}（テスト{x['test_id']} 第{x['test_version']}版）{x['result']}：{x['actual']}"
                                for x in runs if x) or "なし（資料診断段階）"],
        ["資料上の仕様", c["spec_in_docs"]], ["営業説明", c["sales_explanation"]],
        ["実際の動き（テストで確認した現象）", c["actual_behavior"] or "（実機では未確認）"],
        ["発生条件", c["conditions"]], ["再現手順", c["repro_steps"]],
        ["必要な動き", c["needed_behavior"]], ["差分", c["gap"]], ["業務影響", c["impact"]],
        ["希望範囲", c["scope"]], ["対象外", c["out_of_scope"]],
        ["優先度と理由", f"{c['priority']}：{c['priority_reason']}"],
        ["希望時期と理由", f"{c['desired_date'] or '未定'}：{c['desired_date_reason']}"],
        ["前提・未確定事項", c["assumptions"]], ["相手への質問", c["questions_to_vendor"]],
        ["受入条件", c["acceptance_criteria"]], ["テスト候補", c["test_candidates"]],
        ["根拠", _evs(project, c.get("evidence"))],
        ["費用・工期", "未回答（不明な費用・工期は記載していません）" if v["cost_amount"] is None and v["effort"] is None
         else f"費用：{v['cost_amount'] if v['cost_amount'] is not None else '未回答'} {v['cost_currency']}／"
              f"工数：{v['effort'] if v['effort'] is not None else '未回答'} {v['effort_unit']}"],
        ["作成", c["origin"] + ("（AIの下書きを人が確認・編集）" if c["origin"] == "AI生成" else "")],
    ]
    _table(ws, r, ["項目", "内容"], rows, [28, 100])
    return _save(wb)


def _save(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
