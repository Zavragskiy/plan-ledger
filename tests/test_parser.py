import importlib.util
import pathlib
import sys


def _load(rel: str):
    path = pathlib.Path(__file__).resolve().parents[1] / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def test_split_keeps_tail():
    parser = _load("src/message_parser.py")
    buffer = b"<Msg>a</Msg><Msg>b</Msg><Msg>par"
    messages, rest = parser.split_messages(buffer)
    assert messages == [b"<Msg>a</Msg>", b"<Msg>b</Msg>"]
    assert rest == b"<Msg>par"
