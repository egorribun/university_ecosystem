"""Contract tests for reusable, provenance-bound retry contexts."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import scripts.quality.coverage_retry_context as retry_context
from tests.symlink_support import DIRECTORY_SYMLINKS_SUPPORTED

GIT_EXECUTABLE = shutil.which("git")
WORKFLOW_SHA = "89abcdef0123456789abcdef0123456789abcdef"  # pragma: allowlist secret


def _git_head(repository_root: Path) -> str:
    assert GIT_EXECUTABLE is not None
    return subprocess.check_output(  # noqa: S603
        [GIT_EXECUTABLE, "rev-parse", "HEAD"],
        cwd=repository_root,
        text=True,
    ).strip()


@pytest.fixture
def retry_repository(tmp_path: Path) -> Path:
    assert GIT_EXECUTABLE is not None
    subprocess.run(  # noqa: S603
        [GIT_EXECUTABLE, "init", "-q"], cwd=tmp_path, check=True
    )
    subprocess.run(  # noqa: S603
        [
            GIT_EXECUTABLE,
            "-c",
            "user.name=Quality Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    _write(tmp_path, "config/application.toml", b"theme = 'university'\n")
    _write(tmp_path, "config/security.toml", b"mfa = 'email_otp'\n")
    _write(tmp_path, "quality/policy.json", b'{"coverage":100}\n')
    return tmp_path


def _write(repository_root: Path, relative_path: str, content: bytes) -> Path:
    path = repository_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _producer_kwargs(repository_root: Path, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "repository_root": repository_root,
        "config_inputs": ("config/security.toml", "config/application.toml"),
        "policy_inputs": ("quality/policy.json",),
        "repository": "example/university-ecosystem",
        "run_id": "123456789",
        "run_attempt": "2",
        "workflow_ref": (
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        "workflow_sha": WORKFLOW_SHA,
        "event": "pull_request",
        "artifact": "coverage-python-shard-0",
    }
    values.update(overrides)
    return values


def _consumer_kwargs(repository_root: Path, **overrides: object) -> dict[str, object]:
    values = _producer_kwargs(repository_root, **overrides)
    values.pop("run_attempt")
    values.pop("artifact")
    return values


def _build_producer(repository_root: Path, **overrides: object) -> dict[str, str]:
    return retry_context.build_retry_provenance(
        **_producer_kwargs(repository_root, **overrides)  # type: ignore[arg-type]
    )


def _build_consumer(repository_root: Path, **overrides: object) -> dict[str, str]:
    return retry_context.build_consumer_retry_context(
        **_consumer_kwargs(repository_root, **overrides)  # type: ignore[arg-type]
    )


def test_build_retry_provenance_is_deterministic_and_binds_current_head(
    retry_repository: Path,
) -> None:
    first = _build_producer(retry_repository)
    second = _build_producer(
        retry_repository,
        config_inputs=("config/application.toml", "config/security.toml"),
    )

    assert first == second
    assert first == {
        "repository": "example/university-ecosystem",
        "run_id": "123456789",
        "run_attempt": "2",
        "source_sha": _git_head(retry_repository),
        "source_revision": _git_head(retry_repository),
        "workflow_ref": (
            "example/university-ecosystem/.github/workflows/ci.yml@refs/heads/main"
        ),
        "workflow_sha": WORKFLOW_SHA,
        "event": "pull_request",
        "config_digest": first["config_digest"],
        "policy_digest": first["policy_digest"],
        "artifact": "coverage-python-shard-0",
    }


def test_digests_bind_each_input_path_and_content(retry_repository: Path) -> None:
    initial = _build_producer(retry_repository)
    _write(retry_repository, "config/application.toml", b"theme = 'new-campus'\n")
    changed_content = _build_producer(retry_repository)
    _write(retry_repository, "config/another.toml", b"theme = 'new-campus'\n")
    changed_path = _build_producer(
        retry_repository,
        config_inputs=("config/another.toml", "config/security.toml"),
    )

    assert initial["config_digest"] != changed_content["config_digest"]
    assert changed_content["config_digest"] != changed_path["config_digest"]
    assert initial["policy_digest"] == changed_path["policy_digest"]


def test_native_relative_path_inputs_normalize_to_the_same_digest(
    retry_repository: Path,
) -> None:
    string_inputs = _build_producer(retry_repository)
    path_inputs = _build_producer(
        retry_repository,
        config_inputs=(
            Path("config") / "security.toml",
            Path("config") / "application.toml",
        ),
        policy_inputs=(Path("quality") / "policy.json",),
    )

    assert path_inputs["config_digest"] == string_inputs["config_digest"]
    assert path_inputs["policy_digest"] == string_inputs["policy_digest"]


def test_build_consumer_context_uses_the_same_immutable_fields(
    retry_repository: Path,
) -> None:
    producer = _build_producer(retry_repository)
    consumer = _build_consumer(retry_repository)

    assert set(consumer) == retry_context.CONSUMER_RETRY_CONTEXT_FIELDS
    assert consumer == {
        name: producer[name] for name in retry_context.CONSUMER_RETRY_CONTEXT_FIELDS
    }


def test_validators_accept_contexts_built_from_trusted_inputs(
    retry_repository: Path,
) -> None:
    producer = _build_producer(retry_repository)
    consumer = _build_consumer(retry_repository)

    assert (
        retry_context.validate_retry_provenance(
            producer,
            **_producer_kwargs(retry_repository),  # type: ignore[arg-type]
        )
        == producer
    )
    assert (
        retry_context.validate_consumer_retry_context(
            consumer,
            **_consumer_kwargs(retry_repository),  # type: ignore[arg-type]
        )
        == consumer
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("repository", "", "repository must be a non-empty string"),
        ("run_id", "0", "run_id must be a positive decimal identifier"),
        ("run_attempt", "01a", "run_attempt must be a positive decimal identifier"),
        ("workflow_ref", "bad\nref", "workflow_ref contains forbidden control"),
        ("workflow_sha", "A" * 40, "workflow_sha must be an exact lowercase"),
        ("event", "", "event must be a non-empty string"),
        ("artifact", "bad\x00artifact", "artifact contains forbidden control"),
    ],
)
def test_build_retry_provenance_rejects_invalid_identity_fields(
    retry_repository: Path, field: str, value: str, message: str
) -> None:
    with pytest.raises(retry_context.RetryContextError, match=message):
        _build_producer(retry_repository, **{field: value})


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        ".",
        "..",
        "config/../application.toml",
        "/etc/passwd",
        "C:\\outside\\input.toml",
        "config\\..\\application.toml",
    ],
)
def test_build_retry_provenance_rejects_unsafe_input_paths(
    retry_repository: Path, unsafe_path: str
) -> None:
    with pytest.raises(
        retry_context.RetryContextError,
        match="safe repository-relative POSIX path",
    ):
        _build_producer(retry_repository, config_inputs=(unsafe_path,))


def test_build_retry_provenance_rejects_non_sequence_and_duplicate_inputs(
    retry_repository: Path,
) -> None:
    with pytest.raises(retry_context.RetryContextError, match="explicit sequence"):
        _build_producer(retry_repository, config_inputs="config/application.toml")

    with pytest.raises(retry_context.RetryContextError, match="duplicate input path"):
        _build_producer(
            retry_repository,
            config_inputs=("config/application.toml", "config/application.toml"),
        )

    with pytest.raises(retry_context.RetryContextError, match="at least one input"):
        _build_producer(retry_repository, config_inputs=())

    with pytest.raises(
        retry_context.RetryContextError,
        match="safe repository-relative POSIX path",
    ):
        _build_producer(retry_repository, config_inputs=(123,))


@pytest.mark.parametrize(
    ("relative_path", "prepare", "message"),
    [
        ("config/missing.toml", lambda root: None, "does not identify an input file"),
        (
            "config/empty.toml",
            lambda root: _write(root, "config/empty.toml", b""),
            "non-empty input",
        ),
        (
            "config/directory",
            lambda root: (root / "config/directory").mkdir(),
            "regular file",
        ),
    ],
)
def test_build_retry_provenance_rejects_missing_empty_and_nonregular_inputs(
    retry_repository: Path,
    relative_path: str,
    prepare: Callable[[Path], object],
    message: str,
) -> None:
    prepare(retry_repository)

    with pytest.raises(retry_context.RetryContextError, match=message):
        _build_producer(retry_repository, config_inputs=(relative_path,))


def test_build_retry_provenance_rejects_hardlinked_inputs(
    retry_repository: Path,
) -> None:
    source = retry_repository / "config/application.toml"
    hardlink = retry_repository / "config/hardlinked.toml"
    os.link(source, hardlink)

    with pytest.raises(retry_context.RetryContextError, match="hard link"):
        _build_producer(retry_repository, config_inputs=("config/hardlinked.toml",))


def test_build_retry_provenance_rejects_junction_marked_input_ancestors(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        os.path,
        "isjunction",
        lambda path: Path(path).name == "config",
        raising=False,
    )

    with pytest.raises(retry_context.RetryContextError, match="symlink or junction"):
        _build_producer(retry_repository, config_inputs=("config/application.toml",))


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable on this platform",
)
def test_build_retry_provenance_rejects_symlinked_input_ancestors(
    retry_repository: Path,
) -> None:
    outside = retry_repository.parent / "retry-context-outside"
    outside.mkdir()
    _write(outside, "nested.toml", b"outside = true\n")
    linked = retry_repository / "config-link"
    linked.symlink_to(outside, target_is_directory=True)

    with pytest.raises(retry_context.RetryContextError, match="symlink or junction"):
        _build_producer(retry_repository, config_inputs=("config-link/nested.toml",))


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable on this platform",
)
def test_build_retry_provenance_rejects_symlinked_repository_root(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked_root = retry_repository.parent / "retry-context-repository-link"
    linked_root.symlink_to(retry_repository, target_is_directory=True)

    with pytest.raises(
        retry_context.RetryContextError,
        match="repository root must not be a symlink or junction",
    ):
        _build_producer(linked_root)

    monkeypatch.setattr(retry_context, "_is_link_or_junction", lambda _: False)
    with pytest.raises(
        retry_context.RetryContextError,
        match="repository root traverses a symlink or junction",
    ):
        _build_producer(linked_root)


@pytest.mark.parametrize(
    ("validator", "field", "value", "message"),
    [
        ("producer", "source_sha", "0" * 40, "source_sha mismatch"),
        ("producer", "source_revision", "0" * 40, "source_revision mismatch"),
        ("producer", "repository", "other/repository", "repository mismatch"),
        ("producer", "run_id", "987654321", "run_id mismatch"),
        ("producer", "workflow_ref", "other/workflow", "workflow_ref mismatch"),
        ("producer", "workflow_sha", "0" * 40, "workflow_sha mismatch"),
        ("producer", "event", "push", "event mismatch"),
        ("producer", "config_digest", "0" * 64, "config_digest mismatch"),
        ("producer", "config_digest", "not-a-digest", "must be lowercase SHA-256"),
        ("producer", "policy_digest", "0" * 64, "policy_digest mismatch"),
        ("producer", "artifact", "other-artifact", "artifact mismatch"),
        ("producer", "run_attempt", "0", "run_attempt must be a positive"),
        ("consumer", "source_sha", "0" * 40, "source_sha mismatch"),
    ],
)
def test_validators_reject_unbound_or_malformed_context_fields(
    retry_repository: Path,
    validator: str,
    field: str,
    value: str,
    message: str,
) -> None:
    if validator == "producer":
        provenance = dict(_build_producer(retry_repository))
        provenance[field] = value

        def action() -> dict[str, str]:
            return retry_context.validate_retry_provenance(
                provenance,
                **_producer_kwargs(retry_repository),  # type: ignore[arg-type]
            )

    else:
        context = dict(_build_consumer(retry_repository))
        context[field] = value

        def action() -> dict[str, str]:
            return retry_context.validate_consumer_retry_context(
                context,
                **_consumer_kwargs(retry_repository),  # type: ignore[arg-type]
            )

    with pytest.raises(retry_context.RetryContextError, match=message):
        action()


@pytest.mark.parametrize("validator", ["producer", "consumer"])
def test_validators_reject_missing_unexpected_and_non_mapping_values(
    retry_repository: Path, validator: str
) -> None:
    original: dict[str, object]
    kwargs: dict[str, object]
    action: Callable[[object], dict[str, str]]
    if validator == "producer":
        original = dict(_build_producer(retry_repository))
        kwargs = _producer_kwargs(retry_repository)

        def action(value: object) -> dict[str, str]:
            return retry_context.validate_retry_provenance(
                value,
                **kwargs,  # type: ignore[arg-type]
            )

    else:
        original = dict(_build_consumer(retry_repository))
        kwargs = _consumer_kwargs(retry_repository)

        def action(value: object) -> dict[str, str]:
            return retry_context.validate_consumer_retry_context(
                value,
                **kwargs,  # type: ignore[arg-type]
            )

    missing = dict(original)
    missing.pop("event")
    unexpected = dict(original)
    unexpected["unexpected"] = "value"

    with pytest.raises(retry_context.RetryContextError, match="must be an object"):
        action("not-a-mapping")
    with pytest.raises(retry_context.RetryContextError, match="missing fields: event"):
        action(missing)
    with pytest.raises(
        retry_context.RetryContextError, match="unexpected fields: unexpected"
    ):
        action(unexpected)


def test_build_retry_provenance_fails_closed_without_git(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "scripts.quality.coverage_retry_context.shutil.which", lambda _: None
    )

    with pytest.raises(retry_context.RetryContextError, match="git is unavailable"):
        _build_producer(retry_repository)


def test_build_retry_provenance_fails_closed_when_git_head_cannot_be_read(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*args: Any, **kwargs: Any) -> None:
        raise OSError("git failed")

    monkeypatch.setattr("scripts.quality.coverage_retry_context.subprocess.run", _raise)

    with pytest.raises(
        retry_context.RetryContextError, match="current repository HEAD"
    ):
        _build_producer(retry_repository)


def test_build_retry_provenance_rejects_unavailable_or_nondirectory_roots(
    retry_repository: Path,
) -> None:
    missing = retry_repository / "missing"
    file_root = _write(retry_repository, "not-a-directory", b"file\n")

    with pytest.raises(retry_context.RetryContextError, match="root is unavailable"):
        _build_producer(missing)
    with pytest.raises(
        retry_context.RetryContextError, match="root is not a directory"
    ):
        _build_producer(file_root)


def test_private_path_guard_rejects_an_escape_before_any_input_is_read(
    retry_repository: Path,
) -> None:
    outside = retry_repository.parent / "outside-input.toml"

    with pytest.raises(retry_context.RetryContextError, match="escapes the trusted"):
        retry_context._reject_linked_ancestors(
            retry_repository, outside, "config_inputs"
        )


@pytest.mark.skipif(
    not DIRECTORY_SYMLINKS_SUPPORTED,
    reason="directory symlinks are unavailable on this platform",
)
def test_private_file_guard_rejects_a_final_symlink_even_if_ancestor_check_is_bypassed(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = retry_repository / "config/final-link.toml"
    linked.symlink_to(retry_repository / "config/application.toml")
    monkeypatch.setattr(retry_context, "_reject_linked_ancestors", lambda *args: None)

    with pytest.raises(retry_context.RetryContextError, match="must not be a symlink"):
        retry_context._safe_regular_file(
            retry_repository, "config/final-link.toml", "config_inputs"
        )


def test_digest_fails_closed_when_an_input_cannot_be_read(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_open = Path.open

    def _deny_open(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.name == "application.toml":
            raise OSError("read denied")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _deny_open)

    with pytest.raises(retry_context.RetryContextError, match="cannot be read"):
        _build_producer(retry_repository, config_inputs=("config/application.toml",))


def test_digest_fails_closed_when_an_input_changes_during_hashing(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retry_context, "_same_file_identity", lambda *args: False)

    with pytest.raises(retry_context.RetryContextError, match="changed while"):
        _build_producer(retry_repository, config_inputs=("config/application.toml",))


def test_build_retry_provenance_fails_closed_when_head_changes_during_digest(
    retry_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    heads = iter((_git_head(retry_repository), "0" * 40))
    monkeypatch.setattr(retry_context, "_git_head", lambda _: next(heads))

    with pytest.raises(retry_context.RetryContextError, match="HEAD changed while"):
        _build_producer(retry_repository)
