"""Приём без привязки к одному пакету фиксированного размера (демо-шард s3)."""

READ_CHUNK = 65536


def read_batch(connection) -> bytes:
    """Читает всё, что готов отдать сокет, за один проход."""
    chunks: list[bytes] = []
    while True:
        chunk = connection.recv(READ_CHUNK)
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)
