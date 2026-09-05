/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include <nrf.h>
#include <nrfkit/runtime.h>
#if defined(NRFKIT_M8_COMBINED)
#include <nrfkit/sdc.h>
#endif
#include <nrfkit/usbhs.h>
#include <nrfx_timer.h>
#include <usbd_core.h>
#include <usbd_hid.h>

#define USB_VID UINT16_C(0xCAFE)
#define USB_PID UINT16_C(0x4011)
#define BULK_OUT_EP UINT8_C(0x01)
#define BULK_IN_EP UINT8_C(0x81)
#define HID_OUT_EP UINT8_C(0x02)
#define HID_IN_EP UINT8_C(0x82)
#define BULK_MPS_HS UINT16_C(512)
#define BULK_MPS_FS UINT16_C(64)
#define HID_MPS UINT16_C(64)
#define VENDOR_REQUEST_STATUS UINT8_C(0x40)
#define VENDOR_REQUEST_ARM_REMOTE_WAKE UINT8_C(0x41)
#define USB_STATUS_MAGIC UINT32_C(0x4D345553)
#define HID_REPORT_DESCRIPTOR_LENGTH UINT16_C(85)

#if defined(NRFKIT_M8_COMBINED)
#define CONTROLLER_MEMORY_SIZE (8U * 1024U)
static uint8_t controller_memory[CONTROLLER_MEMORY_SIZE]
    __attribute__((aligned(8)));
#endif

#define CONFIG_TOTAL_LENGTH (9U + 9U + 7U + 7U + 9U + 9U + 7U + 7U)

static const uint8_t device_descriptor[] = {
    USB_DEVICE_DESCRIPTOR_INIT(USB_2_0, 0U, 0U, 0U, USB_VID, USB_PID, 0x0100, 1U)
};

static const uint8_t config_descriptor_hs[] = {
    USB_CONFIG_DESCRIPTOR_INIT(CONFIG_TOTAL_LENGTH, 2U, 1U,
        USB_CONFIG_BUS_POWERED | USB_CONFIG_REMOTE_WAKEUP, 100U),
    USB_INTERFACE_DESCRIPTOR_INIT(0U, 0U, 2U, 0xFFU, 0U, 0U, 4U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_OUT_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_HS, 0U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_IN_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_HS, 0U),
    HID_CUSTOM_INOUT_DESCRIPTOR_INIT(1U, 0U, HID_REPORT_DESCRIPTOR_LENGTH,
        HID_OUT_EP, HID_IN_EP, HID_MPS, 1U),
};

static const uint8_t config_descriptor_fs[] = {
    USB_CONFIG_DESCRIPTOR_INIT(CONFIG_TOTAL_LENGTH, 2U, 1U,
        USB_CONFIG_BUS_POWERED | USB_CONFIG_REMOTE_WAKEUP, 100U),
    USB_INTERFACE_DESCRIPTOR_INIT(0U, 0U, 2U, 0xFFU, 0U, 0U, 4U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_OUT_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_FS, 0U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_IN_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_FS, 0U),
    HID_CUSTOM_INOUT_DESCRIPTOR_INIT(1U, 0U, HID_REPORT_DESCRIPTOR_LENGTH,
        HID_OUT_EP, HID_IN_EP, HID_MPS, 1U),
};

/* Selected while running at high speed, so this descriptor describes full speed. */
static const uint8_t other_speed_descriptor_hs[] = {
    USB_OTHER_SPEED_CONFIG_DESCRIPTOR_INIT(CONFIG_TOTAL_LENGTH, 2U, 1U,
        USB_CONFIG_BUS_POWERED | USB_CONFIG_REMOTE_WAKEUP, 100U),
    USB_INTERFACE_DESCRIPTOR_INIT(0U, 0U, 2U, 0xFFU, 0U, 0U, 4U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_OUT_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_FS, 0U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_IN_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_FS, 0U),
    HID_CUSTOM_INOUT_DESCRIPTOR_INIT(1U, 0U, HID_REPORT_DESCRIPTOR_LENGTH,
        HID_OUT_EP, HID_IN_EP, HID_MPS, 1U),
};

