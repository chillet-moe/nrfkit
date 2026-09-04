/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrfkit/board.h>
#include <nrfkit/nrfx.h>
#include <nrfkit/runtime.h>
#include <nrfkit/sdc.h>
#if defined(NRFKIT_M7_TIMESLOT)
#include <nrfkit/timeslot.h>
#endif
#include <nrfx_uarte.h>

#define PIN(port, pin) NRF_PIN_PORT_TO_PIN_NUMBER((pin), (port))
#define RX_RING_SIZE 512U
#define CONTROLLER_MEMORY_SIZE (8U * 1024U)
#define STACK_WATERMARK_PATTERN UINT8_C(0xA5)
#define STACK_WATERMARK_GUARD 128U
#define CONTROLLER_CANARY UINT64_C(0x5344434D454D4F52)

extern uint8_t __StackLimit[];
extern uint8_t __StackTop[];

static nrfx_uarte_t hci_uart = NRFX_UARTE_INSTANCE(NRF_UARTE20);
static struct {
    uint64_t before;
    uint8_t memory[CONTROLLER_MEMORY_SIZE];
    uint64_t after;
} controller_region __attribute__((aligned(8)));
static uint8_t rx_dma[2];
static uint8_t rx_dma_index;
static volatile uint16_t rx_read;
static volatile uint16_t rx_write;
static uint8_t rx_ring[RX_RING_SIZE];
static volatile uint8_t tx_done;
static volatile uint8_t uart_fault;
static uint8_t *stack_watermark_end;
static volatile uint8_t acl_submissions;
static volatile int32_t acl_put_result;
volatile uint32_t nrfkit_m6_required_memory;
volatile uint32_t nrfkit_m6_lifecycle_enables;

#if defined(NRFKIT_M7_TIMESLOT)
static volatile uint32_t timeslot_grants;
static volatile uint32_t timeslot_deadlines;
static volatile uint32_t timeslot_blocked;
static volatile uint32_t timeslot_cancelled;
static volatile uint32_t timeslot_closed;
static volatile uint32_t timeslot_extend_succeeded;
static volatile uint32_t timeslot_extend_failed;
static volatile uint8_t timeslot_idle;
static volatile uint8_t timeslot_extension_enabled;
static volatile uint8_t timeslot_extension_requested;
static volatile uint8_t timeslot_burst_remaining;
static volatile uint8_t timeslot_retry_budget;

static struct nrfkit_timeslot_action timeslot_handler(
    enum nrfkit_timeslot_signal signal, void *context)
{
    (void)context;
    struct nrfkit_timeslot_action action = {
        .kind = NRFKIT_TIMESLOT_ACTION_NONE,
    };
    if (signal == NRFKIT_TIMESLOT_SIGNAL_START) {
        ++timeslot_grants;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_TIMER) {
        ++timeslot_deadlines;
        if (timeslot_extension_enabled != 0U &&
            timeslot_extension_requested == 0U) {
            timeslot_extension_requested = 1U;
            action.kind = NRFKIT_TIMESLOT_ACTION_EXTEND;
            action.length_us = 200U;
        } else if (timeslot_burst_remaining > 1U) {
            --timeslot_burst_remaining;
            action.kind = NRFKIT_TIMESLOT_ACTION_REQUEST_NORMAL;
            action.length_us = 1000U;
            action.distance_us = 10000U;
        } else {
            timeslot_burst_remaining = 0U;
            action.kind = NRFKIT_TIMESLOT_ACTION_END;
        }
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_EXTEND_SUCCEEDED) {
        ++timeslot_extend_succeeded;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_EXTEND_FAILED) {
        ++timeslot_extend_failed;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_BLOCKED) {
        ++timeslot_blocked;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_CANCELLED) {
        ++timeslot_cancelled;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_IDLE) {
        timeslot_idle = 1U;
    } else if (signal == NRFKIT_TIMESLOT_SIGNAL_CLOSED) {
        ++timeslot_closed;
    }
    return action;
}

