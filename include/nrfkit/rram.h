/* SPDX-License-Identifier: BSD-3-Clause */
#ifndef NRFKIT_RRAM_H
#define NRFKIT_RRAM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Caller-declared writable application region; configuration memory is never
 * accepted. The consumer supplies its linker-owned settings bounds.
 */
struct nrfkit_rram_region { uint32_t origin; uint32_t length; };

#define NRFKIT_RRAM_MAX_WRITE 256U

/** Copy and submit one 16-byte-aligned write of 16..256 bytes. Requires active
 * MPSL; does not disable SDC or interrupt USB. Returns -NRF_EAGAIN until the
 * previous transaction has fully closed its session. Main context only.
 */
int32_t nrfkit_rram_submit(const struct nrfkit_rram_region *region,
                          uint32_t address, const void *data, size_t size);
/** Call alongside nrfkit_sdc_process from serialized main context. */
void nrfkit_rram_process(void);
/** -NRF_EINPROGRESS while pending, zero on verified completion, or a negative
 * error. On failure some preceding data units may have been written. The
 * caller retains its dirty state and owns record-level atomicity/retry policy.
 */
int32_t nrfkit_rram_result(void);

#ifdef __cplusplus
}
#endif
#endif
