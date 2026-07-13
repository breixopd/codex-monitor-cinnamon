"""Optional in-memory QR matrix generation for short-lived pairing payloads."""

from __future__ import annotations


def _default_qr():
    import qrcode

    return qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=0,
    )


def encode_qr(value, *, qr_factory=None):
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    factory = qr_factory or _default_qr
    try:
        qr = factory()
        qr.add_data(value)
        qr.make(fit=True)
        matrix = qr.get_matrix()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None
    if not isinstance(matrix, list) or not 1 <= len(matrix) <= 177:
        return None
    size = len(matrix)
    if any(not isinstance(row, list) or len(row) != size for row in matrix):
        return None
    return ["".join("1" if bool(cell) else "0" for cell in row) for row in matrix]
