"""Разбор маркированных сообщений без полного XML-дерева (демо-шард s2)."""

import re

MESSAGE = re.compile(rb"<Msg>.*?</Msg>", re.DOTALL)


def split_messages(buffer: bytes) -> tuple[list[bytes], bytes]:
    """Возвращает готовые сообщения и недособранный хвост буфера."""
    messages = MESSAGE.findall(buffer)
    end = buffer.rfind(b"</Msg>")
    rest = buffer[end + len(b"</Msg>") :] if end != -1 else buffer
    return messages, rest
