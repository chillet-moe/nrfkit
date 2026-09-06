/* SPDX-License-Identifier: BSD-3-Clause */

#include <stddef.h>
#include <stdint.h>

#include <nrf_errno.h>
#include <nrfkit/sdc.h>
#include <sdc_hci_cmd_controller_baseband.h>
#include <sdc_hci_cmd_info_params.h>
#include <sdc_hci_cmd_link_control.h>
#include <sdc_hci_cmd_le.h>

#define HCI_STATUS_UNKNOWN_COMMAND UINT8_C(0x01)
#define HCI_STATUS_INVALID_PARAMETERS UINT8_C(0x12)
#define HCI_EVENT_COMMAND_COMPLETE UINT8_C(0x0e)
#define HCI_EVENT_COMMAND_STATUS UINT8_C(0x0f)

static void copy_bytes(uint8_t *destination, const void *source, size_t size)
{
    const uint8_t *bytes = source;
    for (size_t index = 0; index < size; ++index) {
        destination[index] = bytes[index];
    }
}

static uint8_t dispatch(uint16_t opcode,
                        const uint8_t *parameters,
                        size_t parameter_size,
                        uint8_t *return_parameters,
                        size_t *return_size,
                        uint8_t *command_status)
{
    *return_size = 0U;
    *command_status = 0U;
    switch (opcode) {
    case SDC_HCI_OPCODE_CMD_CB_RESET:
        return parameter_size == 0U ? sdc_hci_cmd_cb_reset() :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_IP_READ_LOCAL_VERSION_INFORMATION: {
        if (parameter_size != 0U) {
            return HCI_STATUS_INVALID_PARAMETERS;
        }
        sdc_hci_cmd_ip_read_local_version_information_return_t value;
        uint8_t const status =
            sdc_hci_cmd_ip_read_local_version_information(&value);
        if (status == 0U) {
            copy_bytes(return_parameters, &value, sizeof(value));
            *return_size = sizeof(value);
        }
        return status;
    }
    case SDC_HCI_OPCODE_CMD_IP_READ_LOCAL_SUPPORTED_FEATURES: {
        if (parameter_size != 0U) {
            return HCI_STATUS_INVALID_PARAMETERS;
        }
        sdc_hci_cmd_ip_read_local_supported_features_return_t value;
        uint8_t const status =
            sdc_hci_cmd_ip_read_local_supported_features(&value);
        if (status == 0U) {
            copy_bytes(return_parameters, &value, sizeof(value));
            *return_size = sizeof(value);
        }
        return status;
    }
    case SDC_HCI_OPCODE_CMD_LE_READ_LOCAL_SUPPORTED_FEATURES: {
        if (parameter_size != 0U) {
            return HCI_STATUS_INVALID_PARAMETERS;
        }
        sdc_hci_cmd_le_read_local_supported_features_return_t value;
        uint8_t const status =
            sdc_hci_cmd_le_read_local_supported_features(&value);
        if (status == 0U) {
            copy_bytes(return_parameters, &value, sizeof(value));
            *return_size = sizeof(value);
        }
        return status;
    }
    case SDC_HCI_OPCODE_CMD_CB_SET_EVENT_MASK:
        return parameter_size == sizeof(sdc_hci_cmd_cb_set_event_mask_t) ?
            sdc_hci_cmd_cb_set_event_mask((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_LE_SET_EVENT_MASK:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_event_mask_t) ?
            sdc_hci_cmd_le_set_event_mask((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_LE_SET_RANDOM_ADDRESS:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_random_address_t) ?
            sdc_hci_cmd_le_set_random_address((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
#if defined(NRFKIT_SDC_VARIANT_MULTIROLE) || defined(NRFKIT_SDC_VARIANT_PERIPHERAL)
    case SDC_HCI_OPCODE_CMD_LE_SET_ADV_PARAMS:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_adv_params_t) ?
            sdc_hci_cmd_le_set_adv_params((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_LE_SET_ADV_DATA:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_adv_data_t) ?
            sdc_hci_cmd_le_set_adv_data((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_LE_SET_ADV_ENABLE:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_adv_enable_t) ?
            sdc_hci_cmd_le_set_adv_enable((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
#endif
#if defined(NRFKIT_SDC_VARIANT_MULTIROLE) || defined(NRFKIT_SDC_VARIANT_CENTRAL)
    case SDC_HCI_OPCODE_CMD_LE_SET_SCAN_PARAMS:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_scan_params_t) ?
            sdc_hci_cmd_le_set_scan_params((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_LE_SET_SCAN_ENABLE:
        return parameter_size == sizeof(sdc_hci_cmd_le_set_scan_enable_t) ?
            sdc_hci_cmd_le_set_scan_enable((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    case SDC_HCI_OPCODE_CMD_LE_CREATE_CONN:
        *command_status = 1U;
        return parameter_size == sizeof(sdc_hci_cmd_le_create_conn_t) ?
            sdc_hci_cmd_le_create_conn((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
#endif
    case SDC_HCI_OPCODE_CMD_LC_DISCONNECT:
        *command_status = 1U;
        return parameter_size == sizeof(sdc_hci_cmd_lc_disconnect_t) ?
            sdc_hci_cmd_lc_disconnect((const void *)parameters) :
            HCI_STATUS_INVALID_PARAMETERS;
    default:
        return HCI_STATUS_UNKNOWN_COMMAND;
    }
}

int32_t nrfkit_sdc_hci_command(const uint8_t *command,
                               size_t command_size,
                               uint8_t *event,
                               size_t event_capacity,
                               size_t *event_size)
{
    if (command == NULL || event == NULL || event_size == NULL ||
        command_size < 3U || command_size != (size_t)command[2] + 3U ||
        event_capacity < 14U) {
        return -NRF_EINVAL;
    }
    uint16_t const opcode = (uint16_t)command[0] |
        ((uint16_t)command[1] << 8U);
    size_t return_size;
    uint8_t return_parameters[8];
    uint8_t command_status;
    uint8_t const status = dispatch(opcode, &command[3], command[2],
                                    return_parameters, &return_size,
                                    &command_status);
    if (command_status != 0U) {
        event[0] = HCI_EVENT_COMMAND_STATUS;
        event[1] = 4U;
        event[2] = status;
        event[3] = 1U;
        event[4] = command[0];
        event[5] = command[1];
        *event_size = 6U;
        return 0;
    }
    event[0] = HCI_EVENT_COMMAND_COMPLETE;
    event[1] = (uint8_t)(4U + return_size);
    event[2] = 1U;
    event[3] = command[0];
    event[4] = command[1];
    event[5] = status;
    copy_bytes(&event[6], return_parameters, return_size);
    *event_size = 6U + return_size;
    return 0;
}
