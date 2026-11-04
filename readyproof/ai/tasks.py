"""AI の作業（要件分割・診断・依頼書・テスト）と、実行前見積・利用記録。

流れ：入力を組み立てる → 見積と枠確認 → 実行 → 出力を検証して「下書き」として登録
"""
from __future__ import annotations

import json
import re

from ..core import find, now_iso
from ..logic import rules
from ..logic.evidence import evidence_label, norm
from ..media.subtitles import fmt_ts
from ..search import candidates, with_context
from .client import AIError, AIResult
from .prompts import (DIAG_SCHEMA, INTERVIEW_SCHEMA, REQUEST_SCHEMA, SPLIT_SCHEMA, TEST_MULTI_SCHEMA, TEST_SCHEMA,
                      data_block)


# ---------------- 見積 ----------------
def estimate_cost_jpy(input_chars: int, max_output_tokens: int, budget, retries: int = 1) -> dict:
    """上限見積。日本語は1文字≒1トークン以上として多めに見積もる。再試行分も含める。"""
    in_tok = int(input_chars * 1.1) + 2500  # 指示文・スキーマ分
    one = in_tok / 1e6 * budget.input_usd_per_mtok + max_output_tokens / 1e6 * budget.output_usd_per_mtok
    usd = one * (1 + retries)
    return {"input_tokens": in_tok, "max_output_tokens": max_output_tokens, "usd": round(usd, 3),
            "jpy": round(usd * budget.usd_jpy, 1), "note": f"出力上限まで使い、再試行{retries}回が発生した場合の最大見込み"}


def actual_cost_jpy(res_in: int, res_out: int, budget) -> float:
    usd = res_in / 1e6 * budget.input_usd_per_mtok + res_out / 1e6 * budget.output_usd_per_mtok
    return round(usd * budget.usd_jpy, 2)


def execute(ai, task: str, prompt: str, schema: dict, max_tokens: int, settings, ledger=None, code: str = "") -> AIResult:
    """枠の予約 → 実行 → 実績で確定。デモ・テスト用の FakeAI は記録しない（料金なし）。"""
    if len(prompt) > settings.limits.max_ai_input_chars + 5000:
        raise AIError(f"AI への入力が上限（{settings.limits.max_ai_input_chars:,}字）を超えます。対象を減らしてください。")
    if not getattr(ai, "paid", False):
        return ai.run(task, prompt, schema, max_tokens)
    if ledger is None:
        raise AIError("利用記録の保存先がないため、有料処理を実行できません。")
    est = estimate_cost_jpy(len(prompt), max_tokens, settings.budget)
    try:
        run_id = ledger.reserve(settings.budget, "ai", code, est["jpy"], task)
    except PermissionError as e:
        raise AIError(str(e)) from e
    except Exception as e:  # 記録先に書けないときは実行しない（上限を守れないため）
        raise AIError("利用記録を保存できないため、AIを実行しませんでした。時間をおいて再度お試しください。") from e
    try:
        res = ai.run(task, prompt, schema, max_tokens)
    except AIError as e:
        cost = actual_cost_jpy(e.input_tokens, e.output_tokens, settings.budget) if e.tokens_known else None
        ledger.finalize(run_id, "失敗", cost, api_calls=1, input_tokens=e.input_tokens,
                        output_tokens=e.output_tokens, error=str(e))
        raise
    except Exception as e:  # 想定外の失敗も枠は見積額で残す
        ledger.finalize(run_id, "失敗", None, api_calls=1, error=type(e).__name__)
        raise AIError("AI の実行中に予期しないエラーが発生しました。入力内容は保持されています。") from e
    ledger.finalize(run_id, "成功", actual_cost_jpy(res.input_tokens, res.output_tokens, settings.budget),
                    api_calls=res.api_calls, input_tokens=res.input_tokens, output_tokens=res.output_tokens)
    return res


