"""③ 診断結果の E2E テスト（実際のブラウザで操作する）。

実行：$env:RP_E2E="1"; .venv\\Scripts\\python -m pytest -q tests\\e2e
- 時間がかかり Chrome が必要なので、通常の pytest では実行しない
- 有料APIは呼ばない（デモは保存済みのAI出力を表示するだけ）
"""
import os
import re

import pytest

from e2e_support import app_url, browser, no_paid_api  # noqa: F401（pytest の fixture として使う）

pytestmark = pytest.mark.skipif(os.environ.get("RP_E2E") != "1", reason="RP_E2E=1 のときだけ実行する")


def open_demo(browser, url, width=1366, height=900):
    pg = browser.new_page(viewport={"width": width, "height": height})
    pg.goto(url + "/result?demo=demo1", wait_until="domcontentloaded")
    pg.wait_for_selector(".rp-sum", timeout=90000)
    pg.wait_for_timeout(2500)
    return pg


def open_req001(pg):
    card = pg.locator('[class*="st-key-rpbox_"]').filter(has_text="REQ-001").first
    card.get_by_role("button", name="詳細を見る").click()
    pg.get_by_text("診断と対応", exact=True).wait_for(timeout=15000)
    return card


def pick(pg, text):
    pg.locator('[data-testid="stButtonGroup"]').get_by_text(re.compile(text)).first.click()
    pg.wait_for_timeout(2500)


def test_summary_shows_conclusion_first(browser, app_url):
    pg = open_demo(browser, app_url)
    head = pg.locator(".rp-sum .head").inner_text()
    assert head == "必須要件2件は、製品の設定で対応できる見込みです"
    text = pg.locator(".rp-grid").first.inner_text()
    assert "9/9件" in text and "未診断" in text
    assert pg.get_by_role("button", name="閉じる").count() == 0  # 最初はすべて閉じている
    assert pg.get_by_role("button", name="詳細を見る").count() == 3
    pg.close()


def test_filter_and_sort(browser, app_url):
    pg = open_demo(browser, app_url)
    cards = "n => document.querySelectorAll('.rp-rq').length === n"
    pick(pg, "未診断（1）")
    pg.wait_for_function(cards, arg=1, timeout=20000)
    assert "代理承認" in pg.locator(".rp-rq").first.inner_text()
    pick(pg, "対応可能な見込み（2）")
    pg.wait_for_function(cards, arg=2, timeout=20000)
    pick(pg, "対応困難（0）")
    pg.get_by_text("条件に合う要件はありません").wait_for(timeout=20000)
    pg.close()


def test_detail_tabs_keep_evidence_and_history(browser, app_url):
    pg = open_demo(browser, app_url)
    open_req001(pg)
    pick(pg, "根拠資料（7）")
    assert pg.get_by_role("button", name="この根拠を外す").count() == 7
    assert pg.get_by_role("button", name="この根拠を外す").first.is_disabled()  # デモでは押せない
    assert pg.locator("mark.rp-mark").count() >= 1  # 引用箇所の印
    pick(pg, "確認・質問履歴（2）")
    body = pg.locator('[data-testid="stMain"]').inner_text()
    assert "Q-001" in body and "Q-002" in body and "部門長" in body
    assert pg.get_by_role("button", name="確認結果を記録").is_disabled()
    pick(pg, "対応・依頼")
    assert pg.get_by_role("button", name="この要件について質問を作る").is_disabled()
    pick(pg, "確認・質問履歴（2）")  # 面を戻しても開いた要件は保たれる
    assert pg.get_by_role("button", name="閉じる").count() == 1
    pg.get_by_role("button", name="閉じる").click()
    pg.wait_for_timeout(2500)
    assert pg.get_by_role("button", name="詳細を見る").count() == 3
    pg.close()


def test_next_action_and_next_page(browser, app_url):
    pg = open_demo(browser, app_url)
    pg.get_by_role("button", name="② 自社のルールへ").first.click()
    pg.wait_for_url("**/rules*", timeout=30000)
    pg.goto(app_url + "/result?demo=demo1", wait_until="domcontentloaded")
    pg.wait_for_selector(".rp-sum", timeout=90000)
    pg.wait_for_timeout(2000)
    pg.get_by_role("button", name="次へ：④ 受入テスト").click()
    pg.wait_for_url("**/tests*", timeout=30000)
    pg.close()


def test_phone_width_has_no_horizontal_scroll(browser, app_url):
    pg = open_demo(browser, app_url, width=390, height=844)
    wide = "() => { const m = document.querySelector('[data-testid=\"stMain\"]'); return m.scrollWidth > m.clientWidth + 1 }"
    assert not pg.evaluate(wide)
    box = pg.locator(".rp-sum .head").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390
    assert pg.locator('[data-testid="stSidebar"]').bounding_box()["x"] < 0 or not pg.locator('[data-testid="stSidebar"]').is_visible()
    open_req001(pg)
    pick(pg, "根拠資料（7）")
    assert not pg.evaluate(wide)
    pg.close()
