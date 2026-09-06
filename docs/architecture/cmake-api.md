# Consumer CMake API

Use `find_package(NrfKit CONFIG REQUIRED)`, create an executable, configure its
image, link capabilities, and finalize it. The same API is available from a source
checkout and an installed SDK. Configuration does not fetch dependencies.

```cmake
add_executable(app main.cpp)
nrfkit_configure_target(app
  SOC nrf54lm20a CORE cpuapp
  LINKER_SCRIPT "${CMAKE_CURRENT_SOURCE_DIR}/image/app.ld"
  IMAGE_LAYOUT "${CMAKE_CURRENT_SOURCE_DIR}/image/app-layout.json"
)
nrfkit_configure_usb(app CLASSES hid
  IN_ENDPOINT_MAX_PACKET_SIZES 8 64 32 32)
target_link_libraries(app PRIVATE
  NrfKit::sdc_multirole
  NrfKit::radio_timeslot
  NrfKit::rram
  NrfKit::usb_device
  NrfKit::nrfx_gpio
)
nrfkit_finalize_target(app)
```

## Capability targets

| Target | Contents and requirements |
| --- | --- |
| `NrfKit::core` | Public SDK headers; usable without a firmware runtime. |
| `NrfKit::nrfx_<driver>` | Selected nrfx driver and its source dependencies. |
| `NrfKit::sdc_multirole` | Multirole Controller, SDK platform/HCI implementation, and locked MPSL/FEM dependencies. |
| `NrfKit::sdc_peripheral` | Peripheral-only version of the same integration. |
| `NrfKit::sdc_central` | Central-only version of the same integration. |
| `NrfKit::radio_direct` | Exclusive RADIO backend and nrfx CLOCK; incompatible with SDC. |
| `NrfKit::radio_timeslot` | RADIO backend under MPSL Timeslot scheduling; requires one SDC variant. |
| `NrfKit::rram` | Asynchronous RRAM writes scheduled by MPSL; requires one SDC variant. |
| `NrfKit::usb_port` | LM20 CherryUSB DCD and clock/power glue; consumer owns the compatible core/class sources. |
| `NrfKit::usb_device` | USB port plus the supplied CherryUSB core and configured classes. |

Supported nrfx driver names are `clock`, `power`, `gpio`, `gpiote`, `grtc`, `timer`, `dppi`,
`uarte`, `spim`, `twim`, `pwm`, `saadc`, `rramc`, `watchdog`, `reset`, `retention`,
and `cracen`. Driver names select source components, not peripheral instances.
Select at most one SDC variant. For USB, choose the complete-device target or
the port target according to which project owns core/class sources; the complete
device target carries the port transitively.

These capabilities use INTERFACE libraries to carry sources and usage requirements.
INTERFACE does not mean header-only: SDK and nrfx sources compile separately in
each firmware's context. The Controller/MPSL archives remain imported static
libraries. PRS is carried automatically by serial-driver dependencies; consumers
do not need to select it separately. Linking `NrfKit::rram` does not implicitly choose a Controller variant.

A consumer-owned INTERFACE library can collect capabilities for several images:

```cmake
add_library(wireless_features INTERFACE)
target_link_libraries(wireless_features INTERFACE
  NrfKit::sdc_multirole NrfKit::radio_timeslot)
target_link_libraries(app PRIVATE wireless_features)
```

Group these capabilities in INTERFACE libraries, not precompiled STATIC/OBJECT
libraries: a single compiled library cannot inherit different configuration from
multiple firmware executables. Compile reusable firmware sources through an
INTERFACE library when they depend on per-image SDK configuration.

Capability links must be configuration-independent. `BUILD_INTERFACE` and
`TARGET_NAME_IF_EXISTS` wrappers are supported. Arbitrary conditional expressions
that hide a capability, including through a bundle, are rejected; use an ordinary
CMake `if()` to select features before finalization. An `INSTALL_INTERFACE` edge
does not contribute build-tree compile usage requirements.

## Per-image configuration

`nrfkit_configure_target(target ...)` binds an executable to `SOC nrf54lm20a` and
`CORE cpuapp` (the default). Optional `BOARD nrf54lm20dk` adds SDK board headers. The supported
runtime is `freestanding`, also the default. Supply `LINKER_SCRIPT` and `IMAGE_LAYOUT` together to
use a consumer-owned memory layout; omit both for the SDK standalone layout.
Configure each executable exactly once.

`nrfkit_configure_usb(target ...)` supplies parameters without selecting a USB
capability. `SOURCE_DIR` chooses a compatible CherryUSB checkout; omission uses
the SDK's fixed input. `CLASSES hid` adds HID support to the complete-device target
and header access to the port target. `IN_ENDPOINT_MAX_PACKET_SIZES` describes
EP1 upward; omission retains the validated two-endpoint default. Configuration
validates packet sizes and FIFO capacity. These parameters belong to each image,
so app and bootloader can use different endpoint layouts.

`nrfkit_claim_resources(target OWNER name RESOURCES ...)` is an advanced interface
for declaring application-owned hardware resources. It rejects duplicate ownership
and invalid channel indices. SDC reserves its documented resources automatically.
It does not allocate peripherals or initialize hardware.

`nrfkit_finalize_target(target)` resolves the selected capabilities, checks
conflicts, generates that firmware's nrfx/USB configuration and reports, and
attaches ELF/HEX/BIN/map/layout artifacts. Finish capability selection and
configuration before this call. Runtime initialization remains application-owned;
link order does not replace SDC/MPSL lifecycle requirements.

Capability selection uses `target_link_libraries`; the earlier `nrfkit_enable_*`
functions have been removed. Names beginning `_nrfkit_`, raw
archive plumbing, and generated configuration paths are implementation details.
