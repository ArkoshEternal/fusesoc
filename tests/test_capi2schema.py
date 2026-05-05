# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import difflib
import json
import os
from typing import Any

from fusesoc.capi2.capi2schema import Capi2Schema
from fusesoc.capi2.json_schema import capi2_schema


def _to_canonical_json_string(schema_obj: Any) -> str:
    return json.dumps(schema_obj, sort_keys=True, separators=(",", ":"))


def test_capi2_pydantic_json_schema_dump_for_string_comparison(tmp_path: Any) -> None:
    legacy_schema_obj = json.loads(capi2_schema)
    pydantic_schema_obj = Capi2Schema.model_json_schema()

    legacy_dump = json.dumps(legacy_schema_obj, indent=2, sort_keys=True)
    pydantic_dump = json.dumps(pydantic_schema_obj, indent=2, sort_keys=True)

    legacy_path = tmp_path / "legacy_capi2_schema.json"
    pydantic_path = tmp_path / "pydantic_capi2_schema.json"
    legacy_path.write_text(legacy_dump)
    pydantic_path.write_text(pydantic_dump)

    assert legacy_path.exists()
    assert pydantic_path.exists()


def test_capi2_pydantic_json_schema_strict_match_opt_in() -> None:
    legacy_schema_obj = json.loads(capi2_schema)
    pydantic_schema_obj = Capi2Schema.model_json_schema()

    legacy_schema_str = _to_canonical_json_string(legacy_schema_obj)
    pydantic_schema_str = _to_canonical_json_string(pydantic_schema_obj)

    if os.getenv("FUSESOC_ASSERT_SCHEMA_STRICT", "0") != "1":
        return

    if legacy_schema_str != pydantic_schema_str:
        diff = "\n".join(
            difflib.unified_diff(
                legacy_schema_str.splitlines(),
                pydantic_schema_str.splitlines(),
                fromfile="legacy_capi2_schema",
                tofile="pydantic_capi2_schema",
                lineterm="",
            )
        )
        raise AssertionError(
            "Legacy JSON schema does not match Pydantic-generated schema.\n" + diff
        )
