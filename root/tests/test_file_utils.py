import re

from app.utils import files


def test_normalize_filename_prefix_basic():
    assert files.normalize_filename_prefix("My Avatar 1") == "my-avatar-1"


def test_normalize_filename_prefix_compacts_symbols():
    value = files.normalize_filename_prefix("***Weird__Prefix   ---+++!!!")
    assert value == "weird__prefix"
    assert not re.search(r"\s", value)
