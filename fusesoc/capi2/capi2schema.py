# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LicenseCustom(StrictModel):
    name: str
    text: str


License = str | LicenseCustom


class GeneratorInstance(StrictModel):
    generator: str
    position: Literal["first", "prepend", "append", "last"] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class Generator(StrictModel):
    command: str
    interpreter: str | None = None
    cache_type: Literal["none", "input", "generator"] | None = None
    file_input_parameters: str | None = None
    description: str | None = None
    usage: str | None = None


class Parameter(StrictModel):
    datatype: Literal["bool", "file", "int", "real", "str"]
    default: bool | str | int | float | None = None
    description: str | None = None
    paramtype: Literal[
        "cmdlinearg",
        "generic",
        "plusarg",
        "vlogdefine",
        "vlogparam",
    ]
    scope: str | None = None


class ProviderBase(StrictModel):
    name: str
    patches: list[str] = Field(default_factory=list)
    cachable: bool | None = None


class GithubProvider(ProviderBase):
    name: Literal["github"]
    user: str
    repo: str
    version: str


class LocalProvider(ProviderBase):
    name: Literal["local"]


class GitProvider(ProviderBase):
    name: Literal["git"]
    repo: str
    version: str | None = None


class OpencoresProvider(ProviderBase):
    name: Literal["opencores"]
    repo_name: str
    repo_root: str
    revision: str


class SvnProvider(ProviderBase):
    name: Literal["svn"]
    url: str
    revision: str | None = None
    ignore_externals: bool | None = None


class UrlProvider(ProviderBase):
    name: Literal["url"]
    url: str
    user_agent: str | None = Field(default=None, alias="user-agent")
    verify_cert: str | None = None
    filetype: str


Provider = Annotated[
    GithubProvider
    | LocalProvider
    | GitProvider
    | OpencoresProvider
    | SvnProvider
    | UrlProvider,
    Field(discriminator="name"),
]


class Script(StrictModel):
    env: dict[str, str] = Field(default_factory=dict)
    cmd: list[str] = Field(default_factory=list)
    cmd_append: list[str] = Field(default_factory=list)
    filesets: list[str] = Field(default_factory=list)
    filesets_append: list[str] = Field(default_factory=list)


class Hooks(StrictModel):
    pre_build: list[str] = Field(default_factory=list)
    pre_build_append: list[str] = Field(default_factory=list)
    post_build: list[str] = Field(default_factory=list)
    post_build_append: list[str] = Field(default_factory=list)
    pre_run: list[str] = Field(default_factory=list)
    pre_run_append: list[str] = Field(default_factory=list)
    post_run: list[str] = Field(default_factory=list)
    post_run_append: list[str] = Field(default_factory=list)


class VpiLibrary(StrictModel):
    filesets: list[str] = Field(default_factory=list)
    filesets_append: list[str] = Field(default_factory=list)
    libs: list[str] = Field(default_factory=list)
    libs_append: list[str] = Field(default_factory=list)


class FileAttributes(StrictModel):
    define: dict[str, str | int | float | bool] = Field(default_factory=dict)
    is_include_file: bool = False
    include_path: str | None = None
    file_type: str | None = None
    logical_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    copyto: str | None = None


class FileObject(StrictModel):
    root: dict[str, FileAttributes]

    @model_validator(mode="before")
    @classmethod
    def validate_single_entry(cls, data: Any) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise TypeError("File object must be a mapping")
        if len(data) != 1:
            raise ValueError("File object must contain exactly one file entry")
        return {"root": data}

    def to_mapping(self) -> dict[str, FileAttributes]:
        return self.root


FileEntry = str | FileObject


class Fileset(StrictModel):
    file_type: str | None = None
    logical_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    files: list[FileEntry] = Field(default_factory=list)
    files_append: list[FileEntry] = Field(default_factory=list)
    depend: list[str] = Field(default_factory=list)
    depend_append: list[str] = Field(default_factory=list)


class Target(StrictModel):
    default_tool: str | None = None
    description: str | None = None
    flow: str | None = None
    flow_options: dict[str, Any] = Field(default_factory=dict)
    hooks: Hooks | None = None
    tools: dict[str, dict[str, Any]] = Field(default_factory=dict)
    toplevel: str | list[str] | None = None
    flags: dict[str, Any] = Field(default_factory=dict)
    filesets: list[str] = Field(default_factory=list)
    filesets_append: list[str] = Field(default_factory=list)
    filters: list[str] = Field(default_factory=list)
    filters_append: list[str] = Field(default_factory=list)
    generate: list[str | dict[str, Any]] = Field(default_factory=list)
    generate_append: list[str | dict[str, Any]] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)
    parameters_append: list[str] = Field(default_factory=list)
    vpi: list[str] = Field(default_factory=list)
    vpi_append: list[str] = Field(default_factory=list)


class Capi2Schema(StrictModel):
    description: str | None = None
    license: License | None = None
    filesets: dict[str, Fileset] = Field(default_factory=dict)
    generate: dict[str, GeneratorInstance] = Field(default_factory=dict)
    generators: dict[str, Generator] = Field(default_factory=dict)
    name: str
    parameters: dict[str, Parameter] = Field(default_factory=dict)
    provider: Provider | None = None
    scripts: dict[str, Script] = Field(default_factory=dict)
    targets: dict[str, Target] = Field(default_factory=dict)
    vpi: dict[str, VpiLibrary] = Field(default_factory=dict)
    virtual: list[str] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)


class Capi2SchemaWithAdditionalProperties(Capi2Schema):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
