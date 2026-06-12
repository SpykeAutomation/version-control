"""Converter wrapper: SDK calls, error wrapping, and the no-SDK message."""
import asyncio
import sys
import types

import pytest

from ingest import IngestError, acd_to_l5x


class FakeSdkError(Exception):
    """Stands in for the SDK's LogixSdkError base class."""


def install_fake_sdk(monkeypatch, *, open_error=None, save_error=None, open_delay=0.0):
    """Put a pretend logix_designer_sdk into sys.modules and record its calls."""
    calls = {}

    class FakeProject:
        @staticmethod
        async def open_logix_project(path, operation_events=None):
            if open_delay:
                await asyncio.sleep(open_delay)
            if open_error is not None:
                raise open_error
            calls["opened"] = path
            return FakeProject()

        async def save_as(self, path, force=False, detailed_l5x=False):
            if save_error is not None:
                raise save_error
            calls["saved"] = (path, force, detailed_l5x)

        def close(self):
            calls["closed"] = True

    module = types.ModuleType("logix_designer_sdk")
    module.LogixProject = FakeProject
    exceptions = types.ModuleType("logix_designer_sdk.exceptions")
    exceptions.LogixSdkError = FakeSdkError
    module.exceptions = exceptions
    monkeypatch.setitem(sys.modules, "logix_designer_sdk", module)
    monkeypatch.setitem(sys.modules, "logix_designer_sdk.exceptions", exceptions)
    return calls


def make_acd(tmp_path, name="Mixer.ACD"):
    acd = tmp_path / name
    acd.write_bytes(b"not a real project")
    return acd


def test_converts_next_to_source_by_default(tmp_path, monkeypatch):
    calls = install_fake_sdk(monkeypatch)
    acd = make_acd(tmp_path)
    result = acd_to_l5x(acd)
    assert result == tmp_path / "Mixer.L5X"
    assert calls["opened"] == str(acd)
    assert calls["saved"] == (str(result), True, False)
    assert calls["closed"] is True


def test_output_path_can_be_chosen(tmp_path, monkeypatch):
    calls = install_fake_sdk(monkeypatch)
    target = tmp_path / "out" / "converted.l5x"
    result = acd_to_l5x(make_acd(tmp_path), target)
    assert result == target
    assert calls["saved"][0] == str(target)


def test_missing_file_rejected(tmp_path, monkeypatch):
    install_fake_sdk(monkeypatch)
    with pytest.raises(IngestError, match="no such file"):
        acd_to_l5x(tmp_path / "absent.ACD")


def test_wrong_input_extension_rejected(tmp_path, monkeypatch):
    install_fake_sdk(monkeypatch)
    wrong = tmp_path / "export.L5X"
    wrong.write_bytes(b"<xml/>")
    with pytest.raises(IngestError, match="expected an .ACD"):
        acd_to_l5x(wrong)


def test_wrong_output_extension_rejected(tmp_path, monkeypatch):
    install_fake_sdk(monkeypatch)
    with pytest.raises(IngestError, match="must end in .L5X"):
        acd_to_l5x(make_acd(tmp_path), tmp_path / "wrong.txt")


def test_missing_sdk_explains_plainly(tmp_path, monkeypatch):
    # A None entry in sys.modules makes the import fail, like on a
    # computer without Studio 5000.
    monkeypatch.setitem(sys.modules, "logix_designer_sdk", None)
    monkeypatch.setitem(sys.modules, "logix_designer_sdk.exceptions", None)
    with pytest.raises(IngestError, match="Studio 5000"):
        acd_to_l5x(make_acd(tmp_path))


def test_sdk_failure_is_wrapped_and_project_closed(tmp_path, monkeypatch):
    calls = install_fake_sdk(monkeypatch, save_error=FakeSdkError("file is newer"))
    with pytest.raises(IngestError, match="file is newer"):
        acd_to_l5x(make_acd(tmp_path))
    assert calls["closed"] is True


def test_open_failure_is_wrapped(tmp_path, monkeypatch):
    calls = install_fake_sdk(monkeypatch, open_error=FakeSdkError("bad project"))
    with pytest.raises(IngestError, match="bad project"):
        acd_to_l5x(make_acd(tmp_path))
    assert "closed" not in calls


def test_hung_conversion_times_out(tmp_path, monkeypatch):
    install_fake_sdk(monkeypatch, open_delay=0.5)
    with pytest.raises(IngestError, match="did not finish"):
        acd_to_l5x(make_acd(tmp_path), timeout=0.05)
