import base64
import hashlib
import json
import socket
import struct
import threading

import pytest

from codex_bridge.websocket_rpc import (
    MAX_MESSAGE_BYTES,
    UnixSocketAppServerClient,
)


def _read_until(connection, marker, maximum=16_384):
    value = bytearray()
    while marker not in value:
        chunk = connection.recv(4096)
        if not chunk:
            raise RuntimeError("connection closed")
        value.extend(chunk)
        if len(value) > maximum:
            raise RuntimeError("request too large")
    return bytes(value)


def _handshake(connection, *, valid=True):
    request = _read_until(connection, b"\r\n\r\n").decode("ascii")
    headers = {}
    lines = request.split("\r\n")
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.lower()] = value.strip()
    assert lines[0] == "GET / HTTP/1.1"
    assert headers["upgrade"].lower() == "websocket"
    assert "upgrade" in headers["connection"].lower()
    assert headers["sec-websocket-version"] == "13"
    assert "origin" not in headers
    accept = base64.b64encode(
        hashlib.sha1(
            (headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
            .encode("ascii")
        ).digest()
    ).decode("ascii")
    if not valid:
        accept = "invalid"
    connection.sendall(
        (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        ).encode("ascii")
    )


def _read_exact(connection, size):
    value = bytearray()
    while len(value) < size:
        chunk = connection.recv(size - len(value))
        if not chunk:
            raise RuntimeError("connection closed")
        value.extend(chunk)
    return bytes(value)


def _read_frame(connection):
    first, second = _read_exact(connection, 2)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(connection, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(connection, 8))[0]
    assert second & 0x80, "client frames must be masked"
    mask = _read_exact(connection, 4)
    payload = _read_exact(connection, length)
    payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bool(first & 0x80), first & 0x0F, payload


def _send_frame(connection, payload=b"", *, opcode=1, final=True):
    first = opcode | (0x80 if final else 0)
    length = len(payload)
    if length < 126:
        header = bytes((first, length))
    elif length <= 65_535:
        header = bytes((first, 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 127)) + struct.pack("!Q", length)
    connection.sendall(header + payload)


def _start_server(socket_path, handler):
    ready = threading.Event()
    outcome = {}

    def run():
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(socket_path))
            server.listen(1)
            ready.set()
            connection, _address = server.accept()
            with connection:
                handler(connection)
        except BaseException as error:
            outcome["error"] = error
            ready.set()
        finally:
            server.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(1)
    return thread, outcome


def _finish_server(thread, outcome):
    thread.join(timeout=2)
    assert not thread.is_alive()
    if "error" in outcome:
        raise outcome["error"]


def test_unix_socket_client_initializes_and_reads_fragmented_json_rpc(tmp_path):
    socket_path = tmp_path / "app-server-control.sock"

    def handler(connection):
        _handshake(connection)
        final, opcode, payload = _read_frame(connection)
        initialize = json.loads(payload)
        assert final is True
        assert opcode == 1
        assert initialize["method"] == "initialize"
        assert initialize["params"]["capabilities"]["experimentalApi"] is True

        _send_frame(connection, b"health", opcode=9)
        final, opcode, payload = _read_frame(connection)
        assert (final, opcode, payload) == (True, 10, b"health")
        _send_frame(connection, b'{"id":1,"result":{"platformOs":"linux"}}')

        final, opcode, payload = _read_frame(connection)
        assert json.loads(payload) == {"method": "initialized"}

        final, opcode, payload = _read_frame(connection)
        request = json.loads(payload)
        assert request == {
            "id": 2,
            "method": "remoteControl/client/list",
            "params": {"environmentId": "environment-1"},
        }
        response = json.dumps(
            {"id": 2, "result": {"data": [{"clientId": "client-1"}]}},
            separators=(",", ":"),
        ).encode("utf-8")
        split = len(response) // 2
        _send_frame(connection, response[:split], opcode=1, final=False)
        _send_frame(connection, b"still-alive", opcode=9)
        final, opcode, payload = _read_frame(connection)
        assert (final, opcode, payload) == (True, 10, b"still-alive")
        _send_frame(connection, response[split:], opcode=0, final=True)

    thread, outcome = _start_server(socket_path, handler)
    client = UnixSocketAppServerClient(
        socket_path=socket_path,
        timeout_seconds=0.5,
    )
    try:
        assert client.initialize() == {"platformOs": "linux"}
        assert client.request(
            "remoteControl/client/list", {"environmentId": "environment-1"}
        ) == {"data": [{"clientId": "client-1"}]}
    finally:
        client.close()
    _finish_server(thread, outcome)


def test_unix_socket_client_rejects_invalid_upgrade_accept(tmp_path):
    socket_path = tmp_path / "app-server-control.sock"

    def handler(connection):
        _handshake(connection, valid=False)

    thread, outcome = _start_server(socket_path, handler)
    client = UnixSocketAppServerClient(socket_path=socket_path, timeout_seconds=0.2)
    with pytest.raises(RuntimeError, match="control channel handshake failed"):
        client.initialize()
    client.close()
    _finish_server(thread, outcome)


def test_unix_socket_client_rejects_oversized_message_before_reading_payload(tmp_path):
    socket_path = tmp_path / "app-server-control.sock"

    def handler(connection):
        _handshake(connection)
        _read_frame(connection)
        connection.sendall(
            bytes((0x81, 127)) + struct.pack("!Q", MAX_MESSAGE_BYTES + 1)
        )

    thread, outcome = _start_server(socket_path, handler)
    client = UnixSocketAppServerClient(socket_path=socket_path, timeout_seconds=0.2)
    with pytest.raises(RuntimeError, match="control channel message was too large"):
        client.initialize()
    client.close()
    _finish_server(thread, outcome)


def test_unix_socket_client_uses_sanitized_timeout(tmp_path):
    socket_path = tmp_path / "app-server-control.sock"
    release = threading.Event()

    def handler(connection):
        _handshake(connection)
        _read_frame(connection)
        release.wait(1)

    thread, outcome = _start_server(socket_path, handler)
    client = UnixSocketAppServerClient(socket_path=socket_path, timeout_seconds=0.05)
    try:
        with pytest.raises(TimeoutError, match="Codex control channel timed out"):
            client.initialize()
    finally:
        release.set()
        client.close()
    _finish_server(thread, outcome)


def test_unix_socket_client_rejects_a_non_socket_endpoint(tmp_path):
    socket_path = tmp_path / "not-a-socket"
    socket_path.write_text("untrusted", encoding="utf-8")

    def socket_factory(*_args):
        raise AssertionError("socket creation must not happen for an invalid endpoint")

    client = UnixSocketAppServerClient(
        socket_path=socket_path,
        timeout_seconds=0.05,
        socket_factory=socket_factory,
    )

    with pytest.raises(RuntimeError, match="control channel is unavailable"):
        client.initialize()