/* Selected while running at full speed, so this descriptor describes high speed. */
static const uint8_t other_speed_descriptor_fs[] = {
    USB_OTHER_SPEED_CONFIG_DESCRIPTOR_INIT(CONFIG_TOTAL_LENGTH, 2U, 1U,
        USB_CONFIG_BUS_POWERED | USB_CONFIG_REMOTE_WAKEUP, 100U),
    USB_INTERFACE_DESCRIPTOR_INIT(0U, 0U, 2U, 0xFFU, 0U, 0U, 4U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_OUT_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_HS, 0U),
    USB_ENDPOINT_DESCRIPTOR_INIT(BULK_IN_EP, USB_ENDPOINT_TYPE_BULK, BULK_MPS_HS, 0U),
    HID_CUSTOM_INOUT_DESCRIPTOR_INIT(1U, 0U, HID_REPORT_DESCRIPTOR_LENGTH,
        HID_OUT_EP, HID_IN_EP, HID_MPS, 1U),
};

static const uint8_t qualifier_descriptor[] = {
    10U, USB_DESCRIPTOR_TYPE_DEVICE_QUALIFIER, 0x00U, 0x02U,
    0U, 0U, 0U, 64U, 1U, 0U,
};

static const char *const string_descriptors[] = {
    (const char[]){0x09, 0x04},
    "NrfKit",
    "USBHS validation",
    "M4-VALIDATION",
    "Bulk loopback",
    "HID loopback",
};

static const uint8_t hid_report_descriptor[] = {
    0x06, 0x00, 0xFF, 0x09, 0x01, 0xA1, 0x01,
    0x85, 0x01, 0x09, 0x02, 0x15, 0x00, 0x26, 0xFF, 0x00,
    0x75, 0x08, 0x95, 0x3F, 0x81, 0x02,
    0x85, 0x02, 0x09, 0x03, 0x15, 0x00, 0x26, 0xFF, 0x00,
    0x75, 0x08, 0x95, 0x3F, 0x91, 0x02, 0xC0,
    /* A standard keyboard input report lets host input drivers exercise
     * their normal autosuspend and remote-wakeup contract. The validation
     * firmware never emits this report, so it cannot inject input. */
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x85, 0x03,
    0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00,
    0x25, 0x01, 0x75, 0x01, 0x95, 0x08, 0x81, 0x02,
    0x95, 0x01, 0x75, 0x08, 0x81, 0x01,
    0x95, 0x06, 0x75, 0x08, 0x15, 0x00, 0x25, 0x65,
    0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xC0,
};

_Static_assert(sizeof(hid_report_descriptor) == HID_REPORT_DESCRIPTOR_LENGTH,
    "HID report descriptor length mismatch");

static uint8_t bulk_rx_buffer[BULK_MPS_HS] __attribute__((aligned(4)));
static uint8_t bulk_tx_buffer[BULK_MPS_HS] __attribute__((aligned(4)));
static uint8_t hid_rx_buffer[HID_MPS] __attribute__((aligned(4)));
static uint8_t hid_tx_buffer[HID_MPS] __attribute__((aligned(4)));
static volatile uint32_t configured_count;
static volatile uint32_t suspend_count;
static volatile uint32_t resume_count;
static volatile uint32_t bulk_rx_bytes;
static volatile uint32_t bulk_tx_bytes;
static volatile uint32_t hid_rx_count;
static volatile uint32_t hid_tx_count;
static volatile uint32_t remote_wakeup_count;
static volatile int32_t remote_wakeup_result;
static volatile uint32_t remote_wakeup_delay_ms;
static volatile bool remote_wakeup_armed;
static volatile bool remote_wakeup_timer_active;
static volatile bool remote_wakeup_due;
static volatile uint32_t wake_dctl_before;
static volatile uint32_t wake_dctl_after;
static volatile uint32_t wake_dsts_before;
static volatile uint32_t wake_dsts_after;
static volatile uint32_t wake_pcgcctl_before;
static volatile uint32_t wake_pcgcctl_after;
static volatile int32_t bulk_arm_result;
static volatile int32_t hid_arm_result;
static nrfx_timer_t timer = NRFX_TIMER_INSTANCE(NRF_TIMER21);

