import pytest

from forge.build import main, parse_sites
from forge.dataset import read_samples

PAGE = """<!doctype html><html><body style="margin:0">
<div style="width:400px">
<div style="height:120px;background:#c0392b"></div>
<div style="height:120px;background:#2980b9"></div>
<p>Some text</p>
</div></body></html>"""


def test_parse_sites():
    assert parse_sites(["a=http://x.com/?q=1", "b=file:///p.html"]) == {
        "a": "http://x.com/?q=1",
        "b": "file:///p.html",
    }


@pytest.mark.parametrize("bad", ["noequals", "=url", "name="])
def test_parse_sites_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        parse_sites([bad])


def test_main_builds_and_prints_summary(tmp_path, capsys):
    page = tmp_path / "page.html"
    page.write_text(PAGE, encoding="utf-8")
    samples = tmp_path / "samples.jsonl"
    code = main(
        [
            "--site", f"demo={page.as_uri()}",
            "--viewports", "mobile",
            "--bug-types", "OVERFLOW",
            "--seeds", "1",
            "--threshold", "0",
            "--out-dir", str(tmp_path / "raw"),
            "--samples", str(samples),
        ]
    )  # fmt: skip
    assert code == 0
    assert "accepted=1" in capsys.readouterr().out
    assert len(read_samples(samples)) == 1


def test_main_rejects_malformed_site():
    with pytest.raises(SystemExit):
        main(["--site", "oops"])