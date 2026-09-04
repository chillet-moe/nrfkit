/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_BOARD_H
#define NRFKIT_BOARD_H

/* nRF54LM20 DK LED0 is active-high on P1.22. */
#define NRFKIT_LED0_PORT NRF_P1
#define NRFKIT_LED0_PIN 22u

/* Arduino-compatible expansion header pins D4 and D5 are P1.4 and P1.13. */
#define NRFKIT_EXPANSION_D4_PORT 1u
#define NRFKIT_EXPANSION_D4_PIN 4u
#define NRFKIT_EXPANSION_D5_PORT 1u
#define NRFKIT_EXPANSION_D5_PIN 13u

/* VCOM1 is routed to UARTE20 through the DK interface MCU. */
#define NRFKIT_VCOM_UARTE NRF_UARTE20
#define NRFKIT_VCOM_TX_GPIO NRF_P1
#define NRFKIT_VCOM_TX_PORT 1u
#define NRFKIT_VCOM_TX_PIN 16u
#define NRFKIT_VCOM_BAUDRATE UARTE_BAUDRATE_BAUDRATE_Baud115200

void nrfkit_board_prepare_s115(void);
int nrfkit_board_start_s115_grtc(void);

#endif
