# PYTHON_ARGCOMPLETE_OK
# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

"""The fusesoc command-line interface.

This package only aggregates command-line arguments, sets up the
:class:`~fusesoc.config.Config` and :class:`~fusesoc.fusesoc.Fusesoc`
instances, and dispatches to the handlers in
:mod:`fusesoc.cli.commands`. All reusable functionality lives in the
Fusesoc API; see :mod:`fusesoc.fusesoc`.
"""

import logging
import signal
import sys

from fusesoc.cli.commands import _effective_config_path
from fusesoc.cli.parser import parse_args
from fusesoc.config import Config
from fusesoc.errors import FusesocError
from fusesoc.fusesoc import Fusesoc

logger = logging.getLogger(__name__)


def abort_handler(signal, frame):
    print("")
    logger.info("****************************")
    logger.info("****   FuseSoC aborted  ****")
    logger.info("****************************")
    print("")
    sys.exit(0)


def fusesoc(args):
    Fusesoc.init_logging(args.verbose, args.monochrome, args.log_file)

    config = Config(_effective_config_path(args.config), create_if_missing=False)
    fs = Fusesoc(
        config,
        cores_root=args.cores_root,
        verbose=args.verbose,
        resolve_env_vars_early=getattr(args, "resolve_env_vars_early", False) or None,
        allow_additional_properties=getattr(args, "allow_additional_properties", False)
        or None,
    )

    # Run the function. The API layer signals errors by raising; translate
    # them into an error message and exit code at this single boundary.
    try:
        args.func(fs, args)
    except (FusesocError, RuntimeError, SyntaxError) as e:
        logger.error(str(e))
        sys.exit(1)


def main():
    signal.signal(signal.SIGINT, abort_handler)

    args = parse_args(sys.argv[1:])
    if not args:
        exit(0)

    logger.debug("Command line arguments: " + str(sys.argv))

    fusesoc(args)


if __name__ == "__main__":
    main()
