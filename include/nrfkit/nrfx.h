/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_NRFX_H
#define NRFKIT_NRFX_H

#ifdef __cplusplus
extern "C" {
#endif

/** Initialize nrfx GPPI with all unreserved LM20A D2PPI channels and groups. */
void nrfkit_gppi_init(void);

#ifdef __cplusplus
}
#endif

#endif
