# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""Handlers for the fusesoc CLI subcommands.

Each handler has the signature ``handler(fs, args)`` where ``fs`` is a
:class:`fusesoc.fusesoc.Fusesoc` instance and ``args`` the parsed argparse
namespace. Handlers call the Fusesoc API and format/print the results;
errors are signaled by raising and translated into an error message and
exit code by the dispatcher in :mod:`fusesoc.cli`.
"""

import logging
import os
import warnings
from pathlib import Path

from fusesoc import signature
from fusesoc.config import Config
from fusesoc.errors import FusesocError
from fusesoc.fusesoc import Fusesoc
from fusesoc.librarymanager import Library

logger = logging.getLogger(__name__)


def _effective_config_path(args_config):
    """Return the config path to use, with CLI taking precedence over env var."""
    if args_config:
        return args_config
    return os.environ.get("FUSESOC_CONFIG")


def pgm(fs, args):
    warnings.warn(
        "The 'pgm' subcommand has been removed. "
        "Use 'fusesoc run --target=synth --run' instead."
    )


def fetch(fs, args):
    core = fs.get_core(args.core)

    try:
        core.setup()
    except RuntimeError as e:
        raise FusesocError(f"Failed to fetch '{core.name}': {e}") from e


def list_paths(fs, args):
    cores_root = [x.location for x in fs.get_libraries()]
    print("\n".join(cores_root))


def add_library(fs, args):
    if vars(args).get("global", False):
        library_root = fs.config.library_root
    else:
        library_root = "fusesoc_libraries"

    library = Library.from_sync_uri(
        vars(args)["sync-uri"],
        name=args.name,
        location=args.location,
        sync_type=vars(args).get("sync-type"),
        sync_version=vars(args).get("sync-version"),
        auto_sync=not args.no_auto_sync,
        library_root=library_root,
    )

    # Decide which config file the library is added to
    effective_config = _effective_config_path(args.config)
    if effective_config:
        config = Config(effective_config)
    elif vars(args)["global"]:
        xdg_config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
        config_file = os.path.join(xdg_config_home, "fusesoc", "fusesoc.conf")
        config = Config(config_file)
    else:
        config = Config("fusesoc.conf")

    try:
        config.add_library(library)
    except RuntimeError as e:
        raise FusesocError("`add library` failed: " + str(e)) from e


def library_list(fs, args):
    lengths = [4, 8, 9, 8, 12, 9]
    for lib in fs.get_libraries():
        lengths[0] = max(lengths[0], len(lib.name))
        lengths[1] = max(lengths[1], len(lib.location))
        lengths[2] = max(lengths[2], len(lib.sync_type))
        lengths[3] = max(lengths[3], len(lib.sync_uri or ""))
        lengths[4] = max(lengths[4], len(lib.sync_version or ""))
    print(
        "{} : {} : {} : {} : {} : {}".format(
            "Name".ljust(lengths[0]),
            "Location".ljust(lengths[1]),
            "Sync type".ljust(lengths[2]),
            "Sync URI".ljust(lengths[3]),
            "Sync version".ljust(lengths[4]),
            "Auto sync".ljust(lengths[5]),
        )
    )
    for lib in fs.get_libraries():
        print(
            "{} : {} : {} : {} : {} : {}".format(
                lib.name.ljust(lengths[0]),
                lib.location.ljust(lengths[1]),
                lib.sync_type.ljust(lengths[2]),
                (lib.sync_uri or "N/A").ljust(lengths[3]),
                (lib.sync_version or "(none)").ljust(lengths[4]),
                ("y" if lib.auto_sync else "n").ljust(lengths[5]),
            )
        )


def list_cores(fs, args):
    cores = fs.get_cores()
    trustfile = fs.config.ssh_trustfile or args.ssh_trustfile
    if not trustfile:
        logger.warn(
            "No trustfile configured (ssh-trustfile in fusesoc.conf), signatures will not be checked."
        )
    elif not os.path.isfile(trustfile):
        logger.warn(
            "The trustfile configured in fusesoc.conf does not exist, signatures will not be checked."
        )
    print("\nAvailable cores:\n")
    if not cores:
        cores_root = fs.get_libraries()
        if cores_root:
            logger.error("No cores found in any library")
        else:
            logger.error("No libraries registered")
        exit(1)
    maxlen = max(map(len, cores.keys()))
    print("Core".ljust(maxlen) + "  Cache status  Signature  Description")
    print("=" * 80)
    for name in sorted(cores.keys()):
        core = cores[name]
        print(
            name.ljust(maxlen)
            + " : "
            + core.cache_status().rjust(10)
            + " : "
            + core.sig_status(trustfile).rjust(8)
            + " : "
            + (core.get_description() or "<No description>")
        )


def list_tools(fs, args):
    tools = Fusesoc.get_tools()
    maxlen = max(map(len, tools), default=0)

    for tool_name, desc in tools.items():
        print(f"{tool_name:{maxlen}} : {desc}")


def gen_list(fs, args):
    cores = fs.get_generators()
    if not cores:
        print("\nNo available generators\n")
    else:
        print("\nAvailable generators:\n")
        maxlen = max(map(len, cores.keys()))
        print("Core".ljust(maxlen) + "   Generator")
        print("=" * (maxlen + 12))
        for core in sorted(cores.keys()):
            for generator_name, generator_data in cores[core].items():
                print(
                    "{} : {} : {}".format(
                        core.ljust(maxlen),
                        generator_name,
                        generator_data.get("description", "<No description>"),
                    )
                )


def gen_show(fs, args):
    cores = fs.get_generators()
    for core in sorted(cores.keys()):
        for generator_name, generator_data in cores[core].items():
            if generator_name == args.generator:
                print(
                    """
