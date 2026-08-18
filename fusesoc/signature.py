# Copyright FuseSoC contributors
# Licensed under the 2-Clause BSD License, see LICENSE for details.
# SPDX-License-Identifier: BSD-2-Clause

import logging
import os
import shutil
import subprocess
import tempfile

import yaml

from fusesoc import utils

logger = logging.getLogger(__name__)


def sign(core, key_file_name, old_sig_file):
    """
    Generate signature for a core file and return as signature yaml document.
    """
    # Get the name and key type from the public key file, which we
    # assume is in the same directory and has the same name with .pub
    # appended.
    file = open(key_file_name + ".pub")
    key_parts = file.read().split(" ")
    file.close()
    key_type = key_parts[0].strip()
    signatory = key_parts[2].strip()
    core_canonical = core.signed_data()

    if shutil.which("ssh-keygen") is None:
        raise RuntimeError("ssh-keygen not found in $PATH")

    cmd = ["ssh-keygen", "-Y", "sign", "-f", key_file_name, "-n", "file"]
    logger.info("Run command: " + " ".join(cmd))
    res = subprocess.run(cmd, input=core_canonical, capture_output=True)
    sig_data = {
        "coresig": {
            "name": str(core.name),
            "signatures": [
                {
                    "type": key_type,
                    "user_id": signatory,
                    "signature": res.stdout.decode("utf-8").strip(),
                },
            ],
        }
    }

    # Dump multi line signature in yaml | style, without mutating global
    # PyYAML state.
    def str_presenter(dumper, data):
        if len(data.splitlines()) > 1:  # check for multiline string
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    class _SigDumper(yaml.Dumper):
        pass

    _SigDumper.add_representer(str, str_presenter)
    return yaml.dump(sig_data, Dumper=_SigDumper)


def verify(core_obj, trust_file_name, sig_file_name):
    """
    Verify signatures of a core and return a dictionary of users whos
    signatures were tried and their result (True or False).

    The parameter trust_file_name must point to an ssh trust file
    which lists the users and public keys that are trusted, one per
    line, in the format:

        <user_name> <keytype> <public key>

    See man ssh-keygen for details.

    """
    logger.debug("verify core:       " + core_obj.core_file)
    logger.debug("against signature: " + sig_file_name)
    logger.debug("with trustfile:    " + trust_file_name)
    core_canonical = core_obj.signed_data()
    sig_data = utils.yaml_fread(sig_file_name)
    if "coresig" not in sig_data:
        raise RuntimeError("Signature file missing coresig member.")
    if not isinstance(sig_data["coresig"], dict):
        raise RuntimeError("coresig object in signature is not an object.")
    if "name" not in sig_data["coresig"]:
        raise RuntimeError("Signature file missing name member in coresig object.")
    if sig_data["coresig"]["name"] != str(core_obj.name):
        raise RuntimeError(
            "Signature file and core file must have the same 'name' field."
        )
    if shutil.which("ssh-keygen") is None:
        raise RuntimeError("ssh-keygen not found in $PATH")

    user_results = {}
    for sig in sig_data["coresig"]["signatures"]:
        f_os, tmp_name = tempfile.mkstemp(prefix="sig_", suffix=".asc")
        os.write(f_os, bytes(sig["signature"].encode("utf-8")))
        os.close(f_os)
        cmd = [
            "ssh-keygen",
            "-Y",
            "verify",
            "-f",
            trust_file_name,
            "-I",
            sig["user_id"],
            "-n",
            "file",
            "-s",
            tmp_name,
        ]
        logger.debug("Run command: " + str(cmd))
        res = subprocess.run(cmd, input=core_canonical, capture_output=True)
        # A user may have signed a core with several keys, report OK
        # as long as one of them matches.
        try:
            user_results[sig["user_id"]] |= res.returncode == 0
        except KeyError:
            user_results[sig["user_id"]] = res.returncode == 0
        os.remove(tmp_name)
    logger.debug("Result: " + str(user_results))
    return user_results
