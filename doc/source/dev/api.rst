.. _dev_api:

Using FuseSoC from Python
=========================

Everything the ``fusesoc`` command-line tool can do is available
programmatically through the :class:`fusesoc.fusesoc.Fusesoc` class. This
makes it possible to run targets and query cores from other tools, e.g. a
pytest testbench runner or a custom build script.

The API never calls ``sys.exit()`` and never prints results. Errors are
raised as :class:`fusesoc.errors.FusesocError` subclasses (or
``RuntimeError`` from lower layers); results are returned as values.

Running a target
----------------

The one-shot :meth:`~fusesoc.fusesoc.Fusesoc.run_target` mirrors the
``fusesoc run`` command::

    from fusesoc.config import Config
    from fusesoc.fusesoc import Fusesoc

    fs = Fusesoc(Config(), cores_root=["path/to/my/cores"])

    result = fs.run_target(
        "my:lib:some_soc",
        target="sim",
        flags={"my_use_flag": True},
        build_root="/tmp/build",
    )
    print(result.work_root)  # where the build happened
    print(result.edam_file)  # the generated EDAM file

``Config()`` reads the usual ``fusesoc.conf`` locations; pass a path
(``Config("my.conf")``) to use a specific file. The ``cores_root``
constructor argument registers additional core libraries, equivalent to the
``--cores-root`` command-line option. Per-run options such as
``build_root``, ``work_root``, ``no_export``, ``system_name`` and
``filters`` are keyword arguments on ``run_target`` and override the config
file values.

The ``setup``, ``build`` and ``run`` booleans select which stages to
execute. For finer control, compose the underlying primitives and drive the
edalize backend directly::

    core = fs.get_core("some_soc")  # bare names are resolved
    flags = fs.get_target_flags(core, target="synth")
    edam_file, backend = fs.get_backend(core, flags)

    backend.configure()
    backend.build()  # inspect outputs between stages as needed
    backend.run()

Use in a pytest fixture
-----------------------

::

    import pytest
    from fusesoc.config import Config
    from fusesoc.fusesoc import Fusesoc


    @pytest.fixture(scope="session")
    def fusesoc():
        return Fusesoc(Config(), cores_root=["rtl/"])


    def test_smoke_sim(fusesoc, tmp_path):
        result = fusesoc.run_target(
            "my:lib:some_soc", target="sim", build_root=str(tmp_path)
        )
        assert (tmp_path / "some.log").exists()

Querying cores and libraries
----------------------------

::

    fs.get_cores()          # {vlnv string: core object} for all known cores
    core = fs.get_core("some_soc")
    core.get_description()
    fs.get_libraries()      # registered Library objects
    Fusesoc.get_tools()     # {edalize tool name: description}

:meth:`~fusesoc.fusesoc.Fusesoc.get_core` raises
:class:`~fusesoc.errors.CoreNotFoundError` for unknown cores and
:class:`~fusesoc.errors.AmbiguousCoreNameError` when a bare name matches
several cores.
