/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <nrf.h>
#include <nrfkit/runtime.h>
#include <nrfkit/usbhs.h>
#include <lib/nrfx_coredep.h>
#include <hal/nrf_clock.h>
#include <hal/nrf_vregusb.h>
#include <usb_dwc2_param.h>
#include <usbd_core.h>

#if defined(NRFKIT_USBHS_MPSL_CLOCK)
#include "../../softdevice/sdc/nrf54l/platform_internal.h"
#endif

#define USBHS_WAIT_ITERATIONS UINT32_C(10000000)

#ifndef NRFKIT_USBHS_DEVICE_TX_FIFO_WORDS
#define NRFKIT_USBHS_DEVICE_TX_FIFO_WORDS \
    { 16U, 128U, 64U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U }
#endif

static volatile bool initialized;
static volatile bool connected;
static volatile bool connect_requested;
static volatile bool vbus_present;
static uint8_t usb_busid;
#if defined(NRFKIT_USBHS_MPSL_CLOCK)
static bool mpsl_clock_requested;
#endif

/* Kept as global symbols so the repository GDB gate can diagnose headless bring-up. */
volatile uint32_t nrfkit_usbhs_stage;
volatile int nrfkit_usbhs_result = NRFKIT_USBHS_OK;

static bool vbus_detected(void)
{
    return vbus_present;
}

static bool wait_for(volatile uint32_t const *reg, uint32_t mask, bool set)
{
    uint32_t remaining = USBHS_WAIT_ITERATIONS;
    while (remaining-- != 0U) {
        if (((*reg & mask) != 0U) == set) {
            return true;
        }
    }
    return false;
}

