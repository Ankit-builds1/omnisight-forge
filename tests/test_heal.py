import pytest
from playwright.sync_api import sync_playwright

from forge.heal import find_symptoms, heal, healed_answer, scan_page
from forge.mutations import inject_bug

HTML = """<!doctype html>
<html><body style="margin:0">
<div id="wrap" style="width:400px;padding:10px">
  <div id="one" style="height:40px;background:#ccd">One</div>
  <p id="two" style="height:30px;margin:8px 0;background:#cdc">Two two two</p>
  <div id="three" style="height:40px;background:#dcc">Three</div>
</div>
</body></html>"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 800, "height": 600})
    page.set_content(HTML)
    yield page
    page.close()


def width(page, selector):
    return page.evaluate("(s) => document.querySelector(s).getBoundingClientRect().width", selector)


def test_a_clean_page_has_no_symptoms(page):
    assert find_symptoms(page, "#two") == []
    assert heal(page, "#two") is None


def test_heals_an_overflow_next_to_the_models_element(page):
    inject_bug(page, "#three", "width: 900px")
    repair = heal(page, "#two")
    assert repair.kind == "overflow"
    assert (repair.property, repair.value) == ("width", "auto")
    assert repair.distance == 2  # #two -> #wrap -> #three
    assert repair.selector.endswith("div:nth-of-type(2)")


def test_heals_an_overlap_with_margin_top(page):
    inject_bug(page, "#two", "margin-top: -30px")
    repair = heal(page, "#two")
    assert (repair.kind, repair.property, repair.value, repair.distance) == (
        "overlap", "margin-top", "0px", 0
    )


def test_heals_clipping_with_height_auto(page):
    inject_bug(page, "#two", "height: 6px; overflow: hidden")
    repair = heal(page, "#one")
    assert (repair.kind, repair.property, repair.value) == ("clipping", "height", "auto")


def test_trying_a_fix_leaves_the_page_unchanged(page):
    inject_bug(page, "#three", "width: 900px")
    heal(page, "#two")
    assert width(page, "#three") == 900


def test_text_hidden_on_purpose_is_not_a_symptom(page):
    page.evaluate(
        """() => {
          const sr = document.createElement('span');
          sr.textContent = 'Screen reader only';
          sr.style.cssText = 'position:absolute;width:1px;height:1px;overflow:hidden';
          const dots = document.createElement('div');
          dots.textContent = 'A long line of text that does not fit in this narrow box at all';
          dots.style.cssText = 'width:60px;height:12px;overflow:hidden;text-overflow:ellipsis';
          document.querySelector('#one').append(sr, dots);
        }"""
    )
    assert find_symptoms(page, "#one") == []


def test_a_bug_outside_the_radius_is_not_found(page):
    inject_bug(page, "#three", "width: 900px")
    assert heal(page, "#two", radius=1) is None


def test_healed_answer_keeps_the_model_answer_when_nothing_is_found(page):
    answer = {"selector": "#two", "property": "margin-top", "value": "0px"}
    assert healed_answer(page, answer) == answer


def test_scan_page_finds_a_bug_without_any_model(page):
    inject_bug(page, "#three", "width: 900px")
    repair = scan_page(page)
    assert (repair.kind, repair.property) == ("overflow", "width")


def test_whole_page_is_used_only_when_nothing_is_near(page):
    inject_bug(page, "#three", "width: 900px")
    assert healed_answer(page, None) is None
    healed = healed_answer(page, None, whole_page=True)
    assert (healed["property"], healed["value"]) == ("width", "auto")


def test_healed_answer_replaces_the_property(page):
    inject_bug(page, "#two", "width: 900px")
    answer = {"selector": "#two", "property": "margin-top", "value": "0px"}
    healed = healed_answer(page, answer)
    assert (healed["property"], healed["value"]) == ("width", "auto")
