#!/usr/bin/env python3
"""Codex Monitor helper process."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from codex_bridge.history import QuotaHistory
from codex_bridge.launcher import TerminalLauncher
from codex_bridge.process import serve, spawn_app_server
from codex_bridge.protocol import CommandRouter
from codex_bridge.remote import RemoteControl
from codex_bridge.rpc import AppServerClient
from codex_bridge.service import CodexService


UUID = "codex-monitor@breixopd"


def create_runtime(
    options,
    *,
    spawn=None,
    client_factory=None,
    remote_runner=None,
    terminal_popen=None,
):
    spawn = spawn or spawn_app_server
    client_factory = client_factory or (lambda process: AppServerClient(process=process))

    process = spawn(
        options.codex,
        codex_home=options.codex_home,
        proxy=False,
    )
    client = client_factory(process)
    client.initialize()

    history = QuotaHistory(
        Path(options.data_dir) / "history.jsonl",
        retention_days=options.history_days,
    )

    def create_proxy_client():
        proxy_process = spawn(
            options.codex,
            codex_home=options.codex_home,
            proxy=True,
        )
        return client_factory(proxy_process)

    remote_environment = dict(os.environ)
    if options.codex_home:
        remote_environment["CODEX_HOME"] = options.codex_home
    remote_kwargs = {
        "client_factory": create_proxy_client,
        "environment": remote_environment,
    }
    if remote_runner is not None:
        remote_kwargs["runner"] = remote_runner
    remote = RemoteControl(options.codex, **remote_kwargs)
    launcher_kwargs = {}
    if terminal_popen is not None:
        launcher_kwargs["popen"] = terminal_popen
    launcher = TerminalLauncher(options.codex, **launcher_kwargs)
    service = CodexService(client, history, remote=remote, launcher=launcher)
    return SimpleNamespace(
        client=client,
        history=history,
        remote=remote,
        launcher=launcher,
        service=service,
        router=CommandRouter(service),
    )


def parse_args(argv=None):
    default_data_home = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    parser = argparse.ArgumentParser(description="Codex Monitor Cinnamon bridge")
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME"))
    parser.add_argument(
        "--data-dir", default=str(default_data_home / UUID), help=argparse.SUPPRESS
    )
    parser.add_argument("--history-days", type=int, default=30)
    return parser.parse_args(argv)


def main(argv=None):
    options = parse_args(argv)
    runtime = None
    try:
        runtime = create_runtime(options)
        serve(runtime.router, input_stream=sys.stdin, output_stream=sys.stdout)
    except (OSError, RuntimeError, TimeoutError):
        sys.stdout.write(
            '{"id":null,"ok":false,"error":{"code":"BRIDGE_START_FAILED",'
            '"message":"Unable to connect to Codex","retryable":true}}\n'
        )
        sys.stdout.flush()
        return 1
    finally:
        if runtime is not None:
            runtime.client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
