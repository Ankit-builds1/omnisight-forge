import pytest
from playwright.sync_api import sync_playwright

from forge.mutations import inject_bug
from forge.report import check_page, write_report

HTML = """<!doctype html>
<html><body style="margin:0">
<div id="wrap" style="width:400px;padding:10px">
  <div id="one" style="height:40px;background:#ccd">One</div>
  <p id="two" style="height:30px;margin:8px 0;background:#cdc">Two two two</p>
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
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.set_content(HTML)
    yield page
    page.close()


def width(page, selector):
    return page.evaluate("(s) => document.querySelector(s).getBoundingClientRect().width", selector)


def test_a_clean_page_has_no_findings(page, tmp_path):
    assert check_page(page, "desktop", tmp_path) == []


def test_finds_and_pictures_an_overflow(page, tmp_path):
    inject_bug(page, "#two", "width: 900px")
    findings = check_page(page, "desktop", tmp_path)
    assert [(f.kind, f.property, f.value) for f in findings] == [("overflow", "width", "auto")]
    assert (tmp_path / findings[0].before).exists()
    assert (tmp_path / findings[0].after).exists()


def test_the_page_is_left_as_it_was(page, tmp_path):
    inject_bug(page, "#two", "width: 900px")
    check_page(page, "desktop", tmp_path)
    assert width(page, "#two") == 900


def test_report_lists_findings(page, tmp_path):
    inject_bug(page, "#two", "height: 6px; overflow: hidden")
    findings = check_page(page, "desktop", tmp_path)
    path = write_report("https://example.com", findings, ["desktop"], tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "height: auto;" in text
    assert "1 finding(s)" in text


def test_report_says_when_nothing_is_found(tmp_path):
    text = write_report("https://example.com", [], ["mobile"], tmp_path).read_text("utf-8")
    assert "No layout symptom found." in text
