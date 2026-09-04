/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf.h>
#include <nrfkit/board.h>
#include <nrfx_pwm.h>
#include <nrfx_rramc.h>
#include <nrfx_saadc.h>
#include <nrfx_spim.h>
#include <nrfx_twim.h>
#include <nrfx_wdt.h>

#define PASS_TOKEN "NRFKIT_M3_PERIPHERALS PASS\r\n"
#define TIMEOUT UINT32_C(2000000)
#define SCRATCH_MAGIC UINT32_C(0x4D335252)
#define TWIM_SCL_PIN NRF_PIN_PORT_TO_PIN_NUMBER(NRFKIT_EXPANSION_D4_PIN, \
    NRFKIT_EXPANSION_D4_PORT)
#define TWIM_SDA_PIN NRF_PIN_PORT_TO_PIN_NUMBER(NRFKIT_EXPANSION_D5_PIN, \
    NRFKIT_EXPANSION_D5_PORT)

extern uint8_t __rram_scratch_start[];
extern uint8_t __rram_scratch_end[];

struct scratch_record {
    uint32_t sequence;
    uint32_t sequence_inverse;
    uint32_t magic;
    uint32_t magic_inverse;
};

static nrfx_spim_t spim = NRFX_SPIM_INSTANCE(NRF_SPIM21);
static nrfx_twim_t twim = NRFX_TWIM_INSTANCE(NRF_TWIM22);
static nrfx_pwm_t pwm = NRFX_PWM_INSTANCE(NRF_PWM20);
static nrfx_wdt_t wdt = NRFX_WDT_INSTANCE(NRF_WDT30);
static volatile uint32_t spim_done;
static volatile uint32_t twim_done;
static volatile nrfx_twim_event_type_t twim_result;
static volatile uint32_t pwm_done;
static volatile uint32_t saadc_done;
static volatile uint32_t wdt_stopped;
volatile uint32_t nrfkit_m3_peripheral_stage;
static uint8_t dma_tx[4] __attribute__((aligned(4))) = {0x11, 0x22, 0x33, 0x44};
static uint8_t dma_rx[4] __attribute__((aligned(4)));
static uint16_t pwm_values[1] __attribute__((aligned(4))) = {500};
static nrf_saadc_value_t saadc_sample __attribute__((aligned(4)));
static uint8_t token[sizeof(PASS_TOKEN) - 1U] __attribute__((aligned(4)));

NRFX_INSTANCE_IRQ_HANDLER_DEFINE(pwm, 20, &pwm);
NRFX_INSTANCE_IRQ_HANDLER_DEFINE(wdt, 30, &wdt);

static void require_stage(int condition, uint32_t stage)
{
    if (!condition) {
        nrfkit_m3_peripheral_stage = stage;
        nrfkit_assert_fail();
    }
}

#define REQUIRE(condition, stage) require_stage((condition), (stage))

static void spim_handler(nrfx_spim_event_t const *event, void *context)
{
    (void)event;
    (void)context;
    spim_done = 1U;
}

static void twim_handler(nrfx_twim_event_t const *event, void *context)
{
    (void)context;
    twim_result = event->type;
    twim_done = 1U;
}

static void pwm_handler(nrfx_pwm_event_type_t event, void *context)
{
    (void)context;
    if (event == NRFX_PWM_EVENT_STOPPED) {
        pwm_done = 1U;
    }
}

static void saadc_handler(nrfx_saadc_evt_t const *event)
{
    if (event->type == NRFX_SAADC_EVT_DONE) {
        saadc_done = 1U;
    }
}

static void wdt_handler(nrf_wdt_event_t event, uint32_t requests, void *context)
{
    (void)event;
    (void)requests;
    (void)context;
    if (event == NRF_WDT_EVENT_STOPPED) {
        wdt_stopped = 1U;
    }
}

static void wait_flag(volatile uint32_t const *flag, uint32_t stage)
{
    uint32_t timeout = TIMEOUT;
    while (*flag == 0U && timeout-- != 0U) {
        __NOP();
    }
    REQUIRE(*flag != 0U, stage);
}

