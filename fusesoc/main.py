#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Deprecated location of the FuseSoC command-line entry point.

The CLI lives in :mod:`fusesoc.cli`; this module is kept so that
``python -m fusesoc.main`` and existing imports keep working.
"""

from fusesoc.cli import fusesoc, main  # noqa: F401
from fusesoc.cli.parser import parse_args  # noqa: F401

if __name__ == "__main__":
    main()
