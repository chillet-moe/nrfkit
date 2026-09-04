/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <hal/nrf_grtc.h>
#include <hal/nrf_power.h>
#include <haly/nrfy_grtc.h>
#include <mpsl.h>
#include <mpsl_clock.h>
#include <nrf.h>
#include <nrfkit/sdc.h>
#include <nrfx_cracen.h>
#include <sdc.h>
#include <sdc_hci.h>
#include <sdc_soc.h>

volatile struct nrfkit_sdc_fault_record nrfkit_sdc_last_fault
    __attribute__((section(".noinit.sdc_fault")));

static volatile uint8_t low_priority_pending;
static volatile uint8_t hci_pending;
static volatile uint8_t enabled;
static volatile uint8_t low_latency_depth;
static uint8_t controller_initialized;
static uint8_t grtc_was_enabled;
static uint32_t saved_rram_low_power;
static size_t controller_memory_size;
static struct nrfkit_sdc_config locked_config;

static void initialize_interrupts(void);
static void fatal_reset(uint32_t source, uint32_t line)
    __attribute__((noreturn));

static void fatal_reset(uint32_t source, uint32_t line)
{
    nrfkit_sdc_last_fault.magic = NRFKIT_SDC_FAULT_MAGIC;
    nrfkit_sdc_last_fault.source = source;
    nrfkit_sdc_last_fault.line = line;
    __DSB();
    NVIC_SystemReset();
    __builtin_unreachable();
}

static void mpsl_assert(const char *file, uint32_t line)
{
    (void)file;
    fatal_reset(NRFKIT_SDC_FAULT_SOURCE_MPSL, line);
}

static void controller_fault(const char *file, uint32_t line)
{
    (void)file;
    fatal_reset(NRFKIT_SDC_FAULT_SOURCE_CONTROLLER, line);
}

static void entropy_poll(uint8_t *buffer, uint8_t length)
{
    if (nrfx_cracen_entropy_get(buffer, length) != 0) {
        fatal_reset(NRFKIT_SDC_FAULT_SOURCE_ENTROPY, length);
    }
}

static void controller_callback(void)
{
    hci_pending = 1U;
}

static int32_t configure_controller(void)
{
#if defined(NRFKIT_SDC_VARIANT_MULTIROLE)
    sdc_support_adv();
    sdc_support_peripheral();
    sdc_support_scan();
    sdc_support_central();
#elif defined(NRFKIT_SDC_VARIANT_PERIPHERAL)
    sdc_support_adv();
    sdc_support_peripheral();
#elif defined(NRFKIT_SDC_VARIANT_CENTRAL)
    sdc_support_scan();
    sdc_support_central();
#else
#error "The SDC archive variant must be selected by nrfkit_enable_sdc"
#endif
    return sdc_cfg_set(SDC_DEFAULT_RESOURCE_CFG_TAG, SDC_CFG_TYPE_NONE, NULL);
}

static void disable_interrupts(void)
{
    NVIC_DisableIRQ(SWI00_IRQn);
    NVIC_DisableIRQ(RADIO_0_IRQn);
    NVIC_DisableIRQ(TIMER10_IRQn);
    NVIC_DisableIRQ(GRTC_3_IRQn);
    NVIC_DisableIRQ(CLOCK_POWER_IRQn);
}

static void release_mpsl(void)
{
    mpsl_uninit();
    disable_interrupts();
    low_priority_pending = 0U;
    if (grtc_was_enabled == 0U) {
        nrf_grtc_sys_counter_set(NRF_GRTC, false);
    }
}

static int config_equal(const struct nrfkit_sdc_config *left,
                        const struct nrfkit_sdc_config *right)
{
    return left->lfclk_source == right->lfclk_source &&
        left->lfclk_accuracy_ppm == right->lfclk_accuracy_ppm &&
        left->rc_calibration_interval_250_ms ==
            right->rc_calibration_interval_250_ms &&
        left->rc_temperature_interval_count ==
            right->rc_temperature_interval_count &&
        left->hfclk_startup_time_us == right->hfclk_startup_time_us;
}

