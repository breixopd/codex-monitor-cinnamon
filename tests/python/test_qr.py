from codex_bridge.qr import encode_qr_svg
import pytest


class FakeQr:
    def __init__(self):
        self.value = None

    def add_data(self, value):
        self.value = value

    def make(self, fit=True):
        assert fit is True

    def get_matrix(self):
        assert self.value == "pairing-payload"
        return [[True, False, True], [False, True, False], [True, False, True]]


def test_encode_qr_svg_returns_bounded_in_memory_image_with_quiet_zone():
    svg = encode_qr_svg("pairing-payload", qr_factory=FakeQr)

    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert 'viewBox="0 0 11 11"' in svg
    assert '<rect width="11" height="11" fill="#fff"/>' in svg
    assert "M4 4h1v1h-1z" in svg
    assert "M6 6h1v1h-1z" in svg
    assert len(svg.encode("utf-8")) <= 256 * 1024
    assert "<text" not in svg
    assert "pairing-payload" not in svg


def test_encode_qr_svg_degrades_when_encoder_or_matrix_is_invalid():
    assert encode_qr_svg("", qr_factory=FakeQr) is None
    assert encode_qr_svg("x" * 4097, qr_factory=FakeQr) is None
    assert (
        encode_qr_svg(
            "payload", qr_factory=lambda: (_ for _ in ()).throw(ValueError())
        )
        is None
    )

    class InvalidQr(FakeQr):
        def get_matrix(self):
            return [[True], [False, True]]

    assert encode_qr_svg("pairing-payload", qr_factory=InvalidQr) is None


def test_encode_qr_svg_never_exceeds_the_svg_size_bound():
    class HugeQr(FakeQr):
        def get_matrix(self):
            return [
                [(x + y) % 2 == 0 for x in range(177)]
                for y in range(177)
            ]

    svg = encode_qr_svg("pairing-payload", qr_factory=HugeQr)

    assert svg is None or len(svg.encode("utf-8")) <= 256 * 1024


def test_system_qr_encoder_produces_a_standard_svg_when_available():
    pytest.importorskip("qrcode")

    svg = encode_qr_svg("codex-monitor-qr-smoke")

    assert svg is not None
    assert "<svg" in svg
    assert "<path" in svg
    assert "shape-rendering=\"crispEdges\"" in svg
