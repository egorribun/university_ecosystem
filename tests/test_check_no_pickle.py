from __future__ import annotations

import runpy
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.quality import check_no_pickle as gate

MODULE_PATH = Path(gate.__file__)


@pytest.mark.parametrize(
    "source",
    [
        "import pickle  # nosec",
        "import pickle as serializer",
        "import pickle.core as pickle_core",
        "from pickle import loads  # nosec",
        "import _pickle  # nosec",
        "import _pickle as low_level_pickle",
        "from _pickle import Unpickler",
    ],
)
def test_direct_pickle_imports_are_rejected_despite_nosec(source: str) -> None:
    findings = gate.scan_source(source, filename="unsafe.py")

    assert len(findings) == 1
    assert findings[0].path == Path("unsafe.py")
    assert "pickle" in findings[0].message


@pytest.mark.parametrize(
    "source",
    [
        "pickle.loads(payload)",
        "pickle.dumps(value)",
        "_pickle.Unpickler(stream)",
        "_pickle.loads(payload)",
        "factory = pickle.loads",
    ],
)
def test_direct_pickle_api_use_is_rejected(source: str) -> None:
    assert gate.scan_source(source, filename="unsafe.py")


def test_comments_docstrings_relative_imports_and_other_names_are_ignored() -> None:
    source = '''
# import pickle # nosec
"""from _pickle import loads"""
import pickletools
from .pickle import loads
from . import local_name
object.loads(payload)
factory().loads(payload)
value = "pickle.loads is forbidden"
'''
    assert gate.scan_source(source, filename="safe.py") == ()


def test_parse_errors_fail_closed_with_source_location() -> None:
    with pytest.raises(gate.ScanError, match=r"cannot parse Python source.*broken.py"):
        gate.scan_source("def broken(:\n", filename="broken.py")


