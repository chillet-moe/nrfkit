/* SPDX-License-Identifier: BSD-3-Clause */
#include <nrfx.h>
_Static_assert(NRFKIT_DPPI20_CHANNELS_RESERVED == EXPECTED_CHANNELS,
               "application and SDC channels must be combined per firmware");
_Static_assert(NRFKIT_DPPI20_GROUPS_RESERVED == EXPECTED_GROUPS,
               "later claims must preserve earlier reservations");
_Static_assert(NRFX_GPIOTE20_CHANNELS_USED == EXPECTED_GPIOTE,
               "GPIOTE allocation must honor application ownership");
_Static_assert(NRFX_DEFAULT_IRQ_PRIORITY == EXPECTED_PRIORITY,
               "consumer priority override must remain target scoped");
