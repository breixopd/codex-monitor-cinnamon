import subprocess

import pytest

from codex_bridge.launcher import TerminalLauncher


THREAD_ID = "019c0000-0000-7000-8000-000000000001"


class FakePopen:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.error:
            raise self.error
        return object()


def test_open_session_uses_default_terminal_fixed_arguments_and_existing_cwd(tmp_path):
    popen = FakePopen()
    launcher = TerminalLauncher(
        "codex", popen=popen, default_cwd=tmp_path.parent
    )

    result = launcher.open_session(THREAD_ID, str(tmp_path))

    assert result == {"launched": True}
    command, kwargs = popen.calls[0]
    assert command == [
        "x-terminal-emulator",
        "-e",
        "codex",
        "resume",
        THREAD_ID,
    ]
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert kwargs["close_fds"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_open_codex_and_unsafe_cwd_fall_back_to_default_directory(tmp_path):
    popen = FakePopen()
    launcher = TerminalLauncher("/opt/codex", popen=popen, default_cwd=tmp_path)

    assert launcher.open_codex() == {"launched": True}
    launcher.open_session(THREAD_ID, "relative/path")
    launcher.open_session(THREAD_ID, str(tmp_path / "missing"))

    assert popen.calls[0][0] == ["x-terminal-emulator", "-e", "/opt/codex"]
    assert all(call[1]["cwd"] == str(tmp_path) for call in popen.calls)


def test_open_session_rejects_noncanonical_uuid_before_spawning(tmp_path):
    popen = FakePopen()
    launcher = TerminalLauncher("codex", popen=popen, default_cwd=tmp_path)

    with pytest.raises(ValueError, match="thread identifier"):
        launcher.open_session("not-a-uuid", str(tmp_path))

    assert popen.calls == []


def test_launch_error_is_propagated_without_command_details(tmp_path):
    launcher = TerminalLauncher(
        "codex", popen=FakePopen(OSError("private executable path")), default_cwd=tmp_path
    )

    with pytest.raises(RuntimeError, match="Unable to open the default terminal") as error:
        launcher.open_codex()

    assert "private executable path" not in str(error.value)
