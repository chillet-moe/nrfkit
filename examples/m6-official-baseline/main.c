// SPDX-License-Identifier: BSD-3-Clause

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include <nrf.h>
#include <nrf_error.h>
#include <nrfkit/bm_port.h>
#include <nrfkit/board.h>
#include <nrfkit/radio.h>
#include <nrfkit/runtime.h>

#include <ble_gap.h>
#include <bm/bluetooth/ble_adv.h>
#include <bm/bluetooth/ble_qwr.h>
#include <bm/bluetooth/peer_manager/nrf_ble_lesc.h>
#include <bm/bluetooth/peer_manager/peer_manager.h>
#include <bm/bluetooth/peer_manager/peer_manager_handler.h>
#include <bm/bluetooth/services/ble_hids.h>
#include <bm/bluetooth/services/uuid.h>
#include <bm/softdevice_handler/nrf_sdh.h>
#include <bm/softdevice_handler/nrf_sdh_ble.h>

#define DEVICE_NAME "nrfkit-m6-official"
#define READY_TOKEN "NRFKIT_M6_OFFICIAL READY\r\n"

BLE_ADV_DEF(ble_adv);
BLE_HIDS_DEF(ble_hids);
BLE_QWR_DEF(ble_qwr);

static uint8_t serial_token[sizeof(READY_TOKEN) - 1U] __attribute__((aligned(4)));
static uint16_t connection = BLE_CONN_HANDLE_INVALID;

volatile uint32_t nrfkit_m6_official_stage;
volatile uint32_t nrfkit_m6_official_result;
volatile uint32_t nrfkit_m6_official_security_successes;
volatile uint32_t nrfkit_m6_official_bond_updates;
volatile uint32_t nrfkit_m6_official_ble_events;
volatile uint32_t nrfkit_m6_official_last_ble_event;
volatile uint32_t nrfkit_m6_official_disconnect_reason;

static const uint8_t report_map[] = {
	0x05, 0x01, 0x09, 0x02, 0xA1, 0x01, 0x85, 0x01,
	0x09, 0x01, 0xA1, 0x00, 0x05, 0x09, 0x19, 0x01,
	0x29, 0x03, 0x15, 0x00, 0x25, 0x01, 0x75, 0x01,
	0x95, 0x03, 0x81, 0x02, 0x95, 0x01, 0x75, 0x05,
	0x81, 0x01, 0x05, 0x01, 0x09, 0x30, 0x09, 0x31,
	0x15, 0x81, 0x25, 0x7F, 0x75, 0x08, 0x95, 0x02,
	0x81, 0x06, 0xC0, 0xC0,
};

static void fail(uint32_t stage, uint32_t result)
{
	nrfkit_m6_official_stage = stage;
	nrfkit_m6_official_result = result;
	nrfkit_assert_fail();
}