def test_scan_paths_counts_nested_python_files_and_deduplicates(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "app"
    nested = source_dir / "nested"
    nested.mkdir(parents=True)
    safe = source_dir / "safe.py"
    unsafe = nested / "unsafe.PY"
    safe.write_text("value = 1\n", encoding="utf-8")
    unsafe.write_text("import _pickle  # nosec\n", encoding="utf-8")
    (source_dir / "notes.txt").write_text("import pickle\n", encoding="utf-8")

    count, findings = gate.scan_paths([source_dir, safe])

    assert count == 2
    assert len(findings) == 1
    assert findings[0].path == unsafe


def test_empty_or_non_python_directories_fail_closed(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    notes = tmp_path / "notes"
    notes.mkdir()
    (notes / "readme.txt").write_text("import pickle\n", encoding="utf-8")

    with pytest.raises(gate.ScanError, match="no Python source files"):
        gate.scan_paths([empty])
    with pytest.raises(gate.ScanError, match="no Python source files"):
        gate.scan_paths([notes])


def test_empty_nested_directory_is_allowed_when_scan_root_has_python(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "app"
    (source_dir / "empty").mkdir(parents=True)
    (source_dir / "safe.py").write_text("value = 1\n", encoding="utf-8")

    count, findings = gate.scan_paths([source_dir])

    assert count == 1
    assert findings == ()


def test_scan_paths_fails_closed_for_missing_non_python_and_empty_inputs(
    tmp_path: Path,
) -> None:
    with pytest.raises(gate.ScanError, match="source path"):
        gate.scan_paths([tmp_path / "missing"])
    non_python = tmp_path / "notes.txt"
    non_python.write_text("import pickle\n", encoding="utf-8")
    with pytest.raises(gate.ScanError, match="not Python source"):
        gate.scan_paths([non_python])
    with pytest.raises(gate.ScanError, match="at least one"):
        gate.scan_paths([])


def test_walk_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    source_dir.mkdir()

    def fail_walk(*args: object, **kwargs: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(gate.os, "walk", fail_walk)
    with pytest.raises(gate.ScanError, match="cannot traverse"):
        gate.scan_paths([source_dir])


def test_walk_callback_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    source_dir.mkdir()

    def call_onerror(
        directory: Path, *, followlinks: bool, onerror: object
    ) -> list[object]:
        del followlinks
        onerror(PermissionError(13, "denied", str(directory)))
        return []

    monkeypatch.setattr(gate.os, "walk", call_onerror)
    with pytest.raises(gate.ScanError, match="cannot traverse"):
        gate.scan_paths([source_dir])


def test_walk_rejects_symlinked_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    linked = source_dir / "linked"
    linked.mkdir(parents=True)
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked or is_symlink(path),
    )

    with pytest.raises(gate.ScanError, match="source directory symlink"):
        gate.scan_paths([source_dir])


def test_walk_rejects_symlinked_python_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    source_dir.mkdir()
    linked = source_dir / "linked.py"
    linked.write_text("value = 1\n", encoding="utf-8")
    is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == linked or is_symlink(path),
    )

    with pytest.raises(gate.ScanError, match="source file symlink"):
        gate.scan_paths([source_dir])


def test_root_junction_is_rejected_before_directory_walk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "root-junction"
    source_dir.mkdir()
    is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == source_dir or is_junction(path),
    )

    def fail_walk(*args: object, **kwargs: object) -> None:
        raise AssertionError("junction root must be rejected before traversal")

    monkeypatch.setattr(gate.os, "walk", fail_walk)
    with pytest.raises(gate.ScanError, match="source path junction"):
        gate.scan_paths([source_dir])


def test_nested_junction_is_rejected_before_walking_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path / "app"
    linked = source_dir / "linked"
    linked.mkdir(parents=True)
    (source_dir / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (linked / "outside.py").write_text("import pickle\n", encoding="utf-8")

    is_junction = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == linked or is_junction(path),
    )
    real_walk = gate.os.walk
    visited: list[Path] = []

    def track_walk(*args: object, **kwargs: object) -> object:
        for entry in real_walk(*args, **kwargs):
            visited.append(Path(entry[0]))
            yield entry

    monkeypatch.setattr(gate.os, "walk", track_walk)
    with pytest.raises(gate.ScanError, match="source directory junction"):
        gate.scan_paths([source_dir])

    assert visited == [source_dir]


def test_junction_check_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    is_junction = Path.is_junction

    def fail_junction_check(path: Path) -> bool:
        if path == source:
            raise PermissionError("denied")
        return is_junction(path)

    monkeypatch.setattr(Path, "is_junction", fail_junction_check)
    with pytest.raises(gate.ScanError, match="cannot inspect source path"):
        gate.scan_paths([source])


def test_input_symlinks_and_non_regular_paths_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    linked = tmp_path / "linked.py"
    special = tmp_path / "special"
    real_lstat = Path.lstat

    def fake_lstat(path: Path) -> object:
        if path == linked:
            return SimpleNamespace(st_mode=stat.S_IFLNK)
        if path == special:
            return SimpleNamespace(st_mode=stat.S_IFCHR)
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", fake_lstat)
    with pytest.raises(gate.ScanError, match="source path symlink"):
        gate.scan_paths([linked])
    with pytest.raises(gate.ScanError, match="not a regular file or directory"):
        gate.scan_paths([special])


def test_resolution_and_read_errors_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.py"
    source.write_text("value = 1\n", encoding="utf-8")
    real_resolve = Path.resolve

    def fail_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path == source:
            raise RuntimeError("resolution failed")
        return real_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    with pytest.raises(gate.ScanError, match="cannot inspect source path"):
        gate.scan_paths([source])


def test_tokenize_open_reads_valid_pep263_source(tmp_path: Path) -> None:
    source = tmp_path / "latin1.py"
    source.write_bytes(b"# coding: latin-1\nname = 'caf\xe9'\n")

    count, findings = gate.scan_paths([source])

    assert count == 1
    assert findings == ()


def test_tokenize_open_reads_utf8_bom_and_finds_pickle_import(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bom.py"
    source.write_bytes(b"\xef\xbb\xbfimport pickle  # nosec\n")

    count, findings = gate.scan_paths([source])

    assert count == 1
    assert len(findings) == 1
    assert "pickle" in findings[0].message


@pytest.mark.parametrize(
    "content",
    [
        b"\xff",
        b"# coding: unknown-codec\nvalue = 1\n",
    ],
)
def test_invalid_source_encodings_fail_closed(tmp_path: Path, content: bytes) -> None:
    source = tmp_path / "invalid.py"
    source.write_bytes(content)

    with pytest.raises(gate.ScanError, match="cannot read Python source"):
        gate.scan_paths([source])


def test_main_returns_distinct_status_for_clean_findings_and_scan_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = tmp_path / "clean.py"
    unsafe = tmp_path / "unsafe.py"
    invalid = tmp_path / "invalid.py"
    empty = tmp_path / "empty"
    empty.mkdir()
    clean.write_text("value = 1\n", encoding="utf-8")
    unsafe.write_text("from _pickle import loads # nosec\n", encoding="utf-8")
    invalid.write_text("def invalid(:\n", encoding="utf-8")

    assert gate.ALLOWED_PICKLE_FINDING_COUNT == 0
    assert gate.main([str(clean)]) == 0
    assert "allowed=0" in capsys.readouterr().out
    assert gate.main([str(unsafe)]) == 1
    assert "pickle" in capsys.readouterr().out.lower()
    assert gate.main([str(invalid)]) == 2
    assert "no_pickle_scan_error" in capsys.readouterr().err
    assert gate.main([str(empty)]) == 2
    assert "no_pickle_scan_error" in capsys.readouterr().err


def test_script_entrypoint_exits_with_scanner_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [str(MODULE_PATH), str(clean)])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(str(MODULE_PATH), run_name="__main__")

    assert exc_info.value.code == 0


@pytest.mark.parametrize(
    ("source", "module"),
    [
        (
            'import importlib as loader\nloader.import_module("pickle")  # nosec',
            "pickle",
        ),
        (
            "from importlib import import_module as load_module\n"
            'load_module("_pickle")  # nosec',
            "_pickle",
        ),
        (
            'import builtins as native\nnative.__import__("pickle")  # nosec',
            "pickle",
        ),
        (
            "from builtins import __import__ as load_module\n"
            'load_module("_pickle")  # nosec',
            "_pickle",
        ),
        (
            'module_name = "pickle"\n__import__(module_name)  # nosec',
            "pickle",
        ),
        (
            'import importlib\nmodule_name = "_pickle"\n'
            "importlib.import_module(module_name)  # nosec",
            "_pickle",
        ),
    ],
)
def test_known_dynamic_pickle_imports_are_rejected_despite_nosec(
    source: str, module: str
) -> None:
    findings = gate.scan_source(source, filename="unsafe.py")

    assert len(findings) == 1
    assert findings[0].path == Path("unsafe.py")
    assert f"dynamic pickle import: {module}" in findings[0].message


def test_known_safe_dynamic_imports_are_ignored() -> None:
    source = """
import importlib as loader
from importlib import import_module as load_module
import builtins as native
from builtins import __import__ as dynamic_import
loader.import_module("json")
load_module("json")
native.__import__("json")
dynamic_import("json")
module_name = "json"
__import__(module_name)
"""

    assert gate.scan_source(source, filename="safe.py") == ()


@pytest.mark.parametrize(
    ("source", "module"),
    [
        (
            "import importlib as loader\nload_module = loader.import_module\n"
            'load_module("pickle")  # nosec',
            "pickle",
        ),
        (
            "from importlib import import_module as load_module\n"
            'alias = load_module\nalias("_pickle")  # nosec',
            "_pickle",
        ),
        (
            'load_module = __import__\nload_module(name="pickle")  # nosec',
            "pickle",
        ),
        (
            "from importlib import import_module as load_module\n"
            'load_module(name="_pickle")  # nosec',
            "_pickle",
        ),
        (
            'import importlib as loader\nmodule_name = "pick" + "le"\n'
            "loader.import_module(module_name)  # nosec",
            "pickle",
        ),
        (
            'module_name = "pickle"\nmodule_alias = module_name\n'
            "__import__(module_alias)  # nosec",
            "pickle",
        ),
    ],
)
def test_aliased_and_static_dynamic_pickle_imports_are_rejected(
    source: str, module: str
) -> None:
    findings = gate.scan_source(source, filename="unsafe.py")

    assert len(findings) == 1
    assert f"dynamic pickle import: {module}" in findings[0].message


def test_unrelated_or_unknown_dynamic_imports_are_ignored() -> None:
    source = """
import importlib as loader
from importlib import import_module as load_module
from importlib import machinery
loader.import_module()
loader.import_module(name=unknown_module)
load_module("json")
factory().import_module("pickle")
loader.import_module(resolve_module_name())
holder.importer: object = loader.import_module
"""

    assert gate.scan_source(source, filename="safe.py") == ()


@pytest.mark.parametrize(
    ("source", "module"),
    [
        (
            'module_name: str = "_pickle"\n__import__(module_name)  # nosec',
            "_pickle",
        ),
        (
            'load_module: object = __import__\nload_module("pickle")  # nosec',
            "pickle",
        ),
        (
            'prefix = "pickle"\nimport importlib\n'
            'importlib.import_module(prefix + ".core")  # nosec',
            "pickle.core",
        ),
    ],
)
def test_annotated_or_composed_known_pickle_imports_are_rejected(
    source: str, module: str
) -> None:
    findings = gate.scan_source(source, filename="unsafe.py")

    assert len(findings) == 1
    assert f"dynamic pickle import: {module}" in findings[0].message


def test_unknown_dynamic_module_expression_is_ignored() -> None:
    source = """
import importlib
importlib.import_module(unknown_name + ".pickle")
"""

    assert gate.scan_source(source, filename="safe.py") == ()


def test_main_rejects_dynamic_pickle_import_despite_nosec(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    unsafe = tmp_path / "unsafe_dynamic.py"
    unsafe.write_text(
        "from importlib import import_module as load_module\n"
        'load_module("_pickle")  # nosec\n',
        encoding="utf-8",
    )

    assert gate.main([str(unsafe)]) == 1
    output = capsys.readouterr().out
    assert "dynamic pickle import: _pickle" in output
    assert "violations=1" in output


@pytest.mark.parametrize(
    "source",
    [
        (
            "import importlib\nmodule_alias = importlib\n"
            'module_alias.import_module("pickle")  # nosec'
        ),
        (
            "import importlib as imported\nmodule_alias = imported\n"
            'module_alias.import_module("_pickle")  # nosec'
        ),
    ],
)
def test_assigned_importlib_module_aliases_are_rejected(source: str) -> None:
    findings = gate.scan_source(source, filename="unsafe.py")

    assert len(findings) == 1
    assert "dynamic pickle import" in findings[0].message


@pytest.mark.parametrize(
    "source",
    [
        (
            'import importlib\nname = "pickle"\nname = resolve()\n'
            "importlib.import_module(name)  # nosec"
        ),
        (
            "from importlib import import_module as load_module\n"
            'load_module = resolve()\nload_module("pickle")  # nosec'
        ),
        (
            "import importlib\nimportlib = resolve()\n"
            'importlib.import_module("pickle")  # nosec'
        ),
        (
            "import importlib\n"
            "def decode(importlib):\n"
            '    importlib.import_module("pickle")  # nosec'
        ),
        (
            "import importlib\n"
            "def decode(name):\n"
            "    importlib.import_module(name)  # nosec"
        ),
        (
            "from importlib import import_module as load_module\n"
            "def decode(load_module):\n"
            '    load_module("pickle")  # nosec'
        ),
        (
            "import importlib\n"
            "def decode():\n"
            "    importlib = resolve()\n"
            '    importlib.import_module("pickle")  # nosec'
        ),
        (
            "import importlib\n"
            "if condition:\n"
            "    importlib = resolve()\n"
            '    importlib.import_module("pickle")  # nosec\n'
            'importlib.import_module("pickle")  # nosec'
        ),
        (
            'import importlib\nname = "pickle"\n'
            "def decode(name):\n"
            "    importlib.import_module(name)  # nosec"
        ),
    ],
)
def test_rebinding_and_scope_shadows_do_not_use_stale_pickle_bindings(
    source: str,
) -> None:
    assert gate.scan_source(source, filename="safe.py") == ()


def test_unshadowed_dynamic_imports_in_function_scopes_are_rejected() -> None:
    source = """
import importlib

def decode():
    importlib.import_module("pickle")  # nosec

def load():
    from importlib import import_module as import_value
    import_value("_pickle")  # nosec
"""

    findings = gate.scan_source(source, filename="unsafe_function.py")

    assert len(findings) == 2
    assert all("dynamic pickle import" in finding.message for finding in findings)


def test_function_and_nested_scope_bindings_do_not_leak() -> None:
    source = """
import importlib as module_loader

def outer():
    import json as module_loader
    from json import loads as load_module

    @decorate(module_loader)
    def nested(
        module_loader,
        load_module=resolve(),
        /,
        *args: module_loader,
        required: module_loader,
        optional: module_loader = module_loader,
        **kwargs,
    ) -> module_loader:
        module_loader.import_module("pickle")
        load_module("pickle")

    async def nested_async(module_loader):
        module_loader.import_module("_pickle")

    class Local:
        pass

    local_lambda = lambda value="pickle": module_loader.import_module(value)
    keyword_lambda = lambda *, value: module_loader.import_module("pickle")
    list_values = [module_loader.import_module("pickle") for module_loader in []]
    set_values = {module_loader.import_module("_pickle") for module_loader in []}
    dict_values = {module_loader.import_module("pickle"): None for module_loader in []}
    generator = (module_loader.import_module("_pickle") for module_loader in [])
    conditional_values = [
        module_loader.import_module("pickle")
        for module_loader in []
        if module_loader is None
    ]

    def untyped(value):
        return

    def annotated(
        value: module_loader,
        /,
        *args: module_loader,
        required: module_loader,
        optional: module_loader = module_loader,
        **kwargs,
    ):
        return module_loader.import_module("json")

    try:
        raise ValueError
    except Exception as module_loader:
        module_loader.import_module("pickle")

    try:
        raise ValueError
    except:
        pass

    with manager:
        pass

    match 0:
        case {"value": [module_loader]} as match_result if match_result is not None:
            module_loader.import_module("pickle")
        case [*module_loader]:
            module_loader.import_module("_pickle")
        case [*_]:
            pass
        case _:
            pass
"""

    assert gate.scan_source(source, filename="scopes.py") == ()


def test_class_body_uses_predefinition_binding_but_methods_use_class_binding() -> None:
    unsafe = (
        'import importlib\nclass importlib:\n    importlib.import_module("pickle")\n'
    )
    findings = gate.scan_source(unsafe, filename="class_body.py")
    assert len(findings) == 1
    assert "dynamic pickle import: pickle" in findings[0].message

    safe = 'import importlib\nclass importlib:\n    def decode(self):\n        importlib.import_module("pickle")\n'
    assert gate.scan_source(safe, filename="class_method.py") == ()


def test_class_comprehension_body_uses_enclosing_scope_not_class_namespace() -> None:
    source = 'import importlib\nclass Example:\n    importlib = resolve()\n    values = [importlib.import_module("pickle") for _ in [0]]\n'

    findings = gate.scan_source(source, filename="class_comprehension.py")

    assert len(findings) == 1
    assert "dynamic pickle import: pickle" in findings[0].message


def test_uninitialized_annotation_bare_raise_and_assert_are_safe() -> None:
    source = """
def control():
    value: object
    try:
        assert True
    except Exception:
        raise
"""

    assert gate.scan_source(source, filename="safe_controls.py") == ()


def test_static_expression_and_assignment_target_controls() -> None:
    source = """
import importlib
module_name = "pickle" if condition else "pickle"
unknown_module_name = "pickle" if condition else "_pickle"
importlib.import_module(unknown_module_name)
if (module_alias := importlib):
    module_alias.import_module(module_name)  # nosec

importlib, *rest = resolve_pair()
importlib.import_module("pickle")  # nosec

values = [module_alias.import_module("pickle") for module_alias, *tail in []]
other = [importlib.import_module("pickle") for object.field in []]
"""

    source += "\nimport json\njson.loads(payload)\n"
    findings = gate.scan_source(source, filename="targets.py")

    assert len(findings) == 1
    assert findings[0].message == "dynamic pickle import: pickle"


def test_unknown_reassignment_augassign_and_delete_invalidate_bindings() -> None:
    source = """
import importlib
from importlib import import_module as load_module
name = "pickle"
name = resolve()
importlib.import_module(name)
load_module = resolve()
load_module("pickle")
name = "pickle"
name += suffix
importlib.import_module(name)
name = "pickle"
del name
importlib.import_module(name)
"""

    assert gate.scan_source(source, filename="writes.py") == ()


def test_safe_dynamic_imports_in_function_annotations_defaults_and_decorators() -> None:
    source = """
import importlib as module_loader

@decorate(module_loader.import_module("json"))
def typed(
    first: module_loader.import_module("json") = module_loader.import_module("json"),
    /,
    *args: module_loader.import_module("json"),
    keyword_only: module_loader.import_module("json") = module_loader.import_module("json"),
    **kwargs: module_loader.import_module("json"),
) -> module_loader.import_module("json"):
    return module_loader.import_module("json")
"""

    assert gate.scan_source(source, filename="annotations.py") == ()


def test_imported_pickle_api_use_is_reported() -> None:
    findings = gate.scan_source(
        "import _pickle\n_pickle.loads(payload)\n", filename="api.py"
    )

    assert len(findings) == 2
    assert any("pickle module import" in finding.message for finding in findings)
    assert any("pickle API use: loads" in finding.message for finding in findings)


def test_statement_control_flow_forms_are_scanned_and_merged() -> None:
    source = """
import importlib

with manager as local_importer:
    local_importer.import_module("pickle")

for local_importer in ():
    local_importer.import_module("pickle")
else:
    pass

while False:
    importlib.import_module("_pickle")
else:
    pass

try:
    importlib.import_module("pickle")
except ImportError as local_importer:
    local_importer.import_module("pickle")
else:
    importlib.import_module("_pickle")
finally:
    pass

class Local:
    importlib = resolve()
    importlib.import_module("pickle")
"""

    findings = gate.scan_source(source, filename="flow.py")

    assert len(findings) == 3
    assert all("dynamic pickle import" in finding.message for finding in findings)


def test_function_scope_with_varargs_and_assignment_expressions_is_scanned() -> None:
    source = """
import importlib

def decode(*importlib, **module_name):
    importlib.import_module("pickle")
    return module_name

if (name := "pickle"):
    importlib.import_module(name)
"""

    findings = gate.scan_source(source, filename="bindings.py")

    assert len(findings) == 1
    assert findings[0].message == "dynamic pickle import: pickle"


def test_remaining_scope_and_statement_shapes_are_scanned() -> None:
    source = """
import importlib as module_loader

def reassign_global():
    global module_loader
    module_loader = resolve()
    module_loader.import_module("pickle")

def outer():
    closure_loader = module_loader

    def inner():
        nonlocal closure_loader
        closure_loader = resolve()
        closure_loader.import_module("pickle")

    @decorate(module_loader.import_module("json"))
    def typed(
        value: module_loader.import_module("json") = module_loader.import_module("json"),
        /,
        *args: module_loader.import_module("json"),
        keyword_only: module_loader.import_module("json") = module_loader.import_module("json"),
        **kwargs: module_loader.import_module("json"),
    ) -> module_loader.import_module("json"):
        assert module_loader.import_module("json"), module_loader.import_module("json")
        raise ValueError from module_loader.import_module("json")

    class Local(base_factory(), metaclass=metaclass_factory()):
        pass

    values = [module_loader.import_module("pickle") for module_loader in [] if module_loader is None]
    match subject:
        case {"value": [module_loader]} as match_result if match_result is not None:
            module_loader.import_module("pickle")

class TopLevelLocal(base_factory(), metaclass=metaclass_factory()):
    pass

# The generic statement fallback still scans expressions in type aliases.
type DynamicType[T] = module_loader.import_module("json")
"""

    assert gate.scan_source(source, filename="shapes.py") == ()
