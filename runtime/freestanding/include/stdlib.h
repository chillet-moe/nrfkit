/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_FREESTANDING_STDLIB_H
#define NRFKIT_FREESTANDING_STDLIB_H

/*
 * Freestanding targets intentionally provide no heap. This header exists so
 * libraries whose allocation-dependent features are disabled can include the
 * standard name without pulling in a hosted C library.
 */

#endif
