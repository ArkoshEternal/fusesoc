# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for the Fusesoc facade as a library API (no CLI involved)."""

import os

import pytest

from fusesoc.config import Config
from fusesoc.exceptions import (
    AmbiguousCoreError,
    CoreNotFoundError,
    FusesocError,
    ToolOrFlowError,
)
from fusesoc.fusesoc import Fusesoc, resolve_stages
from fusesoc.librarymanager import Library

tests_dir = os.path.dirname(__file__)
cores_dir = os.path.join(tests_dir, "capi2_cores", "misc")


def _make_fs(tmp_path, cores_root):
    config_file = tmp_path / "fusesoc.conf"
    config_file.write_text(f"[main]\ncache_root = {tmp_path / 'cache'}\n")
    config = Config(
        str(config_file),
        overrides={
            "cores_root": [cores_root],
            "build_root": str(tmp_path / "build"),
        },
    )
    return Fusesoc(config)


def test_resolve_core(tmp_path):
    fs = _make_fs(tmp_path, cores_dir)

    # Full VLNV and short name resolve to the same core
    assert str(fs.resolve_core("::flags:0").name) == "::flags:0"
    assert str(fs.resolve_core("flags").name) == "::flags:0"

    with pytest.raises(CoreNotFoundError) as excinfo:
        fs.resolve_core("no-such-core")
    assert "this core was not found" in str(excinfo.value)
    assert isinstance(excinfo.value.parse_errors, list)


def test_resolve_core_ambiguous(tmp_path):
    core_dir = tmp_path / "cores"
    core_dir.mkdir()
    for vendor in ("vendora", "vendorb"):
        (core_dir / f"{vendor}.core").write_text(
            f"CAPI=2:\nname: {vendor}:lib:samecore:1.0\ntargets:\n  default: {{}}\n"
        )
    fs = _make_fs(tmp_path, str(core_dir))

    with pytest.raises(AmbiguousCoreError) as excinfo:
        fs.resolve_core("samecore")
    assert excinfo.value.candidates == {
        "vendora:lib:samecore",
        "vendorb:lib:samecore",
    }
    assert "is ambiguous" in str(excinfo.value)


def test_resolve_stages():
    # No stage requested -> all stages
    assert resolve_stages(False, False, False) == (True, True, True)
    # build implies setup
    assert resolve_stages(False, True, False) == (True, True, False)
    assert resolve_stages(True, False, False) == (True, False, False)
    assert resolve_stages(False, False, True) == (False, False, True)
    with pytest.raises(FusesocError, match="Configure and run without build"):
        resolve_stages(True, False, True)


def test_build_edam_returns_edam_without_writing(tmp_path):
    core_dir = tmp_path / "cores"
    core_dir.mkdir()
    (core_dir / "top.v").write_text("module top; endmodule\n")
    (core_dir / "apicore.core").write_text(
        "CAPI=2:\n"
        "name: ::apicore:1.0\n"
        "filesets:\n"
        "  rtl:\n"
        "    files: [top.v]\n"
        "    file_type: verilogSource\n"
        "targets:\n"
        "  default:\n"
        "    filesets: [rtl]\n"
        "    toplevel: top\n"
        "    default_tool: icarus\n"
    )
    fs = _make_fs(tmp_path, str(core_dir))
    core = fs.resolve_core("::apicore")

    edam, work_root = fs.build_edam(core, {})

    assert edam["name"] == "apicore_1.0"
    assert edam["toplevel"] == "top"
    # Files are exported under src/<core>/ by default
    assert [os.path.basename(f["name"]) for f in edam["files"]] == ["top.v"]
    # build_edam does not write the EDAM file; get_backend does
    edam_file = os.path.join(work_root, "apicore_1.0.eda.yml")
    assert not os.path.exists(edam_file)

    # write_edam writes it, and rewriting identical content is a no-op
    fs.write_edam(edam, edam_file)
    assert os.path.exists(edam_file)
    mtime = os.path.getmtime(edam_file)
    fs.write_edam(edam, edam_file)
    assert os.path.getmtime(edam_file) == mtime


def test_resolve_backend_class_errors(tmp_path):
    fs = _make_fs(tmp_path, cores_dir)
    core = fs.resolve_core("::flags")

    # No tool or flow anywhere
    with pytest.raises(ToolOrFlowError, match="No flow or tool"):
        fs.resolve_backend_class(core, {"target": "empty_default"})

    # Nonexistent tool
    with pytest.raises(ToolOrFlowError, match="not found"):
        fs.resolve_backend_class(core, {"tool": "no_such_tool_ever"})


def test_get_tools():
    try:
        from edalize.edatool import walk_tool_packages  # noqa: F401
    except ImportError:
        pytest.skip("installed edalize version has no walk_tool_packages")
    tools = Fusesoc.get_tools()
    assert isinstance(tools, dict)
    assert "icarus" in tools


def test_library_from_uri(tmp_path):
    # Existing directory -> local provider, location is the URI itself
    lib = Library.from_uri(str(tmp_path))
    assert lib.sync_type == "local"
    assert lib.location == str(tmp_path)
    assert lib.name == tmp_path.name

    # Non-directory -> git, location under the default root
    lib = Library.from_uri("https://example.com/repo/mylib")
    assert lib.sync_type == "git"
    assert lib.name == "mylib"
    assert lib.location == os.path.join("fusesoc_libraries", "mylib")

    # Explicit values win
    lib = Library.from_uri(
        "https://example.com/repo/mylib",
        name="renamed",
        location="/explicit",
        sync_type="git",
        default_root="/root",
    )
    assert (lib.name, lib.location) == ("renamed", "/explicit")


def test_library_update_returns_results(tmp_path):
    from fusesoc.librarymanager import LibraryManager

    lm = LibraryManager()
    # A local library is skipped cleanly
    lm.add_library(Library("loc", str(tmp_path), "local"))
    # A git library without a sync-uri is an error
    lm.add_library(Library("broken", str(tmp_path / "nope"), "git", None))

    results = lm.update(["loc", "broken", "missing"])
    assert results["loc"] is None
    assert "sync-uri" in results["broken"]
    assert results["missing"] == "Could not find library"
