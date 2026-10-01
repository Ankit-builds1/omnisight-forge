import pytest
from PIL import Image, ImageDraw

from forge.quality import DEFAULT_THRESHOLD, ImageSizeError, passes_quality_filter, visual_diff


def make_image(path, size=(200, 200), box=None, pixel=None):
    img = Image.new("RGB", size, "white")
    if box:
        ImageDraw.Draw(img).rectangle(box, fill="black")
    if pixel:
        img.putpixel(pixel, (0, 0, 0))
    img.save(path)
    return path


def test_identical_images_score_zero(tmp_path):
    a = make_image(tmp_path / "a.png")
    b = make_image(tmp_path / "b.png")
    assert visual_diff(a, b) == pytest.approx(0.0)


def test_clear_difference_passes_filter(tmp_path):
    a = make_image(tmp_path / "a.png")
    b = make_image(tmp_path / "b.png", box=(50, 50, 150, 150))
    score = visual_diff(a, b)
    assert 0.0 <= score <= 1.0
    assert score > DEFAULT_THRESHOLD
    assert passes_quality_filter(score)


def test_tiny_change_is_filtered_out(tmp_path):
    a = make_image(tmp_path / "a.png")
    b = make_image(tmp_path / "b.png", pixel=(100, 100))
    score = visual_diff(a, b)
    assert 0.0 < score < DEFAULT_THRESHOLD
    assert not passes_quality_filter(score)


def test_size_mismatch_raises(tmp_path):
    a = make_image(tmp_path / "a.png", size=(200, 200))
    b = make_image(tmp_path / "b.png", size=(100, 100))
    with pytest.raises(ImageSizeError):
        visual_diff(a, b)


def test_threshold_boundary():
    assert passes_quality_filter(0.05, threshold=0.05)
    assert not passes_quality_filter(0.049, threshold=0.05)


def test_faint_colour_noise_is_ignored(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    Image.new("RGB", (50, 50), (255, 255, 255)).save(a)
    Image.new("RGB", (50, 50), (252, 252, 252)).save(b)
    assert visual_diff(a, b) == 0.0