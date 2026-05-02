# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

from fusesoc.capi2.core import Core as Capi2Core

# Re-export Capi2Core under the public name Core.
# A plain alias allows static type checkers to resolve the full API.
Core = Capi2Core

__all__ = ["Core"]
