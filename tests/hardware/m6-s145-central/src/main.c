/* SPDX-License-Identifier: BSD-3-Clause */

#include <stdbool.h>
#include <stdint.h>

#include <ble.h>
#include <ble_gap.h>
#include <bm/bluetooth/ble_scan.h>
#include <bm/bluetooth/peer_manager/nrf_ble_lesc.h>
#include <bm/bluetooth/peer_manager/peer_manager.h>
#include <bm/softdevice_handler/nrf_sdh.h>
#include <bm/softdevice_handler/nrf_sdh_ble.h>
#include <nrf_error.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/logging/log_ctrl.h>

LOG_MODULE_REGISTER(nrfkit_m6_central, LOG_LEVEL_INF);

BLE_SCAN_DEF(scanner);

static uint16_t connection = BLE_CONN_HANDLE_INVALID;
static bool scan_after_delete;

static const char *phase_name(void)
{
    if (!IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_LESC)) {
        return "legacy";
    }
    return IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_BOND) ? "lesc-bond" : "lesc-no-bond";
}

static void result(const char *status, uint32_t error, uint32_t source,
                   uint32_t bonded, uint32_t lesc, uint32_t encrypted,
                   uint32_t own_enc, uint32_t own_id,
                   uint32_t peer_enc, uint32_t peer_id)
{
    LOG_INF("NRFKIT_M6_CENTRAL RESULT phase=%s status=%s error=%#x source=%u "
            "bonded=%u lesc=%u encrypted=%u own_enc=%u own_id=%u "
            "peer_enc=%u peer_id=%u", phase_name(), status, error, source,
            bonded, lesc, encrypted, own_enc, own_id, peer_enc, peer_id);
    log_flush();
}

static uint8_t io_capability(void)
{
    if (IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_IO_DISPLAY_YESNO)) {
        return BLE_GAP_IO_CAPS_DISPLAY_YESNO;
    }
    if (IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_IO_KEYBOARD_ONLY)) {
        return BLE_GAP_IO_CAPS_KEYBOARD_ONLY;
    }
    return BLE_GAP_IO_CAPS_NONE;
}

static uint32_t scan_start(void)
{
    uint32_t error = ble_scan_start(&scanner);
    if (error) {
        result("scan-failed", error, 0, 0, 0, 0, 0, 0, 0, 0);
    }
    return error;
}

static void on_pm_event(const struct pm_evt *event)
{
    switch (event->evt_id) {
    case PM_EVT_CONN_SEC_SUCCEEDED: {
        struct pm_conn_sec_status status = {0};
        uint32_t error = pm_conn_sec_status_get(event->conn_handle, &status);
        LOG_INF("NRFKIT_M6_CENTRAL SECURED phase=%s error=%#x procedure=%u "
                "data_stored=%u bonded=%u lesc=%u encrypted=%u",
                phase_name(), error, event->conn_sec_succeeded.procedure,
                event->conn_sec_succeeded.data_stored, status.bonded,
                status.lesc, status.encrypted);
        log_flush();
        break;
    }
    case PM_EVT_CONN_SEC_FAILED:
        result("security-failed", event->conn_sec_failed.error,
               event->conn_sec_failed.error_src, 0, 0, 0, 0, 0, 0, 0);
        break;
    case PM_EVT_PEERS_DELETE_SUCCEEDED:
        if (scan_after_delete) {
            scan_after_delete = false;
            (void)scan_start();
        }
        break;
    case PM_EVT_PEERS_DELETE_FAILED:
        result("bond-clear-failed", event->peers_delete_failed_evt.error,
               0, 0, 0, 0, 0, 0, 0, 0);
        break;
    default:
        break;
    }
}

static void on_ble_event(const ble_evt_t *event, void *context)
{
    (void)context;
    switch (event->header.evt_id) {
    case BLE_GAP_EVT_CONNECTED:
        connection = event->evt.gap_evt.conn_handle;
        if (pm_conn_secure(connection, false) != NRF_SUCCESS) {
            result("secure-start-failed", 1, 0, 0, 0, 0, 0, 0, 0, 0);
        }
        break;
    case BLE_GAP_EVT_AUTH_STATUS: {
        const ble_gap_evt_auth_status_t *status =
            &event->evt.gap_evt.params.auth_status;
        const bool encrypted = status->sm1_levels.lv2 || status->sm1_levels.lv3 ||
                               status->sm1_levels.lv4;
        result(status->auth_status == BLE_GAP_SEC_STATUS_SUCCESS ? "ok" : "auth-failed",
               status->auth_status, status->error_src, status->bonded, status->lesc,
               encrypted, status->kdist_own.enc, status->kdist_own.id,
               status->kdist_peer.enc, status->kdist_peer.id);
        break;
    }
    case BLE_GAP_EVT_DISCONNECTED:
        connection = BLE_CONN_HANDLE_INVALID;
        break;
    case BLE_GAP_EVT_PASSKEY_DISPLAY:
        if (event->evt.gap_evt.params.passkey_display.match_request) {
            uint32_t error = sd_ble_gap_auth_key_reply(
                event->evt.gap_evt.conn_handle, BLE_GAP_AUTH_KEY_TYPE_PASSKEY, NULL);
            if (error) {
                result("numeric-confirm-failed", error, 0, 0, 0, 0, 0, 0, 0, 0);
            }
        }
        break;
    default:
        break;
    }
}
NRF_SDH_BLE_OBSERVER(app_ble_observer, on_ble_event, NULL, USER_LOW);

