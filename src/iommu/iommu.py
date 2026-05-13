#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) Simon Andreas Frimann Lund <os@safl.dk>
#
# Manage the Linux IOMMU substrate via the kernel command line.
#
# Three substrate modes (mutually exclusive):
#
#   off     -- IOMMU drivers disabled; no DMA isolation.
#              `uio_pci_generic` works freely; `vfio-pci` works only
#              with the `enable_unsafe_noiommu_mode` module knob.
#
#   strict  -- IOMMU active for every DMA, including host-owned
#              devices. Highest isolation, highest per-DMA overhead.
#
#   pt      -- IOMMU active but host-owned devices are in the
#              passthrough domain; devices bound to `vfio-pci` get
#              isolated translation. Most common for VM-passthrough /
#              SPDK / DPDK workflows.
#
# Switching modes rewrites the kernel command line via the distro's
# bootloader helper (`grubby` on Fedora/RHEL; `/etc/default/grub` +
# `update-grub` on Debian/Ubuntu). The change applies on the next
# boot; this tool does not reboot for you.
#
# Both legacy vfio groups (`/dev/vfio/<group>`) and iommufd
# (`/dev/iommu` + `/dev/vfio/devices/vfioN`) ride on top of the
# substrate -- neither is selected by this tool; both work whenever
# the IOMMU is on.
#
import argparse
import errno
import logging as log
import os
import re
import subprocess
import sys
from pathlib import Path
from shutil import which

PROC_CMDLINE = Path("/proc/cmdline")
DEFAULT_GRUB = Path("/etc/default/grub")
DEV_IOMMU = Path("/dev/iommu")
VFIO_CDEV_DIR = Path("/dev/vfio/devices")

# Token sets per substrate mode. Mutating to a target mode adds these
# tokens and removes every token from every other mode, so toggling
# between modes leaves a clean cmdline.
MODE_TOKENS = {
    "off": {"intel_iommu=off", "amd_iommu=off"},
    "strict": {"intel_iommu=on", "amd_iommu=on"},
    "pt": {"intel_iommu=on", "amd_iommu=on", "iommu=pt"},
}
ALL_TOKENS = set().union(*MODE_TOKENS.values())

MODES = list(MODE_TOKENS.keys())


def run(cmd):
    """Run a command (list form) and capture the output"""

    log.info(f"cmd({cmd})")
    return subprocess.run(cmd, capture_output=True, text=True)


def current_cmdline():
    """Return the active kernel command line as a string"""

    return PROC_CMDLINE.read_text().strip()


def detect_mode(cmdline: str) -> str:
    """Classify the cmdline into 'pt', 'strict', 'off', or 'unset'"""

    tokens = set(cmdline.split())
    if {"intel_iommu=on", "amd_iommu=on"} & tokens:
        if "iommu=pt" in tokens:
            return "pt"
        return "strict"
    if {"intel_iommu=off", "amd_iommu=off"} & tokens:
        return "off"
    return "unset"


def show_status(args):
    """Show current IOMMU mode + cmdline + iommufd/vfio-cdev availability"""

    cmdline = current_cmdline()
    print(f"cmdline:   {cmdline}")
    print(f"mode:      {detect_mode(cmdline)}")
    print(f"iommufd:   {'available' if DEV_IOMMU.exists() else 'absent'} ({DEV_IOMMU})")
    cdev = list(VFIO_CDEV_DIR.glob("vfio*")) if VFIO_CDEV_DIR.exists() else []
    print(f"vfio-cdev: {len(cdev)} device(s) at {VFIO_CDEV_DIR}")


