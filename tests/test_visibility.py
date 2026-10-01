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