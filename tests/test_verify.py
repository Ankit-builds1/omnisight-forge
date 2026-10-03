import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from forge.mutations import MUTATIONS
from forge.pipeline import generate_sample
from forge.scoring import gold_answer
from forge.verify import LOAD_FAILED, _open, verify_fix

PAGE = """<!doctype html><html><body style="margin:0">
<div style="width:400px">
<div style="height:120px;background:#c0392b"></div>
<div style="height:120px;background:#2980b9"></div>
<p>Some text</p>
</div></body></html>"""


def make(tmp_path, bug_type):
    path = tmp_path / "page.html"
    path.write_text(PAGE, encoding="utf-8")
    url = path.as_uri()
    sample = generate_sample(
        url, "demo", "desktop", bug_type, seed=1, out_dir=str(tmp_path / "out"), threshold=0.0
    )
    return url, sample


@pytest.mark.parametrize("bug_type", sorted(MUTATIONS))
def test_gold_fix_is_fixed_and_broken_value_is_not(tmp_path, bug_type):
    url, sample = make(tmp_path, bug_type)
    gold = gold_answer(sample)
    assert verify_fix(url, sample, gold, tmp_path / "gold").fixed
    broken_value = sample.broken_css.split(";")[0].split(":", 1)[1].strip()
    verdict = verify_fix(url, sample, {**gold, "value": broken_value}, tmp_path / "wrong")
    assert verdict.broken_diff > 0
    assert not verdict.fixed


def test_missing_answer_is_not_fixed(tmp_path):
    url, sample = make(tmp_path, "OVERLAP")
    verdict = verify_fix(url, sample, None, tmp_path / "none")
    assert not verdict.fixed
    assert verdict.note == "no answer"


def test_value_with_extra_declarations_is_refused(tmp_path):
    url, sample = make(tmp_path, "OVERLAP")
    gold = gold_answer(sample)
    cheat = {**gold, "value": gold["value"] + "; margin-top: 0px"}
    verdict = verify_fix(url, sample, cheat, tmp_path / "cheat")
    assert not verdict.fixed
    assert verdict.note == "value has several declarations"


class SlowPage:
    """A page whose first `failures` loads time out."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def goto(self, url, timeout):
        self.calls += 1
        if self.calls <= self.failures:
            raise PlaywrightTimeoutError("slow")


def test_open_retries_once_after_a_timeout():
    page = SlowPage(failures=1)
    assert _open(page, "https://example.com")
    assert page.calls == 2


def test_open_gives_up_after_two_timeouts():
    page = SlowPage(failures=5)
    assert not _open(page, "https://example.com")
    assert page.calls == 2


def test_page_that_never_loads_is_reported_not_raised(tmp_path, monkeypatch):
    url, sample = make(tmp_path, "OVERLAP")
    monkeypatch.setattr("forge.verify._open", lambda page, url: False)
    verdict = verify_fix(url, sample, gold_answer(sample), tmp_path / "slow")
    assert not verdict.fixed
    assert verdict.note == LOAD_FAILED

def test_cli_gold_check_reports_all_fixed(tmp_path, capsys):
    from forge.dataset import append_sample
    from forge.verify import main

    url, sample = make(tmp_path, "OVERLAP")
    samples = tmp_path / "samples.jsonl"
    append_sample(sample, samples)
    main(["--samples", str(samples), "--site", f"demo={url}", "--out", str(tmp_path / "v")])
    out = capsys.readouterr().out
    assert "all        n=1   verified_fixed=100%" in out
    assert (tmp_path / "v" / "verdicts.jsonl").exists()