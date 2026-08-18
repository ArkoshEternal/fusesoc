# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import pytest


def test_deptree(tmp_path):
    import os

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    tests_dir = os.path.dirname(__file__)
    deptree_cores_dir = os.path.join(tests_dir, "capi2_cores", "deptree")
    lib = Library("deptree", deptree_cores_dir)

    cm = CoreManager(Config())
    cm.add_library(lib, [])

    root_core = cm.get_core(Vlnv("::deptree-root"))

    # This is an array of (child, parent) core name tuples and
    # is used for checking that the flattened list of core
    # names is consistent with the dependencies.
    dependencies = (
        # Dependencies of the root core
        ("::deptree-child3:0", "::deptree-root:0"),
        ("::deptree-child2:0", "::deptree-root:0"),
        ("::deptree-child1:0", "::deptree-root:0"),
        ("::deptree-child-a:0", "::deptree-root:0"),
        # Dependencies of child1 core
        ("::deptree-child3:0", "::deptree-child1:0"),
        # Dependencies of child-a core
        ("::deptree-child4:0", "::deptree-child-a:0"),
    )

    # The ordered files that we expect from each core.
    expected_core_files = {
        "::deptree-child3:0": (
            "child3-fs1-f1.sv",
            "child3-fs1-f2.sv",
        ),
        "::deptree-child2:0": (
            "child2-fs1-f1.sv",
            "child2-fs1-f2.sv",
        ),
        "::deptree-child1:0": (
            "child1-fs1-f1.sv",
            "child1-fs1-f2.sv",
        ),
        "::deptree-child4:0": ("child4.sv",),
        "::deptree-child-a:0": (
            # Files from filesets are always included before any
            # files from generators with "position: append".
            # This is because generated files are often dependent on files
            # that are not generated, and it convenient to be able to
            # include them in the same core.
            # However, for peculiar cases when non-generated files actually depend on generated, "position: prepend" is also available
            "child-a2.sv",
            "generated-child-a-prepend.sv",
            "generated-child-a.sv",
            "generated-child-a-append.sv",
        ),
        "::deptree-root:0": (
            "root-fs1-f1.sv",
            "root-fs1-f2.sv",
            "root-fs2-f1.sv",
            "root-fs2-f2.sv",
        ),
    }

    # Use Edalizer to get the files.
    # This is necessary because we need to run generators.
    work_root = str(tmp_path / "work")
    os.mkdir(work_root)
    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        work_root=work_root,
        core_manager=cm,
    )
    edam = edalizer.run()

    # Check dependency tree (after running all generators)
    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    all_core_names = set()
    for child, parent in dependencies:
        assert child in deps_names
        assert parent in deps_names
        all_core_names.add(child)
        all_core_names.add(parent)
    # Confirm that we don't have any extra or missing core names.
    assert all_core_names == set(deps_names)
    # Make sure there are no repeats in deps_names
    assert len(all_core_names) == len(deps_names)

    # Now work out what order we expect to get the filenames.
    # The order of filenames within each core in deterministic.
    # Each fileset in order. Followed by each generator in order.
    # The order between the cores is taken the above `dep_names`.
    expected_filenames = []
    # A generator-created core with "position: first"
    expected_filenames.append("generated-child-a-first.sv")
    for dep_name in deps_names:
        expected_filenames += list(expected_core_files[dep_name])
    # A generator-created core with "position: last"
    expected_filenames.append("generated-child-a-last.sv")

    edalized_filenames = [os.path.basename(f["name"]) for f in edam["files"]]

    assert edalized_filenames == expected_filenames


def test_copyto():
    import os
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    work_root = tempfile.mkdtemp(prefix="copyto_")

    core_dir = os.path.join(os.path.dirname(__file__), "cores", "misc", "copytocore")
    lib = Library("misc", core_dir)

    cm = CoreManager(Config())
    cm.add_library(lib, [])

    core = cm.get_core(Vlnv("::copytocore"))

    edalizer = Edalizer(
        toplevel=core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
        export_root=None,
        system_name=None,
    )
    edam = edalizer.run()
    edalizer.export()

    assert edam["files"] == [
        {
            "file_type": "user",
            "core": "::copytocore:0",
            "name": "copied.file",
        },
        {
            "file_type": "tclSource",
            "core": "::copytocore:0",
            "name": "subdir/another.file",
        },
        {
            "file_type": "tclSource",
            "core": "::copytocore:0",
            "name": "copytodot",
        },
    ]
    assert os.path.exists(os.path.join(work_root, "copied.file"))
    assert os.path.exists(os.path.join(work_root, "subdir", "another.file"))
    assert os.path.exists(os.path.join(work_root, "copytodot"))