static void on_scan_event(const struct ble_scan_evt *event)
{
    if (event->evt_type == BLE_SCAN_EVT_CONNECTING_ERROR) {
        result("connect-failed", event->connecting_err.reason, 0, 0, 0, 0, 0, 0, 0, 0);
    } else if (event->evt_type == BLE_SCAN_EVT_SCAN_TIMEOUT) {
        result("scan-timeout", 0, 0, 0, 0, 0, 0, 0, 0, 0);
    }
}

static uint32_t scanner_init(void)
{
    const struct ble_scan_config config = {
        .scan_params = {
            .active = 1,
            .interval = BLE_GAP_SCAN_INTERVAL_US_MIN * 6,
            .window = BLE_GAP_SCAN_WINDOW_US_MIN * 6,
            .filter_policy = BLE_GAP_SCAN_FP_ACCEPT_ALL,
            .timeout = 3000,
            .scan_phys = BLE_GAP_PHY_1MBPS,
        },
        .conn_params = BLE_SCAN_CONN_PARAMS_DEFAULT,
        .connect_if_match = true,
        .conn_cfg_tag = CONFIG_NRF_SDH_BLE_CONN_TAG,
        .evt_handler = on_scan_event,
    };
    uint32_t error = ble_scan_init(&scanner, &config);
    if (error) {
        return error;
    }
    const struct ble_scan_filter_data filter = {
        .name_filter = {.name = CONFIG_NRFKIT_M6_CENTRAL_TARGET_NAME},
    };
    error = ble_scan_filter_add(&scanner, BLE_SCAN_NAME_FILTER, &filter);
    if (error) {
        return error;
    }
    return ble_scan_filters_enable(&scanner, BLE_SCAN_NAME_FILTER, false);
}

int main(void)
{
    int error = nrf_sdh_enable_request();
    if (error) {
        result("softdevice-failed", (uint32_t)-error, 0, 0, 0, 0, 0, 0, 0, 0);
        goto idle;
    }
    error = nrf_sdh_ble_enable(CONFIG_NRF_SDH_BLE_CONN_TAG);
    if (error) {
        result("ble-failed", (uint32_t)error, 0, 0, 0, 0, 0, 0, 0, 0);
        goto idle;
    }
    uint32_t nrf_error = pm_init();
    if (nrf_error) {
        result("pm-init-failed", nrf_error, 0, 0, 0, 0, 0, 0, 0, 0);
        goto idle;
    }
    const ble_gap_sec_params_t security = {
        .bond = IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_BOND),
        .mitm = 0,
        .lesc = IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_LESC),
        .keypress = 0,
        .io_caps = io_capability(),
        .oob = 0,
        .min_key_size = 7,
        .max_key_size = 16,
        .kdist_own = {
            .enc = IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_OWN_ENC),
            .id = IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_OWN_ID),
        },
        .kdist_peer = {
            .enc = IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_PEER_ENC),
            .id = IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_PEER_ID),
        },
    };
    nrf_error = pm_sec_params_set(&security);
    if (!nrf_error) {
        nrf_error = pm_register(on_pm_event);
    }
    if (!nrf_error) {
        nrf_error = scanner_init();
    }
    if (nrf_error) {
        result("fixture-init-failed", nrf_error, 0, 0, 0, 0, 0, 0, 0, 0);
        goto idle;
    }

    LOG_INF("NRFKIT_M6_CENTRAL READY target=%s bond=%u lesc=%u io=%u "
            "own_enc=%u own_id=%u peer_enc=%u peer_id=%u",
            CONFIG_NRFKIT_M6_CENTRAL_TARGET_NAME,
            IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_BOND),
            IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_LESC), io_capability(),
            IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_OWN_ENC),
            IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_OWN_ID),
            IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_PEER_ENC),
            IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_KDIST_PEER_ID));
    if (IS_ENABLED(CONFIG_NRFKIT_M6_CENTRAL_CLEAR_BONDS)) {
        scan_after_delete = true;
        nrf_error = pm_peers_delete();
        if (nrf_error) {
            result("bond-clear-start-failed", nrf_error, 0, 0, 0, 0, 0, 0, 0, 0);
        }
    } else {
        (void)scan_start();
    }

idle:
    for (;;) {
        (void)nrf_ble_lesc_request_handler();
        log_flush();
        k_cpu_idle();
    }
}
