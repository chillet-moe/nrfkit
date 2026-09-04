// SPDX-License-Identifier: BSD-3-Clause

#ifndef NRFKIT_BM_CRYPTO_H
#define NRFKIT_BM_CRYPTO_H

/* Minimal PSA-shaped adapter required by the locked nRF-BM LESC module. */

#include <stddef.h>
#include <stdint.h>

typedef int32_t psa_status_t;
typedef uint32_t psa_key_id_t;
typedef uint32_t psa_algorithm_t;

typedef struct {
	uint32_t usage;
	uint32_t algorithm;
	uint32_t type;
	uint32_t bits;
} psa_key_attributes_t;

#define PSA_SUCCESS 0
#define PSA_ERROR_INVALID_HANDLE (-136)
#define PSA_ERROR_BAD_STATE (-137)
#define PSA_ERROR_INVALID_ARGUMENT (-135)
#define PSA_ERROR_INSUFFICIENT_ENTROPY (-148)
#define PSA_KEY_ATTRIBUTES_INIT { 0 }
#define PSA_KEY_USAGE_DERIVE BIT(0)
#define PSA_KEY_USAGE_EXPORT BIT(1)
#define PSA_KEY_LIFETIME_VOLATILE 0U
#define PSA_ALG_ECDH 0x09020000U
#define PSA_ECC_FAMILY_SECP_R1 0x12U
#define PSA_KEY_TYPE_ECC_KEY_PAIR(family) (0x7100U | (family))
#define PSA_EXPORT_PUBLIC_KEY_OUTPUT_SIZE(type, bits) (1U + 2U * ((bits) / 8U))
#define PSA_EXPORT_KEY_OUTPUT_SIZE(type, bits) ((bits) / 8U)

static inline void psa_set_key_usage_flags(psa_key_attributes_t *attributes,
					   uint32_t usage)
{
	attributes->usage = usage;
}

static inline void psa_set_key_lifetime(psa_key_attributes_t *attributes,
					uint32_t lifetime)
{
	(void)attributes;
	(void)lifetime;
}

static inline void psa_set_key_algorithm(psa_key_attributes_t *attributes,
					 psa_algorithm_t algorithm)
{
	attributes->algorithm = algorithm;
}

static inline void psa_set_key_type(psa_key_attributes_t *attributes, uint32_t type)
{
	attributes->type = type;
}

static inline void psa_set_key_bits(psa_key_attributes_t *attributes, uint32_t bits)
{
	attributes->bits = bits;
}

psa_status_t psa_crypto_init(void);
psa_status_t psa_destroy_key(psa_key_id_t key);
psa_status_t psa_generate_key(const psa_key_attributes_t *attributes, psa_key_id_t *key);
psa_status_t psa_export_public_key(psa_key_id_t key, uint8_t *data, size_t data_size,
				   size_t *data_length);
psa_status_t psa_raw_key_agreement(psa_algorithm_t algorithm, psa_key_id_t key,
				   const uint8_t *peer_key, size_t peer_key_length,
				   uint8_t *output, size_t output_size,
				   size_t *output_length);

#endif
