from __future__ import annotations

import pytest

from scripts import live_stand


def test_seed_requires_explicit_demo_opt_in_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[bool] = []
    monkeypatch.setattr(live_stand, "seed", lambda: dispatched.append(True))

    with pytest.raises(SystemExit) as error:
        live_stand.main(["seed"])

    assert error.value.code == 2
    assert dispatched == []


def test_seed_dispatches_when_demo_opt_in_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dispatched: list[bool] = []
    monkeypatch.setattr(live_stand, "seed", lambda: dispatched.append(True))

    assert live_stand.main(["seed", "--demo"]) == 0
    assert dispatched == [True]
