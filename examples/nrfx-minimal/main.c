/* SPDX-License-Identifier: BSD-3-Clause */

#include <hal/nrf_gpio.h>
#include <helpers/nrfx_reset_reason.h>

int main(void)
{
    uint32_t const pin = NRF_PIN_PORT_TO_PIN_NUMBER(15U, 1U);
    nrf_gpio_cfg_output(pin);
    nrf_gpio_pin_clear(pin);
    (void)nrfx_reset_reason_get();
    for (;;) {
        __asm volatile ("wfe");
    }
}
