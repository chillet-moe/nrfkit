# Dependency layout

All shipped upstream inputs live under `external/`. nrfx, CherryUSB, and
sdk-nrfxlib remain immutable Git submodules at their existing locked commits.
CMSIS Core remains an unmodified, per-file hash-locked snapshot under
`external/cmsis`; moving it does not upgrade or replace its source.

The firmware startup, SystemInit, device headers, and nrfx drivers use the same
nrfx checkout. The earlier standalone MDK copy has been removed after comparing
its bytes with the locked upstream. Source provenance retains the original
upstream paths and file hashes.

The selected nrfx file set in `cmake/nrfx-selection.txt` is shared by installation
and prepared-cache creation.
It includes the supported driver/header closure and its source/license evidence;
unrelated upstream examples and documentation are not copied into the cache.
Only requested driver sources are compiled for each firmware. The two existing
GRTC and XO corrections remain separate patches, applied to the ignored consumer
cache in order. The upstream checkout is never patched in place.

A checkout still requires `git clone --recurse-submodules` (or explicit submodule
initialization). A release archive includes the selected inputs. Normal CMake
configure remains offline and does not discover an installed NCS tree.

## Header boundaries

Project sources use include names resolved by target-scoped CMake include paths.
Cross-module dependencies must not be encoded as `../../` traversal in C/C++
include directives. Private SDC headers stay private to the SDK implementation;
providing their include path does not make them public consumer API.
The SDC private header lives in `softdevice/include/nrfkit/internal/`; enabling
SDC adds `softdevice/include` to the firmware's private include directories.

Upstream relative includes internal to an unchanged vendor tree retain their
original layout and bytes. A relative include within a self-contained source tree
is portable; the failure to avoid is a path escaping the installed dependency or
assuming a particular surrounding workspace. Installed firmware and relocated
package builds verify these boundaries without requiring the original checkout.

Repository-local agent skills live under `.agents/skills/`, independently of the
SDK's runtime dependencies and installation layout.

## Validation of the layout change

The 134-test host suite passed, including Clang and GNU firmware checks,
source/installed consumers, relocated installation, provenance, and reproducible
release archives. An independent source copy in a path containing spaces built
all 28 example ELF targets with invalid NCS/Zephyr environment paths. Seven core
examples produced BIN and HEX files byte-identical to the pre-change baseline.
The prepared cache and installed nrfx tree match the file selection exactly;
changing the manifest triggers automatic reconfiguration and cache replacement.
No board operation was performed for this build-only reorganization.