static void write_ready_token(void)
{
	memcpy(serial_token, READY_TOKEN, sizeof(serial_token));
	NRFKIT_VCOM_TX_GPIO->OUTSET = BIT(NRFKIT_VCOM_TX_PIN);
	NRFKIT_VCOM_TX_GPIO->PIN_CNF[NRFKIT_VCOM_TX_PIN] =
		(GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
		(GPIO_PIN_CNF_INPUT_Disconnect << GPIO_PIN_CNF_INPUT_Pos);
	NRFKIT_VCOM_UARTE->PSEL.TXD =
		(NRFKIT_VCOM_TX_PIN << UARTE_PSEL_TXD_PIN_Pos) |
		(NRFKIT_VCOM_TX_PORT << UARTE_PSEL_TXD_PORT_Pos);
	NRFKIT_VCOM_UARTE->BAUDRATE = NRFKIT_VCOM_BAUDRATE;
	NRFKIT_VCOM_UARTE->ENABLE = UARTE_ENABLE_ENABLE_Enabled;
	NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END = 0U;
	NRFKIT_VCOM_UARTE->DMA.TX.PTR = (uint32_t)(uintptr_t)serial_token;
	NRFKIT_VCOM_UARTE->DMA.TX.MAXCNT = sizeof(serial_token);
	NRFKIT_VCOM_UARTE->TASKS_DMA.TX.START = UARTE_TASKS_DMA_TX_START_START_Trigger;
	while (NRFKIT_VCOM_UARTE->EVENTS_DMA.TX.END == 0U) {
		__WFE();
	}
}

static uint16_t qwr_event(struct ble_qwr *qwr, const struct ble_qwr_evt *event)
{
	ARG_UNUSED(qwr);
	if (event->evt_type == BLE_QWR_EVT_ERROR) {
		nrfkit_m6_official_result = event->error.reason;
	}
	return BLE_GATT_STATUS_SUCCESS;
}

static void hids_event(struct ble_hids *hids, const struct ble_hids_evt *event)
{
	ARG_UNUSED(hids);
	if (event->evt_type == BLE_HIDS_EVT_ERROR) {
		nrfkit_m6_official_result = event->error.reason;
	}
}

static void application_ble_event(const ble_evt_t *event, void *context)
{
	ARG_UNUSED(context);
	++nrfkit_m6_official_ble_events;
	nrfkit_m6_official_last_ble_event = event->header.evt_id;
	if (event->header.evt_id == BLE_GAP_EVT_CONNECTED) {
		connection = event->evt.gap_evt.conn_handle;
		const uint32_t result = ble_qwr_conn_handle_assign(&ble_qwr, connection);
		if (result != NRF_SUCCESS) {
			nrfkit_m6_official_result = result;
		}
	} else if (event->header.evt_id == BLE_GAP_EVT_DISCONNECTED &&
		   connection == event->evt.gap_evt.conn_handle) {
		nrfkit_m6_official_disconnect_reason =
			event->evt.gap_evt.params.disconnected.reason;
		connection = BLE_CONN_HANDLE_INVALID;
	}
}
NRF_SDH_BLE_OBSERVER(application_ble_observer, application_ble_event, NULL, USER_LOW);

static void advertising_event(struct ble_adv *instance, const struct ble_adv_evt *event)
{
	ARG_UNUSED(instance);
	if (event->evt_type == BLE_ADV_EVT_ERROR) {
		nrfkit_m6_official_result = event->error.reason;
	}
}

static void peer_manager_event(const struct pm_evt *event)
{
	pm_handler_on_pm_evt(event);
	pm_handler_disconnect_on_sec_failure(event);
	pm_handler_flash_clean(event);
	if (event->evt_id == PM_EVT_CONN_SEC_SUCCEEDED) {
		++nrfkit_m6_official_security_successes;
	} else if (event->evt_id == PM_EVT_PEER_DATA_UPDATE_SUCCEEDED &&
		   event->peer_data_update_succeeded.flash_changed &&
		   event->peer_data_update_succeeded.data_id == PM_PEER_DATA_ID_BONDING) {
		++nrfkit_m6_official_bond_updates;
	}
}

static uint32_t peer_manager_start(void)
{
	uint32_t result = pm_init();
	if (result != NRF_SUCCESS) {
		return result;
	}
	ble_gap_sec_params_t security = {
		.bond = 1, .mitm = 0, .lesc = 1, .keypress = 0,
		.io_caps = BLE_GAP_IO_CAPS_DISPLAY_YESNO, .oob = 0,
		.min_key_size = 7, .max_key_size = 16,
		.kdist_own = { .enc = 1, .id = 1 },
		.kdist_peer = { .enc = 1, .id = 1 },
	};
	result = pm_sec_params_set(&security);
	return result == NRF_SUCCESS ? pm_register(peer_manager_event) : result;
}

static uint32_t hids_start(void)
{
	const struct ble_hids_report_config input_report = {
		.len = 3, .report_id = 1,
		.report_type = BLE_HIDS_REPORT_TYPE_INPUT,
		.sec_mode = {
			.read = BLE_GAP_CONN_SEC_MODE_ENC_NO_MITM,
			.write = BLE_GAP_CONN_SEC_MODE_ENC_NO_MITM,
			.cccd_write = BLE_GAP_CONN_SEC_MODE_ENC_NO_MITM,
		},
	};
	const struct ble_hids_config config = {
		.evt_handler = hids_event,
		.input_report_count = 1, .input_report = &input_report,
		.output_report_count = 0, .output_report = NULL,
		.feature_report_count = 0, .feature_report = NULL,
		.report_map = {
			.data = (uint8_t *)(uintptr_t)report_map,
			.len = sizeof(report_map),
		},
		.hid_information = {
			.bcd_hid = 0x0111, .b_country_code = 0,
			.flags = { .normally_connectable = 1, .remote_wake = 1 },
		},
		.included_services_count = 0, .included_services_array = NULL,
		.sec_mode = BLE_HIDS_CONFIG_SEC_MODE_DEFAULT_MOUSE,
	};
	return ble_hids_init(&ble_hids, &config);
}

int main(void)
{
	nrfkit_m6_official_stage = 1;
	if (nrfkit_radio_acquire(NRFKIT_RADIO_OWNER_BLE) != NRFKIT_RADIO_OK) {
		fail(1, NRF_ERROR_BUSY);
	}
	nrfkit_board_prepare_s115();
	if (nrfkit_board_start_s115_grtc() != 0) {
		fail(2, NRF_ERROR_TIMEOUT);
	}
	if (nrfkit_nrf_bm_irq_init() != 0) {
		fail(3, NRF_ERROR_INTERNAL);
	}
	uint32_t result = nrf_sdh_enable_request();
	if (result != NRF_SUCCESS) {
		fail(4, result);
	}
	result = nrf_sdh_ble_enable(CONFIG_NRF_SDH_BLE_CONN_TAG);
	if (result != NRF_SUCCESS) {
		fail(5, result);
	}
	ble_gap_conn_sec_mode_t name_write_security;
	BLE_GAP_CONN_SEC_MODE_SET_NO_ACCESS(&name_write_security);
	result = sd_ble_gap_device_name_set(&name_write_security,
		(const uint8_t *)DEVICE_NAME, sizeof(DEVICE_NAME) - 1U);
	if (result != NRF_SUCCESS) {
		fail(6, result);
	}
	result = peer_manager_start();
	if (result != NRF_SUCCESS) {
		fail(7, result);
	}
	const struct ble_qwr_config qwr_config = { .evt_handler = qwr_event };
	result = ble_qwr_init(&ble_qwr, &qwr_config);
	if (result != NRF_SUCCESS) {
		fail(8, result);
	}
	result = hids_start();
	if (result != NRF_SUCCESS) {
		fail(9, result);
	}
	ble_uuid_t advertised_service = {
		.uuid = BLE_UUID_HUMAN_INTERFACE_DEVICE_SERVICE,
		.type = BLE_UUID_TYPE_BLE,
	};
	const struct ble_adv_config advertising = {
		.adv_data = {
			.name_type = BLE_ADV_DATA_FULL_NAME,
			.flags = BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE,
		},
		.sr_data.uuid_lists.complete = {
			.uuid = &advertised_service, .len = 1,
		},
		.evt_handler = advertising_event,
		.conn_cfg_tag = CONFIG_NRF_SDH_BLE_CONN_TAG,
	};
	result = ble_adv_init(&ble_adv, &advertising);
	if (result != NRF_SUCCESS) {
		fail(10, result);
	}
	result = ble_adv_start(&ble_adv, BLE_ADV_MODE_FAST);
	if (result != NRF_SUCCESS) {
		fail(11, result);
	}
	nrfkit_m6_official_stage = 12;
	write_ready_token();
	for (;;) {
		(void)nrf_ble_lesc_request_handler();
		__WFE();
	}
}
