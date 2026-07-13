from codex_bridge.qr import encode_qr


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


def test_encode_qr_returns_bounded_serializable_matrix():
    assert encode_qr("pairing-payload", qr_factory=FakeQr) == [
        "101",
        "010",
        "101",
    ]


def test_encode_qr_degrades_when_encoder_or_matrix_is_invalid():
    assert encode_qr("", qr_factory=FakeQr) is None
    assert encode_qr("x" * 4097, qr_factory=FakeQr) is None
    assert encode_qr("payload", qr_factory=lambda: (_ for _ in ()).throw(ValueError())) is None
