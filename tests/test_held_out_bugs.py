import pytest
from playwright.sync_api import sync_playwright

from forge.mutations import (
    HELD_OUT_BUG_TYPES,
    LIFT,
    MUTATIONS,
    NOWRAP,
    SHIFT,
    TRAIN_BUG_TYPES,
    apply_declaration,
    mutate_lift,
    mutate_nowrap,
    mutate_shift,
)

HTML = """<!doctype html>
<html><body style="margin:0">
<div id="wrap" style="width:400px;padding:10px">
  <div style="height:40px;background:#ccd">One</div>
  <p style="margin:8px 0;background:#cdc">This paragraph is long enough to wrap onto a second
  line inside a box that is only four hundred pixels wide.</p>
  <div style="height:40px;background:#dcc">Three</div>
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


def box(page, selector):
    return page.evaluate(
        "(s) => { const r = document.querySelector(s).getBoundingClientRect();"
        " return [r.left, r.top, r.right]; }",
        selector,
    )


def test_held_out_types_are_separate_from_training_types():
    assert set(HELD_OUT_BUG_TYPES).isdisjoint(TRAIN_BUG_TYPES)
    assert set(HELD_OUT_BUG_TYPES) | set(TRAIN_BUG_TYPES) == set(MUTATIONS)


@pytest.mark.parametrize(
    ("mutate", "bug_type", "prop"),
    [(mutate_shift, SHIFT, "left"), (mutate_lift, LIFT, "transform"),
     (mutate_nowrap, NOWRAP, "white-space")],
)
def test_held_out_bug_breaks_the_page_and_gold_fix_restores_it(page, mutate, bug_type, prop):
    before = page.evaluate("() => document.body.scrollWidth")
    mutation = mutate(page, seed=0)
    assert (mutation.bug_type, mutation.property) == (bug_type, prop)
    assert mutation.broken_css.split(":")[0] not in page.content()  # bug is not in the HTML
    apply_declaration(page, mutation.target_selector, mutation.gold_fix)
    assert page.evaluate("() => document.body.scrollWidth") == before


def test_shift_moves_the_element_without_changing_its_width(page):
    mutation = mutate_shift(page, seed=0)
    assert "width" not in mutation.broken_css
    left, _, _ = box(page, mutation.target_selector)
    apply_declaration(page, mutation.target_selector, mutation.gold_fix)
    assert box(page, mutation.target_selector)[0] < left


def test_lift_uses_a_transform_not_a_margin(page):
    mutation = mutate_lift(page, seed=0)
    assert mutation.broken_css.startswith("transform: translateY(-")
    assert "margin" not in mutation.broken_css
