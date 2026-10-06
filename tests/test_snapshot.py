import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from forge.capture import capture_page, snapshot_path
from forge.pipeline import generate_sample
from forge.scoring import gold_answer
from forge.snapshot import main, record
from forge.verify import verify_fix

PAGE = """<!doctype html><html><body style="margin:0">
<div style="width:400px">
<div style="height:120px;background:#c0392b"></div>
<div style="height:120px;background:#2980b9"></div>
<p>Some text</p>
</div></body></html>"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def live_site(tmp_path):
    """A small local web site standing in for a live page that can change or go down."""
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text(PAGE, encoding="utf-8")
    handler = functools.partial(QuietHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield root, f"http://127.0.0.1:{server.server_port}/index.html", server
    server.shutdown()
    server.server_close()


def test_snapshot_path_is_one_file_per_site_and_viewport(tmp_path):
    assert snapshot_path(None, "wiki", "mobile") is None
    assert snapshot_path(tmp_path, "wiki", "mobile") == tmp_path / "wiki_mobile.zip"


def test_replay_shows_the_recorded_page_after_the_live_page_changed(live_site, tmp_path):
    root, url, _ = live_site
    har = snapshot_path(tmp_path / "snaps", "demo", "desktop")
    record(url, har, "desktop")
    (root / "index.html").write_text(PAGE.replace("Some text", "Edited text"), encoding="utf-8")

    replayed = capture_page(url, "desktop", tmp_path / "out", "demo", har=har)
    assert "Some text" in replayed.dom_html
    assert "Edited text" not in replayed.dom_html


def test_replay_works_with_the_site_down(live_site, tmp_path):
    _, url, server = live_site
    har = snapshot_path(tmp_path / "snaps", "demo", "mobile")
    record(url, har, "mobile")
    server.shutdown()
    server.server_close()

    replayed = capture_page(url, "mobile", tmp_path / "out", "demo", har=har)
    assert "Some text" in replayed.dom_html


def test_missing_snapshot_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        capture_page("http://127.0.0.1:9/", "mobile", tmp_path, "demo",
                     har=tmp_path / "none.zip")


def test_gold_fix_verifies_offline_after_the_live_page_changed(live_site, tmp_path):
    root, url, _ = live_site
    snaps = tmp_path / "snaps"
    record(url, snapshot_path(snaps, "demo", "desktop"), "desktop")
    sample = generate_sample(url, "demo", "desktop", "OVERLAP", seed=1,
                             out_dir=str(tmp_path / "out"), threshold=0.0, snapshots=snaps)
    (root / "index.html").write_text("<p>The site was redesigned</p>", encoding="utf-8")

    assert verify_fix(url, sample, gold_answer(sample), tmp_path / "v", snaps).fixed


def test_cli_records_every_viewport_and_keeps_old_snapshots(live_site, tmp_path, capsys):
    _, url, _ = live_site
    out = tmp_path / "snaps"
    args = ["--site", f"demo={url}", "--viewports", "mobile", "tablet", "--out", str(out)]
    assert main(args) == 0
    assert sorted(p.name for p in out.iterdir()) == ["demo_mobile.zip", "demo_tablet.zip"]
    assert main(args) == 0
    assert capsys.readouterr().out.count("kept") == 2