void usb_dc_low_level_init(uint8_t busid)
{
    nrfkit_usbhs_stage = 1U;
    if (busid != 0U || initialized) {
        nrfkit_usbhs_result = NRFKIT_USBHS_ERR_STATE;
        nrfkit_assert_fail();
    }
    usb_busid = busid;

    /* A stop/start cycle makes cable state observable through documented events. */
    NRF_VREGUSB->TASKS_STOP = 1U;
    nrfx_coredep_delay_us(10U);
    NRF_VREGUSB->EVENTS_VBUSDETECTED = 0U;
    NRF_VREGUSB->EVENTS_VBUSREMOVED = 0U;
    NRF_VREGUSB->INTENSET = VREGUSB_INTENSET_VBUSDETECTED_Msk |
        VREGUSB_INTENSET_VBUSREMOVED_Msk;
    NRF_VREGUSB->TASKS_START = 1U;
    nrfkit_usbhs_stage = 2U;
    if (NRF_VREGUSB->EVENTS_VBUSDETECTED != 0U) {
        NRF_VREGUSB->EVENTS_VBUSDETECTED = 0U;
        vbus_present = true;
    } else {
        vbus_present = false;
    }
    nrfkit_usbhs_stage = 3U;

#if defined(NRFKIT_USBHS_MPSL_CLOCK)
    if (nrfkit_mpsl_hfclk24m_request() != 0) {
        nrfkit_usbhs_result = NRFKIT_USBHS_ERR_CLOCK_CONTROL;
        nrfkit_assert_fail();
    }
    mpsl_clock_requested = true;
    bool clock_running = false;
    uint32_t remaining = USBHS_WAIT_ITERATIONS;
    int32_t clock_result = 0;
    while (remaining-- != 0U && !clock_running) {
        clock_result = nrfkit_mpsl_hfclk24m_is_running(&clock_running);
        if (clock_result != 0) {
            break;
        }
    }
    if (clock_result != 0 || !clock_running) {
        (void)nrfkit_mpsl_hfclk24m_release();
        mpsl_clock_requested = false;
        nrfkit_usbhs_result = clock_result == 0 ?
            NRFKIT_USBHS_ERR_CLOCK_TIMEOUT : NRFKIT_USBHS_ERR_CLOCK_CONTROL;
        nrfkit_assert_fail();
    }
#else
    nrf_clock_event_clear(NRF_CLOCK, NRF_CLOCK_EVENT_HFCLK24MSTARTED);
    nrf_clock_task_trigger(NRF_CLOCK, NRF_CLOCK_TASK_HFCLK24MSTART);
    if (!wait_for(&NRF_CLOCK->EVENTS_XO24MSTARTED, 1U, true)) {
        nrfkit_usbhs_result = NRFKIT_USBHS_ERR_CLOCK_TIMEOUT;
        nrfkit_assert_fail();
    }
    nrf_clock_event_clear(NRF_CLOCK, NRF_CLOCK_EVENT_HFCLK24MSTARTED);
#endif
    nrfkit_usbhs_stage = 4U;

    NRF_USBHS->ENABLE = USBHS_ENABLE_CORE_Msk;
    NRF_USBHS->PHY.OVERRIDEVALUES = USBHS_PHY_OVERRIDEVALUES_ID_Msk;
    NRF_USBHS->PHY.INPUTOVERRIDE = USBHS_PHY_INPUTOVERRIDE_ID_Msk |
        USBHS_PHY_INPUTOVERRIDE_VBUSVALID_Msk |
        USBHS_PHY_INPUTOVERRIDE_SUSPENDM0_Msk;
    NRF_USBHS->ENABLE = USBHS_ENABLE_PHY_Msk | USBHS_ENABLE_CORE_Msk;
    NRF_USBHS->PHY.INPUTOVERRIDE &= ~USBHS_PHY_INPUTOVERRIDE_SUSPENDM0_Msk;
    nrfx_coredep_delay_us(45U);
    NRF_USBHS->TASKS_START = 1U;
    /* The wrapper start task requires a settling interval before DWC2 access. */
    nrfx_coredep_delay_us(1000U);
    nrfkit_usbhs_stage = 5U;

    NVIC_ClearPendingIRQ(USBHS_IRQn);
    NVIC_SetPriority(USBHS_IRQn, 7U);
    NVIC_EnableIRQ(USBHS_IRQn);
    NVIC_ClearPendingIRQ(VREGUSB_IRQn);
    NVIC_SetPriority(VREGUSB_IRQn, 7U);
    NVIC_EnableIRQ(VREGUSB_IRQn);
    initialized = true;
    connected = false;
    connect_requested = false;
    nrfkit_usbhs_result = NRFKIT_USBHS_OK;
    nrfkit_usbhs_stage = 6U;
}

void usb_dc_low_level_deinit(uint8_t busid)
{
    if (busid != usb_busid) {
        return;
    }
    NVIC_DisableIRQ(USBHS_IRQn);
    NVIC_DisableIRQ(VREGUSB_IRQn);
    connected = false;
    connect_requested = false;
    initialized = false;
    vbus_present = false;
    NRF_USBHS->PHY.INPUTOVERRIDE = USBHS_PHY_INPUTOVERRIDE_ID_Msk |
        USBHS_PHY_INPUTOVERRIDE_VBUSVALID_Msk |
        USBHS_PHY_INPUTOVERRIDE_SUSPENDM0_Msk;
    NRF_USBHS->PHY.OVERRIDEVALUES = USBHS_PHY_OVERRIDEVALUES_ID_Msk;
    NRF_USBHS->ENABLE = 0U;
    nrfx_coredep_delay_us(10U);
#if defined(NRFKIT_USBHS_MPSL_CLOCK)
    if (mpsl_clock_requested) {
        if (nrfkit_mpsl_hfclk24m_release() != 0) {
            nrfkit_usbhs_result = NRFKIT_USBHS_ERR_CLOCK_CONTROL;
            nrfkit_assert_fail();
        }
        mpsl_clock_requested = false;
    }
#else
    nrf_clock_task_trigger(NRF_CLOCK, NRF_CLOCK_TASK_HFCLK24MSTOP);
#endif
    NRF_VREGUSB->INTENCLR = VREGUSB_INTENCLR_VBUSDETECTED_Msk |
        VREGUSB_INTENCLR_VBUSREMOVED_Msk;
    NRF_VREGUSB->TASKS_STOP = 1U;
}

