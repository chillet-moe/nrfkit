# Consumer CMake API

`find_package(NrfKit CONFIG REQUIRED)` supplies ordinary targets in both source
and installed packages. Link the capabilities you need. Configuration is offline;
there is no firmware configure/finalize function or deferred graph traversal.

```cmake
add_executable(firmware main.cpp)
target_link_libraries(firmware PRIVATE
  NrfKit::runtime_freestanding NrfKit::board_nrf54lm20dk
  NrfKit::nrfx_gpio)
target_compile_definitions(firmware PRIVATE __STACK_SIZE=0x4000 __HEAP_SIZE=0)
set(linker_script "${CMAKE_CURRENT_SOURCE_DIR}/image/application.ld")
target_link_options(firmware PRIVATE "LINKER:-T,${linker_script}")
set_property(TARGET firmware APPEND PROPERTY LINK_DEPENDS "${linker_script}")
```

## Capability targets

| Target | Contents and requirements |
| --- | --- |
| `NrfKit::core` | Public SDK headers; usable without a firmware runtime. |
| `NrfKit::soc_nrf54lm20a` | Chip macros, CMSIS/MDK headers, SystemInit, Cortex-M33 and hard-float ABI requirements. |
| `NrfKit::startup` | Official LM20 startup and the SoC target; consumer supplies runtime entry conventions. |
| `NrfKit::runtime_freestanding` | Optional minimal runtime, fault/reset support and startup; no application linker layout. |
| `NrfKit::board_nrf54lm20dk` | DK headers and the SoC target. |
| `NrfKit::nrfx_<driver>` | Selected nrfx driver and its source dependencies. |
| `NrfKit::sdc_multirole` | Multirole Controller, SDK platform/HCI implementation, and locked MPSL/FEM dependencies. |
| `NrfKit::sdc_peripheral` | Peripheral-only version of the same integration. |
| `NrfKit::sdc_central` | Central-only version of the same integration. |
| `NrfKit::radio_direct` | Exclusive RADIO backend and nrfx CLOCK; incompatible with SDC. |
| `NrfKit::radio_timeslot` | RADIO backend under MPSL Timeslot scheduling; requires one SDC variant. |
| `NrfKit::rram` | Asynchronous RRAM writes scheduled by MPSL; requires one SDC variant. |
| `NrfKit::usb_port` | Optional built-in LM20 CherryUSB port. Consumer provides core/classes, configuration and clock-mode selection, or links a maintained local port instead. |

Supported nrfx driver names are `clock`, `power`, `gpio`, `gpiote`, `grtc`, `timer`, `dppi`,
`uarte`, `spim`, `twim`, `pwm`, `saadc`, `rramc`, `watchdog`, `reset`, `retention`,
and `cracen`. Driver names select source components, not peripheral instances.
Select at most one SDC variant. USB port/core/class selection belongs to the
consumer; see the [USB support notes](../../src/usb/README.md).

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

SDK source targets compile in each consuming target's context. Use INTERFACE
libraries for source bundles that must share each firmware's configuration.
A STATIC/OBJECT library has its own compilation context; executable-private
options do not configure already compiled sources. Standard CMake conditional
links and generator expressions retain their native meaning.

## Consumer policy and configuration

The consumer owns MEMORY/SECTIONS, stack/heap sizes, optimization, language
policy (exceptions/RTTI), section garbage collection, map files, output suffixes,
and conversion to HEX/BIN. `runtime_freestanding` supplies `-ffreestanding`,
`-nostdlib`, its entry-point definitions and minimal compiler-runtime closure.
It does not provide a hosted C++ runtime. The SoC target supplies ABI requirements,
not an image layout. Use the startup target alone when providing another runtime.

The SDK runtime's static linker assertions validate the startup ABI, vector size
and alignment, copy/zero ranges, conservative physical RAM/RRAM and stack overlap.
Consumer assertions enforce product-specific boot, settings and scratch boundaries.
A layout JSON is not a build input. Only the explicitly invoked guarded hardware
workflow requires a reviewed allowlist, supplied with `sdk manifest --image-layout`
or from the SDK example artifacts; it continues to reject forbidden regions.

nrfx driver targets supply enable definitions and share an overridable default
`nrfx_config.h`; instance and IRQ options can be target-scoped compile definitions.
No generated per-firmware header or capability graph is needed. Resource claims
remain explicit through `nrfkit_claim_resources(target OWNER name RESOURCES ...)`;
the target must be an executable. Calls accumulate application reservations,
which are combined with the selected SDC's documented masks. Ownership, variant,
RADIO and CLOCK conflicts fail during CMake generation; a missing SDC dependency
for Timeslot/RRAM fails compilation. Claims do not initialize peripherals.
See the implementation notes for conflict checks and reservation behavior.

SDK examples explicitly include `examples/common/firmware.cmake` for their own
standalone layout and artifacts. It is a validation-fixture helper, not a public
application API. USB configuration likewise stays with the consumer.

Names beginning `_nrfkit_`, raw archive targets and prepared-cache paths are private.
