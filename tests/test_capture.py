import pytest
from PIL import Image

from forge.capture import VIEWPORTS, capture_page

HTML = '<!doctype html><html><body><h1 id="title">Hello Forge</h1></body></html>'


@pytest.mark.parametrize("viewport", sorted(VIEWPORTS))
def test_capture_page_saves_screenshot_and_dom(tmp_path, viewport):
    page_file = tmp_path / "index.html"
    page_file.write_text(HTML, encoding="utf-8")

    result = capture_page(
        page_file.as_uri(),
        viewport=viewport,
        out_dir=tmp_path / "out",
        name="demo",
    )

    width, height = VIEWPORTS[viewport]
    assert result.screenshot_path.exists()
    assert result.dom_path.exists()
    assert 'id="title"' in result.dom_html
    with Image.open(result.screenshot_path) as img:
        assert img.size == (width, height)


def test_unknown_viewport_raises(tmp_path):
    with pytest.raises(ValueError):
        capture_page("about:blank", viewport="watch", out_dir=tmp_path)