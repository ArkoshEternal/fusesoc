# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os
import shutil
from importlib import import_module
from pathlib import Path

from fusesoc.capi2.flags import Flags
from fusesoc.coremanager import CoreManager, DependencyError
from fusesoc.edalizer import Edalizer
from fusesoc.exceptions import (
    AmbiguousCoreError,
    BackendError,
    CoreNotFoundError,
    FusesocError,
    ToolOrFlowError,
)
from fusesoc.librarymanager import Library, LibraryManager
from fusesoc.utils import setup_logging, yaml_fread, yaml_fwrite
from fusesoc.vlnv import Vlnv

try:
    from edalize.edatool import ToolResolutionError, get_edatool
except ImportError:
    from edalize import get_edatool

logger = logging.getLogger(__name__)

_TOOL_ERROR = (
    "No flow or tool was supplied on command line or found in '{}' core description"
)


def resolve_stages(setup, build, run):
    """Apply the stage-selection policy.

    Returns ``(do_configure, do_build, do_run)``. Running setup is implied
    by build; when no stage is requested, all stages run. Requesting setup
    and run without build is invalid.
    """
    setup |= build
    if not (setup or build or run):
        return (True, True, True)
    if (setup, build, run) == (True, False, True):
        raise FusesocError("Configure and run without build is invalid")
    return (setup, build, run)


def prepare_work_root(work_root):
    """Create *work_root* if needed and clean out anything inside it."""
    if os.path.exists(work_root):
        for f in os.listdir(work_root):
            if os.path.isdir(os.path.join(work_root, f)):
                shutil.rmtree(os.path.join(work_root, f))
            else:
                os.remove(os.path.join(work_root, f))
    else:
        os.makedirs(work_root)