void USBHS_IRQHandler(void)
{
    USBD_IRQHandler(usb_busid);
}

void VREGUSB_IRQHandler(void)
{
    if (NRF_VREGUSB->EVENTS_VBUSREMOVED != 0U) {
        NRF_VREGUSB->EVENTS_VBUSREMOVED = 0U;
        NRF_USBHS->PHY.INPUTOVERRIDE |= USBHS_PHY_INPUTOVERRIDE_VBUSVALID_Msk;
        NRF_USBHS->PHY.OVERRIDEVALUES &= ~USBHS_PHY_OVERRIDEVALUES_VBUSVALID_Msk;
        connected = false;
        vbus_present = false;
        if (initialized) {
            usbd_event_disconnect_handler(usb_busid);
        }
    }
    if (NRF_VREGUSB->EVENTS_VBUSDETECTED != 0U) {
        NRF_VREGUSB->EVENTS_VBUSDETECTED = 0U;
        vbus_present = true;
        if (initialized && connect_requested && !connected) {
            NRF_USBHS->PHY.INPUTOVERRIDE = USBHS_PHY_INPUTOVERRIDE_ID_Msk;
            NRF_USBHS->PHY.OVERRIDEVALUES = USBHS_PHY_OVERRIDEVALUES_ID_Msk;
            connected = true;
            usbd_event_connect_handler(usb_busid);
        }
    }
}

int nrfkit_usbhs_connect(void)
{
    if (!initialized) {
        nrfkit_usbhs_result = NRFKIT_USBHS_ERR_STATE;
        return nrfkit_usbhs_result;
    }
    connect_requested = true;
    if (!vbus_detected()) {
        nrfkit_usbhs_result = NRFKIT_USBHS_OK;
        return nrfkit_usbhs_result;
    }
    NRF_USBHS->PHY.INPUTOVERRIDE = USBHS_PHY_INPUTOVERRIDE_ID_Msk;
    NRF_USBHS->PHY.OVERRIDEVALUES = USBHS_PHY_OVERRIDEVALUES_ID_Msk;
    connected = true;
    usbd_event_connect_handler(usb_busid);
    nrfkit_usbhs_result = NRFKIT_USBHS_OK;
    nrfkit_usbhs_stage = 7U;
    return nrfkit_usbhs_result;
}

bool nrfkit_usbhs_vbus_present(void)
{
    return vbus_detected();
}

int nrfkit_usbhs_last_result(void)
{
    return nrfkit_usbhs_result;
}

void dwc2_get_user_params(uint32_t reg_base, struct dwc2_user_params *params)
{
    static const struct dwc2_user_params nrf54l_usbhs_params = {
        .phy_type = DWC2_PHY_TYPE_PARAM_UTMI,
        .phy_utmi_width = 8U,
        .device_dma_enable = true,
        .device_dma_desc_enable = false,
        /* 25% of the LM20 core's 3040-word SPRAM, matching Nordic's cap. */
        .device_rx_fifo_size = 760U,
        .device_tx_fifo_size = NRFKIT_USBHS_DEVICE_TX_FIFO_WORDS,
    };

    if (reg_base != (uintptr_t)NRF_USBHSCORE) {
        nrfkit_usbhs_result = NRFKIT_USBHS_ERR_STATE;
        nrfkit_assert_fail();
    }
    memcpy(params, &nrf54l_usbhs_params, sizeof(*params));
}

void usbd_dwc2_delay_ms(uint8_t milliseconds)
{
    while (milliseconds-- != 0U) {
        nrfx_coredep_delay_us(1000U);
    }
}

uint32_t usbd_dwc2_get_system_clock(void)
{
    return SystemCoreClock;
}
