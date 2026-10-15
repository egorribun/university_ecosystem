"""Pin the disposable Redis stacks to the fixed, supported 8.10.2 image."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILES = ("docker-compose.test.yml", "docker-compose.sandbox.yml")
_REDIS_PIN = re.compile(r"redis:8\.10\.2-alpine@sha256:[0-9a-f]{64}\Z")


def _redis_image(compose_name: str) -> str:
    source = (ROOT / compose_name).read_text(encoding="utf-8")
    compose = yaml.safe_load(source)
    return compose["services"]["redis"]["image"]


def test_test_and_sandbox_redis_pins_are_same_fixed_8102_release() -> None:
    images = [_redis_image(name) for name in _COMPOSE_FILES]

    assert images[0] == images[1]
    for image in images:
        match = _REDIS_PIN.fullmatch(image)
        assert match is not None, image