Core        : {}
Generator   : {}
Description : {}
Usage       :

{}""".format(
                        core,
                        generator_name,
                        generator_data["description"] or "<No description>",
                        generator_data["usage"] or "",
                    )
                )


def core_info(fs, args):
    core = fs.get_core(args.core)
    trustfile = fs.config.ssh_trustfile or args.ssh_trustfile
    print(core.info(trustfile))


def core_sign(fs, args):
    core = fs.get_core(args.core)
    logger.info("sign core file: " + core.core_file)
    logger.info("with key file: " + args.keyfile)
    logger.info("put result in: " + core.core_file + ".sig")
    sigfile = signature.sign_to_file(core, args.keyfile)
    print(f"{sigfile} created")


def gen_clean(fs, args):
    print(f"Cleaned generator cache: {fs.clean_generator_cache()}")


def run(fs, args):
    stages = (args.setup, args.build, args.run)

    # Always run setup if build is true
    args.setup |= args.build

    # Run all stages by default if no stage flags are set
    if stages == (False, False, False):
        do_configure = True
        do_build = True
        do_run = True
    elif stages == (True, False, True):
        raise FusesocError("Configure and run without build is invalid")
    else:
        do_configure = args.setup
        do_build = args.build
        do_run = args.run

    flags = {}
    for flag in args.flag:
        if flag[0] == "+":
            flags[flag[1:]] = True
        elif flag[0] == "-":
            flags[flag[1:]] = False
        else:
            flags[flag] = True

    fs.apply_mappings(args.mapping)

    if args.lockfile is not None:
        fs.load_lockfile(args.lockfile)

    fs.run_target(
        args.system,
        target=args.target,
        tool=args.tool,
        flags=flags,
        backendargs=args.backendargs,
        setup=do_configure,
        build=do_build,
        run=do_run,
        clean=args.clean,
        build_root=args.build_root,
        work_root=args.work_root,
        no_export=args.no_export or None,
        system_name=args.system_name,
        filters=args.filter,
    )


def config(fs, args):
    conf = Config(path=_effective_config_path(args.config), create_if_missing=False)

    if not hasattr(conf, args.key):
        logger.error(f"Invalid config parameter: {args.key}")
        exit(1)

    if not args.value:
        # Read
        if hasattr(conf, args.key):
            print(getattr(conf, args.key))
    else:
        # Write
        if hasattr(conf, args.key):
            setattr(conf, args.key, args.value)
            conf.write()


def update(fs, args):
    fs.update_libraries(args.libraries)
