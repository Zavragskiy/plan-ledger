"""Генератор входящего потока сообщений (демо-шард s1)."""

RATE_HZ = 25


def make_message(tag: str = "Value", value: float = 0.0) -> bytes:
    """Одно сообщение в формате `<Msg><Tag>...</Tag></Msg>`."""
    return f"<Msg><{tag}>{value}</{tag}></Msg>".encode("utf-8")
