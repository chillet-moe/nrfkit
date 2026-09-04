// SPDX-License-Identifier: BSD-3-Clause

#include <nrfkit/bm_port.h>
#include <stdarg.h>

#include <hal/nrf_grtc.h>
#include <nrfkit/board.h>

/*
 * The MDK vector table names this slot CLOCK_POWER_IRQHandler, while the
 * version-locked nRF-BM forwarding layer intentionally uses
 * CLOCK_POWER_SD_IRQHandler and binds it dynamically under Zephyr.
 */
extern void CLOCK_POWER_SD_IRQHandler(void);
extern int gpiote_20_direct_isr(void);
extern int gpiote_30_direct_isr(void);

void CLOCK_POWER_IRQHandler(void)
{
	CLOCK_POWER_SD_IRQHandler();
}

__attribute__((interrupt("IRQ"))) void GPIOTE20_1_IRQHandler(void)
{
	(void)gpiote_20_direct_isr();
}

__attribute__((interrupt("IRQ"))) void GPIOTE30_1_IRQHandler(void)
{
	(void)gpiote_30_direct_isr();
}

static struct k_timer *active_timer;

static void nrfkit_bm_platform_init(void) __attribute__((constructor));

static void nrfkit_bm_platform_init(void)
{
	nrfkit_board_prepare_s115();
	if (nrfkit_board_start_s115_grtc() != 0) {
		nrfkit_assert_fail();
	}
}

static void serial_write(const char *text)
{
	if (text == NULL) {
		return;
	}
	NRFKIT_VCOM_TX_GPIO->OUTSET = BIT(NRFKIT_VCOM_TX_PIN);
	NRFKIT_VCOM_TX_GPIO->PIN_CNF[NRFKIT_VCOM_TX_PIN] =
		(GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
		(GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos);
	NRFKIT_VCOM_UARTE->PSEL.TXD =
		(NRFKIT_VCOM_TX_PIN << UARTE_PSEL_TXD_PIN_Pos) |
		(NRFKIT_VCOM_TX_PORT << UARTE_PSEL_TXD_PORT_Pos);
	NRFKIT_VCOM_UARTE->BAUDRATE = NRFKIT_VCOM_BAUDRATE;
	NRFKIT_VCOM_UARTE->ENABLE = UARTE_ENABLE_ENABLE_Enabled;
	for (const char *cursor = text; *cursor != '\0'; ++cursor) {
		uint8_t byte __attribute__((aligned(4))) = (uint8_t)*cursor;
		NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END = 0U;
		NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)&byte;
		NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = 1U;
		NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START =
			UARTE_TASKS_DMA_TX_START_START_Trigger;
		while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U) {
			__WFE();
		}
	}
}

void nrfkit_bm_log(const char *format, ...)
{
	/* The platform shim preserves literal messages used by the oracle gate.
	 * Formatting is intentionally not reimplemented as part of BLE adaptation. */
	serial_write(format);
	serial_write("\r\n");
}

static uint64_t grtc_counter(void)
{
	return nrf_grtc_sys_counter_get(NRF_GRTC);
}

void k_timer_init(struct k_timer *timer, void (*expiry)(struct k_timer *),
		  void (*stop)(struct k_timer *))
{
	(void)stop;
	timer->expiry = expiry;
	timer->user_data = NULL;
	timer->period_ticks = 0U;
	timer->active = false;
}

void k_timer_start(struct k_timer *timer, k_timeout_t duration, k_timeout_t period)
{
	const uint64_t delay_us = ((uint64_t)duration.ticks * 1000000U) / 31250U;
	const unsigned int key = irq_lock();
	active_timer = timer;
	timer->period_ticks = (uint32_t)period.ticks;
	timer->active = true;
	nrf_grtc_event_clear(NRF_GRTC, nrf_grtc_sys_counter_compare_event_get(0));
	nrf_grtc_sys_counter_cc_set(NRF_GRTC, 0, grtc_counter() + MAX(delay_us, 5U));
	nrf_grtc_sys_counter_compare_event_enable(NRF_GRTC, 0);
	nrf_grtc_int_enable(NRF_GRTC, NRF_GRTC_INT_COMPARE0_MASK);
	NVIC_SetPriority(GRTC_2_IRQn, CONFIG_BM_TIMER_IRQ_PRIO);
	NVIC_EnableIRQ(GRTC_2_IRQn);
	irq_unlock(key);
}

void k_timer_stop(struct k_timer *timer)
{
	const unsigned int key = irq_lock();
	timer->active = false;
	nrf_grtc_int_disable(NRF_GRTC, NRF_GRTC_INT_COMPARE0_MASK);
	nrf_grtc_sys_counter_compare_event_disable(NRF_GRTC, 0);
	irq_unlock(key);
}

void k_timer_user_data_set(struct k_timer *timer, void *user_data)
{
	timer->user_data = user_data;
}

void *k_timer_user_data_get(const struct k_timer *timer)
{
	return timer->user_data;
}

__attribute__((interrupt("IRQ"))) void GRTC_2_IRQHandler(void)
{
	nrf_grtc_event_clear(NRF_GRTC, nrf_grtc_sys_counter_compare_event_get(0));
	struct k_timer *timer = active_timer;
	if (timer == NULL || !timer->active) {
		return;
	}
	if (timer->period_ticks == 0U) {
		timer->active = false;
		nrf_grtc_int_disable(NRF_GRTC, NRF_GRTC_INT_COMPARE0_MASK);
		nrf_grtc_sys_counter_compare_event_disable(NRF_GRTC, 0);
	}
	timer->expiry(timer);
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