static int32_t initialize_libraries(const struct nrfkit_sdc_config *config)
{
    if (config == NULL || config->lfclk_accuracy_ppm == 0U ||
        config->lfclk_accuracy_ppm > 500U ||
        config->hfclk_startup_time_us == 0U ||
        config->hfclk_startup_time_us > MPSL_CLOCK_HF_LATENCY_WORST_CASE ||
        config->lfclk_source > NRFKIT_SDC_LFCLK_SYNTH) {
        return -NRF_EINVAL;
    }
    if (controller_initialized != 0U && !config_equal(config, &locked_config)) {
        return -NRF_EPERM;
    }
    if (config->lfclk_source != NRFKIT_SDC_LFCLK_RC &&
        (config->rc_calibration_interval_250_ms != 0U ||
         config->rc_temperature_interval_count != 0U)) {
        return -NRF_EINVAL;
    }
    if (config->lfclk_source == NRFKIT_SDC_LFCLK_RC &&
        config->rc_calibration_interval_250_ms == 0U) {
        return -NRF_EINVAL;
    }

    SystemCoreClockUpdate();
    if (SystemCoreClock != UINT32_C(128000000)) {
        return -NRF_EPERM;
    }

    grtc_was_enabled = nrf_grtc_sys_counter_check(NRF_GRTC) ? 1U : 0U;
    if (grtc_was_enabled == 0U) {
        nrfy_grtc_sys_counter_start(NRF_GRTC, true);
    }

    mpsl_clock_lfclk_cfg_t clock = {
        .source = (uint8_t)config->lfclk_source,
        .rc_ctiv = config->rc_calibration_interval_250_ms,
        .rc_temp_ctiv = config->rc_temperature_interval_count,
        .accuracy_ppm = config->lfclk_accuracy_ppm,
        .skip_wait_lfclk_started = false,
    };
    initialize_interrupts();
    int32_t result = mpsl_init(&clock, SWI00_IRQn, mpsl_assert);
    if (result != 0) {
        disable_interrupts();
        if (grtc_was_enabled == 0U) {
            nrf_grtc_sys_counter_set(NRF_GRTC, false);
        }
        return result;
    }
    result = mpsl_clock_hfclk_latency_set(config->hfclk_startup_time_us);
    if (result != 0) {
        release_mpsl();
        return result;
    }
    if (controller_initialized == 0U) {
        result = sdc_init(controller_fault);
        if (result != 0) {
            release_mpsl();
            return result;
        }
        result = configure_controller();
        if (result < 0) {
            release_mpsl();
            return result;
        }
        controller_memory_size = (size_t)result;
        locked_config = *config;
        controller_initialized = 1U;
    }
    return 0;
}

static void initialize_interrupts(void)
{
    NVIC_SetPriority(RADIO_0_IRQn, 0U);
    NVIC_SetPriority(TIMER10_IRQn, 0U);
    NVIC_SetPriority(GRTC_3_IRQn, 0U);
    NVIC_SetPriority(CLOCK_POWER_IRQn, 4U);
    NVIC_SetPriority(SWI00_IRQn, 4U);
    NVIC_ClearPendingIRQ(SWI00_IRQn);
    NVIC_EnableIRQ(RADIO_0_IRQn);
    NVIC_EnableIRQ(TIMER10_IRQn);
    NVIC_EnableIRQ(GRTC_3_IRQn);
    NVIC_EnableIRQ(CLOCK_POWER_IRQn);
    NVIC_EnableIRQ(SWI00_IRQn);
}

int32_t nrfkit_sdc_required_memory(const struct nrfkit_sdc_config *config,
                                   size_t *required_memory)
{
    if (required_memory == NULL || enabled != 0U) {
        return -NRF_EINVAL;
    }
    int32_t result = initialize_libraries(config);
    if (result != 0) {
        return result;
    }
    release_mpsl();
    *required_memory = controller_memory_size;
    return 0;
}

