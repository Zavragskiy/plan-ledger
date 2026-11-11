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


class FakeConnection:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def recv(self, size):
        return self._chunks.pop(0) if self._chunks else b""


def test_read_batch_collects_all_chunks():
    mod = _load("src/transport.py")
    data = mod.read_batch(FakeConnection([b"ab", b"cd", b""]))
    assert data == b"abcd"
