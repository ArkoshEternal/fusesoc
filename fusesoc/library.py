# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause


class Library:
    """FuseSoC library."""

    def __init__(
        self,
        name: str,
        location: str,
        sync_type: str | None = None,
        sync_uri: str | None = None,
        sync_version: str | None = None,
        auto_sync: bool = True,
        sync_submodules: bool = False,
    ) -> None:
        """Create a new instance of FuseSoC library.

        Args:
            name: Name of library.
            location: Path to library directory.
            sync_type: Type of library synchronization.
            sync_uri: URI to remote library.
            sync_version: Version of library to synchronize during library updates.
            auto_sync: If set to :data:`True` then it will automatically synchronize library.
            sync_submodules: If set to :data:`True` then it will also clone/fetch git submodules.
        """
        self.name = name
        self.location = location
        self.sync_type = sync_type or "local"
        self.sync_uri = sync_uri
        self.sync_version = sync_version
        self.auto_sync = auto_sync
        self.sync_submodules = sync_submodules

    @classmethod
    def from_uri(
        cls,
        sync_uri: str,
        name: str | None = None,
        location: str | None = None,
        sync_type: str | None = None,
        sync_version: str | None = None,
        auto_sync: bool = True,
        sync_submodules: bool = False,
        default_root: str = "fusesoc_libraries",
    ) -> "Library":
        """Create a library description from a sync URI, applying the same
        defaulting the CLI uses: the name defaults to the last URI component,
        the sync type is autodetected (an existing directory means 'local',
        anything else 'git'), and a local library's location is the URI
        itself while remote libraries default to *default_root*/*name*.
        """
        import logging
        import os

        name = name or os.path.basename(sync_uri.rstrip("/"))
        location = location or os.path.join(default_root, name)

        if not sync_type:
            sync_type = "local" if os.path.isdir(sync_uri) else "git"

        if sync_type == "local":
            logging.getLogger(__name__).info(
                f"Interpreting sync-uri '{sync_uri}' as location for local provider."
            )
            location = os.path.abspath(sync_uri)

        return cls(
            name,
            location,
            sync_type,
            sync_uri,
            sync_version,
            auto_sync,
            sync_submodules,
        )
