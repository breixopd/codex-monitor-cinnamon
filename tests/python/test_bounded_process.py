import subprocess
import sys

import pytest

from codex_bridge.bounded_process import CommandOutputTooLarge, run_bounded


def test_bounded_process_captures_each_stream_with_fixed_argv():
    completed = run_bounded(
        [
            sys.executable,
            "-c",
            "import os; os.write(1, b'out'); os.write(2, b'err')",
        ],
        timeout=2,
        stdout_limit=16,
        stderr_limit=16,
    )

    assert completed.returncode == 0
    assert completed.stdout == b"out"
    assert completed.stderr == b"err"


def test_bounded_process_enforces_one_total_timeout():
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded(
            [sys.executable, "-c", "import time; time.sleep(2)"],
            timeout=0.05,
            stdout_limit=16,
        )


def test_bounded_process_reports_the_stream_that_exceeded_its_limit():
    with pytest.raises(CommandOutputTooLarge) as captured:
        run_bounded(
            [sys.executable, "-c", "import os; os.write(2, b'x' * 128)"],
            timeout=2,
            stdout_limit=16,
            stderr_limit=32,
        )

    assert captured.value.stream == "stderr"
    assert len(captured.value.captured) == 32
