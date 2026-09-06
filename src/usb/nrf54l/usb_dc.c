/* SPDX-License-Identifier: BSD-3-Clause */

/* Compile the immutable upstream DCD through a thin initialization wrapper.
 * PHY attachment must follow FIFO/core initialization, not low_level_init.
 */
#define usb_dc_init nrfkit_dwc2_init
#include "usb_dc_dwc2.c"
#undef usb_dc_init

#include <nrfkit/usbhs.h>

int usb_dc_init(uint8_t busid)
{
    int result = nrfkit_dwc2_init(busid);
    if (result == 0) {
        result = nrfkit_usbhs_connect();
    }
    if (result != 0) {
        usb_dc_deinit(busid);
    }
    return result;
}
