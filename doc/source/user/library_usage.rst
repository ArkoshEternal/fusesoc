.. _ug_library_usage:

Using FuseSoC as a Python library
=================================

FuseSoC can be used as a Python library from other tools and frontends, not
just through the ``fusesoc`` command line. The supported API is exported from
the top-level :mod:`fusesoc` package; anything imported from submodules
directly is considered internal and may change without notice.

All errors raised by the library derive from :class:`fusesoc.FusesocError`,
so a frontend can catch that single type at its boundary and dispatch on the
specific subclasses (:class:`fusesoc.CoreNotFoundError`,
:class:`fusesoc.DependencyError`, :class:`fusesoc.FlagError`, ...) where it
wants to react differently. Library code never terminates the process.

Getting started
---------------

.. code-block:: python

   from fusesoc import Config, Flags, Fusesoc

   # Read fusesoc.conf from the default locations (/etc, XDG, cwd), a
   # specific file, or construct a configuration programmatically:
   config = Config.from_dict(
       {
           "build_root": "/tmp/build",
           "cores_root": ["/path/to/my/cores"],
       }
   )

   fs = Fusesoc(config)

   # Resolve a core; short names work like on the command line
   core = fs.resolve_core("my-soc")

Configuration values can also be overridden per-instance without a config
file edit, which replaces the command line's argument handling:

.. code-block:: python

   config = Config("fusesoc.conf", overrides={"no_export": True})

Flags
-----

Target, tool and use flags are represented by the immutable
:class:`fusesoc.Flags` class. It validates the reserved flags (``target``,
``tool``, ``flow``, ``is_toplevel``) and rejects use flags that collide with
them:

.. code-block:: python

   flags = Flags(target="synth", tool="vivado", use_flags={"fast": True})

   # or, from CLI-style strings:
   flags = Flags.from_cli_strings(["+fast", "-debug"], target="synth")

Building
--------

To produce the EDAM description of a system without touching disk, or run a
full flow:

.. code-block:: python

   # EDAM only (e.g. to feed a custom build system)
   edam, work_root = fs.build_edam(core, flags)

   # ... or a backend, ready to configure/build/run
   edam_file, backend = fs.get_backend(core, flags)
   backend.configure()
   backend.build()

   # ... or the full stage pipeline the CLI runs, in one call
   fs.run(core, flags)

Backend-specific parameters (the trailing arguments of ``fusesoc run``) are
passed programmatically as a mapping:

.. code-block:: python

   edam, work_root = fs.build_edam(core, flags, backend_params={"SIMULATOR": "verilator"})

Lock files and mappings are explicit calls:

.. code-block:: python

   fs.load_lockfile("my-design.lock.yml")
   fs.set_mappings(["my:mapping:core"])

Logging
-------

The library reports progress through the standard :mod:`logging` module
(logger names below ``fusesoc``). A frontend configures handlers as it sees
fit; :meth:`fusesoc.Fusesoc.init_logging` sets up the CLI's colored console
logging and is entirely optional.