# ---------------- 要件の分割 ----------------
def split_prompt(text: str) -> str:
    return ("次の自社の業務ルール・作業手順の文章を、確認しやすい要件の単位に分割してください。"
            "金額・以上/未満・禁止・例外を必ず保持し、曖昧な点や矛盾は open_issues に書いてください。"
            "original_text には元の文章の該当部分をそのまま書いてください。\n\n" + data_block("自社の文章", text))


def apply_split(project: dict, text: str, data: dict, origin: str = "AI生成") -> list[dict]:
    out = []
    for item in data.get("requirements", []):
        req = rules.add_requirement(project, item, origin=origin)
        if item.get("original_text") and norm(item["original_text"]) not in norm(text):
            req["term_warnings"] = req.get("term_warnings", []) + ["元文の引用が入力文に見つかりません（要確認）"]
        out.append(req)
    return out


# ---------------- 診断 ----------------
def _excerpt_line(key: str, c: dict) -> str:
    if c["ref_type"] == "source":
        head = f"[{key}] 資料「{c['source_name']}」{c['loc_label']}"
    else:
        state = "利用者確認済み" if (c.get("speaker_confirmed") and c.get("review_status") == "確認済み") else "未確認の文字起こし"
        head = (f"[{key}] 録画「{c.get('meeting') or c['rec_id']}」{fmt_ts(c.get('start'))}-{fmt_ts(c.get('end'))} "
                f"話者:{c.get('speaker_role') or '未分類'} 種類:{c.get('utterance_type') or '未分類'} {state}")
    return f"{head}\n{c['text']}"


def build_diagnosis_input(project: dict, req_ids: list[str], product_id: str | None, settings) -> tuple[str, dict, dict]:
    """診断用の入力（要件＋関連抜粋）と、参照キー→根拠 の対応表を作る。"""
    prod = find(project, "products", product_id) if product_id else None
    refmap, lines, req_lines, coverage = {}, [], [], {}
    budget_chars = settings.limits.max_ai_input_chars
    used = 0
    for rid in req_ids:
        req = find(project, "requirements", rid)
        if not req:
            continue
        req_lines.append(f"[{rid}] 業務:{req['business']} / 作業:{req['workflow']} / 役割:{req['role']} / "
                         f"ルール:{req['rules']} / 例外:{req['exceptions']} / 重要度:{req['priority']}")
        hits = with_context(candidates(project, req, product_id))
        coverage[rid] = len(hits)
        for c in hits:
            exists = next((k for k, v in refmap.items() if v.get("seg_id") == c.get("seg_id")
                           and v.get("utt_id") == c.get("utt_id") and v.get("source_id") == c.get("source_id")
                           and v.get("rec_id") == c.get("rec_id")), None)
            if exists:
                continue
            line = _excerpt_line(f"E{len(refmap) + 1}", c)
            if used + len(line) > budget_chars:
                break
            key = f"E{len(refmap) + 1}"
            refmap[key] = {k: c[k] for k in ("ref_type", "source_id", "version", "seg_id", "rec_id",
                                              "rec_version", "utt_id") if k in c}
            lines.append(line)
            used += len(line)
    product_line = (f"検討中の製品：{prod['name']}（ベンダー：{prod['vendor']}、検討プラン：{prod['plan'] or '未記入'}、"
                    f"版：{prod.get('edition') or '未記入'}）" if prod else "検討中の製品：未登録")
    prompt = (product_line + "\n\n各要件について、抜粋だけを根拠に適合性を診断してください。"
              "抜粋にないことは情報不足としてください。evidence.ref には抜粋の参照キーを入れてください。"
              "質問（questions）と対応方法の候補（actions）も、必要な場合のみ挙げてください。\n\n"
              + data_block("自社の要件", "\n".join(req_lines)) + "\n\n"
              + data_block("製品の資料・営業説明の抜粋（検索で見つかった箇所のみ）", "\n\n".join(lines) or "（該当する抜粋なし）"))
    return prompt, refmap, coverage


