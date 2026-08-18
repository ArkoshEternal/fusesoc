# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Pin the current observable behavior of the flags system (refactor Phase 0).

These tests assert behavior as-is. Tests marked with a NOTE pin behavior that
is scheduled to be deliberately changed in a later phase.
"""

import os.path

import pytest

tests_dir = os.path.dirname(__file__)
cores_dir = os.path.join(tests_dir, "capi2_cores", "misc")


def test_into_flag_defs_encoding():
    from fusesoc.capi2.flags import into_flag_defs

    # True encodes as the bare key
    assert into_flag_defs({"k": True}) == frozenset({"k"})
    # str and int values encode as 'key_value'
    assert into_flag_defs({"k": "v"}) == frozenset({"k_v"})
    assert into_flag_defs({"k": 5}) == frozenset({"k_5"})
    # int 0 is falsy but still encodes
    assert into_flag_defs({"k": 0}) == frozenset({"k_0"})
    # an empty string value yields a def with a trailing underscore
    assert into_flag_defs({"k": ""}) == frozenset({"k_"})
    # None values are dropped
    assert into_flag_defs({"k": None}) == frozenset()
    assert into_flag_defs({}) == frozenset()


def test_into_flag_defs_false_encodes_instead_of_being_dropped():
    from fusesoc.capi2.flags import into_flag_defs

    # NOTE: pins current behavior. bool is a subclass of int, so a False
    # value is caught by the isinstance(v, (str, int)) branch and encodes as
    # 'k_False' rather than being dropped like None.
    assert into_flag_defs({"k": False}) == frozenset({"k_False"})


def test_into_flag_defs_aliasing():
    from fusesoc.capi2.flags import into_flag_defs

    # The 'key_value' encoding is ambiguous: distinct flag mappings collapse
    # to the same def.
    assert into_flag_defs({"a": "b_c"}) == frozenset({"a_b_c"})
    assert into_flag_defs({"a_b": "c"}) == frozenset({"a_b_c"})
    assert into_flag_defs({"a_b_c": True}) == frozenset({"a_b_c"})


def test_get_target_name():
    from fusesoc.capi2.flags import get_target_name

    # 'target' is honored only when 'is_toplevel' is truthy AND 'target' is
    # truthy; everything else falls back to 'default'.
    assert get_target_name({"is_toplevel": True, "target": "sim"}) == "sim"
    assert get_target_name({"is_toplevel": False, "target": "sim"}) == "default"
    assert get_target_name({"target": "sim"}) == "default"
    assert get_target_name({"is_toplevel": True}) == "default"
    assert get_target_name({}) == "default"
    # any truthy is_toplevel value works, not just True
    assert get_target_name({"is_toplevel": "yes", "target": "sim"}) == "sim"
    # falsy targets (even non-str) fall back to 'default' without complaint
    assert get_target_name({"is_toplevel": True, "target": ""}) == "default"
    assert get_target_name({"is_toplevel": True, "target": 0}) == "default"


def test_get_target_name_non_str_target_raises_flag_error():
    from fusesoc.capi2.flags import get_target_name
    from fusesoc.exceptions import FlagError

    with pytest.raises(FlagError, match="Target must be a string"):
        get_target_name({"is_toplevel": True, "target": 5})


def test_get_flags_folds_default_tool_into_tool_flag():
    from fusesoc.capi2.coreparser import Core2Parser
    from fusesoc.core import Core

    core = Core(Core2Parser(), os.path.join(cores_dir, "flags.core"))

    # default_tool is folded into flags['tool']
    assert core.get_flags("emptyflagstool") == {"tool": "mytool"}
    # ...and a 'tool' entry in the target's flags block is overridden by
    # default_tool ('tool: notmytool' loses to 'default_tool: mytool')
    assert core.get_flags("allflagstool") == {
        "flag1": False,
        "flag2": True,
        "tool": "mytool",
    }


def test_cli_flags_override_target_flags():
    from fusesoc.capi2.coreparser import Core2Parser
    from fusesoc.core import Core

    core = Core(Core2Parser(), os.path.join(cores_dir, "flags.core"))

    # Merge policy as implemented in the 'run' subcommand (fusesoc/main.py):
    #   flags = dict(core.get_flags(flags["target"]), **flags)
    # CLI flags win over target-declared flags and over default_tool.
    cli_flags = {"target": "allflagstool", "flag1": True, "tool": "clitool"}
    merged = dict(core.get_flags(cli_flags["target"]), **cli_flags)
    assert merged == {
        "target": "allflagstool",
        "flag1": True,  # CLI wins over the target's 'flag1: false'
        "flag2": True,  # inherited from the target's flags block
        "tool": "clitool",  # CLI wins over default_tool
    }

    # Without a CLI override, the target-declared values flow through
    cli_flags = {"target": "allflagstool"}
    merged = dict(core.get_flags(cli_flags["target"]), **cli_flags)
    assert merged == {
        "target": "allflagstool",
        "flag1": False,
        "flag2": True,
        "tool": "mytool",
    }


def test_get_flow_flag_short_circuits_target_resolution():
    from fusesoc.capi2.coreparser import Core2Parser
    from fusesoc.core import Core

    core = Core(Core2Parser(), os.path.join(cores_dir, "flow.core"))

    # A truthy 'flow' flag is returned as-is, without consulting the target,
    # even when the target declares a different flow
    assert core.get_flow({"flow": "someflow"}) == "someflow"
    assert core.get_flow({"flow": "someflow", "target": "flowonly"}) == "someflow"

    # flow is typed str | None: a truthy non-str value is rejected
    from fusesoc.exceptions import FlagError

    with pytest.raises(FlagError, match="Flow must be a string"):
        core.get_flow({"flow": True})

    # Falsy 'flow' values fall through to target resolution (get_flow forces
    # is_toplevel internally, so no is_toplevel flag is needed)
    assert core.get_flow({"flow": False, "target": "flowonly"}) == "icestorm"
    assert core.get_flow({"target": "flowonly"}) == "icestorm"
    assert core.get_flow({"target": "flowandtool"}) == "icestorm"
    # a target with only default_tool has no flow
    assert core.get_flow({"target": "toolonly"}) is None
    # empty-string flow is falsy too; no 'default' target exists -> None
    assert core.get_flow({"flow": ""}) is None


def test_reserved_flag_names_are_not_validated():
    from fusesoc.capi2.flags import into_flag_defs

    # The def encoding itself treats reserved keys like any other flag; the
    # typed Flags class (tested separately) rejects reserved names only in
    # its use_flags namespace:
    assert into_flag_defs({"tool": "vivado"}) == frozenset({"tool_vivado"})
    assert into_flag_defs({"target": "sim"}) == frozenset({"target_sim"})
    assert into_flag_defs({"flow": "icestorm"}) == frozenset({"flow_icestorm"})
    assert into_flag_defs({"is_toplevel": True}) == frozenset({"is_toplevel"})

    # The encoding makes a reserved key indistinguishable from a user boolean
    # flag literally named after the encoded def:
    assert into_flag_defs({"tool": "vivado"}) == into_flag_defs({"tool_vivado": True})


def test_flags_class_mapping_protocol():
    from fusesoc.capi2.flags import Flags

    flags = Flags(target="synth", tool="vivado", use_flags={"fast": True})

    # Flattened mapping view: set reserved fields first, then use flags
    assert dict(flags) == {"target": "synth", "tool": "vivado", "fast": True}
    assert flags["target"] == "synth"
    assert flags["fast"] is True
    assert "tool" in flags
    assert "flow" not in flags  # unset reserved flags are absent
    assert len(flags) == 3
    assert flags.get("flow") is None

    with pytest.raises(KeyError):
        flags["flow"]

    # Equality against plain mappings, both directions
    assert flags == {"target": "synth", "tool": "vivado", "fast": True}
    assert {"target": "synth", "tool": "vivado", "fast": True} == flags

    # is_toplevel=False is set-and-present, matching historical injection
    assert dict(Flags(is_toplevel=False)) == {"is_toplevel": False}

    # kwargs expansion and copy() keep working like the old plain dicts
    assert dict({"base": 1}, **flags)["fast"] is True
    mutable = flags.copy()
    mutable["extra"] = True
    assert isinstance(mutable, dict)


def test_flags_class_hashable():
    from fusesoc.capi2.flags import Flags, derive

    a = Flags(target="sim", use_flags={"x": 1})
    b = derive({"target": "sim", "x": 1})
    assert a == b
    assert hash(a) == hash(b)
    assert a != Flags(target="sim", use_flags={"x": 2})
    # usable as a dict key
    assert {a: "cached"}[b] == "cached"


def test_flags_class_validation():
    from fusesoc.capi2.flags import Flags
    from fusesoc.exceptions import FlagError

    with pytest.raises(FlagError, match="Target must be a string"):
        Flags(target=5)
    with pytest.raises(FlagError, match="Tool must be a string"):
        Flags(tool=True)
    with pytest.raises(FlagError, match="Flow must be a string"):
        Flags(flow=True)
    with pytest.raises(FlagError, match="is_toplevel must be a boolean"):
        Flags(is_toplevel="yes")


def test_reserved_flag_names_rejected_as_use_flags():
    from fusesoc.capi2.flags import Flags
    from fusesoc.exceptions import FlagError

    for name in ("target", "tool", "flow", "is_toplevel"):
        with pytest.raises(FlagError, match="reserved flag name"):
            Flags(use_flags={name: True})
        with pytest.raises(FlagError, match="reserved flag name"):
            Flags.from_cli_strings([f"+{name}"])


def test_flags_from_mapping_compat_coercions():
    from fusesoc.capi2.flags import Flags

    # Reserved keys are routed to fields
    flags = Flags.from_mapping({"target": "synth", "tool": "vivado", "x": True})
    assert flags.target == "synth"
    assert flags.tool == "vivado"
    assert flags.use_flags == {"x": True}

    # Falsy target/tool/flow mean unset (historical truthiness checks)
    assert Flags.from_mapping({"flow": False}).flow is None
    assert Flags.from_mapping({"flow": ""}).flow is None
    assert Flags.from_mapping({"target": 0}).target is None

    # is_toplevel keeps its presence and is coerced to bool
    assert Flags.from_mapping({"is_toplevel": "yes"}).is_toplevel is True
    assert Flags.from_mapping({"is_toplevel": False}).is_toplevel is False
    assert Flags.from_mapping({}).is_toplevel is None

    # A Flags instance passes through unchanged
    f = Flags(target="sim")
    assert Flags.from_mapping(f) is f


def test_flags_replace_and_derive():
    from fusesoc.capi2.flags import Flags, derive

    base = Flags(target="sim", use_flags={"x": True})
    top = base.replace(is_toplevel=True)
    assert top.is_toplevel is True
    assert top.target == "sim"
    assert top.use_flags == {"x": True}
    assert base.is_toplevel is None  # original unchanged

    # derive() accepts plain mappings, replacing the copy-and-mutate idiom
    derived = derive({"target": "sim", "x": True}, is_toplevel=True)
    assert derived == top


def test_flags_from_cli_strings():
    from fusesoc.capi2.flags import Flags
    from fusesoc.exceptions import FlagError

    flags = Flags.from_cli_strings(["+a", "-b", "c"], target="synth", tool="vivado")
    assert flags.target == "synth"
    assert flags.tool == "vivado"
    assert flags.use_flags == {"a": True, "b": False, "c": True}

    # target defaults to "default" as the CLI always did
    assert Flags.from_cli_strings([]).target == "default"

    for bad in ("", "+", "-"):
        with pytest.raises(FlagError, match="empty flag name"):
            Flags.from_cli_strings([bad])


def test_flags_with_core_defaults_matches_legacy_merge():
    from fusesoc.capi2.coreparser import Core2Parser
    from fusesoc.capi2.flags import Flags
    from fusesoc.core import Core

    core = Core(Core2Parser(), os.path.join(cores_dir, "flags.core"))

    # Equivalent to the historical dict(core.get_flags(target), **cli_flags)
    cli = Flags.from_cli_strings(["+cliflag"], target="allflagstool")
    merged = cli.with_core_defaults(core)
    legacy = dict(core.get_flags("allflagstool"), **cli)
    assert merged == legacy

    # Explicit tool wins over the target's default_tool
    cli_tool = Flags.from_cli_strings([], target="allflagstool", tool="clitool")
    assert cli_tool.with_core_defaults(core)["tool"] == "clitool"


def test_into_flag_defs_warns_on_ambiguous_defs(caplog):
    import logging

    from fusesoc.capi2.flags import into_flag_defs

    with caplog.at_level(logging.WARNING):
        defs = into_flag_defs({"a": "b_c", "a_b": "c"})
    assert defs == frozenset({"a_b_c"})
    assert "Ambiguous flags" in caplog.text
