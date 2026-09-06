// SPDX-License-Identifier: BSD-3-Clause

#include <stdbool.h>

bool nrfkit_usbhs_vbus_present(void)
{
    /* Consumer replacement sentinel: the SDK DCD must not enter this image. */
    return true;
}
