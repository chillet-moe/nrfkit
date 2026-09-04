// SPDX-License-Identifier: BSD-3-Clause

#ifndef NRFKIT_CRACEN_PSA_SHIM_H
#define NRFKIT_CRACEN_PSA_SHIM_H

#include <nrfkit/bm_crypto.h>

psa_status_t cracen_get_trng(uint8_t *output, size_t output_size);

#endif