static void timeslot_request(void)
{
    timeslot_idle = 0U;
    if (nrfkit_timeslot_request_earliest(1000U, 100000U, 150U) != 0) {
        nrfkit_assert_fail();
    }
}
#endif

static void stack_watermark_initialize(void)
{
    uintptr_t stack_pointer;
    __asm volatile("mrs %0, msp" : "=r"(stack_pointer));
    uintptr_t const limit = (uintptr_t)__StackLimit;
    uintptr_t const end = stack_pointer > limit + STACK_WATERMARK_GUARD ?
        stack_pointer - STACK_WATERMARK_GUARD : limit;
    stack_watermark_end = (uint8_t *)end;
    for (uint8_t *byte = __StackLimit; byte < stack_watermark_end; ++byte) {
        *byte = STACK_WATERMARK_PATTERN;
    }
}

static uint32_t stack_watermark_used(void)
{
    uint8_t *byte = __StackLimit;
    while (byte < stack_watermark_end && *byte == STACK_WATERMARK_PATTERN) {
        ++byte;
    }
    return (uint32_t)((uintptr_t)__StackTop - (uintptr_t)byte);
}

static void uart_handler(const nrfx_uarte_event_t *event, void *context)
{
    (void)context;
    if (event->type == NRFX_UARTE_EVT_RX_BUF_REQUEST) {
        uint8_t *next = &rx_dma[rx_dma_index++ & 1U];
        if (nrfx_uarte_rx_buffer_set(&hci_uart, next, 1U) != 0) {
            uart_fault = 1U;
        }
    } else if (event->type == NRFX_UARTE_EVT_RX_DONE) {
        for (size_t index = 0; index < event->data.rx.length; ++index) {
            uint16_t const next = (uint16_t)((rx_write + 1U) % RX_RING_SIZE);
            if (next == rx_read) {
                uart_fault = 1U;
                return;
            }
            rx_ring[rx_write] = event->data.rx.p_buffer[index];
            rx_write = next;
        }
    } else if (event->type == NRFX_UARTE_EVT_TX_DONE) {
        tx_done = 1U;
    } else if (event->type == NRFX_UARTE_EVT_ERROR ||
               event->type == NRFX_UARTE_EVT_RX_BUF_TOO_LATE) {
        uart_fault = 1U;
    }
}

static void send(const uint8_t *data, size_t size)
{
    tx_done = 0U;
    if (nrfx_uarte_tx(&hci_uart, data, size, 0U) != 0) {
        nrfkit_assert_fail();
    }
    while (tx_done == 0U) {
        nrfkit_sdc_process();
        __WFE();
    }
}

static size_t received(void)
{
    return rx_write >= rx_read ? (size_t)(rx_write - rx_read) :
        RX_RING_SIZE - rx_read + rx_write;
}

static uint8_t receive_byte(void)
{
    uint8_t const value = rx_ring[rx_read];
    rx_read = (uint16_t)((rx_read + 1U) % RX_RING_SIZE);
    return value;
}

int main(void)
{
    stack_watermark_initialize();
    nrfx_uarte_config_t uart = NRFX_UARTE_DEFAULT_CONFIG(
        PIN(NRFKIT_VCOM_TX_PORT, NRFKIT_VCOM_TX_PIN),
        PIN(NRFKIT_VCOM_RX_PORT, NRFKIT_VCOM_RX_PIN));
    uart.rts_pin = PIN(NRFKIT_VCOM_RTS_PORT, NRFKIT_VCOM_RTS_PIN);
    uart.cts_pin = PIN(NRFKIT_VCOM_CTS_PORT, NRFKIT_VCOM_CTS_PIN);
    uart.baudrate = NRF_UARTE_BAUDRATE_1000000;
    uart.config.hwfc = NRF_UARTE_HWFC_ENABLED;
    if (nrfx_uarte_init(&hci_uart, &uart, uart_handler) != 0 ||
        nrfx_uarte_rx_enable(&hci_uart, 0U) != 0) {
        nrfkit_assert_fail();
    }

    const struct nrfkit_sdc_config controller = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20U,
        .hfclk_startup_time_us = 1400U,
    };
    controller_region.before = CONTROLLER_CANARY;
    controller_region.after = CONTROLLER_CANARY;
    size_t required_memory;
    if (nrfkit_sdc_required_memory(&controller, &required_memory) != 0 ||
        required_memory > sizeof(controller_region.memory) ||
        nrfkit_sdc_enable(&controller, controller_region.memory,
                          sizeof(controller_region.memory)) != 0) {
        nrfkit_assert_fail();
    }
