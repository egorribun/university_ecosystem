import os

import pytest


@pytest.fixture(autouse=True)
def my_autouse():
    print("SETUP: autouse")
    yield
    print("TEARDOWN: autouse")
    print("env var is:", os.environ.get("MY_VAR"))


def test_order(monkeypatch):
    print("SETUP: test")
    monkeypatch.setenv("MY_VAR", "monkeypatched")
    print("TEST")
