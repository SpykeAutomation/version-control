"""CLI behavior: output, exit codes, error reporting."""
from ingest.__main__ import main

from test_ingest import install_fake_sdk, make_acd


def test_success_prints_target_and_returns_zero(tmp_path, monkeypatch, capsys):
    install_fake_sdk(monkeypatch)
    acd = make_acd(tmp_path)
    code = main([str(acd)])
    out = capsys.readouterr()
    assert code == 0
    assert out.out.strip() == str(tmp_path / "Mixer.L5X")
    assert out.err == ""


def test_explicit_output_path(tmp_path, monkeypatch, capsys):
    install_fake_sdk(monkeypatch)
    target = tmp_path / "converted.L5X"
    code = main([str(make_acd(tmp_path)), str(target)])
    assert code == 0
    assert capsys.readouterr().out.strip() == str(target)


def test_error_goes_to_stderr_with_exit_two(tmp_path, monkeypatch, capsys):
    install_fake_sdk(monkeypatch)
    code = main([str(tmp_path / "absent.ACD")])
    out = capsys.readouterr()
    assert code == 2
    assert "no such file" in out.err
    assert out.out == ""
