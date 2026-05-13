# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) Simon Andreas Frimann Lund <os@safl.dk>

import subprocess
import sys


def test_help():
    result = subprocess.run(
        [sys.executable, "-m", "iommu.iommu", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "iommu" in result.stdout.lower()
    assert "show" in result.stdout.lower()


def test_show_runs():
    """`show` reads /proc/cmdline; no privileges needed, must not fail"""

    result = subprocess.run(
        [sys.executable, "-m", "iommu.iommu", "show"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "cmdline:" in result.stdout
    assert "mode:" in result.stdout


def test_default_action_is_show():
    """Running with no action falls back to `show`"""

    result = subprocess.run(
        [sys.executable, "-m", "iommu.iommu"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "mode:" in result.stdout


def test_help_lists_all_modes():
    result = subprocess.run(
        [sys.executable, "-m", "iommu.iommu", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    for mode in ("off-for-uio", "off-for-vfio", "strict", "pt"):
        assert mode in result.stdout


def test_dry_run_set_runs_unprivileged():
    """`--dry-run <mode>` must work as any user (no GRUB write)"""

    result = subprocess.run(
        [sys.executable, "-m", "iommu.iommu", "--dry-run", "pt"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "would set" in result.stdout.lower()


def test_import():
    from iommu import main

    assert callable(main)