@pytest.mark.network
def test_export():
    import os
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    export_root = os.path.join(build_root, "exported_files")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "cores")

    cm = CoreManager(Config())
    cm.add_library(Library("cores", core_dir), [])

    core = cm.get_core(Vlnv("::wb_intercon"))

    edalizer = Edalizer(
        toplevel=core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
        export_root=export_root,
        system_name=None,
    )
    edalizer.run()
    edalizer.export()

    for f in [
        "wb_intercon_1.0/dummy_icarus.v",
        "wb_intercon_1.0/bench/wb_mux_tb.v",
        "wb_intercon_1.0/bench/wb_upsizer_tb.v",
        "wb_intercon_1.0/bench/wb_intercon_tb.v",
        "wb_intercon_1.0/bench/wb_arbiter_tb.v",
        "wb_intercon_1.0/rtl/verilog/wb_data_resize.v",
        "wb_intercon_1.0/rtl/verilog/wb_mux.v",
        "wb_intercon_1.0/rtl/verilog/wb_arbiter.v",
        "wb_intercon_1.0/rtl/verilog/wb_upsizer.v",
    ]:
        assert os.path.isfile(os.path.join(export_root, f))


def test_override(caplog):
    import logging
    import os

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    core_base_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "override")
    cm = CoreManager(Config())
    with caplog.at_level(logging.WARNING):
        cm.add_library(Library("1", os.path.join(core_base_dir, "1")), [])
    assert caplog.text == ""

    with caplog.at_level(logging.WARNING):
        cm.add_library(Library("2", os.path.join(core_base_dir, "2")), [])
    assert "Replacing ::basic:0 in" in caplog.text

    core = cm.get_core(Vlnv("::basic"))
    assert core.core_root.endswith("2")


def test_virtual():
    import os
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "virtual")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])

    test_vectors = {
        "::top_impl1": ["::impl1:0", "::user:0", "::top_impl1:0"],
        "::top_impl2": ["::impl2:0", "::user:0", "::top_impl2:0"],
    }
    for top_vlnv, expected_deps in test_vectors.items():
        root_core = cm.get_core(Vlnv(top_vlnv))

        edalizer = Edalizer(
            toplevel=root_core.name,
            flags=flags,
            core_manager=cm,
            work_root=work_root,
        )
        edalizer.run()

        deps = cm.get_depends(root_core.name, {})
        deps_names = [str(c) for c in deps]

        assert deps_names == expected_deps


