# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os.path

from fusesoc.exceptions import LibraryError
from fusesoc.library import Library
from fusesoc.provider.provider import Provider

logger = logging.getLogger(__name__)


class Local(Provider):
    @staticmethod
    def init_library(library: Library) -> None:
        if not os.path.isdir(library.location):
            raise LibraryError(
                f"Local library at location '{library.location}' not found."
            )

    def _checkout(self, local_dir):
        pass

    @staticmethod
    def update_library(library: Library) -> None:
        pass
