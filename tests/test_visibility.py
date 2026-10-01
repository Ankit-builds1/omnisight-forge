import pytest
from playwright.sync_api import sync_playwright

from forge.mutations import MUTATIONS

VIEWPORT = {"width": 400, "height": 300}
HTML = """<!doctype html><html><body style="margin:0">
<div style="width:300px">
<div style="height:100px;background:#c0392b">Top box</div>
<p>Visible paragraph text here</p>
</div>
<div style="height:3000px"></div>
<div style="width:300px">
<div style="height:100px;background:#2980b9">Far box</div>
<p>Far paragraph text here</p>
</div></body></html>"""
TOP_JS = "(selector) => document.querySelector(selector).getBoundingClientRect().top"


@pytest.mark.parametrize("bug_type", sorted(MUTATIONS))
def test_mutation_targets_only_elements_inside_the_viewport(bug_type):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        for seed in range(4):
            page.set_content(HTML)
            mutation = MUTATIONS[bug_type](page, seed=seed)
            top = page.evaluate(TOP_JS, mutation.target_selector)
            assert top < VIEWPORT["height"]
        browser.close()

HIDDEN_HTML = """<!doctype html><html><body style="margin:0">
<nav style="position:absolute;left:-300px;top:0;width:250px">
<h4>Offscreen heading</h4><p style="margin:0">Offscreen paragraph text</p></nav>
<div style="opacity:0"><div style="height:40px;background:#c0392b">Faded box</div>
<p style="margin:0">Faded paragraph text</p></div>
<div style="visibility:hidden"><div style="height:40px;background:#8e44ad">Hidden box</div>
<p style="margin:0">Hidden paragraph text</p></div>
<div id="shown" style="width:300px"><div style="height:40px;background:#2980b9">Shown box</div>
<p style="margin:0">Shown paragraph text</p></div>
</body></html>"""
INSIDE_SHOWN_JS = "(sel) => document.querySelector(sel).closest('#shown') !== null"

CLIP_HTML = """<!doctype html><html><body style="margin:0">
<div style="width:300px;overflow:hidden"><p style="margin:0">Clipped paragraph text</p></div>
<div style="width:300px"><div style="width:200px">
<div style="width:100px;height:20px;background:#27ae60"></div></div></div>
<div style="width:300px"><p style="margin:0">Free paragraph text</p></div>
</body></html>"""
OVERFLOW_OK_JS = """
(sel) => {
  const el = document.querySelector(sel);
  const s = getComputedStyle(el);
  const ownText = Array.from(el.childNodes).some(
    (n) => n.nodeType === 3 && n.textContent.trim().length > 0
  );
  const painted = s.backgroundColor !== 'rgba(0, 0, 0, 0)' || parseFloat(s.borderTopWidth) > 0;
  for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
    if (getComputedStyle(a).overflowX !== 'visible') return false;
  }
  return ownText || painted;
}
"""


@pytest.mark.parametrize("bug_type", sorted(MUTATIONS))
def test_mutation_skips_offscreen_and_hidden_elements(bug_type):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        for seed in range(6):
            page.set_content(HIDDEN_HTML)
            mutation = MUTATIONS[bug_type](page, seed=seed)
            assert page.evaluate(INSIDE_SHOWN_JS, mutation.target_selector), mutation
        browser.close()


def test_overflow_targets_painted_unclipped_elements():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)
        for seed in range(8):
            page.set_content(CLIP_HTML)
            mutation = MUTATIONS["OVERFLOW"](page, seed=seed)
            assert page.evaluate(OVERFLOW_OK_JS, mutation.target_selector), mutation
        browser.close()