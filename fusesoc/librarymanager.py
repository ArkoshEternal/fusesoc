# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os

from fusesoc.provider.provider import get_provider

logger = logging.getLogger(__name__)


class Library:
    def __init__(
        self,
        name,
        location,
        sync_type=None,
        sync_uri=None,
        sync_version=None,
        auto_sync=True,
    ):
        if sync_type and sync_type not in ["local", "git", "url"]:
            raise ValueError(
                "Library {} ({}) Invalid sync-type '{}'".format(
                    name, location, sync_type
                )
            )

        if sync_type in ["git", "url"]:
            if not sync_uri:
                raise ValueError(
                    f"Library name ({location}) {sync_uri} must be set when using sync_type '{sync_type}'"
                )

        self.name = name
        self.location = location
        self.sync_type = sync_type or "local"
        self.sync_uri = sync_uri
        self.sync_version = sync_version
        self.auto_sync = auto_sync

    @classmethod
    def from_sync_uri(
        cls,
        sync_uri,
        name=None,
        location=None,
        sync_type=None,
        sync_version=None,
        auto_sync=True,
        library_root="fusesoc_libraries",
    ):
        """Create a Library from a sync URI, inferring missing properties.

        ``name`` defaults to the last path component of ``sync_uri``.
        ``sync_type`` defaults to 'local' if ``sync_uri`` is an existing
        directory, and 'git' otherwise. ``location`` defaults to
        ``<library_root>/<name>``; for local libraries the (absolutized)
        ``sync_uri`` itself is used as the location.
        """
        name = name or os.path.basename(sync_uri.rstrip("/"))

        if not location:
            location = os.path.join(library_root, name)

        if not sync_type:
            sync_type = "local" if os.path.isdir(sync_uri) else "git"

        if sync_type == "local":
            logger.info(
                "Interpreting sync-uri '{}' as location for local provider.".format(
                    sync_uri
                )
            )
            location = os.path.abspath(sync_uri)

        return cls(name, location, sync_type, sync_uri, sync_version, auto_sync)

    def update(self, force=False):
        def lib(s):
            return self.name + " : " + s

        if self.sync_type == "local":
            logger.info(lib("sync-type is local. Ignoring update"))
            return

        if not (self.auto_sync or force):
            logger.info(lib("auto-sync disabled. Ignoring update"))
            return

        provider = get_provider(self.sync_type)

        if not os.path.exists(self.location):
            logger.info(lib(f"{self.location} does not exist. Trying a checkout"))
            try:
                provider.init_library(self)
            except RuntimeError:
                # Keep old behavior of logging a warning if there is a library
                # in `fusesoc.conf`, but the directory does not exist for some
                # reason and it could not be initialized.
                logger.warning(lib(f"{self.location} does not exist. Ignoring update"))
            return

        try:
            logger.info(lib("Updating..."))
            provider.update_library(self)
        except RuntimeError as e:
            logger.error(lib("Failed to update library: " + str(e)))


class LibraryManager:
    def __init__(self, library_root):
        self._libraries = []
        self.library_root = library_root

    def add_library(self, library):
        self._libraries.append(library)

    def get_library(self, value, key="name"):
        for library in self._libraries:
            if getattr(library, key) == value:
                return library

    def get_libraries(self):
        return self._libraries

    def update(self, library_names):
        libraries = []
        for name in library_names:
            library = self.get_library(name)
            if library:
                libraries.append(library)
            else:
                logger.warning(f"Could not find library {name}")

        if library_names:
            force = True
        else:
            libraries = self._libraries
            force = False

        for library in libraries:
            library.update(force)
