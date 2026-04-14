# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os
import shutil
from importlib import import_module
from pathlib import Path

from fusesoc.coremanager import CoreManager, DependencyError
from fusesoc.edalizer import Edalizer
from fusesoc.librarymanager import Library, LibraryManager
from fusesoc.utils import setup_logging, yaml_fread
from fusesoc.vlnv import Vlnv

try:
    from edalize.edatool import get_edatool
except ImportError:
    from edalize import get_edatool

logger = logging.getLogger(__name__)


class Fusesoc:
    # =====================================================================
    # Construction / setup
    # =====================================================================

    def __init__(self, config):
        self.config = config

        self.lm = LibraryManager(config.library_root)
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

    # =====================================================================
    # Library Management
    # =====================================================================

    def add_library(self, library):
        self.cm.add_library(library, self.config.ignored_dirs)

    def get_library(self, library_name):
        return self.lm.get_library(library_name)

    def update_libraries(self, library_names):
        self.lm.update(library_names)

    def get_libraries(self):
        return self.lm.get_libraries()

    # =====================================================================
    # Generator and Core Lookup
    # =====================================================================

    def get_core(self, name):
        return self.cm.get_core(Vlnv(name))

    def get_cores(self):
        return self.cm.get_cores()

    def find_cores(self, library):
        return self.cm.find_cores(library, self.config.ignored_dirs)

    def get_generators(self):
        return self.cm.get_generators()

    def resolve_core(self, name):
        """Resolve a user-supplied core name into a Core object.

        A bare short name (no ':') is matched case-insensitively against the
        name field of every known core. Exactly one match is used; several
        matches raise RuntimeError. Unlike the old CLI helper this never calls
        exit() -- callers convert the raised error into an exit code.
        """
        if ":" not in name:
            matches = set()
            for core in self.get_cores():
                (vendor, library, core_name, _) = core.split(":")
                if core_name.lower() == name.lower():
                    matches.add(f"{vendor}:{library}:{core_name}")
            if len(matches) == 1:
                name = matches.pop()
            elif len(matches) > 1:
                _s = f"'{name}' is ambiguous. Potential matches: "
                _s += ", ".join(f"'{x}'" for x in matches)
                raise RuntimeError(_s)

        try:
            return self.get_core(name)
        except DependencyError as e:
            raise RuntimeError(
                f"{name!r} or any of its dependencies requires {e.value!r}, but "
                "this core was not found"
            )

    # =====================================================================
    # Mapping / Lockfiles
    # =====================================================================

    def set_mapping(self, mapping_vlnvs):
        """Wrap cm.db.mapping_set(). Raises RuntimeError on a bad mapping."""
        self.cm.db.mapping_set(mapping_vlnvs or [])

    def load_lockfile(self, filepath):
        """Wrap cm.db.load_lockfile(). No-op when filepath is None."""
        if filepath is None:
            return
        try:
            self.cm.db.load_lockfile(filepath)
        except SyntaxError as e:
            raise RuntimeError(f"Failed to load lock file, {str(e)}")

    # =====================================================================
    # Flags / Work Root
    # =====================================================================

    def build_flags(self, core, target="default", tool=None, extra_flags=None):
        """Assemble the flag dict that the resolver/edalizer consume.

        Order matters: start from {target, tool, *extra_flags}, then overlay
        the core's own defaults so the explicit flags win.
        """
        flags = {"target": target}
        if tool:
            flags["tool"] = tool
        if extra_flags:
            flags.update(extra_flags)

        try:
            flags = dict(core.get_flags(flags["target"]), **flags)
        except (SyntaxError, RuntimeError) as e:
            raise RuntimeError(str(e))
        return flags

    def get_work_root(self, core, flags):
        flow = core.get_flow(flags)

        target = flags["target"]

        build_root = os.path.join(self.config.build_root, core.name.sanitized_name)

        if flow:
            logger.debug(f"Using flow API (flow={flow})")
            work_root = self.config.work_root or os.path.join(build_root, target)
        else:
            logger.debug("flow not set. Falling back to tool API")
            if "tool" in flags:
                tool = flags["tool"]
            else:
                tool_error = "No flow or tool was supplied on command line or found in '{}' core description"
                raise RuntimeError(tool_error.format(core.name.sanitized_name))

            work_root = self.config.work_root or os.path.join(
                build_root, f"{target}-{tool}"
            )

        return work_root

    @staticmethod
    def prepare_work_root(work_root):
        """Clean out (or create) the work root before a fresh configure."""
        if os.path.exists(work_root):
            for f in os.listdir(work_root):
                if os.path.isdir(os.path.join(work_root, f)):
                    shutil.rmtree(os.path.join(work_root, f))
                else:
                    os.remove(os.path.join(work_root, f))
        else:
            os.makedirs(work_root)

    # =====================================================================
    # Backend
    # =====================================================================

    def get_backend(self, core, flags, backendargs=[]):

        work_root = self.get_work_root(core, flags)

        if not self.config.no_export:
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
            try:
                backend_class = get_edatool(flags["tool"])
            except ImportError:
                raise RuntimeError(f"Backend {flags['tool']!r} not found")

        edalizer = Edalizer(
            toplevel=core.name,
            flags=flags,
            core_manager=self.cm,
            work_root=work_root,
            export_root=export_root,
            system_name=self.config.system_name,
            resolve_env_vars=self.config.resolve_env_vars_early,
        )

        try:
            edalizer.run()
            edalizer.export()
            Path(work_root).mkdir(parents=True, exist_ok=True)
            edalizer.parse_args(backend_class, backendargs)
            edalizer.apply_filters(self.config.filters)
        except SyntaxError as e:
            raise RuntimeError(e.msg)
        except RuntimeError as e:
            raise RuntimeError("Setup failed : {}".format(str(e)))
        except DependencyError as e:
            raise RuntimeError("Failed to resolve dependencies. " + e.msg)

        if os.path.exists(edam_file):
            old_edam = yaml_fread(edam_file, self.config.resolve_env_vars_early)
        else:
            old_edam = None

        if edalizer.edam != old_edam:
            edalizer.to_yaml(edam_file)

        return edam_file, backend_class(
            edam=edalizer.edam, work_root=work_root, verbose=self.config.verbose
        )

    # =====================================================================
    # High-level lifecycle entry points
    # =====================================================================

    def fetch(self, core_name):
        """resolve_core(corename) + core.setup()"""
        # TODO
        ...

    def run(
        self,
        core_name,
        *,
        target="default",
        tool=None,
        flags=None,
        mapping=None,
        lockfile=None,
        backendargs=None,
        do_configure=True,
        do_build=True,
        do_run=True,
        clean=False,
    ):
        """Full setup/build/run lifecycle.

        Takes explicit do_* booleans (the 'default to all stages' policy stays
        in the CLI). Raises RuntimeError on any failure; the caller logs it and
        decides on an exit code. Returns the configured backend so library
        callers can reach its artefacts.
        """
        self.set_mapping(mapping)
        self.load_lockfile(lockfile)

        core = self.resolve_core(core_name)
        flags = self.build_flags(core, target=target, tool=tool, extra_flags=flags)

        # Unconditionally clean out the work root on fresh builds if we use the
        # old tool API or the clean flag is set.
        if do_configure and (not core.get_flow(flags) or clean):
            self.prepare_work_root(self.get_work_root(core, flags))

        try:
            edam_file, backend = self.get_backend(core, flags, backendargs or [])
        except FileNotFoundError as e:
            raise RuntimeError(f'Could not find EDA API file "{e.filename}"')

        # Re-configure only when the Makefile is missing or older than the EDAM.
        makefile = os.path.join(backend.work_root, "Makefile")
        do_configure = not os.path.exists(makefile) or (
            os.path.getmtime(makefile) < os.path.getmtime(edam_file)
        )

        if do_configure:
            try:
                backend.configure()
            except RuntimeError as e:
                raise RuntimeError(f"Failed to configure the system\n{str(e)}")

        if do_build:
            try:
                backend.build()
            except RuntimeError as e:
                raise RuntimeError(f"Failed to build {core.name} : {str(e)}")

        if do_run:
            try:
                backend.run()
            except RuntimeError as e:
                raise RuntimeError(f"Failed to run {core.name} : {str(e)}")

        return backend

    def clean_generator_cache(self):
        """clean out generator cache"""
        # TODO:
        ...
