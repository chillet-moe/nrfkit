/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_NRFX_LOG_H
#define NRFKIT_NRFX_LOG_H

#define NRFX_LOG_ERROR(...) ((void)0)
#define NRFX_LOG_WARNING(...) ((void)0)
#define NRFX_LOG_INFO(...) ((void)0)
#define NRFX_LOG_DEBUG(...) ((void)0)
#define NRFX_LOG_HEXDUMP_ERROR(p_memory, length) ((void)(p_memory), (void)(length))
#define NRFX_LOG_HEXDUMP_WARNING(p_memory, length) ((void)(p_memory), (void)(length))
#define NRFX_LOG_HEXDUMP_INFO(p_memory, length) ((void)(p_memory), (void)(length))
#define NRFX_LOG_HEXDUMP_DEBUG(p_memory, length) ((void)(p_memory), (void)(length))
#define NRFX_LOG_ERROR_STRING_GET(error_code) "nrfx error"

#endif
