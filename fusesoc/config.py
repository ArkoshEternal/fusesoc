# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import configparser
import logging
import os
from configparser import ConfigParser as CP
from pathlib import Path

from fusesoc.exceptions import ConfigError, LibraryError, LibraryExistsError
from fusesoc.librarymanager import Library

logger = logging.getLogger(__name__)


def _xdg_home(env_var, *fallback):
    """Return the XDG base directory from *env_var*, or the home-relative
    fallback when the variable is unset or empty."""
    return os.environ.get(env_var) or os.path.join(os.path.expanduser("~"), *fallback)


class Config:
    default_section = "main"

    # Options that may be overridden programmatically (or from CLI arguments)
    # without touching the configuration file.
    _OVERRIDABLE = frozenset(
        {
            "allow_additional_properties",
            "build_root",
            "cores_root",
            "filters",
            "no_export",
            "resolve_env_vars_early",
            "system_name",
            "work_root",
        }
    )

    def __init__(self, path=None, create_if_missing=False, overrides=None):
        """Read configuration from *path*, or from the default search
        locations (/etc, XDG config dir, working directory) when no path is
        given.

        *overrides* is a mapping of option name to value; an override wins
        over the configuration file for that option. See
        :attr:`_OVERRIDABLE` for the recognized names.
        """
        self._overrides = dict(overrides or {})
        for name in self._overrides:
            if name not in self._OVERRIDABLE:
                raise ConfigError(f"Unknown config override '{name}'")

        self._cp = CP(default_section=Config.default_section)

        if path is None:
            config_files = [
                "/etc/fusesoc/fusesoc.conf",
                str(
                    Path(_xdg_home("XDG_CONFIG_HOME", ".config"))
                    / "fusesoc"
                    / "fusesoc.conf"
                ),
                "fusesoc.conf",
            ]
        else:
            logger.debug(f"Using config file '{path}'")
            if not os.path.isfile(path):
                if create_if_missing:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    with open(path, "a"):
                        pass
                else:
                    logger.warning(f"Config file '{path}' was not found")
            config_files = [path]

        logger.debug("Looking for config files from " + ":".join(config_files))
        files_read = self._cp.read(config_files)
        logger.debug("Found config files in " + ":".join(files_read))
        self._path = files_read[-1] if files_read else None

        # Get the environment variable for further cores
        env_cores_root = []
        if os.getenv("FUSESOC_CORES"):
            env_cores_root = os.getenv("FUSESOC_CORES").split(":")
            env_cores_root.reverse()

        self.libraries = [
            Library(root, root) for root in env_cores_root
        ] + self._parse_library()

        logger.debug("cache_root=" + self._get_cache_root())
        logger.debug("library_root=" + self.library_root)
        logger.debug("ssh-trustfile=" + (self.ssh_trustfile or "none"))

    @staticmethod
    def resolve_path(cli_path=None):
        """Return the effective config file path.

        An explicitly given path wins over the ``FUSESOC_CONFIG`` environment
        variable; ``None`` means the default search locations are used.
        """
        return cli_path or os.environ.get("FUSESOC_CONFIG") or None

    @classmethod
    def global_config_path(cls):
        """Path of the user-global configuration file."""
        return str(
            Path(_xdg_home("XDG_CONFIG_HOME", ".config")) / "fusesoc" / "fusesoc.conf"
        )

    @classmethod
    def from_dict(cls, values):
        """Create a Config programmatically, without reading any
        configuration file or environment variable.

        *values* maps option names to values; every settable config option
        (``build_root``, ``cache_root``, ``library_root``, ...) is accepted,
        plus ``libraries`` for a list of :class:`Library` objects.
        """
        config = cls.__new__(cls)
        config._overrides = {}
        config._cp = CP(default_section=Config.default_section)
        config._path = None
        config.libraries = []
        for key, value in values.items():
            if key == "libraries":
                config.libraries = list(value)
                continue
            prop = getattr(type(config), key, None)
            if not isinstance(prop, property) or prop.fset is None:
                raise ConfigError(f"Unknown config option '{key}'")
            setattr(config, key, value)
        return config

    def _parse_library(self):
        # Parse library sections
        libraries = []
        library_sections = [x for x in self._cp.sections() if x.startswith("library")]
        for section in library_sections:
            name = section.partition(".")[2]
            try:
                location = self._resolve_path_from_cfg(
                    self._cp.get(section, "location")
                )
            except configparser.NoOptionError:
                location = os.path.join(self.library_root, name)

            try:
                auto_sync = self._cp.getboolean(section, "auto-sync")
            except configparser.NoOptionError:
                auto_sync = True
            except ValueError as e:
                _s = "Error parsing auto-sync '{}'. Ignoring library '{}'"
                logger.warning(_s.format(str(e), name))
                continue

            sync_uri = self._cp.get(section, "sync-uri", fallback=None)
            sync_version = self._cp.get(section, "sync-version", fallback=None)
            sync_type = self._cp.get(section, "sync-type", fallback=None)

            try:
                sync_submodules = self._cp.getboolean(section, "sync-submodules")
            except configparser.NoOptionError:
                sync_submodules = False
            except ValueError as e:
                _s = "Error parsing sync-submodules '{}'. Ignoring library '{}'"
                logger.warning(_s.format(str(e), name))
                continue

            libraries.append(
                Library(
                    name,
                    location,
                    sync_type,
                    sync_uri,
                    sync_version,
                    auto_sync,
                    sync_submodules,
                )
            )

        return libraries

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.write()

    def _resolve_path_from_cfg(self, path):
        expanded = os.path.expanduser(path)
        if os.path.isabs(expanded):
            return expanded
        if self._path is None:
            # Value set programmatically (from_dict); no config file to be
            # relative to, so resolve against the working directory.
            return os.path.abspath(expanded)
        cfg_file_dir = os.path.dirname(os.path.realpath(self._path))
        return os.path.normpath(os.path.join(cfg_file_dir, expanded))

    def _path_from_cfg(self, name):
        as_str = self._cp.get(Config.default_section, name, fallback=None)
        return self._resolve_path_from_cfg(as_str) if as_str is not None else None

    def _paths_from_cfg(self, name):
        paths = self._cp.get(Config.default_section, name, fallback="")
        return [self._resolve_path_from_cfg(p) for p in paths.split()]

    def _get_build_root(self):
        from_cfg = self._path_from_cfg("build_root")
        if from_cfg is not None:
            return from_cfg

        return os.path.abspath("build")

    def _get_cache_root(self):
        from_cfg = self._path_from_cfg("cache_root")
        if from_cfg is not None:
            return from_cfg

        return str(Path(_xdg_home("XDG_CACHE_HOME", ".cache")) / "fusesoc")

    def _get_library_root(self):
        from_cfg = self._path_from_cfg("library_root")
        if from_cfg is not None:
            return from_cfg

        return str(Path(_xdg_home("XDG_DATA_HOME", ".local/share")) / "fusesoc")

    def _set_default_section(self, name, val):
        self._cp.set(Config.default_section, name, str(val))

    def _override_or(self, name, fallback):
        if name in self._overrides:
            return self._overrides[name]
        return fallback

    @property
    def filters(self):
        # Additive: filters from the config file, then override filters
        return self._cp.get(
            Config.default_section, "filters", fallback=""
        ).split() + list(self._overrides.get("filters", []))

    @filters.setter
    def filters(self, val):
        self._set_default_section(
            "filters", " ".join(val) if isinstance(val, list) else val
        )

    @property
    def build_root(self):
        return self._override_or("build_root", self._get_build_root())

    @build_root.setter
    def build_root(self, val):
        self._set_default_section("build_root", val)

    @property
    def work_root(self):
        return self._override_or("work_root", self._path_from_cfg("work_root"))

    @work_root.setter
    def work_root(self, val):
        self._set_default_section("work_root", val)

    @property
    def cache_root(self):
        # Created on first use rather than at construction time.
        cache_root = self._get_cache_root()
        os.makedirs(cache_root, exist_ok=True)
        return cache_root

    @cache_root.setter
    def cache_root(self, val):
        self._set_default_section("cache_root", val)

    @property
    def ssh_trustfile(self):
        return self._path_from_cfg("ssh-trustfile")

    @ssh_trustfile.setter
    def ssh_trustfile(self, val):
        self._set_default_section("ssh-trustfile", val)

    @property
    def library_root(self):
        return self._get_library_root()

    @library_root.setter
    def library_root(self, val):
        self._set_default_section("library_root", val)

    @property
    def cores_root(self):
        return self._override_or("cores_root", self._paths_from_cfg("cores_root"))

    @cores_root.setter
    def cores_root(self, val):
        self._set_default_section(
            "cores_root", " ".join(val) if isinstance(val, list) else val
        )

    @property
    def ignored_dirs(self):
        return self._paths_from_cfg("ignored_dirs")

    @ignored_dirs.setter
    def ignored_dirs(self, val):
        self._set_default_section(
            "ignored_dirs", " ".join(val) if isinstance(val, list) else val
        )

    @property
    def resolve_env_vars_early(self):
        return self._override_or(
            "resolve_env_vars_early",
            self._cp.getboolean(
                Config.default_section, "resolve_env_vars_early", fallback=False
            ),
        )

    @resolve_env_vars_early.setter
    def resolve_env_vars_early(self, val):
        self._set_default_section("resolve_env_vars_early", val)

    @property
    def allow_additional_properties(self):
        return self._override_or(
            "allow_additional_properties",
            self._cp.getboolean(
                Config.default_section, "allow_additional_properties", fallback=False
            ),
        )

    @allow_additional_properties.setter
    def allow_additional_properties(self, val):
        self._set_default_section("allow_additional_properties", val)

    @property
    def no_export(self):
        return self._override_or(
            "no_export",
            self._cp.getboolean(Config.default_section, "no_export", fallback=False),
        )

    @no_export.setter
    def no_export(self, val):
        self._set_default_section("no_export", val)

    @property
    def system_name(self):
        return self._override_or(
            "system_name",
            self._cp.get(Config.default_section, "system_name", fallback=None),
        )

    @system_name.setter
    def system_name(self, val):
        self._set_default_section("system_name", val)

    def write(self):
        conf_file_name = getattr(self, "_path", None) or "fusesoc.conf"

        with open(conf_file_name, "w") as conf_file:
            self._cp.write(conf_file)

    def record_library(self, library):
        """Record *library* in the configuration file.

        Unlike :meth:`add_library` this has no side effects on the library
        location itself. Raises :class:`LibraryExistsError` if a library of
        the same name is already recorded.
        """
        section_name = "library." + library.name

        if section_name in self._cp.sections():
            raise LibraryExistsError(
                f"Not adding library. {library.name} already exists "
                "in configuration file"
            )

        self._cp.add_section(section_name)

        self._cp.set(section_name, "location", library.location)

        if library.sync_type:
            self._cp.set(section_name, "sync-uri", library.sync_uri)

            if library.sync_version is not None:
                self._cp.set(section_name, "sync-version", library.sync_version)

            self._cp.set(section_name, "sync-type", library.sync_type)
            _auto_sync = "true" if library.auto_sync else "false"
            self._cp.set(section_name, "auto-sync", _auto_sync)
            if library.sync_submodules:
                self._cp.set(section_name, "sync-submodules", "true")

        self.write()

    def add_library(self, library):
        """Initialize *library* on disk via its provider and record it in the
        configuration file."""
        from fusesoc.provider.provider import get_provider

        if "library." + library.name in self._cp.sections():
            raise LibraryExistsError(
                f"Not adding library. {library.name} already exists "
                "in configuration file"
            )

        try:
            provider = get_provider(library.sync_type)
        except ImportError:
            raise LibraryError(f"Invalid sync-type '{library.sync_type}'")

        # Initialize first: if this fails, the configuration file is left
        # untouched.
        provider.init_library(library)

        self.record_library(library)
