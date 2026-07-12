# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Tests for using FuseSoC programmatically through the Fusesoc facade."""

import os

import pytest
from test_common import tests_dir

from fusesoc.config import Config
from fusesoc.errors import AmbiguousCoreNameError, CoreNotFoundError
from fusesoc.fusesoc import Fusesoc

blinky_dir = os.path.join(tests_dir, "userguide", "blinky")

MINIMAL_CORE = """CAPI=2:
name: {name}

targets:
  default: {{}}
"""


def _config(tmp_path, contents=""):
    """An isolated Config that does not read the user's fusesoc.conf."""
    conf_path = tmp_path / "fusesoc.conf"
    conf_path.write_text(f"[main]\ncache_root = {tmp_path}/cache\n" + contents)
    return Config(str(conf_path))


def test_cores_root_constructor_arg(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])
    assert "fusesoc:examples:blinky:1.0.0" in fs.get_cores()


def test_get_core_resolves_partial_name(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])
    core = fs.get_core("blinky")
    assert str(core.name) == "fusesoc:examples:blinky:1.0.0"


def test_get_core_not_found_raises(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])
    with pytest.raises(CoreNotFoundError) as excinfo:
        fs.get_core("doesnotexist")
    assert "this core was not found" in str(excinfo.value)


def test_get_core_ambiguous_name_raises(tmp_path):
    lib = tmp_path / "cores"
    (lib / "a").mkdir(parents=True)
    (lib / "b").mkdir()
    (lib / "a" / "ambig.core").write_text(
        MINIMAL_CORE.format(name="vendora:lib:ambig:1.0")
    )
    (lib / "b" / "ambig.core").write_text(
        MINIMAL_CORE.format(name="vendorb:lib:ambig:1.0")
    )

    fs = Fusesoc(_config(tmp_path), cores_root=[str(lib)])
    with pytest.raises(AmbiguousCoreNameError) as excinfo:
        fs.get_core("ambig")
    assert excinfo.value.candidates == {"vendora:lib:ambig", "vendorb:lib:ambig"}


def test_get_target_flags(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])
    core = fs.get_core("blinky")
    flags = fs.get_target_flags(core, target="sim", flags={"myflag": True})
    assert flags["target"] == "sim"
    assert flags["myflag"] is True


def test_run_target_setup_only(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])
    build_root = str(tmp_path / "build")

    result = fs.run_target(
        "fusesoc:examples:blinky",
        target="sim",
        build=False,
        run=False,
        build_root=build_root,
    )

    expected_work_root = os.path.join(
        build_root, "fusesoc_examples_blinky_1.0.0", "sim-icarus"
    )
    assert result.work_root == expected_work_root
    assert str(result.core.name) == "fusesoc:examples:blinky:1.0.0"
    assert os.path.exists(result.edam_file)
    assert os.path.exists(os.path.join(result.work_root, "Makefile"))


def test_run_target_work_root_override(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])
    work_root = str(tmp_path / "workroot")

    result = fs.run_target(
        "blinky", target="sim", build=False, run=False, work_root=work_root
    )

    assert result.work_root == work_root
    assert os.path.exists(os.path.join(work_root, "Makefile"))


def test_run_target_filters_arg(tmp_path):
    fs = Fusesoc(_config(tmp_path), cores_root=[blinky_dir])

    result = fs.run_target(
        "blinky",
        target="sim",
        build=False,
        run=False,
        build_root=str(tmp_path / "build"),
        filters=["dot"],
    )

    # The dot filter writes <edam name>.gv into the work root
    assert os.path.exists(
        os.path.join(result.work_root, "fusesoc_examples_blinky_1.0.0.gv")
    )


def test_run_target_config_file_filters(tmp_path):
    fs = Fusesoc(
        _config(tmp_path, contents="filters = dot\n"), cores_root=[blinky_dir]
    )

    result = fs.run_target(
        "blinky",
        target="sim",
        build=False,
        run=False,
        build_root=str(tmp_path / "build"),
    )

    assert os.path.exists(
        os.path.join(result.work_root, "fusesoc_examples_blinky_1.0.0.gv")
    )


def test_get_tools():
    try:
        from edalize.edatool import walk_tool_packages  # noqa: F401
    except ImportError:
        pytest.skip("Installed edalize does not provide walk_tool_packages")

    tools = Fusesoc.get_tools()
    assert "icarus" in tools
