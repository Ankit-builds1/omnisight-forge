import pytest
from playwright.sync_api import sync_playwright

from forge.mutations import (
    CLIPPING,
    MUTATIONS,
    OVERFLOW,
    OVERLAP,
    TRAIN_BUG_TYPES,
    MutationError,
    apply_declaration,
    mutate_clipping,
    mutate_overflow,
    mutate_overlap,
)

HTML = """<!doctype html>
<html><body style="margin:0">
<div id="wrap" style="width:400px;padding:10px">
  <div class="box" style="height:40px;background:#ccd">One</div>
  <p style="height:30px;margin:8px 0;background:#cdc">Two</p>
  <div class="box" style="height:40px;background:#dcc">Three</div>
</div>
</body></html>"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


@pytest.fixture
def make_page(browser):
    pages = []

    def _make():
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.set_content(HTML)
        pages.append(page)
        return page

    yield _make
    for page in pages:
        page.close()


def rect(page, selector):
    return page.evaluate(
        "(sel) => { const r = document.querySelector(sel).getBoundingClientRect();"
        " return [r.left, r.top, r.width, r.height]; }",
        selector,
    )


def edges(page, selector):
    return page.evaluate(
        "(sel) => { const el = document.querySelector(sel);"
        " return [el.getBoundingClientRect().right,"
        " el.parentElement.getBoundingClientRect().right]; }",
        selector,
    )


def test_overflow_mutation_fields(make_page):
    mutation = mutate_overflow(make_page(), seed=1)
    assert mutation.bug_type == OVERFLOW
    assert mutation.property == "width"
    assert mutation.broken_css.startswith("width:")
    assert mutation.gold_fix.startswith("width:")
    assert mutation.broken_css != mutation.gold_fix


def test_overflow_actually_overflows(make_page):
    page = make_page()
    mutation = mutate_overflow(page, seed=1)
    right, parent_right = edges(page, mutation.target_selector)
    assert right > parent_right


def test_gold_fix_restores_original_box(make_page):
    broken_page = make_page()
    mutation = mutate_overflow(broken_page, seed=1)
    original = rect(make_page(), mutation.target_selector)

    assert rect(broken_page, mutation.target_selector) != original
    apply_declaration(broken_page, mutation.target_selector, mutation.gold_fix)
    restored = rect(broken_page, mutation.target_selector)
    assert restored == pytest.approx(original, abs=0.5)


def test_same_seed_gives_same_mutation(make_page):
    assert mutate_overflow(make_page(), seed=7) == mutate_overflow(make_page(), seed=7)


def test_empty_page_raises(make_page):
    page = make_page()
    page.set_content("<!doctype html><html><body></body></html>")
    with pytest.raises(MutationError):
        mutate_overflow(page)

def test_registry_covers_tier_one_types():
    assert set(TRAIN_BUG_TYPES) == {"OVERFLOW", "OVERLAP", "CLIPPING"}


def test_overlap_mutation_overlaps_sibling(make_page):
    page = make_page()
    mutation = mutate_overlap(page, seed=1)
    assert mutation.bug_type == OVERLAP
    assert mutation.property == "margin-top"
    assert page.evaluate(
        "(sel) => { const el = document.querySelector(sel);"
        " const a = el.getBoundingClientRect();"
        " const b = el.previousElementSibling.getBoundingClientRect();"
        " return Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top); }",
        mutation.target_selector,
    )


def test_clipping_cuts_off_content(make_page):
    page = make_page()
    mutation = mutate_clipping(page, seed=1)
    assert mutation.bug_type == CLIPPING
    assert "overflow: hidden" in mutation.broken_css
    assert page.evaluate(
        "(sel) => { const el = document.querySelector(sel);"
        " return el.scrollHeight > el.clientHeight; }",
        mutation.target_selector,
    )


@pytest.mark.parametrize("bug_type", sorted(TRAIN_BUG_TYPES))
def test_every_mutation_gold_fix_restores_box(make_page, bug_type):
    mutate = MUTATIONS[bug_type]
    broken_page = make_page()
    mutation = mutate(broken_page, seed=3)
    assert mutation.bug_type == bug_type
    original = rect(make_page(), mutation.target_selector)

    assert rect(broken_page, mutation.target_selector) != original
    apply_declaration(broken_page, mutation.target_selector, mutation.gold_fix)
    assert rect(broken_page, mutation.target_selector) == pytest.approx(original, abs=0.5)


@pytest.mark.parametrize("bug_type", sorted(TRAIN_BUG_TYPES))
def test_bug_changes_the_layout_but_not_the_html(make_page, bug_type):
    clean = make_page()
    broken = make_page()
    mutation = MUTATIONS[bug_type](broken, seed=3)
    assert rect(broken, mutation.target_selector) != rect(clean, mutation.target_selector)
    assert broken.content() == clean.content()


def test_rejected_attempt_is_undone(make_page):
    from forge.mutations import _try_mutation

    page = make_page()
    selector = "body > div:nth-of-type(1) > p:nth-of-type(1)"
    before = rect(page, selector)
    assert not _try_mutation(page, selector, "width: 999px", "() => false")
    assert rect(page, selector) == before


@pytest.mark.parametrize("bug_type", sorted(TRAIN_BUG_TYPES))
def test_every_mutation_is_reproducible(make_page, bug_type):
    mutate = MUTATIONS[bug_type]
    assert mutate(make_page(), seed=5) == mutate(make_page(), seed=5)


@pytest.mark.parametrize("bug_type", sorted(TRAIN_BUG_TYPES))
def test_every_mutation_raises_on_empty_page(make_page, bug_type):
    page = make_page()
    page.set_content("<!doctype html><html><body></body></html>")
    with pytest.raises(MutationError):
        MUTATIONS[bug_type](page)