struct usb_validation_status {
    uint32_t magic;
    uint32_t configured_count;
    uint32_t suspend_count;
    uint32_t resume_count;
    uint32_t bulk_rx_bytes;
    uint32_t bulk_tx_bytes;
    uint32_t hid_rx_count;
    uint32_t hid_tx_count;
    uint32_t remote_wakeup_count;
    uint32_t ghwcfg3;
    uint32_t grxfsiz;
    uint32_t doepctl1;
    uint32_t doeptsiz1;
    uint32_t wake_dctl_before;
    uint32_t wake_dctl_after;
    uint32_t wake_dsts_before;
    uint32_t wake_dsts_after;
    uint32_t wake_pcgcctl_before;
    uint32_t wake_pcgcctl_after;
    int32_t remote_wakeup_result;
    int32_t bulk_arm_result;
    int32_t hid_arm_result;
};

static struct usb_validation_status status_response __attribute__((aligned(4)));

NRFX_INSTANCE_IRQ_HANDLER_DEFINE(timer, 21, &timer);

static void wake_timer_handler(nrf_timer_event_t event, void *context)
{
    (void)context;
    if (event == NRF_TIMER_EVENT_COMPARE0 && remote_wakeup_timer_active) {
        remote_wakeup_timer_active = false;
        nrfx_timer_disable(&timer);
        remote_wakeup_due = true;
    }
}

static void perform_remote_wakeup(void)
{
    wake_dctl_before = NRF_USBHSCORE->DCTL;
    wake_dsts_before = NRF_USBHSCORE->DSTS;
    wake_pcgcctl_before = NRF_USBHSCORE->PCGCCTL;
    remote_wakeup_result = usbd_send_remote_wakeup(0U);
    wake_dctl_after = NRF_USBHSCORE->DCTL;
    wake_dsts_after = NRF_USBHSCORE->DSTS;
    wake_pcgcctl_after = NRF_USBHSCORE->PCGCCTL;
    if (remote_wakeup_result == 0) {
        ++remote_wakeup_count;
    }
}

static const uint8_t *device_descriptor_cb(uint8_t speed)
{
    (void)speed;
    return device_descriptor;
}

static const uint8_t *config_descriptor_cb(uint8_t speed)
{
    if (speed == USB_SPEED_HIGH) {
        return config_descriptor_hs;
    }
    if (speed == USB_SPEED_FULL) {
        return config_descriptor_fs;
    }
    return 0;
}

static const uint8_t *qualifier_descriptor_cb(uint8_t speed)
{
    (void)speed;
    return qualifier_descriptor;
}

static const uint8_t *other_speed_descriptor_cb(uint8_t speed)
{
    if (speed == USB_SPEED_HIGH) {
        return other_speed_descriptor_hs;
    }
    if (speed == USB_SPEED_FULL) {
        return other_speed_descriptor_fs;
    }
    return 0;
}

static const char *string_descriptor_cb(uint8_t speed, uint8_t index)
{
    (void)speed;
    if (index >= sizeof(string_descriptors) / sizeof(string_descriptors[0])) {
        return 0;
    }
    return string_descriptors[index];
}

static const struct usb_descriptor descriptors = {
    .device_descriptor_callback = device_descriptor_cb,
    .config_descriptor_callback = config_descriptor_cb,
    .device_quality_descriptor_callback = qualifier_descriptor_cb,
    .other_speed_descriptor_callback = other_speed_descriptor_cb,
    .string_descriptor_callback = string_descriptor_cb,
};

