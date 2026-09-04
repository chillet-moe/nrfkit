// SPDX-License-Identifier: BSD-3-Clause

#include <nrfkit/bm_port.h>
#include <nrfkit/bm_crypto.h>

#include <nrfx_cracen.h>
#include <ocrypto_ecdh_p256.h>

static uint8_t private_key[32] __aligned(4);
static uint8_t public_key[64] __aligned(4);
static bool key_available;

psa_status_t psa_crypto_init(void)
{
	return PSA_SUCCESS;
}

psa_status_t psa_destroy_key(psa_key_id_t key)
{
	if (key == 0U && !key_available) {
		return PSA_ERROR_INVALID_HANDLE;
	}
	memset(private_key, 0, sizeof(private_key));
	memset(public_key, 0, sizeof(public_key));
	key_available = false;
	return PSA_SUCCESS;
}

psa_status_t psa_generate_key(const psa_key_attributes_t *attributes, psa_key_id_t *key)
{
	if (attributes == NULL || key == NULL || attributes->algorithm != PSA_ALG_ECDH ||
	    attributes->type != PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_SECP_R1) ||
	    attributes->bits != 256U) {
		return PSA_ERROR_INVALID_ARGUMENT;
	}
	do {
		if (nrfx_cracen_entropy_get(private_key, sizeof(private_key)) != 0) {
			memset(private_key, 0, sizeof(private_key));
			return PSA_ERROR_INSUFFICIENT_ENTROPY;
		}
	} while (ocrypto_ecdh_p256_secret_key_check(private_key) != 0);
	if (ocrypto_ecdh_p256_public_key(public_key, private_key) != 0) {
		memset(private_key, 0, sizeof(private_key));
		return PSA_ERROR_BAD_STATE;
	}
	key_available = true;
	*key = 1U;
	return PSA_SUCCESS;
}

psa_status_t psa_export_public_key(psa_key_id_t key, uint8_t *data, size_t data_size,
				   size_t *data_length)
{
	if (key != 1U || !key_available || data == NULL || data_length == NULL ||
	    data_size < 65U) {
		return PSA_ERROR_INVALID_ARGUMENT;
	}
	data[0] = 0x04U;
	memcpy(&data[1], public_key, sizeof(public_key));
	*data_length = 65U;
	return PSA_SUCCESS;
}

psa_status_t psa_raw_key_agreement(psa_algorithm_t algorithm, psa_key_id_t key,
				   const uint8_t *peer_key, size_t peer_key_length,
				   uint8_t *output, size_t output_size,
				   size_t *output_length)
{
	if (algorithm != PSA_ALG_ECDH || key != 1U || !key_available ||
	    peer_key == NULL || peer_key_length != 65U || peer_key[0] != 0x04U ||
	    output == NULL || output_size < 32U || output_length == NULL) {
		return PSA_ERROR_INVALID_ARGUMENT;
	}
	if (ocrypto_ecdh_p256_public_key_check(&peer_key[1]) != 0 ||
	    ocrypto_ecdh_p256_common_secret(output, private_key, &peer_key[1]) != 0) {
		memset(output, 0, MIN(output_size, 32U));
		return PSA_ERROR_BAD_STATE;
	}
	*output_length = 32U;
	return PSA_SUCCESS;
}
