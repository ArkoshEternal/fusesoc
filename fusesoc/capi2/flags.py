# SPDX-License-Identifier: BSD-2-Clause
# SPDX-FileCopyrightText: FuseSoC contributors

"""The flags system.

Flags steer target selection, tool/flow selection and conditional
expressions in core files. Four *reserved* flags (``target``, ``tool``,
``flow`` and ``is_toplevel``) drive FuseSoC itself; all other flags are
user-defined *use flags* consumed by ``cond ? (...)`` expressions.

:class:`Flags` is the canonical, immutable representation. It implements the
``Mapping`` protocol over the flattened view (reserved flags that are set,
followed by the use flags), so it is a drop-in replacement for the plain
dicts that were passed around historically, and it is hashable so it can key
caches directly.
"""

import dataclasses
import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import validate_call

from fusesoc.exceptions import FlagError

logger = logging.getLogger(__name__)

FlagValue = bool | str | int | None
FlagsLike = Mapping[str, FlagValue]
FlagDefs = frozenset[str]

_RESERVED_FLAGS = ("target", "tool", "flow", "is_toplevel")


@dataclass(frozen=True, eq=False)
class Flags(Mapping):
    """Immutable, validated flag set.

    The reserved flags are explicit fields; everything else lives in
    ``use_flags``. A reserved flag set to ``None`` is *unset* and absent
    from the mapping view; ``is_toplevel=False`` is set-and-false, matching
    the historical injection of that key.
    """

    target: str | None = None
    tool: str | None = None
    flow: str | None = None
    is_toplevel: bool | None = None
    use_flags: Mapping[str, FlagValue] = field(default_factory=dict)

    def __post_init__(self):
        for name in ("target", "tool", "flow"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise FlagError(f"{name.capitalize()} must be a string.")
        if self.is_toplevel is not None and not isinstance(self.is_toplevel, bool):
            raise FlagError("is_toplevel must be a boolean.")
        for name in self.use_flags:
            if name in _RESERVED_FLAGS:
                raise FlagError(
                    f"'{name}' is a reserved flag name and cannot be used "
                    "as a use flag"
                )
        object.__setattr__(self, "use_flags", dict(self.use_flags))

    @classmethod
    def from_mapping(cls, flags: FlagsLike) -> "Flags":
        """Build a :class:`Flags` from a plain mapping.

        Reserved keys are routed to their fields. For compatibility with the
        historical truthiness checks, falsy ``target``/``tool``/``flow``
        values are treated as unset, and a set ``is_toplevel`` is coerced to
        its truth value.
        """
        if isinstance(flags, cls):
            return flags
        # Reserved values are staged untyped: a non-string target/tool/flow is
        # forwarded as-is so that __post_init__ rejects it with a typed error,
        # rather than being silently coerced here.
        reserved: dict[str, Any] = {}
        use_flags: dict[str, FlagValue] = {}
        for key, value in flags.items():
            if key == "is_toplevel":
                if value is not None:
                    reserved[key] = bool(value)
            elif key in ("target", "tool", "flow"):
                reserved[key] = value if value else None
            else:
                use_flags[key] = value
        return cls(use_flags=use_flags, **reserved)

    @classmethod
    def from_cli_strings(
        cls,
        flag_strings,
        target: str | None = None,
        tool: str | None = None,
    ) -> "Flags":
        """Parse ``--flag`` style strings: ``+name``/``name`` set a use flag
        to True, ``-name`` sets it to False."""
        use_flags: dict[str, FlagValue] = {}
        for flag in flag_strings:
            if flag.startswith("+"):
                name, value = flag[1:], True
            elif flag.startswith("-"):
                name, value = flag[1:], False
            else:
                name, value = flag, True
            if not name:
                raise FlagError(f"Invalid empty flag name in '--flag={flag}'")
            if name in _RESERVED_FLAGS:
                raise FlagError(
                    f"'{name}' is a reserved flag name; use the dedicated "
                    "option (e.g. --target/--tool) instead of --flag"
                )
            use_flags[name] = value
        return cls(target=target or "default", tool=tool, use_flags=use_flags)

    def replace(self, **overrides) -> "Flags":
        """Return a copy with the given reserved fields replaced."""
        return dataclasses.replace(self, **overrides)

    def with_core_defaults(self, core) -> "Flags":
        """Merge the core's target-declared default flags (including
        ``default_tool``) under this flag set; explicitly set flags win.

        This is the merge the CLI historically performed as
        ``dict(core.get_flags(target), **flags)``.
        """
        merged = dict(core.get_flags(self.target if self.target else "default"))
        merged.update(self.items())
        # Pin the resolved target so downstream flags["target"] lookups work
        # even when the caller left it implicit.
        merged.setdefault("target", self.target or "default")
        return Flags.from_mapping(merged)

    def _set_items(self) -> Iterator[tuple[str, FlagValue]]:
        for name in _RESERVED_FLAGS:
            value = getattr(self, name)
            if value is not None:
                yield name, value

    def __getitem__(self, key: str) -> FlagValue:
        if key in _RESERVED_FLAGS:
            value = getattr(self, key)
            if value is None:
                raise KeyError(key)
            return value
        return self.use_flags[key]

    def __iter__(self) -> Iterator[str]:
        for name, _ in self._set_items():
            yield name
        yield from self.use_flags

    def __len__(self) -> int:
        return sum(1 for _ in self._set_items()) + len(self.use_flags)

    def __eq__(self, other):
        if isinstance(other, Mapping):
            return dict(self) == dict(other)
        return NotImplemented

    def __hash__(self):
        return hash(frozenset(self.items()))

    def copy(self) -> dict:
        """Return a plain mutable dict copy (legacy compatibility)."""
        return dict(self)

    def __repr__(self):
        return f"Flags({dict(self)!r})"


def derive(flags: FlagsLike, **overrides) -> Flags:
    """Return a :class:`Flags` copy of *flags* with reserved-field
    *overrides* applied. Replaces the historical copy-and-mutate idiom."""
    return Flags.from_mapping(flags).replace(**overrides)


@validate_call
def into_flag_defs(flags: FlagsLike) -> FlagDefs:
    ret = []
    for k, v in flags.items():
        if v is True:
            ret.append(k)
        elif isinstance(v, (str, int)):
            ret.append(k + "_" + str(v))
    defs = frozenset(ret)
    if len(defs) < len(ret):
        dupes = sorted({d for d in ret if ret.count(d) > 1})
        logger.warning(
            "Ambiguous flags: multiple flags produce the same expression "
            f"condition(s) {dupes}; expressions cannot tell them apart"
        )
    return defs


def get_target_name(flags: FlagsLike) -> str:
    if flags.get("is_toplevel") and (target := flags.get("target")):
        if not isinstance(target, str):
            raise FlagError("Target must be a string.")
        return target
    else:
        return "default"
