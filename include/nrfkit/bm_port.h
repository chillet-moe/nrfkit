// SPDX-License-Identifier: BSD-3-Clause

#ifndef NRFKIT_BM_PORT_H
#define NRFKIT_BM_PORT_H

/*
 * Small freestanding primitives used by the version-locked nRF Bare Metal
 * modules.  The prepared vendor view replaces Zephyr includes with this file;
 * no Zephyr header, generated configuration, symbol, or runtime is consumed.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <nrf.h>
#include <nrfkit/runtime.h>

#ifndef EPERM
#define EPERM 1
#define ENOENT 2
#define EIO 5
#define ENOMEM 12
#define EFAULT 14
#define EBUSY 16
#define EEXIST 17
#define EINVAL 22
#define ENOSPC 28
#define ENOEXEC 8
#define ENOTSUP 134
#define EALREADY 114
#define EINPROGRESS 115
#define ETIMEDOUT 116
#endif

#define __aligned(value) __attribute__((aligned(value)))
#ifndef __ALIGN
#define __ALIGN(value) __aligned(value)
#endif
#define __packed __attribute__((packed))
#define __weak __attribute__((weak))
#define __fallthrough __attribute__((fallthrough))
#define ARG_UNUSED(value) ((void)(value))

#define BIT(number) (1UL << (number))
#define BITS_PER_BYTE 8U
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define SIZEOF_FIELD(type, member) sizeof(((type *)0)->member)
#define CONTAINER_OF(pointer, type, member) \
	((type *)((char *)(pointer) - offsetof(type, member)))
#define MIN(left, right) ((left) < (right) ? (left) : (right))
#define MAX(left, right) ((left) > (right) ? (left) : (right))
#define CLAMP(value, low, high) MIN(MAX((value), (low)), (high))
#define ROUND_UP(value, alignment) \
	(((value) + (alignment) - 1U) & ~((alignment) - 1U))
#define ROUND_DOWN(value, alignment) ((value) & ~((alignment) - 1U))
#define IS_ALIGNED(value, alignment) (((uintptr_t)(value) & ((alignment) - 1U)) == 0U)
#define UINT_TO_POINTER(value) ((void *)(uintptr_t)(value))
#define STRINGIFY(value) _NRFKIT_BM_STRINGIFY(value)

#define GENMASK(high, low) \
	(((~0UL) - (1UL << (low)) + 1UL) & (~0UL >> (31U - (high))))
#define GENMASK64(high, low) \
	(((~0ULL) - (1ULL << (low)) + 1ULL) & (~0ULL >> (63U - (high))))
#define __NRFKIT_BM_CTZ(mask) __builtin_ctzll((unsigned long long)(mask))
#define FIELD_GET(mask, value) (((value) & (mask)) >> __NRFKIT_BM_CTZ(mask))
#define FIELD_PREP(mask, value) (((value) << __NRFKIT_BM_CTZ(mask)) & (mask))

#define BUILD_ASSERT(condition, ...) _Static_assert(condition, #condition)
#define __ASSERT(condition, ...) \
	do { if (!(condition)) { nrfkit_assert_fail(); } } while (false)
#define __ASSERT_NO_MSG(condition) __ASSERT(condition)

/* Treat undefined configuration tokens as disabled, matching Kconfig callers. */
#define _NRFKIT_BM_ENABLED_1 _nrfkit_bm_enabled,
#define _NRFKIT_BM_ENABLED_STEP1(value) _NRFKIT_BM_ENABLED_STEP2(_NRFKIT_BM_ENABLED_##value)
#define _NRFKIT_BM_ENABLED_STEP2(value) _NRFKIT_BM_ENABLED_STEP3(value 1, 0)
#define _NRFKIT_BM_ENABLED_STEP3(ignore, result, ...) result
#define IS_ENABLED(value) _NRFKIT_BM_ENABLED_STEP1(value)
#define _NRFKIT_BM_DEBRACKET(...) __VA_ARGS__
#define _NRFKIT_BM_COND_0(if_true, if_false) _NRFKIT_BM_DEBRACKET if_false
#define _NRFKIT_BM_COND_1(if_true, if_false) _NRFKIT_BM_DEBRACKET if_true
#define _NRFKIT_BM_COND_SELECT(value) _NRFKIT_BM_COND_##value
#define _NRFKIT_BM_COND_EXPAND(value) _NRFKIT_BM_COND_SELECT(value)
#define COND_CODE_1(value, if_true, if_false) \
	_NRFKIT_BM_COND_EXPAND(IS_ENABLED(value))(if_true, if_false)
