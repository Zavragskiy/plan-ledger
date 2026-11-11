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


def test_message_shape():
    gen = _load("tools/emulator/generator.py")
    msg = gen.make_message(value=1.5)
    assert msg.startswith(b"<Msg>")
    assert b"1.5" in msg
    assert gen.RATE_HZ == 25
