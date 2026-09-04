// SPDX-License-Identifier: BSD-3-Clause

#include <nrfkit/bm_port.h>

/*
 * The MDK vector table names this slot CLOCK_POWER_IRQHandler, while the
 * version-locked nRF-BM forwarding layer intentionally uses
 * CLOCK_POWER_SD_IRQHandler and binds it dynamically under Zephyr.
 */
extern void CLOCK_POWER_SD_IRQHandler(void);

void CLOCK_POWER_IRQHandler(void)
{
	CLOCK_POWER_SD_IRQHandler();
}

int snprintf(char *buffer, size_t size, const char *format, ...)
{
	(void)format;
	if (size != 0U) {
		buffer[0] = '\0';
	}
	return 0;
}

int sprintf(char *buffer, const char *format, ...)
{
	(void)format;
	buffer[0] = '\0';
	return 0;
}

size_t ring_buf_put(struct ring_buf *ring, const uint8_t *data, size_t length)
{
	const size_t count = MIN(length, ring->size - ring->used);
	for (size_t index = 0; index < count; ++index) {
		ring->buffer[ring->head] = data[index];
		ring->head = (ring->head + 1U) % ring->size;
	}
	ring->used += count;
	return count;
}

size_t ring_buf_get(struct ring_buf *ring, uint8_t *data, size_t length)
{
	const size_t count = MIN(length, ring->used);
	for (size_t index = 0; index < count; ++index) {
		data[index] = ring->buffer[ring->tail];
		ring->tail = (ring->tail + 1U) % ring->size;
	}
	ring->used -= count;
	return count;
}

uint8_t crc8(const uint8_t *data, size_t length, uint8_t polynomial,
	     uint8_t initial_value, bool reversed)
{
	uint8_t value = initial_value;
	for (size_t index = 0; index < length; ++index) {
		value ^= data[index];
		for (unsigned int bit = 0; bit < 8U; ++bit) {
			if (reversed) {
				value = (value & 1U) != 0U
					? (uint8_t)((value >> 1U) ^ polynomial)
					: (uint8_t)(value >> 1U);
			} else {
				value = (value & 0x80U) != 0U
					? (uint8_t)((value << 1U) ^ polynomial)
					: (uint8_t)(value << 1U);
			}
		}
	}
	return value;
}

uint32_t crc32_ieee(const uint8_t *data, size_t length)
{
	uint32_t value = UINT32_MAX;
	for (size_t index = 0; index < length; ++index) {
		value ^= data[index];
		for (unsigned int bit = 0; bit < 8U; ++bit) {
			const uint32_t mask = 0U - (value & 1U);
			value = (value >> 1U) ^ (0xEDB88320U & mask);
		}
	}
	return ~value;
}