class Fusesoc:
    def __init__(self, config, verbose=False, strict=False):
        """*strict* makes library-registration failures raise instead of
        being downgraded to warnings."""
        self.config = config
        self.verbose = verbose
        self._strict = strict

        self.lm = LibraryManager()
        self.cm = CoreManager(self.config, library_manager=self.lm)

        self._register_libraries()

    def _register_libraries(self):
        cores_root_libs = [Library(acr, acr) for acr in self.config.cores_root]
        # Add libraries from config file, env var and command-line
        for library in self.config.libraries + cores_root_libs:
            try:
                self.add_library(library)
            except (RuntimeError, OSError):
                try:
                    temporary_lm = LibraryManager()
                    # try to initialize library
                    temporary_lm.add_library(library)
                    temporary_lm.update([library.name])
                    # the initialization worked, now register it properly
                    self.add_library(library)
                except (RuntimeError, OSError) as e:
                    if self._strict:
                        raise
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

    def add_library(self, library):
        self.cm.add_library(library, self.config.ignored_dirs)

    def get_library(self, library_name):
        return self.lm.get_library(library_name)

    def update_libraries(self, library_names):
        self.lm.update(library_names)

    def get_libraries(self):
        return self.lm.get_libraries()

    def get_core(self, name):
        return self.cm.get_core(Vlnv(name))

    def resolve_core(self, core_name):
        """Resolve a core name, which may be a short name (just the name part
        of a VLNV), to a core object.

        Raises :class:`AmbiguousCoreError` when a short name matches several
        cores and :class:`CoreNotFoundError` (carrying ``parse_errors``) when
        the core or one of its dependencies is missing.
        """
        matches = set()
        if ":" not in core_name:
            for core in self.get_cores():
                (vendor, library, name, _) = core.split(":")
                if name.lower() == core_name.lower():
                    matches.add(f"{vendor}:{library}:{name}")
            if len(matches) == 1:
                core_name = matches.pop()
            elif len(matches) > 1:
                raise AmbiguousCoreError(core_name, matches)

        try:
            return self.get_core(core_name)
        except DependencyError as e:
            msg = (
                f"{core_name!r} or any of its dependencies requires {e.value!r}, "
                "but this core was not found"
            )
            raise CoreNotFoundError(msg, parse_errors=self.parse_errors) from e

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

    @staticmethod
    def get_tools():
        """Return a mapping of available edalize tool names to their
        descriptions. Misbehaving backends are skipped."""
        from edalize.edatool import get_edatool, walk_tool_packages

        tools = {}
        for tool_name in walk_tool_packages():
            try:
                tools[tool_name] = get_edatool(tool_name).get_doc(0)["description"]
            # Ignore any misbehaving backends
            except Exception:
                pass
        return tools

    def load_lockfile(self, filepath, disable_store=False):
        """Load a lock file, pinning core versions for subsequent solves.

        Raises :class:`LockfileError` if the file cannot be parsed.
        """
        self.cm.db.load_lockfile(filepath, disable_store)

    def set_mappings(self, mapping_vlnvs):
        """Apply the mappings declared by the given cores (VLNV strings)."""
        self.cm.db.mapping_set(mapping_vlnvs)

    def get_work_root(self, core, flags):
        flags = Flags.from_mapping(flags)
        flow = core.get_flow(flags)

        target = flags["target"]

        build_root = os.path.join(self.config.build_root, core.name.sanitized_name)

        if flow:
            logger.debug(f"Using flow API (flow={flow})")
            work_root = self.config.work_root or os.path.join(build_root, target)
        else:
            logger.debug("flow not set. Falling back to tool API")
            if not flags.tool:
                raise ToolOrFlowError(_TOOL_ERROR.format(core.name.sanitized_name))

            work_root = self.config.work_root or os.path.join(
                build_root, f"{target}-{flags.tool}"
            )

        return work_root

    def resolve_backend_class(self, core, flags):
        """Resolve the edalize flow or tool class for *core* under *flags*.

        Raises :class:`ToolOrFlowError` when no flow or tool is set or the
        requested one does not exist.
        """
        flags = Flags.from_mapping(flags)
        flow = core.get_flow(flags)

        if flow:
            try:
                return getattr(
                    import_module(f"edalize.flows.{flow}"), flow.capitalize()
                )
            except ModuleNotFoundError:
                raise ToolOrFlowError(f"Flow {flow!r} not found")
            except ImportError:
                raise ToolOrFlowError(
                    "Selected Edalize version does not support the flow API"
                )

        if not flags.tool:
            raise ToolOrFlowError(_TOOL_ERROR.format(core.name.sanitized_name))
        try:
            return get_edatool(flags.tool)
        except ToolResolutionError:
            raise ToolOrFlowError(f"Backend {flags.tool!r} not found")

    def build_edam(
        self,
        core,
        flags,
        backend_class=None,
        backendargs=None,
        backend_params=None,
        work_root=None,
    ):
        """Resolve dependencies and produce the EDAM structure for *core*.

        Returns ``(edam, work_root)`` without writing the EDAM to disk.

        *backend_params* is a mapping of backend argument values, the
        programmatic equivalent of the CLI-shaped *backendargs* list (which
        is parsed with argparse and reports errors CLI-style).
        """
        flags = Flags.from_mapping(flags).with_core_defaults(core)

        if work_root is None:
            work_root = self.get_work_root(core, flags)

        if not self.config.no_export:
            export_root = os.path.join(work_root, "src")
            logger.debug(f"Setting export_root to {export_root}")
        else:
            export_root = None

        if (backendargs or backend_params) and backend_class is None:
            backend_class = self.resolve_backend_class(core, flags)

        edalizer = Edalizer(
            toplevel=core.name,
            flags=flags,
            core_manager=self.cm,
            work_root=work_root,
            export_root=export_root,
            system_name=self.config.system_name,
            resolve_env_vars=self.config.resolve_env_vars_early,
        )

        edalizer.run()
        edalizer.export()
        Path(work_root).mkdir(parents=True, exist_ok=True)
        if backendargs:
            edalizer.parse_args(backend_class, backendargs)
        elif backend_params:
            edalizer.add_parsed_args(backend_class, dict(backend_params))
        edalizer.apply_filters(self.config.filters)

        return edalizer.edam, work_root

    def write_edam(self, edam, edam_file):
        """Write *edam* to *edam_file*, unless the file already holds
        identical content (preserves the file mtime for build systems)."""
        if os.path.exists(edam_file):
            old_edam = yaml_fread(edam_file, self.config.resolve_env_vars_early)
        else:
            old_edam = None

        if edam != old_edam:
            yaml_fwrite(edam_file, edam)

    def get_backend(self, core, flags, backendargs=[]):
        # Merge core/target-declared default flags (including default_tool)
        # under the caller's flags, as the CLI has always done.
        flags = Flags.from_mapping(flags).with_core_defaults(core)

        work_root = self.get_work_root(core, flags)
        backend_class = self.resolve_backend_class(core, flags)

        try:
            edam, _ = self.build_edam(
                core,
                flags,
                backend_class=backend_class,
                backendargs=backendargs,
                work_root=work_root,
            )
        except SyntaxError as e:
            raise RuntimeError(e.msg)
        except DependencyError as e:
            raise RuntimeError("Failed to resolve dependencies. " + e.msg)
        except RuntimeError as e:
            raise RuntimeError(f"Setup failed : {str(e)}")

        edam_file = os.path.join(work_root, core.name.sanitized_name + ".eda.yml")
        self.write_edam(edam, edam_file)

        return edam_file, backend_class(
            edam=edam, work_root=work_root, verbose=self.verbose
        )

    def run(
        self,
        core,
        flags,
        setup=False,
        build=False,
        run=False,
        clean=False,
        backendargs=[],
    ):
        """Run the setup/build/run stages for *core* (all of them by
        default).

        Stage failures raise :class:`BackendError` with the failed stage
        name; the setup work (dependency resolution, EDAM generation, backend
        argument parsing) reports errors like :meth:`get_backend`.
        """
        do_configure, do_build, do_run = resolve_stages(setup, build, run)

        flags = Flags.from_mapping(flags).with_core_defaults(core)

        # Unconditionally clean out the work root on fresh builds
        # if we use the old tool API or clean flag is set
        if do_configure and (not core.get_flow(flags) or clean):
            prepare_work_root(self.get_work_root(core, flags))

        edam_file, backend = self.get_backend(core, flags, backendargs)

        # Skip configuration when the Makefile is newer than the EDAM file
        makefile = os.path.join(backend.work_root, "Makefile")
        do_configure = not os.path.exists(makefile) or (
            os.path.getmtime(makefile) < os.path.getmtime(edam_file)
        )

        stages = (
            ("configure", do_configure, backend.configure),
            ("build", do_build, backend.build),
            ("run", do_run, backend.run),
        )
        for stage, enabled, action in stages:
            if enabled:
                try:
                    action()
                except RuntimeError as e:
                    raise BackendError(str(e), stage=stage) from e
