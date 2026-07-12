# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Argument parsing for the fusesoc CLI: the argparse tree and the
argcomplete tab-completion helpers."""

import argparse
import pathlib
import sys

import argcomplete

from fusesoc.cli import commands
from fusesoc.cli.commands import _effective_config_path
from fusesoc.config import Config
from fusesoc.fusesoc import Fusesoc

try:
    from fusesoc.version import version as __version__
except ImportError:
    __version__ = "unknown"


class CoreCompleter:
    def __call__(self, parsed_args, **kwargs):
        config = Config(
            _effective_config_path(parsed_args.config), create_if_missing=False
        )
        fs = Fusesoc(config, cores_root=parsed_args.cores_root)
        cores = fs.get_cores()
        return cores


class ToolCompleter:
    def __call__(self, parsed_args, **kwargs):
        return [name for name, desc in Fusesoc.get_tools().items() if desc]


class GenCompleter:
    def __call__(self, parsed_args, **kwargs):
        config = Config(
            _effective_config_path(parsed_args.config), create_if_missing=False
        )
        fs = Fusesoc(config, cores_root=parsed_args.cores_root)
        cores = fs.get_generators()
        return cores


def get_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    # Global actions
    parser.add_argument(
        "--version",
        help="Display the FuseSoC version",
        action="version",
        version=__version__,
    )

    # Global options
    parser.add_argument(
        "--cores-root",
        help="Add additional directories containing cores",
        default=[],
        action="append",
    )
    parser.add_argument(
        "--config",
        help="Specify the config file to use (overrides FUSESOC_CONFIG env var)",
    )
    parser.add_argument(
        "--monochrome",
        help="Don't use color for messages",
        action="store_true",
        default=not sys.stdout.isatty(),
    )
    parser.add_argument("--verbose", help="More info messages", action="store_true")
    parser.add_argument("--log-file", help="Write log messages to file")
    parser.add_argument("--ssh-trustfile", help="Override trustfile in fusesoc.conf")

    # fetch subparser
    parser_fetch = subparsers.add_parser(
        "fetch", help="Fetch a remote core and its dependencies to local cache"
    )
    parser_fetch.add_argument("core")
    parser_fetch.set_defaults(func=commands.fetch)

    # core subparser
    parser_core = subparsers.add_parser(
        "core", help="Subcommands for dealing with cores"
    )
    core_subparsers = parser_core.add_subparsers()
    parser_core.set_defaults(subparser=parser_core)

    # core list subparser
    parser_core_list = core_subparsers.add_parser("list", help="List available cores")
    parser_core_list.set_defaults(func=commands.list_cores)

    # core show subparser
    parser_core_show = core_subparsers.add_parser(
        "show", help="Show information about a core"
    )
    parser_core_show.add_argument(
        "core", help="Name of the core to show"
    ).completer = CoreCompleter()
    parser_core_show.set_defaults(func=commands.core_info)

    parser_core_sign = core_subparsers.add_parser(
        "sign", help="Create user signature for a core"
    )
    parser_core_sign.add_argument(
        "core", help="Name of the core to sign"
    ).completer = CoreCompleter()
    parser_core_sign.add_argument("keyfile", help="File containing ssh private key")
    parser_core_sign.set_defaults(func=commands.core_sign)

    # tool subparser
    parser_tool = subparsers.add_parser(
        "tool", help="Subcommands for dealing with tools"
    )
    tool_subparsers = parser_tool.add_subparsers()
    parser_tool.set_defaults(subparser=parser_tool)

    # tool list subparser
    parser_tool_list = tool_subparsers.add_parser("list", help="List available tools")
    parser_tool_list.set_defaults(func=commands.list_tools)

    # list-cores subparser
    parser_list_cores = subparsers.add_parser("list-cores", help="List available cores")
    parser_list_cores.set_defaults(func=commands.list_cores)

    # core-info subparser
    parser_core_info = subparsers.add_parser(
        "core-info", help="Display details about a core"
    )
    parser_core_info.add_argument("core").completer = CoreCompleter()
    parser_core_info.set_defaults(func=commands.core_info)

    # gen subparser
    parser_gen = subparsers.add_parser(
        "gen", help="Run or show information about generators"
    )
    parser_gen.set_defaults(subparser=parser_gen)
    gen_subparsers = parser_gen.add_subparsers()

    # gen list subparser
    parser_gen_list = gen_subparsers.add_parser(
        "list", help="List available generators"
    )
    parser_gen_list.set_defaults(func=commands.gen_list)

    # gen show subparser
    parser_gen_show = gen_subparsers.add_parser(
        "show", help="Show information about a generator"
    )
    parser_gen_show.add_argument(
        "generator", help="Name of the generator to show"
    ).completer = GenCompleter()
    parser_gen_show.set_defaults(func=commands.gen_show)

    # gen clean subparser
    parser_gen_clean = gen_subparsers.add_parser(
        "clean", help="Clean generator cache directory"
    )
    parser_gen_clean.set_defaults(func=commands.gen_clean)

    # list-paths subparser
    parser_list_paths = subparsers.add_parser(
        "list-paths", help="Display the search order for core root paths"
    )
    parser_list_paths.set_defaults(func=commands.list_paths)

    # library subparser
    parser_library = subparsers.add_parser(
        "library", help="Subcommands for dealing with library management"
    )
    library_subparsers = parser_library.add_subparsers()
    parser_library.set_defaults(subparser=parser_library)

    # library add subparser
    parser_library_add = library_subparsers.add_parser(
        "add", help="Add new library to fusesoc.conf"
    )
    parser_library_add.add_argument(
        "name",
        nargs="?",
        help="A friendly name  for the library. Defaults to last part of sync-uri if not specified.",
    )
    parser_library_add.add_argument(
        "sync-uri", help="The URI source for the library (can be a file system path)"
    )
    parser_library_add.add_argument(
        "--sync-version",
        help="Optionally specify the version of the library to use, for providers that support it",
        dest="sync-version",
    )
    parser_library_add.add_argument(
        "--location",
        help="The location to store the library into (defaults to fusesoc_libraries/[name] or $XDG_DATA_HOME/[name] when --global is set)",
    )
    parser_library_add.add_argument(
        "--sync-type",
        help="The provider type for the library. Defaults to 'git'.",
        choices=["git", "local", "url"],
        dest="sync-type",
    )
    parser_library_add.add_argument(
        "--no-auto-sync",
        action="store_true",
        help="Disable automatic updates of the library",
    )
    parser_library_add.add_argument(
        "--global",
        action="store_true",
        help="Use the global FuseSoC config file in $XDG_CONFIG_HOME/fusesoc/fusesoc.conf",
    )
    parser_library_add.set_defaults(func=commands.add_library)

    # library list subparser
    parser_library_list = library_subparsers.add_parser(
        "list", help="List core libraries"
    )
    parser_library_list.set_defaults(func=commands.library_list)

    # library update subparser
    parser_library_update = library_subparsers.add_parser(
        "update", help="Update the FuseSoC core libraries"
    )
    parser_library_update.add_argument(
        "libraries", nargs="*", help="The libraries to update (defaults to all)"
    )
    parser_library_update.set_defaults(func=commands.update)

    # run subparser
    parser_run = subparsers.add_parser("run", help="Start a tool flow")
    parser_run.add_argument(
        "--clean",
        action="store_true",
        help="Clean build directory on start",
    )
    parser_run.add_argument(
        "--no-export",
        action="store_true",
        help="Reference source files from their current location instead of exporting to a build tree",
    )
    parser_run.add_argument(
        "--build-root",
        help="Output directory for build. VLNV will be appended (defaults to build/)",
    )
    parser_run.add_argument(
        "--work-root",
        help="Output directory for build. VLNV will not be appended (overrides build-root)",
    )
    parser_run.add_argument(
        "--filter",
        help="Add filter. Can be specified multiple times to add multiple filters",
        action="append",
        default=[],
    )
    parser_run.add_argument("--setup", action="store_true", help="Execute setup stage")
    parser_run.add_argument("--build", action="store_true", help="Execute build stage")
    parser_run.add_argument("--run", action="store_true", help="Execute run stage")
    parser_run.add_argument("--target", help="Override default target")
    parser_run.add_argument(
        "--tool", help="Override default tool for target"
    ).completer = ToolCompleter()
    parser_run.add_argument(
        "--flag",
        help="Set custom use flags. Can be specified multiple times",
        action="append",
        default=[],
    )
    parser_run.add_argument(
        "--resolve-env-vars-early",
        action="store_true",
        help="Resolve environment variables in FuseSoC (defaults to no resolution)",
    )
    parser_run.add_argument(
        "--system-name", help="Override default VLNV name for system"
    )
    parser_run.add_argument(
        "--allow-additional-properties",
        action="store_true",
        help="Allow additional properties in core files",
    )
    parser_run.add_argument(
        "system", help="Select a system to operate on"
    ).completer = CoreCompleter()
    parser_run.add_argument(
        "backendargs", nargs=argparse.REMAINDER, help="arguments to be sent to backend"
    )
    parser_run.add_argument(
        "--lockfile",
        help="Lockfile file path",
        type=pathlib.Path,
    )
    parser_run.add_argument(
        "--mapping",
        help="The VLNV of a core's mapping to apply.",
        default=[],
        action="append",
    )
    parser_run.set_defaults(func=commands.run)

    # config subparser
    parser_config = subparsers.add_parser(
        "config",
        help="Read/write config default section [" + Config.default_section + "]",
    )
    parser_config.set_defaults(func=commands.config)
    parser_config.add_argument("key", help="Config parameter")
    parser_config.add_argument(
        "value", nargs=argparse.OPTIONAL, help="Config parameter"
    )

    return parser


def parse_args(argv):
    parser = get_parser()

    argcomplete.autocomplete(parser, always_complete_options=False)
    args = parser.parse_args(argv)

    if hasattr(args, "func"):
        return args
    if hasattr(args, "subparser"):
        args.subparser.print_help()
    else:
        parser.print_help()
        return None
