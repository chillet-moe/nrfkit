/* SPDX-License-Identifier: BSD-3-Clause */
/* Consumer-owned USB configuration for the built-in port contract. */
#ifndef NRFKIT_GENERATED_CHERRYUSB_CONFIG_H
#define NRFKIT_GENERATED_CHERRYUSB_CONFIG_H
#define CONFIG_USB_PRINTF(...) ((void)0)
#define CONFIG_USB_DBG_LEVEL 0
#define CONFIG_USB_ALIGN_SIZE 4
#define USB_NOCACHE_RAM_SECTION
#define CONFIG_USBDEV_MAX_BUS 1
#define CONFIG_USBDEV_REQUEST_BUFFER_LEN 512
#define CONFIG_USB_DWC2_DMA_ENABLE
#define CONFIG_USB_HS
#include <nrf.h>
#define USBD_REG_BASE_ADDRESS ((uintptr_t)NRF_USBHSCORE)
#define NRFKIT_USBHS_DEVICE_TX_FIFO_WORDS { 16, 16 }
#endif