#define _NRFKIT_BM_FIRST(first, ...) first
#define IS_EMPTY(...) _NRFKIT_BM_FIRST(__VA_OPT__(0,) 1)

#define H_NRF_SDH_OBSERVER_PRIO_HIGHEST_HIGH 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGHEST_USER 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGHEST_USER_LOW 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGHEST_LOWEST 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGH_HIGHEST 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGH_USER 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGH_USER_LOW 0
#define H_NRF_SDH_OBSERVER_PRIO_HIGH_LOWEST 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_HIGHEST 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_HIGH 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_USER_LOW 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_LOWEST 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_LOW_HIGHEST 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_LOW_HIGH 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_LOW_USER 0
#define H_NRF_SDH_OBSERVER_PRIO_USER_LOW_LOWEST 0
#define H_NRF_SDH_OBSERVER_PRIO_LOWEST_HIGHEST 0
#define H_NRF_SDH_OBSERVER_PRIO_LOWEST_HIGH 0
#define H_NRF_SDH_OBSERVER_PRIO_LOWEST_USER 0
#define H_NRF_SDH_OBSERVER_PRIO_LOWEST_USER_LOW 0
#define NRFKIT_BM_PRIO_HIGHEST 0
#define NRFKIT_BM_PRIO_HIGH 1
#define NRFKIT_BM_PRIO_USER 2
#define NRFKIT_BM_PRIO_USER_LOW 3
#define NRFKIT_BM_PRIO_LOWEST 4
#define _NRFKIT_BM_PRIO_INNER(value) NRFKIT_BM_PRIO_##value
#define NRFKIT_BM_PRIO(value) _NRFKIT_BM_PRIO_INNER(value)

#define LOG_MODULE_REGISTER(...)
#define LOG_MODULE_DECLARE(...)
#define LOG_DBG(...) ((void)0)
#define LOG_INF(...) nrfkit_bm_log(__VA_ARGS__)
#define LOG_WRN(...) nrfkit_bm_log(__VA_ARGS__)
#define LOG_ERR(...) nrfkit_bm_log(__VA_ARGS__)
#define log_panic() ((void)0)
#define log_flush() ((void)0)
#define printk(...) (0)
#define snprintk(...) (0)

int sprintf(char *buffer, const char *format, ...);
int snprintf(char *buffer, size_t size, const char *format, ...);
void nrfkit_bm_log(const char *format, ...);

#define APPLICATION 0
#define IRQ_ZERO_LATENCY 1U
#define GRTC_IRQn GRTC_2_IRQn
#define ISR_DIRECT_DECLARE(name) int name(void)
#define BM_IRQ_DIRECT_CONNECT(irqn, priority, handler, flags) \
	do { \
		(void)(handler); \
		(void)(flags); \
		NVIC_SetPriority((irqn), (priority)); \
		NVIC_EnableIRQ((irqn)); \
	} while (false)
#define BM_IRQ_SET_PRIORITY(irqn, priority) NVIC_SetPriority((irqn), (priority))
#define irq_enable(irqn) NVIC_EnableIRQ((irqn))
#define _NRFKIT_BM_SYS_INIT_NAME_INNER(function) nrfkit_sys_init_##function
#define _NRFKIT_BM_SYS_INIT_NAME(function) _NRFKIT_BM_SYS_INIT_NAME_INNER(function)
#define SYS_INIT(function, level, priority) \
	static void _NRFKIT_BM_SYS_INIT_NAME(function)(void) __attribute__((constructor)); \
	static void _NRFKIT_BM_SYS_INIT_NAME(function)(void) { (void)function(); }

int nrfkit_nrf_bm_irq_init(void);

typedef struct {
	int64_t ticks;
} k_timeout_t;

struct k_timer {
	void (*expiry)(struct k_timer *timer);
	void *user_data;
	uint32_t period_ticks;
	bool active;
};

#define K_NO_WAIT ((k_timeout_t){ .ticks = 0 })
#define k_us_to_ticks_floor32(us) ((uint32_t)(((uint64_t)(us) * 31250U) / 1000000U))
#define k_us_to_ticks_ceil32(us) ((uint32_t)((((uint64_t)(us) * 31250U) + 999999U) / 1000000U))
#define k_ms_to_ticks_floor32(ms) ((uint32_t)(((uint64_t)(ms) * 31250U) / 1000U))
#define k_ticks_to_us_ceil32(ticks) \
	((uint32_t)((((uint64_t)(ticks) * 1000000U) + 31249U) / 31250U))

