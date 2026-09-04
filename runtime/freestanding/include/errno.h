/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_FREESTANDING_ERRNO_H
#define NRFKIT_FREESTANDING_ERRNO_H

/* Values follow the Arm embedded C library ABI used by nrfx return codes. */
#define EPERM 1
#define E2BIG 7
#define EAGAIN 11
#define ENOMEM 12
#define EACCES 13
#define EFAULT 14
#define EBUSY 16
#define EINVAL 22
#define EALREADY 114
#define EINPROGRESS 115
#define ETIMEDOUT 116
#define ENOTSUP 134
#define EOVERFLOW 139
#define ECANCELED 140

#endif
