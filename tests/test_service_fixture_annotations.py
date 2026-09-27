import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_redis_fixture_return_annotation_is_safe_to_read_in_a_fresh_process() -> None:
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    probe = dedent(
        """
        import inspect
        import tests.conftest
        from tests.fixtures.services.service_fixtures import _TestingRedisCache

        # <=3.13 evaluates this at import; 3.14 evaluates it when inspected.
        annotations = inspect.get_annotations(
            _TestingRedisCache._get_client, eval_str=False
        )
        assert annotations["return"] == "Redis[Any]", annotations
        """
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
        [sys.executable, "-B", "-c", probe],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