def test_virtual_conflict():
    """
    Test virtual core selection when there are more than one selected implementation.
    This shall result in a conflict of cores.
    """
    import os
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager, DependencyError
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "virtual")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])

    root_core = cm.get_core(Vlnv("::top_conflict"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )
    with pytest.raises(DependencyError) as _:
        edalizer.run()


def test_virtual_non_deterministic_virtual(caplog):
    """
    Test virtual core selection when there are no selected implementations.
    This shall result in a warning that the virtual core selection is non-deteministic.
    """
    import logging
    import os
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "virtual")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])

    root_core = cm.get_core(Vlnv("::top_non_deterministic"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )
    edalizer.run()

    with caplog.at_level(logging.WARNING):
        edalizer.run()
    assert "Non-deterministic selection of virtual core" in caplog.text

    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    for dependency in deps_names:
        assert dependency in [
            "::impl1:0",
            "::impl2:0",
            "::user:0",
            "::top_non_deterministic:0",
        ]


def test_mapping_success_cases():
    from pathlib import Path

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    core_dir = Path(__file__).parent / "capi2_cores" / "mapping"

    top = "test_mapping:t:top"
    top_vlnv = Vlnv(top)

    for mappings, expected_deps in (
        (
            [],
            {
                "test_mapping:t:top:0",
                "test_mapping:l:a:0",
                "test_mapping:l:b:0",
                "test_mapping:l:c:0",
            },
        ),
        (
            [top],
            {
                "test_mapping:t:top:0",
                "test_mapping:l:f:0",
                "test_mapping:l:b:0",
                "test_mapping:l:c:0",
            },
        ),
        (
            ["test_mapping:l:d"],
            {
                "test_mapping:t:top:0",
                "test_mapping:l:a:0",
                "test_mapping:l:d:0",
                "test_mapping:l:e:0",
            },
        ),
        (
            [top, "test_mapping:l:d"],
            {
                "test_mapping:t:top:0",
                "test_mapping:l:f:0",
                "test_mapping:l:d:0",
                "test_mapping:l:e:0",
            },
        ),
        (
            ["test_mapping:l:c"],
            {
                "test_mapping:t:top:0",
                "test_mapping:l:a:0",
                "test_mapping:l:b:0",
            },
        ),
    ):
        cm = CoreManager(Config())
        cm.add_library(Library("mapping_test", core_dir), [])

        cm.db.mapping_set(mappings)

        actual_deps = {str(c) for c in cm.get_depends(top_vlnv, {})}

        assert expected_deps == actual_deps


def test_mapping_failure_cases():
    from pathlib import Path

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.librarymanager import Library

    core_dir = Path(__file__).parent / "capi2_cores" / "mapping"

    for mappings in (
        ["test_mapping:m:non_existent"],
        ["test_mapping:m:map_vers"],
        ["test_mapping:m:map_rec"],
        ["test_mapping:t:top", "test_mapping:l:c"],
        ["test_mapping:t:top", "test_mapping:t:top"],
    ):
        cm = CoreManager(Config())
        cm.add_library(Library("mapping_test", core_dir), [])

        with pytest.raises(RuntimeError):
            cm.db.mapping_set(mappings)


def test_lockfile(caplog):
    """
    Test core selection with a core pinned by a lock file
    """
    import logging
    import os
    import pathlib
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "dependencies")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])
    cm.db.load_lockfile(
        pathlib.Path(__file__).parent / "lockfiles" / "dependencies.lock.yml", True
    )

    root_core = cm.get_core(Vlnv("::dependencies-top"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )

    with caplog.at_level(logging.WARNING):
        edalizer.run()

    assert caplog.records == []

    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    for dependency in deps_names:
        assert dependency in [
            "::used:1.1",
            "::dependencies-top:0",
        ]


def test_lockfile_partial_warning(caplog):
    """
    Test core selection with a core pinned by a lock file
    """
    import logging
    import os
    import pathlib
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "dependencies")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])
    cm.db.load_lockfile(
        pathlib.Path(__file__).parent / "lockfiles" / "dependencies-partial.lock.yml",
        True,
    )

    root_core = cm.get_core(Vlnv("::dependencies-top"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )

    with caplog.at_level(logging.WARNING):
        edalizer.run()

    assert "Using lock file with partial list of cores" in caplog.text

    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    for dependency in deps_names:
        assert dependency in [
            "::used:1.1",
            "::dependencies-top:0",
        ]


def test_lockfile_version_warning(caplog):
    """
    Test core selection with a core pinned by a lock file, warning if version is out of scope
    """
    import logging
    import os
    import pathlib
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "dependencies")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])
    cm.db.load_lockfile(
        pathlib.Path(__file__).parent
        / "lockfiles"
        / "dependencies-partial-1.0.lock.yml",
        True,
    )

    root_core = cm.get_core(Vlnv("::dependencies-top"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )

    with caplog.at_level(logging.WARNING):
        edalizer.run()

    assert "Failed to pin" in caplog.text

    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    for dependency in deps_names:
        assert dependency in [
            "::used:1.1",
            "::dependencies-top:0",
        ]


def test_lockfile_no_file(caplog):
    """
    Test core selection with a core pinned by a lock file
    """
    import logging
    import os
    import pathlib
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "dependencies")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])
    filepath = pathlib.Path(__file__).parent / "lockfiles" / "missing.lock.yml"
    cm.db.load_lockfile(filepath, True)

    root_core = cm.get_core(Vlnv("::dependencies-top"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )

    with caplog.at_level(logging.WARNING):
        edalizer.run()

    assert f"Lockfile {filepath} not found" in caplog.text
    assert not filepath.exists()

    if filepath.exists():
        filepath.unlink()

    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    for dependency in deps_names:
        assert dependency in [
            "::used:1.1",
            "::dependencies-top:0",
        ]


def test_lockfile_no_file_create(caplog):
    """
    Test core selection with a core pinned by a lock file
    """
    import logging
    import os
    import pathlib
    import tempfile

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.edalizer import Edalizer
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    flags = {"tool": "icarus"}

    build_root = tempfile.mkdtemp(prefix="export_")
    work_root = os.path.join(build_root, "work")

    core_dir = os.path.join(os.path.dirname(__file__), "capi2_cores", "dependencies")

    cm = CoreManager(Config())
    cm.add_library(Library("virtual", core_dir), [])
    filepath = pathlib.Path(__file__).parent / "lockfiles" / "created.lock.yml"
    cm.db.load_lockfile(filepath, False)

    root_core = cm.get_core(Vlnv("::dependencies-top"))

    edalizer = Edalizer(
        toplevel=root_core.name,
        flags=flags,
        core_manager=cm,
        work_root=work_root,
    )

    with caplog.at_level(logging.WARNING):
        edalizer.run()

    assert f"Lockfile {filepath} not found" in caplog.text
    assert filepath.exists()

    if filepath.exists():
        filepath.unlink()

    deps = cm.get_depends(root_core.name, {})
    deps_names = [str(c) for c in deps]

    for dependency in deps_names:
        assert dependency in [
            "::used:1.1",
            "::dependencies-top:0",
        ]


def test_find_cores_records_parse_errors(tmp_path):
    """A malformed .core file should be recorded on ``parse_errors`` so callers
    can surface it later instead of having the warning silently scroll off
    screen.

    Regression test for https://github.com/olofk/fusesoc/issues/761.
    """
    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.librarymanager import Library

    (tmp_path / "broken.core").write_text(
        "CAPI=2:\n"
        "name: ::broken:0\n"
        "filesets:\n"
        "  fs:\n"
        "    files: not_an_array\n"
        "targets:\n"
        "  default:\n"
        "    filesets: [fs]\n"
    )
    (tmp_path / "good.core").write_text(
        "CAPI=2:\nname: ::good:0\ntargets:\n  default: {}\n"
    )

    cm = CoreManager(Config())
    cm.add_library(Library("broken-test", str(tmp_path)), [])

    # The valid core is still discoverable.
    cores = {str(c) for c in cm.get_cores()}
    assert "::good:0" in cores
    assert "::broken:0" not in cores

    # The broken core is recorded so a "core not found" caller can surface it.
    assert len(cm.parse_errors) == 1
    bad_file, msg = cm.parse_errors[0]
    assert bad_file.endswith("broken.core")
    assert "must be array" in msg


def test_load_lockfile_invalidates_solver_cache(tmp_path):
    """Loading a lock file invalidates the solver cache, so a subsequent
    solve honors the pinned versions.
    """
    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    core_dir = tmp_path / "cores"
    core_dir.mkdir()
    (core_dir / "top.core").write_text(
        "CAPI=2:\n"
        "name: ::lockstale-top\n"
        "filesets:\n"
        "  fs1:\n"
        "    depend:\n"
        '      - ">=::used:1.0"\n'
        "targets:\n"
        "  default:\n"
        "    filesets:\n"
        "      - fs1\n"
    )
    (core_dir / "used-1.0.core").write_text(
        "CAPI=2:\nname: ::used:1.0\ntargets:\n  default: {}\n"
    )
    (core_dir / "used-1.1.core").write_text(
        "CAPI=2:\nname: ::used:1.1\ntargets:\n  default: {}\n"
    )
    lockfile = tmp_path / "pin-1.0.lock.yml"
    lockfile.write_text(
        "cores:\n" '  - name: "::used:1.0"\n' '  - name: "::lockstale-top:0"\n'
    )

    # A Config with an explicit path keeps the test hermetic: Config() with
    # path=None would read ~/.config and /etc and mkdir the user's cache dir.
    config_file = tmp_path / "fusesoc.conf"
    config_file.write_text(f"[main]\ncache_root = {tmp_path / 'cache'}\n")

    cm = CoreManager(Config(str(config_file)))
    cm.add_library(Library("lockstale", str(core_dir)), [])

    # Without a lock file the highest version of ::used is selected.
    deps_before = cm.get_depends(Vlnv("::lockstale-top"), {})
    assert {str(c) for c in deps_before} == {"::used:1.1", "::lockstale-top:0"}

    cm.db.load_lockfile(lockfile, True)

    # The lock file pins ::used:1.0 and takes effect immediately.
    deps_after = cm.get_depends(Vlnv("::lockstale-top"), {})
    assert {str(c) for c in deps_after} == {"::used:1.0", "::lockstale-top:0"}


def test_mapping_set_invalidates_solver_cache(tmp_path):
    """Applying a mapping invalidates the solver cache, so a subsequent solve
    honors the mapping.
    """
    from pathlib import Path

    from fusesoc.config import Config
    from fusesoc.coremanager import CoreManager
    from fusesoc.librarymanager import Library
    from fusesoc.vlnv import Vlnv

    core_dir = Path(__file__).parent / "capi2_cores" / "mapping"
    top_vlnv = Vlnv("test_mapping:t:top")

    # A Config with an explicit path keeps the test hermetic: Config() with
    # path=None would read ~/.config and /etc and mkdir the user's cache dir.
    config_file = tmp_path / "fusesoc.conf"
    config_file.write_text(f"[main]\ncache_root = {tmp_path / 'cache'}\n")

    cm = CoreManager(Config(str(config_file)))
    cm.add_library(Library("mapping_test", core_dir), [])

    unmapped_deps = {
        "test_mapping:t:top:0",
        "test_mapping:l:a:0",
        "test_mapping:l:b:0",
        "test_mapping:l:c:0",
    }

    deps_before = cm.get_depends(top_vlnv, {})
    assert {str(c) for c in deps_before} == unmapped_deps

    # The mapping of test_mapping:l:d replaces b->d and c->e and takes
    # effect immediately.
    cm.db.mapping_set(["test_mapping:l:d"])
    deps_after = cm.get_depends(top_vlnv, {})
    assert {str(c) for c in deps_after} == {
        "test_mapping:t:top:0",
        "test_mapping:l:a:0",
        "test_mapping:l:d:0",
        "test_mapping:l:e:0",
    }


def test_solve_is_toplevel_not_leaked_between_cores(tmp_path):
    """CoreDB._solve evaluates each core's expressions with its own
    is_toplevel value; the flag no longer leaks between loop iterations, so
    the outcome does not depend on core registration order.
    """
    from fusesoc.capi2.coreparser import Core2Parser
    from fusesoc.core import Core
    from fusesoc.coremanager import CoreDB, DependencyError
    from fusesoc.vlnv import Vlnv

    (tmp_path / "top.core").write_text(
        "CAPI=2:\n"
        "name: ::top:0\n"
        "filesets:\n"
        "  fs1:\n"
        "    depend:\n"
        '      - "::virt-iface"\n'
        "targets:\n"
        "  default:\n"
        "    filesets:\n"
        "      - fs1\n"
    )
    (tmp_path / "impl.core").write_text(
        "CAPI=2:\n"
        "name: ::impl:0\n"
        "virtual:\n"
        '  - "is_toplevel? (::virt-iface)"\n'
    )

    parser = Core2Parser()
    top = Core(parser=parser, core_file=str(tmp_path / "top.core"))
    impl = Core(parser=parser, core_file=str(tmp_path / "impl.core"))

    # The conditional virtual only fires when is_toplevel is set...
    assert [str(v) for v in impl.get_virtuals({})] == []
    assert [str(v) for v in impl.get_virtuals({"is_toplevel": True})] == [
        "::virt-iface:0"
    ]

    # ...and ::impl is never the toplevel, so it never provides ::virt-iface
    # during dependency resolution, regardless of registration order.
    db = CoreDB()
    db.add(top, None)
    db.add(impl, None)
    with pytest.raises(DependencyError):
        db.solve(Vlnv("::top"), {})

    db_reversed = CoreDB()
    db_reversed.add(impl, None)
    db_reversed.add(top, None)
    with pytest.raises(DependencyError):
        db_reversed.solve(Vlnv("::top"), {})


def test_dependency_error_str_includes_msg():
    """DependencyError stringification includes both the failing value and,
    when given, the explanatory msg."""
    from fusesoc.coremanager import DependencyError

    e = DependencyError("foo", msg="bar")
    assert str(e) == "'foo': bar"
    assert e.value == "foo"
    assert e.msg == "bar"
    assert str(DependencyError("foo")) == "'foo'"


def test_solver_cache_lookup_miss_returns_sentinel():
    """CoreDB._solver_cache_lookup signals a cache miss with a dedicated
    sentinel, so a cached falsy value is not mistaken for a miss.
    """
    from fusesoc.coremanager import _CACHE_MISS, CoreDB

    db = CoreDB()
    assert db._solver_cache_lookup(("no", "such", "key")) is _CACHE_MISS

    # A stored value is returned as-is on a hit.
    db._solver_cache_store(("some", "key"), ["value"])
    assert db._solver_cache_lookup(("some", "key")) == ["value"]