static void uart_write_token(void)
{
    for (size_t index = 0; index < sizeof(token); ++index) {
        token[index] = (uint8_t)PASS_TOKEN[index];
    }
    NRFKIT_VCOM_TX_GPIO->OUTSET = 1U << NRFKIT_VCOM_TX_PIN;
    NRFKIT_VCOM_TX_GPIO->PIN_CNF[NRFKIT_VCOM_TX_PIN] =
        (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
        (GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos);
    NRFKIT_VCOM_UARTE->PSEL.TXD =
        (NRFKIT_VCOM_TX_PIN << UARTE_PSEL_TXD_PIN_Pos) |
        (NRFKIT_VCOM_TX_PORT << UARTE_PSEL_TXD_PORT_Pos);
    NRFKIT_VCOM_UARTE->BAUDRATE = NRFKIT_VCOM_BAUDRATE;
    NRFKIT_VCOM_UARTE->CONFIG = 0U;
    NRFKIT_VCOM_UARTE->ENABLE = UARTE_ENABLE_ENABLE_Enabled;
    NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END = 0U;
    NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)token;
    NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = sizeof(token);
    NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START = UARTE_TASKS_DMA_TX_START_START_Trigger;
    uint32_t timeout = TIMEOUT;
    while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U && timeout-- != 0U) {
        __NOP();
    }
    REQUIRE(NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END != 0U, 18U);
}

static void scratch_write_once(void)
{
    uintptr_t const start = (uintptr_t)__rram_scratch_start;
    uintptr_t const end = (uintptr_t)__rram_scratch_end;
    REQUIRE(end - start == 256U && (start & 15U) == 0U, 13U);
    uint32_t maximum = 0U;
    for (uintptr_t address = start; address < end; address += sizeof(struct scratch_record)) {
        struct scratch_record const *record = (struct scratch_record const *)address;
        if (record->sequence_inverse == ~record->sequence &&
            record->magic == SCRATCH_MAGIC && record->magic_inverse == ~SCRATCH_MAGIC &&
            record->sequence > maximum) {
            maximum = record->sequence;
        }
    }
    struct scratch_record const next = {
        .sequence = maximum + 1U,
        .sequence_inverse = ~(maximum + 1U),
        .magic = SCRATCH_MAGIC,
        .magic_inverse = ~SCRATCH_MAGIC,
    };
    uintptr_t const address = start + (maximum % 16U) * sizeof(next);
    nrfx_rramc_config_t config = NRFX_RRAMC_DEFAULT_CONFIG(sizeof(next));
    config.mode_write = true;
    REQUIRE(nrfx_rramc_init(&config, NULL) == 0, 14U);
    nrfx_rramc_words_write((uint32_t)address, &next, sizeof(next) / sizeof(uint32_t));
    nrfx_rramc_write_buffer_commit();
    uint32_t timeout = TIMEOUT;
    while ((!nrfx_rramc_write_buffer_empty_check() || !nrfx_rramc_ready_check()) &&
        timeout-- != 0U) {
        __NOP();
    }
    REQUIRE(timeout != 0U, 15U);
    struct scratch_record verify;
    nrfx_rramc_buffer_read(&verify, (uint32_t)address, sizeof(verify));
    REQUIRE(verify.sequence == next.sequence && verify.sequence_inverse == next.sequence_inverse &&
        verify.magic == next.magic && verify.magic_inverse == next.magic_inverse, 16U);
    nrfx_rramc_uninit();
}

