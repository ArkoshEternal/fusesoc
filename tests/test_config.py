# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import os
import os.path
import tempfile

import pytest
from test_common import cache_root, cores_root, library_root

from fusesoc.config import Config

build_root = "test_build_root"

EXAMPLE_CONFIG = """
[main]
build_root = {build_root}
cache_root = {cache_root}
cores_root = {cores_root}
library_root = {library_root}

[library.test_lib]
location = {library_root}/test_lib
auto-sync = false
sync-uri = https://github.com/fusesoc/fusesoc-cores
"""


def test_config():
    tcf = tempfile.NamedTemporaryFile(mode="w+")
    tcf.write(
        EXAMPLE_CONFIG.format(
            build_root=build_root,
            cache_root=cache_root,
            cores_root=cores_root,
            library_root=library_root,
        )
    )
    tcf.seek(0)

    conf = Config(tcf.name)

    assert conf.library_root == library_root


@pytest.mark.parametrize("from_cli", [False, True])
@pytest.mark.parametrize("from_config", [False, True])
def test_config_filters(from_cli, from_config):
    import tempfile

    from fusesoc.config import Config

    overrides = {"filters": ["clifilter1", "clifilter2"]} if from_cli else None
    if from_config:
        tcf = tempfile.NamedTemporaryFile(mode="w+")
        tcf.write("[main]\nfilters = configfilter1 configfilter2\n")
        tcf.seek(0)
        config = Config(tcf.name, overrides=overrides)
    else:
        config = Config(overrides=overrides)

    expected = {
        (False, False): [],
        (False, True): ["configfilter1", "configfilter2"],
        (True, False): ["clifilter1", "clifilter2"],
        (True, True): ["configfilter1", "configfilter2", "clifilter1", "clifilter2"],
    }
    assert config.filters == expected[(from_cli, from_config)]


def test_config_relative_path():
    with tempfile.TemporaryDirectory() as td:
        config_path = os.path.join(td, "fusesoc.conf")
        with open(config_path, "w") as tcf:
            tcf.write(
                EXAMPLE_CONFIG.format(
                    build_root="build_root",
                    cache_root="cache_root",
                    cores_root="cores_root",
                    library_root="library_root",
                )
            )

        conf = Config(tcf.name)
        for name in ["build_root", "cache_root", "library_root"]:
            abs_td = os.path.realpath(td)
            assert getattr(conf, name) == os.path.join(abs_td, name)


def test_config_relative_path_starts_with_dot():
    with tempfile.TemporaryDirectory() as td:
        config_path = os.path.join(td, "fusesoc.conf")
        with open(config_path, "w") as tcf:
            tcf.write(
                EXAMPLE_CONFIG.format(
                    build_root="./build_root",
                    cache_root="./cache_root",
                    cores_root="./cores_root",
                    library_root="./library_root",
                )
            )

        conf = Config(tcf.name)
        for name in ["build_root", "cache_root", "library_root"]:
            abs_td = os.path.realpath(td)
            assert getattr(conf, name) == os.path.join(abs_td, name)


def test_config_relative_path_with_local_config():
    prev_dir = os.getcwd()
    with tempfile.TemporaryDirectory() as td:
        os.chdir(td)
        config_path = "fusesoc.conf"
        with open(config_path, "w") as tcf:
            tcf.write(
                EXAMPLE_CONFIG.format(
                    build_root="build_root",
                    cache_root="cache_root",
                    cores_root="cores_root",
                    library_root="library_root",
                )
            )

        conf = Config(tcf.name)
        for name in ["build_root", "cache_root", "library_root"]:
            abs_td = os.path.realpath(td)
            assert getattr(conf, name) == os.path.join(abs_td, name)
    os.chdir(prev_dir)


def test_config_libraries():
    tcf = tempfile.NamedTemporaryFile(mode="w+")
    tcf.write(
        EXAMPLE_CONFIG.format(
            build_root=build_root,
            cache_root=cache_root,
            cores_root=cores_root,
            library_root=library_root,
        )
    )
    tcf.seek(0)

    conf = Config(tcf.name)

    lib = None
    for library in conf.libraries:
        if library.name == "test_lib":
            lib = library
    assert lib

    assert lib.location == os.path.join(library_root, "test_lib")
    assert lib.sync_uri == "https://github.com/fusesoc/fusesoc-cores"
    assert not lib.auto_sync


def test_config_write():
    tcf = tempfile.NamedTemporaryFile(mode="w+", delete=False)
    tcf.write(
        EXAMPLE_CONFIG.format(
            build_root=build_root,
            cache_root=cache_root,
            cores_root=cores_root,
            library_root=library_root,
        )
    )
    tcf.flush()

    with Config(tcf.name) as c:
        c.build_root = "/tmp"

    conf = Config(tcf.name)

    assert conf.build_root == "/tmp"
    os.remove(tcf.name)


