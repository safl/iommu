![iommu: inspect and configure the IOMMU isolation level in Linux](https://raw.githubusercontent.com/safl/iommu/main/assets/banner.svg)

# iommu

[![PyPI](https://img.shields.io/pypi/v/iommu.svg)](https://pypi.org/project/iommu/)
[![Python](https://img.shields.io/pypi/pyversions/iommu.svg)](https://pypi.org/project/iommu/)
[![Test](https://github.com/safl/iommu/actions/workflows/test.yml/badge.svg)](https://github.com/safl/iommu/actions/workflows/test.yml)

Inspect and configure the IOMMU isolation level in Linux.

The Linux IOMMU (Intel VT-d, AMD-Vi) sits between the CPU and PCI
devices, translating and isolating DMA. User space tools that talk to
PCI devices directly (`vfio-pci` for VM passthrough, `vfio-pci` or
`uio_pci_generic` for DPDK/SPDK and xNVMe/uPCIe) interact with the
IOMMU substrate differently depending on which mode the kernel was
booted with.

`iommu` is a small CLI for inspecting the current mode and switching
between them. It rewrites the bootloader's kernel command line; the
change applies on the next boot.

## Modes

Four substrate modes, mutually exclusive.

### `off-for-uio`

Tokens: `intel_iommu=off amd_iommu=off`

The IOMMU drivers don't load. No DMA isolation anywhere. `uio_pci_generic`
binds and works. `vfio-pci` does not work here; there are no IOMMU
groups for it to bind against. Zero overhead, zero protection;
appropriate on trusted hardware or for development where the IOMMU is
undesirable.

### `off-for-vfio`

Tokens: `intel_iommu=off amd_iommu=off vfio.enable_unsafe_noiommu_mode=1`

Same as `off-for-uio` (IOMMU off, no DMA isolation), but also tells the
`vfio` module to expose "noiommu" groups so `vfio-pci` binds without an
IOMMU backing it. As unsafe as `off-for-uio` (same lack of isolation),
just a different user space driver framework. Use this when your user
space driver stack (DPDK/SPDK and xNVMe/uPCIe) requires `vfio-pci` but
you can't or don't want to turn the IOMMU on.

### `strict`

Tokens: `intel_iommu=on amd_iommu=on`

The IOMMU drivers load and every DMA from every device is translated,
including host-owned devices. Maximum isolation; defends the host kernel
from malicious or buggy DMA. Highest per-DMA overhead. This is what
"IOMMU on" traditionally meant.

### `pt` (passthrough)

Tokens: `intel_iommu=on amd_iommu=on iommu=pt`

The IOMMU drivers load but host-owned devices skip translation (the
passthrough domain). Devices bound to `vfio-pci` get switched to an
isolated translating domain. Best of both worlds: native host
performance plus full vfio isolation for VM-passthrough / user space
drivers. The most common production configuration.

## Modifiers

Independent of the substrate mode, one further knob sometimes applies:

### Unsafe interrupts (cmdline)

On platforms without Interrupt Remapping, `vfio-pci` passthrough refuses
to bind by default. Two tokens lift that restriction:

```
vfio_iommu_type1.allow_unsafe_interrupts=1
iommufd.allow_unsafe_interrupts=1
```

Only meaningful when combined with `strict` or `pt`. This tool does not
write them automatically today; they are listed here for awareness.

## What this tool does *not* control

- **iommufd vs legacy vfio groups.** Both APIs ride on top of the
  substrate modes above. On kernel 6.5+, `vfio-pci` exposes the legacy
  `/dev/vfio/<group>` container API *and* the iommufd cdev API at
  `/dev/vfio/devices/vfioN` (backed by `/dev/iommu`) simultaneously;
  whichever the user space consumer asks for is what it gets. `iommu`
  doesn't pick.
- **`iommu.strict={0,1}`.** IOTLB-flush policy (lazy vs strict). An
  orthogonal perf-vs-isolation knob; modern x86 defaults to lazy.
- **Architecture-specific IOMMU drivers** beyond Intel VT-d / AMD-Vi
  (e.g. `arm-smmu`). Out of scope.

## Bootloader handling

`iommu <mode>` auto-detects the bootloader manager and writes the
new cmdline:

- **`grubby`** (Fedora / RHEL): one `--update-kernel=ALL` invocation
  to add the target tokens, one to remove the others.
- **`/etc/default/grub` + `update-grub`** (Debian / Ubuntu): rewrites
  `GRUB_CMDLINE_LINUX` in place, then runs `update-grub`.

`--dry-run` shows the intended write without applying it; runs as any
user, no root needed for the preview. The real write requires root
(reading `/proc/cmdline` for `show` does not).

## Usage

```
iommu                              # = iommu show (no-arg default)
iommu show                         # cmdline, mode, iommufd + vfio-cdev availability
iommu --dry-run pt                 # preview without writing GRUB
sudo iommu pt && sudo reboot       # most common: IOMMU on, host passthrough
sudo iommu strict                  # IOMMU on, translating for all devices
sudo iommu off-for-uio             # IOMMU disabled, uio_pci_generic ready
sudo iommu off-for-vfio            # IOMMU disabled + noiommu knob, vfio-pci ready
```

`iommu show` sample output:

```
cmdline:   BOOT_IMAGE=... root=UUID=... intel_iommu=on amd_iommu=on iommu=pt ...
mode:      pt
iommufd:   available (/dev/iommu)
vfio-cdev: 0 device(s) at /dev/vfio/devices
```

## Install

```
pipx install iommu
```

Or standalone (single-file, stdlib only, no pip needed):

```
curl -fsSL https://raw.githubusercontent.com/safl/iommu/main/src/iommu/iommu.py \
  -o ~/.local/bin/iommu && chmod +x ~/.local/bin/iommu
```

## Shell completion

```
iommu --print-completion bash > ~/.local/share/bash-completion/completions/iommu
```

Open a new shell (or `source` the file) and tab-completion is live: `sudo iommu <TAB>` lists `show off-for-uio off-for-vfio strict pt`.

## Related

- [`devbind`](https://github.com/xnvme/devbind): inspect and control PCI device-driver binding in Linux.
- [`hugepages`](https://github.com/xnvme/hugepages): inspect and manage Linux hugepages.
