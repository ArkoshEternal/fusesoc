# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Exception hierarchy for FuseSoC.

All errors raised by FuseSoC itself derive from :class:`FusesocError`, so
library users can catch a single type at the API boundary and dispatch on
the specific subclasses where needed.

Transition note: FuseSoC historically signalled parse errors by raising the
builtin ``SyntaxError`` and most other failures as bare ``RuntimeError``. To
keep existing ``except`` clauses working, the corresponding classes below
also inherit from those builtins. This dual inheritance is a compatibility
bridge that will be removed in a future release; catch the
:class:`FusesocError` types instead.
"""


class FusesocError(Exception):
    """Base class for all errors raised by FuseSoC."""

    def __init__(self, msg=""):
        super().__init__(msg)
        self.msg = msg


class CoreParseError(FusesocError, SyntaxError):
    """A core description file could not be parsed or validated."""


class VlnvError(CoreParseError):
    """A core name (VLNV) string is malformed."""


class LockfileError(FusesocError, SyntaxError):
    """A lock file could not be parsed or validated."""


class LibraryError(FusesocError, RuntimeError):
    """A core library could not be added, initialized or updated."""


class LibraryExistsError(LibraryError):
    """The library is already present in the configuration."""


class ConfigError(FusesocError):
    """Invalid or unusable configuration."""


class FlagError(FusesocError):
    """Invalid flags: reserved-name collision, malformed flag string or a
    reserved flag with the wrong type."""


class CoreNotFoundError(FusesocError):
    """No core matches the requested name.

    ``parse_errors`` carries ``(core_file, error_message)`` tuples for core
    files that failed to parse during library scanning; the missing core may
    be defined in one of them.
    """

    def __init__(self, msg="", parse_errors=None):
        super().__init__(msg)
        self.parse_errors = list(parse_errors or [])

    def __reduce__(self):
        return (type(self), (self.msg, self.parse_errors))


class AmbiguousCoreError(FusesocError):
    """A short core name matches more than one core."""

    def __init__(self, core_name, candidates):
        candidate_str = ", ".join(f"'{c}'" for c in sorted(candidates))
        super().__init__(
            f"'{core_name}' is ambiguous. Potential matches: {candidate_str}"
        )
        self.core_name = core_name
        self.candidates = set(candidates)

    def __reduce__(self):
        return (type(self), (self.core_name, sorted(self.candidates)))


class ToolOrFlowError(FusesocError, RuntimeError):
    """No usable tool or flow could be determined for a core/target."""


class BackendError(FusesocError, RuntimeError):
    """An EDA backend stage (configure/build/run) failed.

    ``stage`` names the failed stage.
    """

    def __init__(self, msg="", stage=None):
        super().__init__(msg)
        self.stage = stage

    def __reduce__(self):
        return (type(self), (self.msg, self.stage))


class DependencyError(FusesocError):
    """Dependency resolution failed for a core.

    ``value`` names the core (or dependency expression) that could not be
    resolved.
    """

    def __init__(self, value, msg=""):
        super().__init__(msg)
        self.value = value

    def __str__(self):
        if self.msg:
            return f"{self.value!r}: {self.msg}"
        return repr(self.value)
