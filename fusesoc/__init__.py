# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""FuseSoC - package manager and build abstraction tool for HDL code.

The names exported from this module form the supported Python API. Anything
imported from submodules directly is considered internal and may change
without notice.
"""

import importlib
from typing import TYPE_CHECKING

from fusesoc.exceptions import (
    AmbiguousCoreError,
    BackendError,
    ConfigError,
    CoreNotFoundError,
    CoreParseError,
    DependencyError,
    FlagError,
    FusesocError,
    LibraryError,
    LibraryExistsError,
    LockfileError,
    ToolOrFlowError,
    VlnvError,
)

if TYPE_CHECKING:
    from fusesoc.capi2.flags import Flags
    from fusesoc.config import Config
    from fusesoc.edalizer import Edalizer
    from fusesoc.fusesoc import Fusesoc
    from fusesoc.library import Library
    from fusesoc.vlnv import Vlnv

try:
    from fusesoc.version import version as __version__
except ImportError:
    # Source checkout where setuptools_scm has not generated version.py.
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _dist_version

    try:
        __version__ = _dist_version("fusesoc")
    except PackageNotFoundError:
        __version__ = "unknown"

# The names below are imported lazily (PEP 562) so that lightweight consumers
# (e.g. generator scripts importing fusesoc.capi2.generator in a subprocess)
# don't pay for the full dependency tree on package import.
_LAZY_EXPORTS = {
    "Config": "fusesoc.config",
    "Edalizer": "fusesoc.edalizer",
    "Flags": "fusesoc.capi2.flags",
    "Fusesoc": "fusesoc.fusesoc",
    "Library": "fusesoc.library",
    "Vlnv": "fusesoc.vlnv",
}

__all__ = [
    "AmbiguousCoreError",
    "BackendError",
    "Config",
    "ConfigError",
    "CoreNotFoundError",
    "CoreParseError",
    "DependencyError",
    "Edalizer",
    "FlagError",
    "Flags",
    "Fusesoc",
    "FusesocError",
    "Library",
    "LibraryError",
    "LibraryExistsError",
    "LockfileError",
    "ToolOrFlowError",
    "Vlnv",
    "VlnvError",
]


def __getattr__(name):
    module = _LAZY_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