def test_effective_config_path_env_var(monkeypatch):
    monkeypatch.setenv("FUSESOC_CONFIG", "/some/path/fusesoc.conf")
    assert Config.resolve_path(None) == "/some/path/fusesoc.conf"


def test_effective_config_path_cli_overrides_env_var(monkeypatch):
    monkeypatch.setenv("FUSESOC_CONFIG", "/env/path/fusesoc.conf")
    assert Config.resolve_path("/cli/path/fusesoc.conf") == "/cli/path/fusesoc.conf"


def test_effective_config_path_no_env_var_no_cli(monkeypatch):
    monkeypatch.delenv("FUSESOC_CONFIG", raising=False)
    assert Config.resolve_path(None) is None


def test_config_missing_file_logs_warning(tmp_path, caplog):
    import logging

    missing = str(tmp_path / "nonexistent.conf")
    with caplog.at_level(logging.WARNING, logger="fusesoc.config"):
        Config(missing, create_if_missing=False)
    assert any(missing in m for m in caplog.messages)


def test_config_missing_file_does_not_create_file(tmp_path, caplog):
    missing = tmp_path / "nonexistent.conf"
    Config(str(missing), create_if_missing=False)
    assert not missing.exists()


def test_config_missing_file_creates_file_when_allowed(tmp_path):
    new_conf = tmp_path / "new.conf"
    Config(str(new_conf), create_if_missing=True)
    assert new_conf.exists()


def test_config_missing_file_no_warning_when_create_allowed(tmp_path, caplog):
    import logging

    new_conf = tmp_path / "new.conf"
    with caplog.at_level(logging.WARNING, logger="fusesoc.config"):
        Config(str(new_conf), create_if_missing=True)
    assert not caplog.records


def test_config_loaded_via_env_var(monkeypatch):
    with tempfile.NamedTemporaryFile(mode="w+", suffix=".conf", delete=False) as tcf:
        tcf.write(
            EXAMPLE_CONFIG.format(
                build_root=build_root,
                cache_root=cache_root,
                cores_root=cores_root,
                library_root=library_root,
            )
        )
        config_path = tcf.name

    try:
        monkeypatch.setenv("FUSESOC_CONFIG", config_path)
        conf = Config(Config.resolve_path(None))
        assert conf.library_root == library_root
    finally:
        os.remove(config_path)


def test_config_overrides_validation():
    from fusesoc.exceptions import ConfigError

    with pytest.raises(ConfigError, match="Unknown config override"):
        Config(overrides={"no_such_option": 1})


def test_config_override_wins_including_falsy():
    tcf = tempfile.NamedTemporaryFile(mode="w+")
    tcf.write("[main]\nno_export = true\nbuild_root = /from/file\n")
    tcf.seek(0)

    config = Config(tcf.name, overrides={"no_export": False, "build_root": "/cli"})
    # Unlike the old args_* mechanism, a falsy override beats a truthy file value
    assert config.no_export is False
    assert config.build_root == "/cli"

    # Without overrides the file values apply
    config_plain = Config(tcf.name)
    assert config_plain.no_export is True
    assert config_plain.build_root == "/from/file"


def test_config_from_dict():
    from fusesoc.exceptions import ConfigError
    from fusesoc.librarymanager import Library

    config = Config.from_dict(
        {
            "build_root": "/b",
            "system_name": "mysys",
            "cores_root": ["/cores/a", "/cores/b"],
            "libraries": [Library("mylib", "/some/loc")],
        }
    )
    assert config.build_root == "/b"
    assert config.system_name == "mysys"
    # List-valued path options round-trip as lists, not stringified
    assert config.cores_root == ["/cores/a", "/cores/b"]
    assert [lib.name for lib in config.libraries] == ["mylib"]

    with pytest.raises(ConfigError, match="Unknown config option"):
        Config.from_dict({"no_such_option": 1})


def test_config_filters_setter_accepts_list():
    tcf = tempfile.NamedTemporaryFile(mode="w+")
    config = Config(tcf.name, create_if_missing=True)
    config.filters = ["f1", "f2"]
    # Round-trips as two filters, not as the repr of a Python list
    assert config.filters == ["f1", "f2"]


def test_record_library_duplicate_raises(tmp_path):
    from fusesoc.exceptions import LibraryExistsError
    from fusesoc.librarymanager import Library

    config_file = tmp_path / "fusesoc.conf"
    config = Config(str(config_file), create_if_missing=True)
    lib = Library("dup", str(tmp_path), "local", str(tmp_path))

    config.record_library(lib)
    with pytest.raises(LibraryExistsError):
        config.record_library(lib)
    with pytest.raises(LibraryExistsError):
        config.add_library(lib)
