"""发布版本检查不导入依赖 Matplotlib 的运行包。"""

import zipfile

import pytest

from tools import check_release


def release_fixture(tmp_path, monkeypatch, version="1.3.0"):
    source = tmp_path / "rrplot"
    source.mkdir()
    source.joinpath("__init__.py").write_text('__version__ = "1.3.0"')
    monkeypatch.setattr(check_release, "ROOT", tmp_path)
    output = tmp_path / "dist"
    output.mkdir()
    with zipfile.ZipFile(output / "rrplot.whl", "w") as wheel:
        wheel.writestr(
            "rrplot.dist-info/METADATA", f"Name: rrplot\nVersion: {version}\n"
        )
    return output


def test_release_accepts_matching_tag_source_and_wheel(tmp_path, monkeypatch):
    output = release_fixture(tmp_path, monkeypatch)
    assert check_release.check_release("v1.3.0", output) == "1.3.0"


@pytest.mark.parametrize("tag", ["v1.2.0", "1.3.0", "main", ""])
def test_release_rejects_nonmatching_tag(tmp_path, monkeypatch, tag):
    output = release_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="发布标签"):
        check_release.check_release(tag, output)


def test_release_rejects_stale_wheel(tmp_path, monkeypatch):
    output = release_fixture(tmp_path, monkeypatch, version="1.2.0")
    with pytest.raises(ValueError, match="wheel 元数据"):
        check_release.check_release("v1.3.0", output)