static int vendor_request(uint8_t busid, struct usb_setup_packet *setup,
    uint8_t **data, uint32_t *length)
{
    if (setup->bRequest == VENDOR_REQUEST_STATUS &&
        (setup->bmRequestType & USB_REQUEST_DIR_MASK) == USB_REQUEST_DIR_IN) {
        status_response = (struct usb_validation_status) {
            .magic = USB_STATUS_MAGIC,
            .configured_count = configured_count,
            .suspend_count = suspend_count,
            .resume_count = resume_count,
            .bulk_rx_bytes = bulk_rx_bytes,
            .bulk_tx_bytes = bulk_tx_bytes,
            .hid_rx_count = hid_rx_count,
            .hid_tx_count = hid_tx_count,
            .remote_wakeup_count = remote_wakeup_count,
            .ghwcfg3 = *(volatile uint32_t *)((uintptr_t)NRF_USBHSCORE + 0x4CU),
            .grxfsiz = *(volatile uint32_t *)((uintptr_t)NRF_USBHSCORE + 0x24U),
            .doepctl1 = *(volatile uint32_t *)((uintptr_t)NRF_USBHSCORE + 0xB20U),
            .doeptsiz1 = *(volatile uint32_t *)((uintptr_t)NRF_USBHSCORE + 0xB30U),
            .wake_dctl_before = wake_dctl_before,
            .wake_dctl_after = wake_dctl_after,
            .wake_dsts_before = wake_dsts_before,
            .wake_dsts_after = wake_dsts_after,
            .wake_pcgcctl_before = wake_pcgcctl_before,
            .wake_pcgcctl_after = wake_pcgcctl_after,
            .remote_wakeup_result = remote_wakeup_result,
            .bulk_arm_result = bulk_arm_result,
            .hid_arm_result = hid_arm_result,
        };
        *data = (uint8_t *)&status_response;
        *length = sizeof(status_response);
        return 0;
    }
    if (setup->bRequest == VENDOR_REQUEST_ARM_REMOTE_WAKE &&
        (setup->bmRequestType & USB_REQUEST_DIR_MASK) == USB_REQUEST_DIR_OUT) {
        uint32_t delay_ms = setup->wValue;
        if (delay_ms == 0U) {
            remote_wakeup_timer_active = false;
            nrfx_timer_disable(&timer);
            nrf_timer_event_clear(timer.p_reg, NRF_TIMER_EVENT_COMPARE0);
            remote_wakeup_armed = false;
            remote_wakeup_due = false;
            remote_wakeup_result = -1;
            *length = 0U;
            (void)busid;
            return 0;
        }
        if (delay_ms < 20U || delay_ms > 5000U) {
            return -1;
        }
        remote_wakeup_result = -1;
        remote_wakeup_delay_ms = delay_ms;
        remote_wakeup_armed = true;
        *length = 0U;
        (void)busid;
        return 0;
    }
    return -1;
}

static void bulk_in_complete(uint8_t busid, uint8_t ep, uint32_t count)
{
    (void)busid;
    (void)ep;
    (void)count;
    bulk_tx_bytes += count;
    bulk_arm_result = usbd_ep_start_read(busid, BULK_OUT_EP,
        bulk_rx_buffer, sizeof(bulk_rx_buffer));
}

static void bulk_out_complete(uint8_t busid, uint8_t ep, uint32_t count)
{
    if (count > sizeof(bulk_tx_buffer)) {
        count = sizeof(bulk_tx_buffer);
    }
    bulk_rx_bytes += count;
    memcpy(bulk_tx_buffer, bulk_rx_buffer, count);
    (void)usbd_ep_start_write(busid, BULK_IN_EP, bulk_tx_buffer, count);
    (void)ep;
}

static void hid_in_complete(uint8_t busid, uint8_t ep, uint32_t count)
{
    (void)busid;
    (void)ep;
    (void)count;
    ++hid_tx_count;
    hid_arm_result = usbd_ep_start_read(busid, HID_OUT_EP,
        hid_rx_buffer, sizeof(hid_rx_buffer));
}

static void hid_out_complete(uint8_t busid, uint8_t ep, uint32_t count)
{
    if (count > sizeof(hid_tx_buffer)) {
        count = sizeof(hid_tx_buffer);
    }
    ++hid_rx_count;
    memcpy(hid_tx_buffer, hid_rx_buffer, count);
    if (count != 0U) {
        hid_tx_buffer[0] = 1U;
    }
    (void)usbd_ep_start_write(busid, HID_IN_EP, hid_tx_buffer, count);
    (void)ep;
}