def _map_evidence(items: list, refmap: dict, kind_default: str = "資料の記載") -> list[dict]:
    out = []
    for e in items or []:
        ref = refmap.get(e.get("ref", ""))
        if ref is None:
            out.append({"ref_type": "unknown", "ref": e.get("ref"), "quote": e.get("quote", "")})
            continue
        kind = "営業・ベンダーの説明" if ref["ref_type"] == "utterance" else kind_default
        out.append({**ref, "quote": e.get("quote", ""), "kind": kind})
    return out


_REF = re.compile(r"(?<![A-Za-z0-9])E[0-9]+(?![0-9])")


def _ref_text(project: dict, refmap: dict, text):
    """AIの文中の参照キー（E3 など）を、人が読める資料名・位置に置き換える。"""
    if not isinstance(text, str) or not text:
        return text

    def rep(m):
        ref = refmap.get(m.group(0))
        if not ref:
            return m.group(0)
        if ref["ref_type"] == "utterance":
            rec = find(project, "recordings", ref.get("rec_id", "")) or {}
            u = next((x for x in rec.get("utterances", []) if x["id"] == ref.get("utt_id")), {})
            return f"録画{fmt_ts(u.get('start'))}の発言（{u.get('speaker_role') or '話者未分類'}）"
        src = find(project, "sources", ref.get("source_id", "")) or {}
        seg = next((g for g in src.get("segments", []) if g["seg_id"] == ref.get("seg_id")), {})
        return f"「{src.get('name', '資料')}」{seg.get('loc_label', '')}"

    return _REF.sub(rep, text)