#if defined(NRFKIT_M7_TIMESLOT)
    if (nrfkit_timeslot_open(timeslot_handler, NULL) != 0) {
        nrfkit_assert_fail();
    }
    if (nrfkit_sdc_disable() != 0) {
        nrfkit_assert_fail();
    }
    timeslot_request();
    while (timeslot_grants == 0U || timeslot_idle == 0U) {
        nrfkit_sdc_process();
        __WFE();
    }
    if (nrfkit_timeslot_close() != 0) {
        nrfkit_assert_fail();
    }
    while (timeslot_closed == 0U) {
        nrfkit_sdc_process();
        __WFE();
    }
    if (nrfkit_sdc_enable(&controller, controller_region.memory,
                          sizeof(controller_region.memory)) != 0 ||
        nrfkit_timeslot_open(timeslot_handler, NULL) != 0) {
        nrfkit_assert_fail();
    }
    timeslot_extension_enabled = 1U;
    timeslot_burst_remaining = 1U;
    timeslot_request();
#else
    if (nrfkit_sdc_disable() != 0 ||
        nrfkit_sdc_enable(&controller, controller_region.memory,
                          sizeof(controller_region.memory)) != 0) {
        nrfkit_assert_fail();
    }
#endif
    nrfkit_m6_required_memory = (uint32_t)required_memory;
    nrfkit_m6_lifecycle_enables = 2U;

    uint8_t command[258];
    uint8_t output[260];
    for (;;) {
        nrfkit_sdc_process();
#if defined(NRFKIT_M7_TIMESLOT)
        if (timeslot_idle != 0U && timeslot_burst_remaining != 0U) {
            if (timeslot_retry_budget == 0U) {
                timeslot_burst_remaining = 0U;
            } else {
                --timeslot_retry_budget;
                timeslot_request();
            }
        }
#endif
        if (uart_fault != 0U) {
            nrfkit_assert_fail();
        }
        while (received() >= 4U) {
            uint8_t const packet_type = rx_ring[rx_read];
            if (packet_type != 0x01U && packet_type != 0x02U) {
                (void)receive_byte();
                continue;
            }
            size_t packet_size;
            if (packet_type == 0x01U) {
                uint16_t const length_index =
                    (uint16_t)((rx_read + 3U) % RX_RING_SIZE);
                packet_size = (size_t)rx_ring[length_index] + 4U;
            } else {
                if (received() < 5U) {
                    break;
                }
                uint16_t const length_low =
                    (uint16_t)((rx_read + 3U) % RX_RING_SIZE);
                uint16_t const length_high =
                    (uint16_t)((rx_read + 4U) % RX_RING_SIZE);
                packet_size = (size_t)rx_ring[length_low] +
                    ((size_t)rx_ring[length_high] << 8U) + 5U;
            }
            if (packet_size - 1U > sizeof(command)) {
                nrfkit_assert_fail();
            }
            if (received() < packet_size) {
                break;
            }
            (void)receive_byte();
            for (size_t index = 0; index < packet_size - 1U; ++index) {
                command[index] = receive_byte();
            }
            if (packet_type == 0x02U) {
                acl_put_result = nrfkit_sdc_hci_acl_put(command);
                if (acl_put_result == 0) {
                    ++acl_submissions;
                }
                continue;
            }
            size_t event_size;
            output[0] = 0x04U;
            if (command[0] == 0x00U && command[1] == 0xFCU &&
                command[2] == 0U) {
                output[1] = 0x0EU;
                uint32_t const stack_used = stack_watermark_used();
                output[2] = 21U;
                output[3] = 1U;
                output[4] = command[0];
                output[5] = command[1];
                output[6] = 0U;
                output[7] = (uint8_t)nrfkit_m6_required_memory;
                output[8] = (uint8_t)(nrfkit_m6_required_memory >> 8U);
                output[9] = (uint8_t)(nrfkit_m6_required_memory >> 16U);
                output[10] = (uint8_t)(nrfkit_m6_required_memory >> 24U);
                output[11] = (uint8_t)stack_used;
                output[12] = (uint8_t)(stack_used >> 8U);
                output[13] = (uint8_t)(stack_used >> 16U);
                output[14] = (uint8_t)(stack_used >> 24U);
                output[15] = (uint8_t)nrfkit_m6_lifecycle_enables;
                output[16] = nrfkit_sdc_last_fault.magic ==
                    NRFKIT_SDC_FAULT_MAGIC ? 1U : 0U;
                output[17] = uart_fault;
                output[18] = acl_submissions;
                output[19] = (uint8_t)acl_put_result;
                output[20] = (uint8_t)((uint32_t)acl_put_result >> 8U);
                output[21] = (uint8_t)((uint32_t)acl_put_result >> 16U);
                output[22] = (uint8_t)((uint32_t)acl_put_result >> 24U);
                output[23] = controller_region.before == CONTROLLER_CANARY &&
                    controller_region.after == CONTROLLER_CANARY ? 1U : 0U;
                event_size = 23U;
#if defined(NRFKIT_M7_TIMESLOT)
            } else if (command[0] == 0x01U && command[1] == 0xFCU &&
                       command[2] == 0U) {
                output[1] = 0x0EU;
                output[2] = 32U;
                output[3] = 1U;
                output[4] = command[0];
                output[5] = command[1];
                output[6] = 0U;
                uint32_t const counters[] = {
                    timeslot_grants, timeslot_deadlines, timeslot_blocked,
                    timeslot_cancelled, timeslot_closed,
                    timeslot_extend_succeeded, timeslot_extend_failed,
                };
                size_t position = 7U;
                for (size_t counter = 0U;
                     counter < sizeof(counters) / sizeof(counters[0]); ++counter) {
                    for (size_t byte = 0U; byte < sizeof(counters[0]); ++byte) {
                        output[position++] =
                            (uint8_t)(counters[counter] >> (byte * 8U));
                    }
                }
                event_size = 34U;
            } else if (command[0] == 0x02U && command[1] == 0xFCU &&
                       command[2] == 0U) {
                output[1] = 0x0EU;
                output[2] = 4U;
                output[3] = 1U;
                output[4] = command[0];
                output[5] = command[1];
                output[6] = timeslot_idle != 0U ? 0U : 0x0CU;
                event_size = 6U;
                if (timeslot_idle != 0U) {
                    timeslot_burst_remaining = 3U;
                    timeslot_retry_budget = 8U;
                    timeslot_request();
                }
#endif
            } else if (nrfkit_sdc_hci_command(
                           command, packet_size - 1U, &output[1],
                           sizeof(output) - 1U, &event_size) != 0) {
                    nrfkit_assert_fail();
            }
            send(output, event_size + 1U);
        }

        uint8_t message_type;
        int32_t result;
        do {
            result = nrfkit_sdc_hci_get(&output[1], &message_type);
            if (result == 0) {
                output[0] = message_type;
                size_t message_size;
                if (message_type == 0x04U) {
                    message_size = (size_t)output[2] + 2U;
                } else if (message_type == 0x02U) {
                    message_size = 4U + (size_t)output[3] +
                        ((size_t)output[4] << 8U);
                } else {
                    nrfkit_assert_fail();
                }
                send(output, message_size + 1U);
            }
        } while (result == 0);
        __WFE();
    }
}
