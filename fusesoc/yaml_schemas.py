# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

# Types for the EDAM (EDA Metadata) format produced by Edalizer and consumed
# by Edalize backends and FuseSoC filters.  The shape is derived from the
# CAPI2 JSON schema (fusesoc/capi2/json_schema.py) plus the transformations
# applied by Edalizer.create_edam().

from typing import Literal, TypedDict


# Core Signature Schema
class SignatureEntry(TypedDict):
    type: str  # SSH key type, e.g. "ssh-ed25519"
    user_id: str  # signatory identity from the public key file
    signature: str  # the signature string produced by ssh-keygen -Y sign


class CoreSig(TypedDict):
    name: str  # core VLNV string
    signatures: list[SignatureEntry]


class Signature(TypedDict):
    coresig: CoreSig


# Lockfile Schema
class Lockfile(TypedDict):
    lockfile_version: int
    fusesoc_version: str
    cores: list[dict[str, str]]


# Generator Input Schema
class GeneratorInput(TypedDict):
    files_root: str
    gapi: Literal["1.0"]
    parameters: dict[str, dict]
    vlnv: str


# EDAM Schema
class CustomLicense(TypedDict):
    name: str
    text: str


License = str | CustomLicense


class _FileRecordRequired(TypedDict):
    name: str  # reparented path relative to work_root (set by Edalizer)
    core: str  # owning core VLNV string (set by Edalizer)


class FileRecord(_FileRecordRequired, total=False):
    # Per-file overrides from CAPI2 schema
    file_type: str
    is_include_file: bool
    include_path: str  # reparented by Edalizer
    logical_name: str
    tags: list[str]
    # Note: "copyto" is stripped by Edalizer before inserting into EDAM


ParameterDatatype = Literal["bool", "file", "int", "real", "str"]
ParameterParamtype = Literal[
    "cmdlinearg", "generic", "plusarg", "vlogdefine", "vlogparam"
]


class _ParameterRecordRequired(TypedDict):
    datatype: ParameterDatatype
    paramtype: ParameterParamtype


class ParameterRecord(_ParameterRecordRequired, total=False):
    description: str
    default: str | bool | int | float


class ScriptRecord(TypedDict):
    name: str
    cmd: list[str]
    env: dict[str, str]  # includes FILES_ROOT injected by Edalizer


HookPhase = Literal["pre_build", "post_build", "pre_run", "post_run"]

Hooks = dict[HookPhase, list[ScriptRecord]]


class VpiRecord(TypedDict):
    name: str
    src_files: list[str]
    include_dirs: list[str]
    libs: list[str]


class CoreRecord(TypedDict):
    core_file: str  # path relative to work_root
    dependencies: list[str]
    license: License


class _EdamRequired(TypedDict):
    version: str
    name: str
    toplevel: str


class Edam(_EdamRequired, total=False):
    # Populated by merging per-core snippets in Edalizer.create_edam()
    dependencies: dict[str, list[str]]
    cores: dict[str, CoreRecord]
    parameters: dict[str, ParameterRecord]
    filters: list[str]
    hooks: Hooks
    files: list[FileRecord]
    vpi: list[VpiRecord]
    # flow_options holds both flow-level and tool-level options (Flow API)
    flow_options: dict[str, object]
    # tool options (legacy tool-api backends)
    tool_options: dict[str, dict[str, object]]