def _ref_all(project: dict, refmap: dict, obj):
    if isinstance(obj, dict):
        return {k: (v if k in ("ref", "quote") else _ref_all(project, refmap, v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ref_all(project, refmap, v) for v in obj]
    return _ref_text(project, refmap, obj)


def apply_diagnosis(project: dict, data: dict, refmap: dict, product_id: str | None,
                    origin: str = "AI生成", allowed_req_ids: list | None = None) -> list[dict]:
    created = []
    for d in data.get("diagnoses", []):
        d = _ref_all(project, refmap, d)
        if allowed_req_ids is not None and d.get("req_id") not in allowed_req_ids:
            continue
        if not find(project, "requirements", d.get("req_id", "")):
            continue
        dg = rules.add_diagnosis(project, {
            "req_id": d["req_id"], "product_id": product_id, "category": d.get("category"),
            "reason": d.get("reason", ""), "met_conditions": d.get("met_conditions", []),
            "remaining_conditions": d.get("remaining_conditions", []),
            "test_conditions": d.get("test_conditions", []),
            "evidence": _map_evidence(d.get("evidence"), refmap),
            "constraints": d.get("constraints", ""), "plan_conditions": d.get("plan_conditions", ""),
            "next_check": d.get("next_check", ""),
        }, origin=origin)
        for q in d.get("questions", []):
            if q.get("question", "").strip():
                rules.add_question(project, {"req_ids": [d["req_id"]], "diag_id": dg["id"], **q}, origin=origin)
        for a in d.get("actions", []):
            rules.add_action(project, {"req_id": d["req_id"], "diag_id": dg["id"], **a}, origin=origin)
        created.append(dg)
    return created


def run_diagnosis(project: dict, req_ids: list[str], product_id: str | None, ai, settings,
                  ledger=None, code: str = "") -> list[dict]:
    if len(req_ids) > settings.limits.max_requirements_per_diagnosis:
        raise AIError(f"1回の診断は最大{settings.limits.max_requirements_per_diagnosis}要件までです。")
    prompt, refmap, _ = build_diagnosis_input(project, req_ids, product_id, settings)
    res = execute(ai, "diagnose", prompt, DIAG_SCHEMA, settings.limits.max_ai_output_tokens, settings, ledger, code)
    return apply_diagnosis(project, res.data, refmap, product_id, allowed_req_ids=req_ids)


# ---------------- 依頼書 ----------------
def build_request_input(project: dict, req_id: str, run_ids: list[str] | None = None) -> tuple[str, dict]:
    req = find(project, "requirements", req_id)
    dg = rules.current_diagnosis(project, req_id)
    refmap, lines = {}, []
    if dg:
        for ev in dg.get("evidence", []):
            key = f"E{len(refmap) + 1}"
            refmap[key] = {k: v for k, v in ev.items() if k not in ("quote", "kind")}
            refmap[key]["_kind"] = ev.get("kind")
            lines.append(f"[{key}] {evidence_label(project, ev)}")
    qs = [q for q in project["questions"] if req_id in q.get("req_ids", []) and q.get("answer_text")]
    ans = [f"質問 {q['id']}：{q['question']}\n回答（{q['status']}）：{q['answer_text']}" for q in qs]
    runs = []
    for rid in run_ids or []:
        r = find(project, "runs", rid)
        if r:
            t = find(project, "tests", r["test_id"])
            runs.append(f"実施 {r['id']}（テスト {r['test_id']} 第{r['test_version']}版「{t['title'] if t else ''}」）"
                        f" 結果:{r['result']} 実際の動き:{r['actual']} 不具合メモ:{r['defect']}")
    acts = [f"{a['type']}（{a['status']}）：{a['reason']}" for a in project["actions"] if a["req_id"] == req_id]
    prompt = ("次の情報から、ベンダーへの改修・設定変更・調査の依頼書の下書きを作成してください。"
              "資料・発言だけの懸念と、テストで実際に発生した現象を区別してください。"
              "費用・工期・内部実装は書かず、不明点は前提・未確定事項と相手への質問にしてください。\n\n"
              + data_block("要件", json.dumps({k: req.get(k) for k in ("id", "version", "business", "workflow", "rules",
                                                                        "exceptions", "priority", "reason")},
                                              ensure_ascii=False))
              + "\n\n" + data_block("診断", json.dumps({k: dg.get(k) for k in ("category", "reason", "met_conditions",
                                                                                "remaining_conditions", "test_conditions", "plan_conditions")},
                                                      ensure_ascii=False) if dg else "なし")
              + "\n\n" + data_block("根拠", "\n".join(lines) or "なし")
              + "\n\n" + data_block("質問と回答", "\n".join(ans) or "なし")
              + "\n\n" + data_block("対応方法", "\n".join(acts) or "なし")
              + "\n\n" + data_block("テスト結果", "\n".join(runs) or "なし（資料診断段階）"))
    return prompt, refmap


def run_request_draft(project: dict, req_id: str, kind: str, ai, settings, run_ids=None, ledger=None,
                      code: str = "", to: str = "") -> dict:
    prompt, refmap = build_request_input(project, req_id, run_ids)
    res = execute(ai, "draft_request", prompt, REQUEST_SCHEMA, 8000, settings, ledger, code)
    d = res.data
    ev = []
    for e in d.get("evidence", []):
        ref = refmap.get(e.get("ref", ""))
        if ref:
            kind_ev = ref.pop("_kind", None) or "資料の記載"
            ev.append({**ref, "quote": e.get("quote", ""), "kind": kind_ev})
    dg = rules.current_diagnosis(project, req_id)
    fields = {k: d.get(k, "") for k in rules.REQUEST_FIELDS if k in d}
    fields.update({"kind": kind, "phase": "テストで発生した現象" if run_ids else "資料診断段階の懸念",
                   "req_ids": [req_id], "diag_ids": [dg["id"]] if dg else [], "run_ids": run_ids or [],
                   "test_ids": sorted({find(project, 'runs', r)['test_id'] for r in (run_ids or []) if find(project, 'runs', r)}),
                   "evidence": ev, "to": to, "desired_date": ""})
    return rules.add_request(project, fields, origin="AI生成")


# ---------------- テスト ----------------
def build_test_input(project: dict, req_id: str, request_id: str | None) -> str:
    req = find(project, "requirements", req_id)
    dg = rules.current_diagnosis(project, req_id)
    cr = find(project, "requests", request_id) if request_id else None
    return ("次の要件について、受入テスト仕様（そのまま実施できる完成度）を作成してください。"
            "通常操作・例外・境界値・権限・承認/差し戻し・設定/改修箇所・関連する既存動作の再確認から、要件に根拠のある観点をすべて選び、"
            "各テストに事前条件・具体的なテストデータ・番号付き手順・確認できる期待結果・合否判定基準を書いてください。"
            "画面名・ボタン名・設定方法が資料にない場合は、業務の操作として書き、存在しない画面を作らないでください。" + chr(10) * 2
            + data_block("要件", json.dumps({k: req.get(k) for k in ("id", "version", "business", "workflow", "role",
                                                                      "rules", "exceptions", "inputs", "outputs")},
                                            ensure_ascii=False))
            + "\n\n" + data_block("診断", json.dumps({k: dg.get(k) for k in ("category", "met_conditions",
                                                                              "remaining_conditions", "test_conditions", "plan_conditions")},
                                                    ensure_ascii=False) if dg else "なし")
            + "\n\n" + data_block("依頼書の受入条件", (cr or {}).get("acceptance_criteria", "") or "なし"))


def apply_tests(project: dict, req_id: str, data: dict, request_id: str | None, origin: str, limit: int) -> list[dict]:
    out = []
    for item in data.get("tests", [])[:limit]:
        t = rules.add_test(project, {**item, "req_ids": [req_id], "request_ids": [request_id] if request_id else [],
                                     "expected_confirmed": False}, origin=origin)
        out.append(t)
    return out


def run_tests(project: dict, req_id: str, ai, settings, request_id=None, ledger=None, code: str = "") -> list[dict]:
    prompt = build_test_input(project, req_id, request_id)
    res = execute(ai, "generate_tests", prompt, TEST_SCHEMA, 12000, settings, ledger, code)
    return apply_tests(project, req_id, res.data, request_id, "AI生成", settings.limits.max_tests_per_generation)


def build_tests_input(project: dict, req_ids: list[str]) -> str:
    """複数の要件のテスト仕様をまとめて作るための入力。要件・診断・依頼書の受入条件を渡す。"""
    from ..core import primary_product

    prod = primary_product(project) or {}
    blocks = []
    for rid in req_ids:
        req = find(project, "requirements", rid)
        if not req:
            continue
        dg = rules.current_diagnosis(project, rid)
        acc = [c["acceptance_criteria"] for c in project["requests"] if rid in c.get("req_ids", []) and c.get("acceptance_criteria")]
        blocks.append(json.dumps({"req_id": rid, "version": req["version"], "business": req["business"],
                                  "workflow": req["workflow"], "role": req["role"], "rules": req["rules"],
                                  "exceptions": req["exceptions"], "inputs": req["inputs"], "outputs": req["outputs"],
                                  "priority": req["priority"],
                                  "diagnosis": {k: dg.get(k) for k in ("category", "met_conditions", "remaining_conditions", "test_conditions",
                                                                       "plan_conditions")} if dg else None,
                                  "acceptance_criteria": acc}, ensure_ascii=False))
    return ("次の自社の要件について、受入テスト仕様（そのまま実施できる完成度）を作成してください。"
            "要件ごとに、通常操作・例外・境界値（金額の境目・上限件数・期限など）・権限・承認/差し戻し・設定/改修箇所・"
            "関連する既存動作の再確認から、要件に根拠のある観点をすべて選び（診断の test_conditions は必ずテストにする）、各テストに req_id・事前条件・具体的なテストデータ・"
            "番号付き手順・確認できる期待結果・合否判定基準・根拠を書いてください。画面名・ボタン名・設定方法が資料にない場合は、"
            "業務の操作として書き、存在しない画面を作らないでください。" + chr(10) * 2
            + f"対象製品：{prod.get('name', '未登録')}（版：{prod.get('edition') or '未記入'}／プラン：{prod.get('plan') or '未記入'}）"
            + chr(10) * 2 + data_block("自社の要件と診断", chr(10).join(blocks)))


def run_tests_multi(project: dict, req_ids: list[str], ai, settings, ledger=None, code: str = "") -> list[dict]:
    """確定した要件のテスト仕様をAIでまとめて作る（下書き）。既存のテストは上書きしない。"""
    prompt = build_tests_input(project, req_ids)
    res = execute(ai, "generate_tests", prompt, TEST_MULTI_SCHEMA, 16000, settings, ledger, code)
    return apply_tests_multi(project, res.data, req_ids, "AI生成", settings.limits.max_tests_per_generation)


def apply_tests_multi(project: dict, data: dict, req_ids: list[str], origin: str, limit: int) -> list[dict]:
    out = []
    for item in data.get("tests", [])[:limit]:
        item = dict(item)
        rid = item.pop("req_id", "")
        if rid not in req_ids:
            continue
        out.append(rules.add_test(project, {**item, "req_ids": [rid], "expected_confirmed": False}, origin=origin))
    return out


def run_split(project: dict, text: str, ai, settings, ledger=None, code: str = "") -> list[dict]:
    res = execute(ai, "split_requirements", split_prompt(text), SPLIT_SCHEMA, 8000, settings, ledger, code)
    return apply_split(project, text, res.data)


def keyword_candidates_report(project: dict, req_id: str, product_id: str | None) -> list[dict]:
    """AI を使わない関連箇所の検索結果（候補表示用）。見つからない＝機能なし ではない。"""
    req = find(project, "requirements", req_id)
    return with_context(candidates(project, req, product_id)) if req else []


__all__ = ["estimate_cost_jpy", "execute", "run_diagnosis", "run_request_draft", "run_tests", "run_split",
           "build_diagnosis_input", "apply_diagnosis", "apply_tests", "apply_split", "keyword_candidates_report",
           "now_iso"]



# ---------------- AIの聞き取り（BL-001 案B） ----------------
UNKNOWN_ANSWER = "分からない・未定"
INTERVIEW_MAX_CHARS = 8000  # 製品資料の抜粋の上限（費用を抑える）
NL = "\n"


def build_interview_input(project: dict, business: str, product_id: str | None) -> str:
    """製品資料（分析の対象に選んだ箇所だけ）と案件の情報から、聞き取りの質問を作るための入力。"""
    prod = find(project, "products", product_id) if product_id else None
    pj = project["project"]
    lines, used = [], 0
    for src in project["sources"]:
        if src["owner"] != "製品" or src["status"] != "有効":
            continue
        for g in src["segments"]:
            if not g.get("selected"):
                continue  # 未選択の箇所・ノートは送らない
            line = f"[{src['name']} {g['loc_label']}] {g['text']}"
            if used + len(line) > INTERVIEW_MAX_CHARS:
                break
            lines.append(line)
            used += len(line)
    for rec in project["recordings"]:
        for u in rec.get("utterances", []):
            if not (u.get("selected", True) and u.get("speaker_confirmed") and u.get("review_status") == "確認済み"):
                continue  # 人が確認していない発言は送らない
            line = f"[録画 {fmt_ts(u.get('start'))} {u.get('speaker_role') or '話者未分類'}] {u.get('edited_text') or u['raw_text']}"
            if used + len(line) > INTERVIEW_MAX_CHARS:
                break
            lines.append(line)
            used += len(line)
    reqs = [f"- {r['business']}：{r['rules'] or r['workflow']}" for r in project["requirements"] if r["status"] != "廃止"]
    product_line = (f"検討中の製品：{prod['name']}（ベンダー：{prod['vendor']}、検討プラン：{prod['plan'] or '未記入'}）"
                    if prod else "検討中の製品：未登録")
    rules_text = NL.join([
        "あなたは、業務システム導入の担当者から、自社の業務ルールを聞き取るインタビュアーです。"
        f"聞き取る業務は「{business}」です。"
        "この製品が自社で使えるかを確かめるために、自社について聞くべき質問を5〜8問作ってください。",
        "- 製品資料に書かれた機能・設定・制限（金額条件、例外、権限、件数の上限、保存期間、プランの違いなど）と照合できるよう、"
        "自社のルールを具体的な値で答えられる質問にしてください（例：境目の金額、ちょうどの金額はどちら側か）。",
        "- 製品の機能を前提に誘導しないでください。自社が本来どうしたいかを聞きます（製品に合わせて答えさせない）。",
        "- 1つの質問で1つのことだけを聞いてください。専門用語は使わず、短く書いてください。",
        "- 既に登録済みの要件と同じことは聞かないでください。",
        f"- choice の選択肢に「{UNKNOWN_ANSWER}」は入れないでください（画面で必ず追加します）。",
    ])
    info = NL.join([f"案件名：{pj.get('name', '')}", f"対象業務：{pj.get('target_business', '')}",
                    f"導入目的：{pj.get('purpose', '')}", f"制約条件：{pj.get('constraints', '')}"])
    return (NL * 2).join([
        product_line, rules_text,
        data_block("案件の情報", info),
        data_block("登録済みの自社の要件", NL.join(reqs) or "なし"),
        data_block("製品の資料・確認済みの営業説明（分析の対象に選んだ箇所のみ）", NL.join(lines) or "なし"),
    ])


def run_interview(project: dict, business: str, product_id: str | None, ai, settings, ledger=None,
                  code: str = "") -> list[dict]:
    """AIが聞き取りの質問を作る（質問は案件に保存しない。回答から要件の下書きを作るまでの一時的なもの）。"""
    prompt = build_interview_input(project, business, product_id)
    res = execute(ai, "interview", prompt, INTERVIEW_SCHEMA, 4000, settings, ledger, code)
    out = []
    for q in res.data.get("questions", [])[:10]:
        if not (q.get("question") or "").strip():
            continue
        typ = q.get("answer_type") if q.get("answer_type") in ("choice", "number", "text") else "text"
        opts = [o for o in (q.get("options") or []) if o and o != UNKNOWN_ANSWER]
        if typ == "choice" and len(opts) < 2:
            typ, opts = "text", []
        out.append({"topic": q.get("topic", ""), "question": q["question"].strip(), "why": q.get("why", ""),
                    "answer_type": typ, "options": opts, "unit": (q.get("unit") or "").strip() if typ == "number" else ""})
    return out


def interview_transcript(questions: list[dict], answers: dict) -> str:
    """質問と回答を、要件の「元の文章」として残す形にまとめる（回答していない質問は含めない）。"""
    rows = []
    for i, q in enumerate(questions):
        a = answers.get(i)
        if a is None or str(a).strip() == "":
            continue
        unit = q.get("unit", "") if q.get("answer_type") == "number" and a != UNKNOWN_ANSWER else ""
        rows.append(f"質問：{q['question']}{NL}回答：{a}{unit}")
    return (NL * 2).join(rows)


def interview_split_prompt(transcript: str) -> str:
    return ("次は、自社の担当者に業務ルールを聞き取った記録です。回答の内容だけをもとに、確認しやすい要件の単位にまとめてください。"
            f"回答が「{UNKNOWN_ANSWER}」の点は、推測で埋めずに open_issues に「未定：（質問の内容）」と書いてください。"
            "回答にない数値・条件を補わないでください。金額・以上/未満・禁止・例外は回答どおりに保持してください。"
            "original_text には、根拠にした質問と回答をそのまま書いてください。"
            + NL * 2 + data_block("聞き取りの記録", transcript))


def run_interview_split(project: dict, transcript: str, ai, settings, ledger=None, code: str = "") -> list[dict]:
    """聞き取りの記録から、要件の下書きを作る（人が確認・確定する）。"""
    res = execute(ai, "split_requirements", interview_split_prompt(transcript), SPLIT_SCHEMA, 8000, settings, ledger, code)
    return apply_split(project, transcript, res.data, origin="AIの聞き取り")
