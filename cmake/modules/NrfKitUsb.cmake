# SPDX-License-Identifier: BSD-3-Clause

include_guard(GLOBAL)

# The built-in port is optional. A consumer with a maintained port links its own
# target instead; core/class sources, usb_config.h, and clock-mode selection stay
# with that consumer in either case.
add_library(NrfKit::usb_port INTERFACE IMPORTED GLOBAL)
set_target_properties(NrfKit::usb_port PROPERTIES SYSTEM FALSE)
target_sources(NrfKit::usb_port INTERFACE
  "${NrfKit_ROOT}/src/usb/nrf54l/usb_dc.c"
  "${NrfKit_ROOT}/src/usb/nrf54l/usb_glue_dwc2.c")
target_link_libraries(NrfKit::usb_port INTERFACE NrfKit::core NrfKit::nrfx_gpio)