static struct usbd_endpoint bulk_out = {BULK_OUT_EP, bulk_out_complete};
static struct usbd_endpoint bulk_in = {BULK_IN_EP, bulk_in_complete};
static struct usbd_endpoint hid_out = {HID_OUT_EP, hid_out_complete};
static struct usbd_endpoint hid_in = {HID_IN_EP, hid_in_complete};
static struct usbd_interface vendor_interface;
static struct usbd_interface hid_interface;

static void usb_event(uint8_t busid, uint8_t event)
{
    switch (event) {
    case USBD_EVENT_CONFIGURED:
        ++configured_count;
        bulk_arm_result = usbd_ep_start_read(busid, BULK_OUT_EP,
            bulk_rx_buffer, sizeof(bulk_rx_buffer));
        hid_arm_result = usbd_ep_start_read(busid, HID_OUT_EP,
            hid_rx_buffer, sizeof(hid_rx_buffer));
        break;
    case USBD_EVENT_SUSPEND:
        ++suspend_count;
        if (remote_wakeup_armed) {
            remote_wakeup_armed = false;
            uint32_t ticks = nrfx_timer_ms_to_ticks(&timer, remote_wakeup_delay_ms);
            nrfx_timer_clear(&timer);
            nrfx_timer_extended_compare(&timer, NRF_TIMER_CC_CHANNEL0, ticks,
                NRF_TIMER_SHORT_COMPARE0_STOP_MASK, true);
            remote_wakeup_timer_active = true;
            nrfx_timer_enable(&timer);
        }
        break;
    case USBD_EVENT_RESUME:
        remote_wakeup_timer_active = false;
        nrfx_timer_disable(&timer);
        remote_wakeup_due = false;
        ++resume_count;
        break;
    default:
        break;
    }
}

int main(void)
{
#if defined(NRFKIT_M8_COMBINED)
    struct nrfkit_sdc_config const sdc_config = {
        .lfclk_source = NRFKIT_SDC_LFCLK_XTAL,
        .lfclk_accuracy_ppm = 20U,
        .hfclk_startup_time_us = 1400U,
    };
    size_t required_memory = 0U;
    if (nrfkit_sdc_required_memory(&sdc_config, &required_memory) != 0 ||
        required_memory > sizeof(controller_memory) ||
        nrfkit_sdc_enable(&sdc_config, controller_memory,
                          sizeof(controller_memory)) != 0) {
        nrfkit_assert_fail();
    }
#endif
    uint32_t timer_frequency = NRF_TIMER_BASE_FREQUENCY_GET(timer.p_reg);
    nrfx_timer_config_t timer_config = NRFX_TIMER_DEFAULT_CONFIG(timer_frequency);
    timer_config.bit_width = NRF_TIMER_BIT_WIDTH_32;
    timer_config.interrupt_priority = 6U;
    if (nrfx_timer_init(&timer, &timer_config, wake_timer_handler) != 0) {
        nrfkit_assert_fail();
    }
    vendor_interface.vendor_handler = vendor_request;
    usbd_desc_register(0U, &descriptors);
    usbd_add_interface(0U, &vendor_interface);
    usbd_add_endpoint(0U, &bulk_out);
    usbd_add_endpoint(0U, &bulk_in);
    usbd_add_interface(0U, usbd_hid_init_intf(0U, &hid_interface,
        hid_report_descriptor, sizeof(hid_report_descriptor)));
    usbd_add_endpoint(0U, &hid_out);
    usbd_add_endpoint(0U, &hid_in);
    if (usbd_initialize(0U, (uintptr_t)NRF_USBHSCORE, usb_event) != 0 ||
        nrfkit_usbhs_connect() != NRFKIT_USBHS_OK) {
        return 1;
    }
    for (;;) {
#if defined(NRFKIT_M8_COMBINED)
        nrfkit_sdc_process();
#endif
        if (remote_wakeup_due) {
            remote_wakeup_due = false;
            perform_remote_wakeup();
        }
        __WFE();
    }
}