int main(void)
{
    nrfkit_m3_peripheral_stage = 1U;
    nrfx_spim_config_t spim_config = NRFX_SPIM_DEFAULT_CONFIG(
        NRF_SPIM_PIN_NOT_CONNECTED, NRF_SPIM_PIN_NOT_CONNECTED,
        NRF_SPIM_PIN_NOT_CONNECTED, NRF_SPIM_PIN_NOT_CONNECTED);
    spim_config.skip_gpio_cfg = true;
    REQUIRE(nrfx_spim_init(&spim, &spim_config, spim_handler, NULL) == 0, 1U);
    nrfkit_m3_peripheral_stage = 2U;
    nrfx_spim_xfer_desc_t const spim_xfer = NRFX_SPIM_XFER_TRX(
        dma_tx, sizeof(dma_tx), dma_rx, sizeof(dma_rx));
    REQUIRE(nrfx_spim_xfer(&spim, &spim_xfer, 0U) == 0, 2U);
    wait_flag(&spim_done, 3U);
    nrfx_spim_uninit(&spim);

    nrfkit_m3_peripheral_stage = 4U;
    nrfx_twim_config_t twim_config = NRFX_TWIM_DEFAULT_CONFIG(
        TWIM_SCL_PIN, TWIM_SDA_PIN);
    REQUIRE(nrfx_twim_init(&twim, &twim_config, twim_handler, NULL) == 0, 4U);
    nrfx_twim_enable(&twim);
    nrfkit_m3_peripheral_stage = 5U;
    nrfx_twim_xfer_desc_t const twim_xfer = NRFX_TWIM_XFER_DESC_TX(0x55U, dma_tx, 1U);
    REQUIRE(nrfx_twim_xfer(&twim, &twim_xfer, 0U) == 0, 5U);
    wait_flag(&twim_done, 6U);
    REQUIRE(twim_result == NRFX_TWIM_EVT_DONE ||
        twim_result == NRFX_TWIM_EVT_ADDRESS_NACK ||
        twim_result == NRFX_TWIM_EVT_DATA_NACK ||
        twim_result == NRFX_TWIM_EVT_OVERRUN ||
        twim_result == NRFX_TWIM_EVT_BUS_ERROR, 6U);
    nrfx_twim_uninit(&twim);

    nrfkit_m3_peripheral_stage = 7U;
    nrfx_pwm_config_t pwm_config = NRFX_PWM_DEFAULT_CONFIG(
        NRF_PWM_PIN_NOT_CONNECTED, NRF_PWM_PIN_NOT_CONNECTED,
        NRF_PWM_PIN_NOT_CONNECTED, NRF_PWM_PIN_NOT_CONNECTED);
    REQUIRE(nrfx_pwm_init(&pwm, &pwm_config, pwm_handler, NULL) == 0, 7U);
    nrf_pwm_sequence_t const sequence = {
        .values.p_common = pwm_values, .length = 1U, .repeats = 0U, .end_delay = 0U,
    };
    (void)nrfx_pwm_simple_playback(&pwm, &sequence, 2U, NRFX_PWM_FLAG_STOP);
    nrfkit_m3_peripheral_stage = 8U;
    wait_flag(&pwm_done, 8U);
    nrfx_pwm_uninit(&pwm);

    nrfkit_m3_peripheral_stage = 9U;
    REQUIRE(nrfx_saadc_init(NRFX_SAADC_DEFAULT_CONFIG_IRQ_PRIORITY) == 0, 9U);
    nrfx_saadc_channel_t const channel = NRFX_SAADC_DEFAULT_CHANNEL_SE(
        NRFX_ANALOG_INTERNAL_VDD, 0U);
    nrfkit_m3_peripheral_stage = 10U;
    REQUIRE(nrfx_saadc_channel_config(&channel) == 0, 10U);
    nrfkit_m3_peripheral_stage = 11U;
    REQUIRE(nrfx_saadc_simple_mode_set(1U, NRF_SAADC_RESOLUTION_12BIT,
        NRF_SAADC_OVERSAMPLE_DISABLED, saadc_handler) == 0, 11U);
    REQUIRE(nrfx_saadc_buffer_set(&saadc_sample, 1U) == 0, 11U);
    REQUIRE(nrfx_saadc_mode_trigger() == 0, 11U);
    wait_flag(&saadc_done, 12U);
    nrfx_saadc_uninit();

    nrfkit_m3_peripheral_stage = 13U;
    scratch_write_once();

    nrfkit_m3_peripheral_stage = 17U;
    nrfx_wdt_config_t wdt_config = NRFX_WDT_DEFAULT_CONFIG;
    wdt_config.behaviour |= NRF_WDT_BEHAVIOUR_STOP_ENABLE_MASK;
    REQUIRE(nrfx_wdt_init(&wdt, &wdt_config, wdt_handler, NULL) == 0, 17U);
    nrfx_wdt_channel_id channel_id;
    REQUIRE(nrfx_wdt_channel_alloc(&wdt, &channel_id) == 0, 17U);
    nrfx_wdt_enable(&wdt);
    nrfx_wdt_channel_feed(&wdt, channel_id);
    REQUIRE(nrfx_wdt_stop(&wdt) == 0, 17U);
    wait_flag(&wdt_stopped, 17U);
    nrfx_wdt_uninit(&wdt);

    nrfkit_m3_peripheral_stage = 18U;
    uart_write_token();
    nrfkit_m3_peripheral_stage = 0U;
    for (;;) {
        __WFE();
    }
}
