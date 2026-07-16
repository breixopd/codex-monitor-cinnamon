import os

from codex_bridge.active_processes import MAX_ENVIRONMENT_BYTES, discover_live_threads


ENV_THREAD_ID = "019c0000-0000-7000-8000-000000000001"
FD_THREAD_ID = "019c0000-0000-7000-8000-000000000002"


def _fake_process(
    proc_root,
    *,
    pid,
    executable,
    started_ticks,
    environment=b"",
    session_file=None,
):
    process = proc_root / str(pid)
    process.mkdir()
    (process / "exe").symlink_to(executable)
    (process / "environ").write_bytes(environment)
    fields_after_comm = ["S", *("0" for _ in range(18)), str(started_ticks)]
    (process / "stat").write_text(
        f"{pid} (codex) {' '.join(fields_after_comm)}\n",
        encoding="utf-8",
    )
    descriptors = process / "fd"
    descriptors.mkdir()
    if session_file is not None:
        (descriptors / "7").symlink_to(session_file)


def test_discovers_validated_thread_ids_from_environment_and_open_session_file(
    tmp_path,
):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "stat").write_text("cpu 0 0 0 0\nbtime 1000\n", encoding="utf-8")
    executable = tmp_path / "codex"
    executable.write_bytes(b"codex")
    codex_home = tmp_path / "codex-home"
    session_file = (
        codex_home
        / "sessions/2026/07/16"
        / f"rollout-2026-07-16T10-00-00-{FD_THREAD_ID}.jsonl"
    )
    session_file.parent.mkdir(parents=True)
    session_file.write_text("not read by discovery", encoding="utf-8")
    clock_ticks = os.sysconf("SC_CLK_TCK")
    _fake_process(
        proc_root,
        pid=123,
        executable=executable,
        started_ticks=5 * clock_ticks,
        environment=f"CODEX_THREAD_ID={ENV_THREAD_ID}\0PRIVATE=discard\0".encode(),
        session_file=session_file,
    )

    result = discover_live_threads(
        str(executable),
        codex_home=str(codex_home),
        proc_root=proc_root,
        uid=os.getuid(),
        now=2000,
    )

    assert result == {ENV_THREAD_ID: 1005, FD_THREAD_ID: 1005}


def test_rejects_other_executables_invalid_ids_and_session_files_outside_home(
    tmp_path,
):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "stat").write_text("btime 1000\n", encoding="utf-8")
    executable = tmp_path / "codex"
    executable.write_bytes(b"codex")
    impostor = tmp_path / "not-codex"
    impostor.write_bytes(b"impostor")
    codex_home = tmp_path / "codex-home"
    outside = tmp_path / f"rollout-{FD_THREAD_ID}.jsonl"
    outside.write_text("private", encoding="utf-8")
    _fake_process(
        proc_root,
        pid=123,
        executable=impostor,
        started_ticks=100,
        environment=f"CODEX_THREAD_ID={ENV_THREAD_ID}\0".encode(),
    )
    _fake_process(
        proc_root,
        pid=124,
        executable=executable,
        started_ticks=100,
        environment=b"CODEX_THREAD_ID=not-a-uuid\0",
        session_file=outside,
    )

    result = discover_live_threads(
        str(executable),
        codex_home=str(codex_home),
        proc_root=proc_root,
        uid=os.getuid(),
        now=2000,
    )

    assert result == {}


def test_missing_proc_and_oversized_environment_fail_closed(tmp_path):
    executable = tmp_path / "codex"
    executable.write_bytes(b"codex")

    assert discover_live_threads(
        str(executable), proc_root=tmp_path / "missing-proc"
    ) == {}

    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "stat").write_text("btime 1000\n", encoding="utf-8")
    _fake_process(
        proc_root,
        pid=123,
        executable=executable,
        started_ticks=100,
        environment=(
            f"CODEX_THREAD_ID={ENV_THREAD_ID}\0".encode()
            + b"x" * MAX_ENVIRONMENT_BYTES
        ),
    )

    assert discover_live_threads(
        str(executable), proc_root=proc_root, uid=os.getuid(), now=2000
    ) == {}
