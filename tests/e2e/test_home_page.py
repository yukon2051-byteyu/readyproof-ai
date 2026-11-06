"""トップページの E2E テスト。実行方法は test_result_page.py と同じ（RP_E2E=1）。"""
import os

import pytest

from e2e_support import ai_password, app_url, browser, no_paid_api  # noqa: F401（pytest の fixture として使う）

pytestmark = pytest.mark.skipif(os.environ.get("RP_E2E") != "1", reason="RP_E2E=1 のときだけ実行する")
WIDE = "() => { const m = document.querySelector('[data-testid=\"stMain\"]'); return m.scrollWidth > m.clientWidth + 1 }"


def open_home(browser, url, width=1440, height=900):
    pg = browser.new_page(viewport={"width": width, "height": height})
    pg.goto(url + "/", wait_until="domcontentloaded")
    pg.wait_for_selector(".rp-hero", timeout=90000)
    pg.wait_for_timeout(2500)
    return pg


@pytest.mark.parametrize("width,height", [(1440, 900), (1024, 768), (390, 844)])
def test_hero_layout_and_links(browser, app_url, width, height):
    pg = open_home(browser, app_url, width, height)
    assert not pg.evaluate(WIDE)
    hero = pg.locator(".rp-hero").bounding_box()
    tag, viz = pg.locator(".rp-hero .tag").bounding_box(), pg.locator(".rp-hero .viz").bounding_box()
    assert tag["x"] + tag["width"] <= hero["x"] + hero["width"] and viz["x"] + viz["width"] <= hero["x"] + hero["width"]
    if width == 1440:
        assert hero["height"] < 470 and viz["x"] > tag["x"] + tag["width"] - 1  # 2カラム
        assert abs((viz["y"] + viz["height"] / 2) - (hero["y"] + hero["height"] / 2)) < 12  # 上下中央
    else:
        assert viz["y"] > tag["y"] + tag["height"]  # 縦並びで文章が先
    assert pg.get_by_text("イメージ（架空の例）").is_visible()
    for name, sel in (("3分デモを体験する", "#rp-demo"), ("自社の案件で試す", "#rp-own")):
        pg.get_by_role("link", name=name).click()
        pg.wait_for_timeout(800)
        y = pg.locator(sel).bounding_box()["y"]
        assert 0 <= y < height
        assert "/product" not in pg.url  # デモを勝手に始めない
    pg.close()


@pytest.mark.parametrize("width,height", [(1920, 1080), (1440, 900), (1280, 853), (1100, 768), (1024, 768)])
def test_flow_stays_on_one_row_on_pc(browser, app_url, width, height):
    pg = open_home(browser, app_url, width, height)
    ys = {round(c.bounding_box()["y"]) for c in pg.locator(".rp-flow5 .rp-card").all()}
    assert len(ys) == 1  # 5枚が1段に収まる
    assert not pg.evaluate(WIDE)
    pg.close()


def test_keyboard_focus_reaches_hero_links(browser, app_url):
    pg = open_home(browser, app_url)
    link = pg.get_by_role("link", name="3分デモを体験する")
    link.focus()
    assert link.evaluate("e => e === document.activeElement")
    pg.keyboard.press("Enter")
    pg.wait_for_timeout(800)
    assert pg.url.endswith("#rp-demo")
    pg.close()


@pytest.mark.parametrize("title", ["経費精算サービスの導入", "製造業の生産・在庫管理システムの導入", "社内アカウント管理サービスの導入"])
def test_each_demo_starts(browser, app_url, title):
    pg = open_home(browser, app_url)
    pg.locator('[data-testid="stSelectbox"]').first.click()
    pg.get_by_role("option", name=title).click()
    pg.wait_for_timeout(2000)
    pg.get_by_role("button", name="3分デモを始める").click()
    pg.wait_for_selector(".rp-stepper", timeout=60000)
    assert "/product" in pg.url and pg.get_by_text("製品の資料", exact=True).first.is_visible()
    pg.close()


def test_create_own_project_needs_password_and_sidebar_works(browser, app_url, ai_password):
    pg = open_home(browser, app_url)
    create = pg.get_by_role("button", name="作成する")
    pg.get_by_label("案件名").fill("E2E確認用の案件")
    pg.get_by_label("案件名").press("Tab")
    pg.wait_for_timeout(1500)
    assert create.is_disabled()
    box = pg.get_by_role("textbox", name="AIパスワード")
    box.fill("wrong")
    box.press("Enter")
    pg.wait_for_timeout(2000)
    assert pg.get_by_text("AIパスワードが正しくありません").count() == 1 and create.is_disabled()
    box.fill(ai_password)
    box.press("Enter")
    pg.wait_for_timeout(2000)
    assert create.is_enabled()
    create.click()
    pg.wait_for_selector(".rp-stepper", timeout=30000)
    assert "/product" in pg.url
    pg.locator('[data-testid="stSidebarNav"]').get_by_text("② 自社のルール").first.click()
    pg.wait_for_timeout(3000)
    assert "/rules" in pg.url
    pg.locator('[data-testid="stSidebarNav"]').get_by_text("ホーム").first.click()
    pg.wait_for_selector(".rp-hero", timeout=30000)
    pg.close()
