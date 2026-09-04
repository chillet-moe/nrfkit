/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_USBHS_H
#define NRFKIT_USBHS_H

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

enum nrfkit_usbhs_result {
    NRFKIT_USBHS_OK = 0,
    NRFKIT_USBHS_ERR_CLOCK_TIMEOUT = -2,
    NRFKIT_USBHS_ERR_STATE = -4,
};

/* Request connection now or on the next documented VBUS-detected event. */
int nrfkit_usbhs_connect(void);
bool nrfkit_usbhs_vbus_present(void);
int nrfkit_usbhs_last_result(void);

#ifdef __cplusplus
}
#endif

#endif
