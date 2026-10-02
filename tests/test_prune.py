from playwright.sync_api import sync_playwright

from forge.pipeline import prune_offscreen

HTML = """<!doctype html><html><body style="margin:0">
<div class="top" style="height:100px">Top box text</div>
<div style="height:3000px"></div>
<div class="far" data-x="1"><p>Far paragraph text</p></div>
<div class="after">After far text</div>
</body></html>"""


def test_prune_empties_offscreen_elements_but_keeps_tags():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 300})
        page.set_content(HTML)
        prune_offscreen(page)
        html = page.content()
        browser.close()
    assert "Top box text" in html
    assert 'class="top"' in html
    assert "Far paragraph text" not in html
    assert "After far text" not in html
    assert 'class="far"' not in html
    assert html.count("<div") == 4

HIDDEN_HTML = """<!doctype html><html><body style="margin:0">
<div class="shown">Shown text</div>
<div class="menu" style="visibility:hidden"><a>Hidden menu link</a></div>
<div class="faded" style="opacity:0"><a>Faded menu link</a></div>
</body></html>"""


def test_prune_empties_hidden_elements_inside_the_viewport():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 300})
        page.set_content(HIDDEN_HTML)
        prune_offscreen(page)
        html = page.content()
        browser.close()
    assert "Shown text" in html
    assert "Hidden menu link" not in html
    assert "Faded menu link" not in html
    assert html.count("<div") == 3

KEEP_HTML = """<!doctype html><html><body style="margin:0">
<div class="wrap" style="visibility:hidden">
<p class="target" style="visibility:visible">Target text</p></div>
<div class="other" style="visibility:hidden">Other hidden text</div>
</body></html>"""


def test_prune_never_removes_the_target_or_its_parents():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 400, "height": 300})
        page.set_content(KEEP_HTML)
        prune_offscreen(page, keep="body > div:nth-of-type(1) > p:nth-of-type(1)")
        html = page.content()
        browser.close()
    assert "Target text" in html
    assert 'style="visibility:visible"' in html
    assert "Other hidden text" not in html