int32_t nrfkit_sdc_enable(const struct nrfkit_sdc_config *config,
                          void *memory,
                          size_t memory_size)
{
    if (enabled != 0U || memory == NULL || ((uintptr_t)memory & 7U) != 0U) {
        return -NRF_EINVAL;
    }
    int32_t result = initialize_libraries(config);
    if (result != 0) {
        return result;
    }
    if (controller_memory_size > memory_size) {
        release_mpsl();
        return -NRF_ENOMEM;
    }
    static const sdc_rand_source_t entropy = {.rand_poll = entropy_poll};
    result = sdc_rand_source_register(&entropy);
    if (result == 0) {
        result = nrfx_cracen_init();
    }
    if (result == 0) {
        result = sdc_enable(controller_callback, memory);
    }
    if (result != 0) {
        nrfx_cracen_uninit();
        release_mpsl();
        return result;
    }
    enabled = 1U;
    return 0;
}

void nrfkit_sdc_process(void)
{
    if (enabled != 0U && low_priority_pending != 0U) {
        low_priority_pending = 0U;
        mpsl_low_priority_process();
    }
}

bool nrfkit_sdc_hci_pending(void)
{
    return hci_pending != 0U;
}

int32_t nrfkit_sdc_hci_get(uint8_t *packet, uint8_t *message_type)
{
    if (enabled == 0U) {
        return -NRF_EPERM;
    }
    int32_t const result = sdc_hci_get(packet, message_type);
    hci_pending = result == -NRF_EAGAIN ? 0U : 1U;
    return result;
}

int32_t nrfkit_sdc_hci_acl_put(const uint8_t *packet)
{
    if (enabled == 0U) {
        return -NRF_EPERM;
    }
    return sdc_hci_data_put(packet);
}

int32_t nrfkit_sdc_disable(void)
{
    if (enabled == 0U) {
        return -NRF_EPERM;
    }
    int32_t result = sdc_disable();
    if (result != 0) {
        return result;
    }
    enabled = 0U;
    hci_pending = 0U;
    low_priority_pending = 0U;
    nrfx_cracen_uninit();
    release_mpsl();
    return 0;
}

void SWI00_IRQHandler(void)
{
    low_priority_pending = 1U;
}

void RADIO_0_IRQHandler(void)
{
    MPSL_IRQ_RADIO_Handler();
}

void TIMER10_IRQHandler(void)
{
    MPSL_IRQ_TIMER0_Handler();
}

void GRTC_3_IRQHandler(void)
{
    MPSL_IRQ_RTC0_Handler();
}

void CLOCK_POWER_IRQHandler(void)
{
    MPSL_IRQ_CLOCK_Handler();
}

void mpsl_low_latency_acquire_callback(void)
{
    uint32_t const primask = __get_PRIMASK();
    __disable_irq();
    if (low_latency_depth++ == 0U) {
        saved_rram_low_power = NRF_RRAMC->POWER.LOWPOWERCONFIG;
        nrf_power_task_trigger(NRF_POWER, NRF_POWER_TASK_CONSTLAT);
        NRF_RRAMC->POWER.LOWPOWERCONFIG =
            RRAMC_POWER_LOWPOWERCONFIG_MODE_Standby
            << RRAMC_POWER_LOWPOWERCONFIG_MODE_Pos;
        __DSB();
    }
    __set_PRIMASK(primask);
}

void mpsl_low_latency_release_callback(void)
{
    uint32_t const primask = __get_PRIMASK();
    __disable_irq();
    if (low_latency_depth != 0U && --low_latency_depth == 0U) {
        NRF_RRAMC->POWER.LOWPOWERCONFIG = saved_rram_low_power;
        nrf_power_task_trigger(NRF_POWER, NRF_POWER_TASK_LOWPWR);
        __DSB();
    }
    __set_PRIMASK(primask);
}