void k_timer_init(struct k_timer *timer, void (*expiry)(struct k_timer *),
		  void (*stop)(struct k_timer *));
void k_timer_start(struct k_timer *timer, k_timeout_t duration, k_timeout_t period);
void k_timer_stop(struct k_timer *timer);
void k_timer_user_data_set(struct k_timer *timer, void *user_data);
void *k_timer_user_data_get(const struct k_timer *timer);

#define FIXED_PARTITION_OFFSET(partition) 0x001E3800UL
#define NRFKIT_DT_CHOSEN_zephyr_sram nrfkit_application_sram
#define NRFKIT_DT_NODELABEL_cpuapp_sram nrfkit_softdevice_sram
#define NRFKIT_DT_NODELABEL_peer_manager_partition nrfkit_peer_manager_storage
#define DT_CHOSEN(node) NRFKIT_DT_CHOSEN_##node
#define DT_NODELABEL(node) NRFKIT_DT_NODELABEL_##node
#define NRFKIT_DT_REG_ADDR_nrfkit_application_sram 0x20004400UL
#define NRFKIT_DT_REG_ADDR_nrfkit_softdevice_sram 0x20000080UL
#define NRFKIT_DT_REG_ADDR_nrfkit_peer_manager_storage 0x001E1800UL
#define NRFKIT_DT_REG_SIZE_nrfkit_peer_manager_storage 0x00002000UL
#define _NRFKIT_DT_REG_ADDR(node) NRFKIT_DT_REG_ADDR_##node
#define NRFKIT_DT_REG_ADDR(node) _NRFKIT_DT_REG_ADDR(node)
#define _NRFKIT_DT_REG_SIZE(node) NRFKIT_DT_REG_SIZE_##node
#define NRFKIT_DT_REG_SIZE(node) _NRFKIT_DT_REG_SIZE(node)
#define DT_REG_ADDR(node) NRFKIT_DT_REG_ADDR(node)
#define DT_REG_SIZE(node) NRFKIT_DT_REG_SIZE(node)

typedef uint32_t atomic_t;
typedef uint32_t atomic_val_t;
#define ATOMIC_INIT(value) (value)
#define ATOMIC_BITS (sizeof(atomic_t) * BITS_PER_BYTE)
#define ATOMIC_BITMAP_SIZE(number_of_bits) \
	(((number_of_bits) + ATOMIC_BITS - 1U) / ATOMIC_BITS)
#define ATOMIC_DEFINE(name, number_of_bits) \
	atomic_t name[ATOMIC_BITMAP_SIZE(number_of_bits)]

