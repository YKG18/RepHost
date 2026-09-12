import os
import stat
import pytest
from pathlib import Path
from app.runners.runner import (
    resolve_executable,
    _msys_to_windows_path,
    _split_path_env,
    _windows_which_fallback,
)


def test_msys_to_windows_path_converts_drive_paths():
    assert _msys_to_windows_path("/c/Program Files/nodejs") == r"C:\Program Files\nodejs"
    assert _msys_to_windows_path("/d/tools") == r"D:\tools"


def test_msys_to_windows_path_leaves_non_msys_paths_unchanged():
    assert _msys_to_windows_path(r"C:\Windows\System32") == r"C:\Windows\System32"
    assert _msys_to_windows_path("relative/path") == "relative/path"


def test_split_path_env_handles_windows_style():
    assert _split_path_env(r"C:\a;C:\b;C:\c") == [r"C:\a", r"C:\b", r"C:\c"]


def test_split_path_env_handles_msys_style():
    assert _split_path_env("/c/a:/c/b:/c/c") == ["/c/a", "/c/b", "/c/c"]


def test_split_path_env_empty():
    assert _split_path_env("") == []


def test_windows_which_fallback_finds_binary_via_msys_style_path(tmp_path, monkeypatch):
    """Simulates the real-world bug: PATH is inherited in MSYS/Git-Bash
    format (colon-separated, Unix-style paths) rather than native Windows
    format, so shutil.which() alone would find nothing even though the
    binary genuinely exists on one of those directories."""
    fake_bin_dir = tmp_path / "nodejs"
    fake_bin_dir.mkdir()
    fake_npm = fake_bin_dir / "npm.CMD"
    fake_npm.write_text("@echo off\n")
    fake_npm.chmod(fake_npm.stat().st_mode | stat.S_IEXEC)

    # Build a PATH string in the Unix/MSYS style this bug produces, using
    # our real tmp_path (no drive-letter rewriting needed since it's
    # already a normal filesystem path on this machine).
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    fake_path = f"{other_dir}:{fake_bin_dir}"

    monkeypatch.setenv("PATH", fake_path)
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")

    found = _windows_which_fallback("npm")
    assert found is not None
    assert found.endswith("npm.CMD")


def test_windows_which_fallback_returns_none_when_truly_absent(tmp_path, monkeypatch):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")

    assert _windows_which_fallback("definitely-not-a-real-binary") is None


def test_resolve_executable_falls_back_when_which_fails(tmp_path, monkeypatch):
    fake_bin_dir = tmp_path / "nodejs"
    fake_bin_dir.mkdir()
    fake_npm = fake_bin_dir / "npm"
    fake_npm.write_text("#!/bin/sh\n")
    fake_npm.chmod(fake_npm.stat().st_mode | stat.S_IEXEC)

    # Force shutil.which() to fail (as it would with a mismatched PATH
    # format) while our manual fallback still has a real directory to find
    # the binary in.
    monkeypatch.setattr("app.runners.runner.shutil.which", lambda name: None)
    monkeypatch.setenv("PATH", str(fake_bin_dir))
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD")

    result = resolve_executable("npm")
    assert result == str(fake_npm)


def test_resolve_executable_returns_bare_name_when_nothing_found(monkeypatch, tmp_path):
    monkeypatch.setattr("app.runners.runner.shutil.which", lambda name: None)
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("PATH", str(empty_dir))

    assert resolve_executable("totally-nonexistent-tool") == "totally-nonexistent-tool"