def update_via_grubby(add, remove, dry_run):
    """Rewrite the kernel cmdline using grubby (Fedora / RHEL)"""

    # --remove-args is best-effort; grubby returns non-zero when none of
    # the args are present, which is fine for our toggle semantics.
    if remove:
        cmd = ["grubby", "--update-kernel=ALL", f"--remove-args={' '.join(sorted(remove))}"]
        if dry_run:
            log.info(f"dry-run: would run {cmd}")
        else:
            run(cmd)

    if add:
        cmd = ["grubby", "--update-kernel=ALL", f"--args={' '.join(sorted(add))}"]
        if dry_run:
            log.info(f"dry-run: would run {cmd}")
            return
        proc = run(cmd)
        if proc.returncode != 0:
            log.error(f"grubby failed: {proc.stderr.strip()}")
            sys.exit(proc.returncode)


def update_via_default_grub(add, remove, dry_run):
    """Rewrite /etc/default/grub's GRUB_CMDLINE_LINUX and run update-grub"""

    pattern = re.compile(r'^(GRUB_CMDLINE_LINUX=")([^"]*)(")$', re.MULTILINE)

    text = DEFAULT_GRUB.read_text() if DEFAULT_GRUB.exists() else ""
    match = pattern.search(text)
    if match:
        prefix, args_str, suffix = match.groups()
        args = args_str.split()
    else:
        prefix, suffix = 'GRUB_CMDLINE_LINUX="', '"'
        args = []

    args = [a for a in args if a not in remove]
    for arg in add:
        if arg not in args:
            args.append(arg)

    new_line = f"{prefix}{' '.join(args)}{suffix}"
    if match:
        new_text = pattern.sub(new_line, text, count=1)
    else:
        sep = "\n" if text and not text.endswith("\n") else ""
        new_text = f"{text}{sep}{new_line}\n"

    if dry_run:
        log.info(f"dry-run: would write {DEFAULT_GRUB} with line: {new_line}")
        log.info("dry-run: would run ['update-grub']")
        return

    log.info(f"writing {DEFAULT_GRUB}")
    DEFAULT_GRUB.write_text(new_text)

    proc = run(["update-grub"])
    if proc.returncode != 0:
        log.error(f"update-grub failed: {proc.stderr.strip()}")
        sys.exit(proc.returncode)


def set_mode(args):
    """Apply the substrate mode to the bootloader config"""

    mode = args.mode
    if mode not in MODE_TOKENS:
        log.error(f"unknown mode: {mode}")
        sys.exit(errno.EINVAL)

    add = MODE_TOKENS[mode]
    remove = ALL_TOKENS - add  # every token from every other mode

    if not args.dry_run and os.geteuid() != 0:
        log.error("Updating GRUB requires root. Re-run with sudo.")
        sys.exit(errno.EPERM)

    if which("grubby"):
        update_via_grubby(add, remove, args.dry_run)
    else:
        update_via_default_grub(add, remove, args.dry_run)

    verb = "Would set" if args.dry_run else "Set"
    print(f"{verb} IOMMU mode to '{mode}'. Reboot for changes to take effect.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage the Linux IOMMU substrate via the kernel command line",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing the bootloader config",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "show",
        help="Show current IOMMU mode, cmdline, and iommufd / vfio-cdev availability",
    )

    set_parser = sub.add_parser(
        "set",
        help="Set the IOMMU substrate mode; reboot to apply",
    )
    set_parser.add_argument(
        "mode",
        choices=MODES,
        help=(
            "off: IOMMU drivers disabled. "
            "strict: IOMMU on, translating for every device. "
            "pt: IOMMU on, host-owned devices in passthrough (most common)."
        ),
    )

    args = parser.parse_args()
    if args.command is None:
        args.command = "show"
    return args


def main():
    args = parse_args()

    log.basicConfig(
        level=log.DEBUG if args.verbose else log.INFO,
        format="# %(levelname)s: %(message)s",
    )

    if args.command == "show":
        show_status(args)
    elif args.command == "set":
        set_mode(args)
    else:
        log.error(f"Unknown command: {args.command}")
        sys.exit(errno.EINVAL)


if __name__ == "__main__":
    main()
