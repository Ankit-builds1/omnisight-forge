from forge.build import build_dataset
from forge.dataset import read_samples
from forge.mutations import TRAIN_BUG_TYPES

PAGE = """<!doctype html><html><body style="margin:0">
<div style="width:400px">
<div style="height:120px;background:#c0392b"></div>
<div style="height:120px;background:#2980b9"></div>
<p>Some text</p>
</div></body></html>"""


def write_page(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(PAGE, encoding="utf-8")
    return path.as_uri()


def options(tmp_path, **extra):
    values = {
        "out_dir": str(tmp_path / "raw"),
        "samples_path": str(tmp_path / "samples.jsonl"),
        "viewports": ["mobile"],
        "seeds": [1],
        "threshold": 0.0,
    }
    values.update(extra)
    return values


def test_builds_dataset_and_resumes(tmp_path):
    sites = {"demo": write_page(tmp_path)}
    opts = options(tmp_path)
    first = build_dataset(sites, **opts)
    assert first.accepted == len(TRAIN_BUG_TYPES)
    assert len(read_samples(opts["samples_path"])) == len(TRAIN_BUG_TYPES)

    second = build_dataset(sites, **opts)
    assert second.accepted == 0
    assert second.skipped == len(TRAIN_BUG_TYPES)
    assert len(read_samples(opts["samples_path"])) == len(TRAIN_BUG_TYPES)


def test_rejections_are_counted_and_not_written(tmp_path):
    sites = {"demo": write_page(tmp_path)}
    opts = options(tmp_path, bug_types=["OVERFLOW"], threshold=1.01)
    report = build_dataset(sites, **opts)
    assert report.accepted == 0
    assert report.reject_counts() == {"OVERFLOW": 1}
    assert "OVERFLOW" in report.summary()
    assert not (tmp_path / "samples.jsonl").exists()


def test_unreachable_page_becomes_a_rejection(tmp_path):
    sites = {"missing": (tmp_path / "does_not_exist.html").as_uri()}
    opts = options(tmp_path, bug_types=["OVERFLOW"])
    report = build_dataset(sites, **opts)
    assert report.accepted == 0
    assert len(report.rejections) == 1
    assert report.rejections[0].reason.startswith("error:")