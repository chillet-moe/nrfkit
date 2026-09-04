/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrfkit/board.h>
#include <nrfkit/nrfx.h>
#include <nrfkit/runtime.h>
#include <nrfkit/sdc.h>
#include <nrfx_uarte.h>

#define PIN(port, pin) NRF_PIN_PORT_TO_PIN_NUMBER((pin), (port))
#define RX_RING_SIZE 512U
#define CONTROLLER_MEMORY_SIZE (64U * 1024U)

static nrfx_uarte_t hci_uart = NRFX_UARTE_INSTANCE(NRF_UARTE20);
static uint8_t controller_memory[CONTROLLER_MEMORY_SIZE] __attribute__((aligned(8)));
static uint8_t rx_dma[2];
static uint8_t rx_dma_index;
static volatile uint16_t rx_read;
static volatile uint16_t rx_write;
static uint8_t rx_ring[RX_RING_SIZE];
static volatile uint8_t tx_done;
static volatile uint8_t uart_fault;
volatile uint32_t nrfkit_m6_required_memory;
volatile uint32_t nrfkit_m6_lifecycle_enables;

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
    size_t required_memory;
    if (nrfkit_sdc_required_memory(&controller, &required_memory) != 0 ||
        required_memory > sizeof(controller_memory) ||
        nrfkit_sdc_enable(&controller, controller_memory,
                          sizeof(controller_memory)) != 0 ||
        nrfkit_sdc_disable() != 0 ||
        nrfkit_sdc_enable(&controller, controller_memory,
                          sizeof(controller_memory)) != 0) {
        nrfkit_assert_fail();
    }
    nrfkit_m6_required_memory = (uint32_t)required_memory;
    nrfkit_m6_lifecycle_enables = 2U;

    uint8_t command[258];
    uint8_t output[260];
    for (;;) {
        nrfkit_sdc_process();
        if (uart_fault != 0U) {
            nrfkit_assert_fail();
        }
        while (received() >= 4U) {
            if (rx_ring[rx_read] != 0x01U) {
                (void)receive_byte();
                continue;
            }
            uint16_t const length_index = (uint16_t)((rx_read + 3U) % RX_RING_SIZE);
            size_t const packet_size = (size_t)rx_ring[length_index] + 4U;
            if (received() < packet_size) {
                break;
            }
            (void)receive_byte();
            for (size_t index = 0; index < packet_size - 1U; ++index) {
                command[index] = receive_byte();
            }
            size_t event_size;
            output[0] = 0x04U;
            if (command[0] == 0x00U && command[1] == 0xFCU &&
                command[2] == 0U) {
                output[1] = 0x0EU;
                output[2] = 9U;
                output[3] = 1U;
                output[4] = command[0];
                output[5] = command[1];
                output[6] = 0U;
                output[7] = (uint8_t)nrfkit_m6_required_memory;
                output[8] = (uint8_t)(nrfkit_m6_required_memory >> 8U);
                output[9] = (uint8_t)(nrfkit_m6_required_memory >> 16U);
                output[10] = (uint8_t)(nrfkit_m6_required_memory >> 24U);
                output[11] = (uint8_t)nrfkit_m6_lifecycle_enables;
                event_size = 11U;
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
