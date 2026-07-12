# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os
import shutil
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from fusesoc.config import Config
from fusesoc.coremanager import CoreManager, DependencyError
from fusesoc.edalizer import Edalizer
from fusesoc.errors import (
    AmbiguousCoreNameError,
    CoreNotFoundError,
    FusesocError,
    StageFailedError,
)
from fusesoc.librarymanager import Library, LibraryManager
from fusesoc.utils import setup_logging, yaml_fread
from fusesoc.vlnv import Vlnv

try:
    from edalize.edatool import ToolResolutionError, get_edatool
except ImportError:
    from edalize import get_edatool

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    """Artifacts of a :meth:`Fusesoc.run_target` invocation.

    ``backend`` is the edalize flow/tool instance; its ``configure()``,
    ``build()`` and ``run()`` methods can be called directly to (re)run
    individual stages.
    """

    core: object
    backend: object
    edam_file: str
    work_root: str


# Clean out old work root
def _clean_work_root(work_root):
    if os.path.exists(work_root):
        for f in os.listdir(work_root):
            if os.path.isdir(os.path.join(work_root, f)):
                shutil.rmtree(os.path.join(work_root, f))
            else:
                os.remove(os.path.join(work_root, f))
    else:
        os.makedirs(work_root)


class Fusesoc:
    """Programmatic entry point to FuseSoC.

    Wires up a :class:`Config`, a library manager and a core manager, and
    exposes the operations the ``fusesoc`` CLI is built on: querying cores
    and libraries, and running targets through edalize backends.

    Errors are signaled by raising :class:`fusesoc.errors.FusesocError`
    subclasses (or ``RuntimeError`` from lower layers); methods never call
    ``sys.exit()`` or print results.
    """

    def __init__(
        self,
        config=None,
        cores_root=None,
        verbose=False,
        resolve_env_vars_early=None,
        allow_additional_properties=None,
    ):
        """
        Args:
            config: A :class:`Config` instance. ``None`` creates a default
                one (read from the standard fusesoc.conf locations).
            cores_root: Extra core-root directories to register as libraries,
                in addition to the libraries from the config.
            verbose: Pass verbose=True to the edalize backend.
            resolve_env_vars_early: Resolve environment variables while
                parsing core files. ``None`` uses the config value.
            allow_additional_properties: Allow unknown properties in core
                files. ``None`` uses the config value.
        """
        if config is None:
            config = Config()
        self.config = config
        self.verbose = verbose

        if resolve_env_vars_early is None:
            resolve_env_vars_early = config.resolve_env_vars_early
        self.resolve_env_vars_early = resolve_env_vars_early

        self.lm = LibraryManager(config.library_root)
        self.cm = CoreManager(
            self.config,
            library_manager=self.lm,
            resolve_env_vars_early=resolve_env_vars_early,
            allow_additional_properties=allow_additional_properties,
        )

        self._cores_root = list(cores_root or [])

        self._register_libraries()

    def _register_libraries(self):
        cores_root_libs = [
            Library(acr, acr) for acr in self.config.cores_root + self._cores_root
        ]
        # Add libraries from config file, env var and command-line
        for library in self.config.libraries + cores_root_libs:
            try:
                self.add_library(library)
            except (RuntimeError, OSError):
                try:
                    temporary_lm = LibraryManager(self.config.library_root)
                    # try to initialize library
                    temporary_lm.add_library(library)
                    temporary_lm.update([library.name])
                    # the initialization worked, now register it properly
                    self.add_library(library)
                except (RuntimeError, OSError) as e:
                    _s = "Failed to register library '{}'"
                    logger.warning(_s.format(str(e)))

    @staticmethod
    def init_logging(verbose, monochrome, log_file=None):
        """
        Call before instantiation of fusesoc.Fusesoc or fusesoc.Config classes if logging is required.
        """
        level = logging.DEBUG if verbose else logging.INFO

        setup_logging(level, monochrome, log_file)

        if verbose:
            logger.debug("Verbose output")
        else:
            logger.debug("Concise output")

        if monochrome:
            logger.debug("Monochrome output")
        else:
            logger.debug("Colorful output")

    @staticmethod
    def get_tools():
        """Enumerate the available edalize tools.

        Returns a dict mapping tool names to their descriptions.
        """
        from edalize.edatool import get_edatool, walk_tool_packages

        tools = {}
        for tool_name in walk_tool_packages():
            try:
                tools[tool_name] = get_edatool(tool_name).get_doc(0)["description"]
            # Ignore any misbehaving backends
            except Exception:
                pass
        return tools

    def add_library(self, library):
        self.cm.add_library(library, self.config.ignored_dirs)

    def get_library(self, library_name):
        return self.lm.get_library(library_name)

    def update_libraries(self, library_names):
        self.lm.update(library_names)

    def get_libraries(self):
        return self.lm.get_libraries()

    def resolve_core_name(self, core_name):
        """Resolve a bare core name to a full VLNV string.

        If ``core_name`` contains no ``:`` it is matched case-insensitively
        against the names of all known cores. A single match returns the
        matching ``vendor:library:name`` string; multiple matches raise
        :class:`AmbiguousCoreNameError`. Otherwise ``core_name`` is
        returned unchanged.
        """
        if ":" in core_name:
            return core_name

        matches = set()
        for core in self.get_cores():
            (vendor, library, name, _) = core.split(":")
            if name.lower() == core_name.lower():
                matches.add(f"{vendor}:{library}:{name}")
        if len(matches) > 1:
            raise AmbiguousCoreNameError(core_name, matches)
        if matches:
            return matches.pop()
        return core_name

    def get_core(self, name):
        """Look up a core by name.

        ``name`` is a VLNV string, a bare core name (resolved with
        :meth:`resolve_core_name`), or a :class:`Vlnv`. Raises
        :class:`CoreNotFoundError` if the core does not exist.
        """
        if isinstance(name, Vlnv):
            core_name = str(name)
            vlnv = name
        else:
            core_name = self.resolve_core_name(name)
            vlnv = Vlnv(core_name)

        try:
            return self.cm.get_core(vlnv)
        except DependencyError as e:
            msg = (
                f"{core_name!r} or any of its dependencies requires {e.value!r}, but "
                "this core was not found"
            )
            # If any core file failed to parse during library scanning, the missing
            # core may simply be one that was silently ignored. Surface those errors
            # alongside the "not found" message so they don't get lost in the log
            # scrollback.
            if self.parse_errors:
                msg += (
                    "\n\n"
                    "The following core files failed to parse and were ignored "
                    "during the library scan; one of them may define the missing "
                    "core:"
                )
                for core_file, err in self.parse_errors:
                    msg += f"\n  - {core_file}: {err}"
            raise CoreNotFoundError(msg, core_name=core_name) from e

    @property
    def parse_errors(self):
        """``(core_file, error_message)`` tuples for files that failed to parse
        during library scanning. Forwarded from the underlying ``CoreManager``
        so callers don't need to reach through the wrapper."""
        return self.cm.parse_errors

    def get_cores(self):
        return self.cm.get_cores()

    def find_cores(self, library):
        return self.cm.find_cores(library, self.config.ignored_dirs)

    def get_generators(self):
        return self.cm.get_generators()

    def apply_mappings(self, mapping_vlnvs):
        """Apply core mappings before dependency resolution.

        ``mapping_vlnvs`` is an iterable of VLNV strings of cores whose
        mappings to apply. Can only be called once per session.
        """
        self.cm.db.mapping_set(mapping_vlnvs)

    def load_lockfile(self, path):
        """Load a lockfile that pins core versions for dependency resolution."""
        try:
            self.cm.db.load_lockfile(path)
        except SyntaxError as e:
            raise FusesocError(f"Failed to load lock file, {str(e)}") from e

    def clean_generator_cache(self):
        """Remove the generator cache directory. Returns the removed path."""
        cachedir = os.path.join(self.config.cache_root, "generator_cache")
        shutil.rmtree(cachedir, ignore_errors=True)
        return cachedir

    def get_target_flags(self, core, target=None, tool=None, flags=None):
        """Build the effective flags dict for running ``core``.

        Combines the target (default ``"default"``), an optional tool, any
        caller-supplied flags, and the core's own flags for the target.
        """
        _flags = {"target": target or "default"}
        if tool:
            _flags["tool"] = tool
        if flags:
            _flags.update(flags)

        return dict(core.get_flags(_flags["target"]), **_flags)

    def get_work_root(self, core, flags, build_root=None, work_root=None):
        """Compute the work root directory for a core and flags combination.

        ``build_root`` and ``work_root`` override the config values when
        given.
        """
        flow = core.get_flow(flags)

        target = flags["target"]

        if build_root is None:
            build_root = self.config.build_root
        if work_root is None:
            work_root = self.config.work_root

        build_root = os.path.join(build_root, core.name.sanitized_name)

        if flow:
            logger.debug(f"Using flow API (flow={flow})")
            work_root = work_root or os.path.join(build_root, target)
        else:
            logger.debug("flow not set. Falling back to tool API")
            if "tool" in flags:
                tool = flags["tool"]
            else:
                tool_error = "No flow or tool was supplied on command line or found in '{}' core description"
                raise RuntimeError(tool_error.format(core.name.sanitized_name))

            work_root = work_root or os.path.join(build_root, f"{target}-{tool}")

        return work_root

    def get_backend(
        self,
        core,
        flags,
        backendargs=[],
        build_root=None,
        work_root=None,
        no_export=None,
        system_name=None,
        filters=None,
    ):
        """Set up a core+flags combination for building with edalize.

        Runs the FuseSoC frontend (dependency resolution, generators, file
        export, EDAM creation) and returns ``(edam_file, backend)`` where
        ``backend`` is an edalize flow/tool instance ready for its
        ``configure()``/``build()``/``run()`` stages.

        ``build_root``, ``work_root``, ``no_export`` and ``system_name``
        override the config values when given; ``filters`` are applied in
        addition to the config-file filters.
        """
        work_root = self.get_work_root(
            core, flags, build_root=build_root, work_root=work_root
        )

        if no_export is None:
            no_export = self.config.no_export
        if system_name is None:
            system_name = self.config.system_name

        if not no_export:
            export_root = os.path.join(work_root, "src")
            logger.debug(f"Setting export_root to {export_root}")
        else:
            export_root = None

        edam_file = os.path.join(work_root, core.name.sanitized_name + ".eda.yml")

        flow = core.get_flow(flags)

        backend_class = None
        if flow:
            try:
                backend_class = getattr(
                    import_module(f"edalize.flows.{flow}"), flow.capitalize()
                )
            except ModuleNotFoundError:
                raise RuntimeError(f"Flow {flow!r} not found")
            except ImportError:
                raise RuntimeError(
                    "Selected Edalize version does not support the flow API"
                )

        else:
            if "tool" in flags:
                tool = flags["tool"]
            else:
                tool_error = "No flow or tool was supplied on command line or found in '{}' core description"
                raise RuntimeError(tool_error.format(core.name.sanitized_name))
            try:
                backend_class = get_edatool(tool)
            except ToolResolutionError:
                raise RuntimeError(f"Backend {tool!r} not found")

        edalizer = Edalizer(
            toplevel=core.name,
            flags=flags,
            core_manager=self.cm,
            work_root=work_root,
            export_root=export_root,
            system_name=system_name,
            resolve_env_vars=self.resolve_env_vars_early,
        )

        try:
            edalizer.run()
            edalizer.export()
            Path(work_root).mkdir(parents=True, exist_ok=True)
            edalizer.parse_args(backend_class, backendargs)
            edalizer.apply_filters(self.config.filters + list(filters or []))
        except SyntaxError as e:
            raise RuntimeError(e.msg)
        except RuntimeError as e:
            raise RuntimeError("Setup failed : {}".format(str(e)))
        except DependencyError as e:
            raise RuntimeError("Failed to resolve dependencies. " + e.msg)
        except FileNotFoundError as e:
            raise FusesocError(f'Could not find EDA API file "{e.filename}"')

        if os.path.exists(edam_file):
            old_edam = yaml_fread(edam_file, self.resolve_env_vars_early)
        else:
            old_edam = None

        if edalizer.edam != old_edam:
            edalizer.to_yaml(edam_file)

        return edam_file, backend_class(
            edam=edalizer.edam, work_root=work_root, verbose=self.verbose
        )

    def run_target(
        self,
        core,
        target=None,
        tool=None,
        flags=None,
        backendargs=None,
        setup=True,
        build=True,
        run=True,
        clean=False,
        build_root=None,
        work_root=None,
        no_export=None,
        system_name=None,
        filters=None,
    ):
        """Run a target of a core through the FuseSoC frontend and an edalize
        backend, mirroring the ``fusesoc run`` CLI command.

        ``core`` is a core name string, a :class:`Vlnv` or an already
        resolved core object. The ``setup``/``build``/``run`` booleans
        select which stages to execute; ``setup`` also controls whether the
        work root is cleaned for tool-API (or ``clean=True``) builds. Note
        that, matching the CLI, the configure stage actually runs only when
        the generated Makefile is missing or older than the EDAM file.

        ``build_root``, ``work_root``, ``no_export``, ``system_name`` and
        ``filters`` override the config values, as in :meth:`get_backend`.

        Raises :class:`StageFailedError` if an edalize stage fails; returns
        a :class:`RunResult` with the core, backend, EDAM file and work root.
        """
        if isinstance(core, (str, Vlnv)):
            core = self.get_core(core)

        flags = self.get_target_flags(core, target=target, tool=tool, flags=flags)

        # Unconditionally clean out the work root on fresh builds
        # if we use the old tool API or clean flag is set
        if setup and (not core.get_flow(flags) or clean):
            _clean_work_root(
                self.get_work_root(
                    core, flags, build_root=build_root, work_root=work_root
                )
            )

        # Frontend/backend separation

        edam_file, backend = self.get_backend(
            core,
            flags,
            backendargs or [],
            build_root=build_root,
            work_root=work_root,
            no_export=no_export,
            system_name=system_name,
            filters=filters,
        )

        makefile = os.path.join(backend.work_root, "Makefile")
        do_configure = not os.path.exists(makefile) or (
            os.path.getmtime(makefile) < os.path.getmtime(edam_file)
        )

        if do_configure:
            try:
                backend.configure()
            except RuntimeError as e:
                raise StageFailedError(
                    "configure", "Failed to configure the system\n" + str(e)
                ) from e

        if build:
            try:
                backend.build()
            except RuntimeError as e:
                raise StageFailedError(
                    "build", f"Failed to build {core.name} : {e}"
                ) from e

        if run:
            try:
                backend.run()
            except RuntimeError as e:
                raise StageFailedError("run", f"Failed to run {core.name} : {e}") from e

        return RunResult(
            core=core,
            backend=backend,
            edam_file=edam_file,
            work_root=backend.work_root,
        )
