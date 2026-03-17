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
        name: str,
        location: str,
        sync_type: str | None = None,
        sync_uri: str | None = None,
        sync_version: str | None = None,
        auto_sync: bool = True,
    ) -> None:
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

    def update(self, force: bool = False) -> None:
        def lib(s: str) -> str:
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
    def __init__(self, library_root: str) -> None:
        self._libraries: list[Library] = []
        self.library_root: str = library_root

    def add_library(self, library: Library) -> None:
        self._libraries.append(library)

    def get_library(self, value: str, key: str = "name") -> Library | None:
        for library in self._libraries:
            if getattr(library, key) == value:
                return library
        raise ValueError(f"Could not find library with {key} '{value}'")

    def get_libraries(self) -> list[Library]:
        return self._libraries

    def update(self, library_names: list[str]) -> None:
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
