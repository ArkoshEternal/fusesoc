# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Exception hierarchy for the FuseSoC library API.

Code in the :class:`fusesoc.fusesoc.Fusesoc` API layer signals user-facing
failures by raising :class:`FusesocError` (or a subclass). The command-line
interface catches these at a single boundary and turns them into an error
message and a non-zero exit code; programmatic users (pytest fixtures, build
scripts) catch them like any other exception.
"""


class FusesocError(Exception):
    """Base class for user-facing FuseSoC errors."""


class CoreNotFoundError(FusesocError):
    """A core, or one of its dependencies, could not be found."""

    def __init__(self, msg, core_name=None):
        super().__init__(msg)
        self.core_name = core_name


class AmbiguousCoreNameError(FusesocError):
    """A partial core name matched more than one core."""

    def __init__(self, core_name, candidates):
        msg = f"'{core_name}' is ambiguous. Potential matches: "
        msg += ", ".join(f"'{x}'" for x in sorted(candidates))
        super().__init__(msg)
        self.core_name = core_name
        self.candidates = candidates


class StageFailedError(FusesocError):
    """An edalize stage (configure, build or run) failed."""

    def __init__(self, stage, msg):
        super().__init__(msg)
        self.stage = stage