static inline atomic_val_t atomic_get(const atomic_t *target)
{
	return __atomic_load_n(target, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_set(atomic_t *target, atomic_val_t value)
{
	return __atomic_exchange_n(target, value, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_add(atomic_t *target, atomic_val_t value)
{
	return __atomic_fetch_add(target, value, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_sub(atomic_t *target, atomic_val_t value)
{
	return __atomic_fetch_sub(target, value, __ATOMIC_SEQ_CST);
}

static inline atomic_val_t atomic_inc(atomic_t *target)
{
	return atomic_add(target, 1U);
}

static inline atomic_val_t atomic_dec(atomic_t *target)
{
	return atomic_sub(target, 1U);
}

static inline atomic_val_t atomic_and(atomic_t *target, atomic_val_t value)
{
	return __atomic_fetch_and(target, value, __ATOMIC_SEQ_CST);
}

static inline void atomic_set_bit(atomic_t *target, unsigned int bit)
{
	atomic_t *word = &target[bit / ATOMIC_BITS];
	(void)__atomic_fetch_or(word, BIT(bit % ATOMIC_BITS), __ATOMIC_SEQ_CST);
}

static inline bool atomic_cas(atomic_t *target, atomic_val_t old_value,
			      atomic_val_t new_value)
{
	return __atomic_compare_exchange_n(target, &old_value, new_value, false,
					   __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST);
}

static inline bool atomic_test_bit(const atomic_t *target, unsigned int bit)
{
	const atomic_t *word = &target[bit / ATOMIC_BITS];
	return (atomic_get(word) & BIT(bit % ATOMIC_BITS)) != 0U;
}

static inline bool atomic_test_and_set_bit(atomic_t *target, unsigned int bit)
{
	atomic_t *word = &target[bit / ATOMIC_BITS];
	const atomic_t mask = BIT(bit % ATOMIC_BITS);
	return (__atomic_fetch_or(word, mask, __ATOMIC_SEQ_CST) & mask) != 0U;
}

static inline void atomic_clear_bit(atomic_t *target, unsigned int bit)
{
	atomic_t *word = &target[bit / ATOMIC_BITS];
	(void)__atomic_fetch_and(word, ~BIT(bit % ATOMIC_BITS), __ATOMIC_SEQ_CST);
}

static inline void k_cpu_idle(void)
{
	__WFE();
}

static inline unsigned int irq_lock(void)
{
	const unsigned int key = __get_PRIMASK();
	__disable_irq();
	return key;
}

static inline void irq_unlock(unsigned int key)
{
	if (key == 0U) {
		__enable_irq();
	}
}

struct ring_buf {
	uint8_t *buffer;
	size_t size;
	size_t head;
	size_t tail;
	size_t used;
};

#define RING_BUF_DECLARE(name, capacity) \
	static uint8_t name##_storage[(capacity)]; \
	static struct ring_buf name = { .buffer = name##_storage, .size = (capacity) }

size_t ring_buf_put(struct ring_buf *ring, const uint8_t *data, size_t length);
size_t ring_buf_get(struct ring_buf *ring, uint8_t *data, size_t length);

static inline void sys_memcpy_swap(void *destination, const void *source, size_t length)
{
	uint8_t *out = destination;
	const uint8_t *in = source;
	for (size_t index = 0; index < length; ++index) {
		out[index] = in[length - index - 1U];
	}
}

static inline void sys_mem_swap(void *data, size_t length)
{
	uint8_t *bytes = data;
	for (size_t index = 0; index < length / 2U; ++index) {
		const uint8_t value = bytes[index];
		bytes[index] = bytes[length - index - 1U];
		bytes[length - index - 1U] = value;
	}
}

static inline void sys_put_le16(uint16_t value, uint8_t *destination)
{
	destination[0] = (uint8_t)value;
	destination[1] = (uint8_t)(value >> 8U);
}

static inline uint16_t sys_get_le16(const uint8_t *source)
{
	return (uint16_t)source[0] | ((uint16_t)source[1] << 8U);
}

static inline void sys_uint64_to_array(uint64_t value, uint8_t *destination)
{
	for (size_t index = 0; index < sizeof(value); ++index) {
		destination[index] = (uint8_t)(value >> (index * 8U));
	}
}

uint8_t crc8(const uint8_t *data, size_t length, uint8_t polynomial,
	     uint8_t initial_value, bool reversed);
uint32_t crc32_ieee(const uint8_t *data, size_t length);

static inline uint8_t crc8_ccitt(uint8_t initial_value, const void *data,
				 size_t length)
{
	return crc8(data, length, 0x07U, initial_value, false);
}

#define _NRFKIT_BM_STRINGIFY_INNER(value) #value
#define _NRFKIT_BM_STRINGIFY(value) _NRFKIT_BM_STRINGIFY_INNER(value)
#define _NRFKIT_BM_SECTION_NAME(section_name, priority) \
	"nrfkit_" #section_name "." _NRFKIT_BM_STRINGIFY(priority)
#define TYPE_SECTION_ITERABLE(type, variable, section_name, priority) \
	type variable __attribute__((used, section(_NRFKIT_BM_SECTION_NAME(section_name, priority))))
#define _NRFKIT_BM_SECTION_START(section_name) __start_nrfkit_##section_name
#define _NRFKIT_BM_SECTION_END(section_name) __stop_nrfkit_##section_name
#define TYPE_SECTION_FOREACH(type, section_name, iterator) \
	for (type *iterator = (type *)(void *)_NRFKIT_BM_SECTION_START(section_name); \
	     iterator < (type *)(void *)_NRFKIT_BM_SECTION_END(section_name); ++iterator)

extern char __start_nrfkit_nrf_sdh_state_evt_observers[];
extern char __stop_nrfkit_nrf_sdh_state_evt_observers[];
extern char __start_nrfkit_nrf_sdh_stack_evt_observers[];
extern char __stop_nrfkit_nrf_sdh_stack_evt_observers[];
extern char __start_nrfkit_nrf_sdh_ble_evt_observers[];
extern char __stop_nrfkit_nrf_sdh_ble_evt_observers[];
extern char __start_nrfkit_nrf_sdh_soc_evt_observers[];
extern char __stop_nrfkit_nrf_sdh_soc_evt_observers[];

#endif
