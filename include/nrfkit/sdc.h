/* SPDX-License-Identifier: BSD-3-Clause */

#ifndef NRFKIT_SDC_H
#define NRFKIT_SDC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum nrfkit_sdc_lfclk_source {
    NRFKIT_SDC_LFCLK_RC = 0,
    NRFKIT_SDC_LFCLK_XTAL = 1,
    NRFKIT_SDC_LFCLK_SYNTH = 2,
};

struct nrfkit_sdc_config {
    enum nrfkit_sdc_lfclk_source lfclk_source;
    uint16_t lfclk_accuracy_ppm;
    uint8_t rc_calibration_interval_250_ms;
    uint8_t rc_temperature_interval_count;
    uint16_t hfclk_startup_time_us;
};

struct nrfkit_sdc_fault_record {
    uint32_t magic;
    uint32_t source;
    uint32_t line;
};

#define NRFKIT_SDC_FAULT_MAGIC UINT32_C(0x53444346)
#define NRFKIT_SDC_FAULT_SOURCE_MPSL UINT32_C(1)
#define NRFKIT_SDC_FAULT_SOURCE_CONTROLLER UINT32_C(2)
#define NRFKIT_SDC_FAULT_SOURCE_ENTROPY UINT32_C(3)

extern volatile struct nrfkit_sdc_fault_record nrfkit_sdc_last_fault;

/**
 * Return the locked controller configuration's required memory size.
 *
 * The first call initializes SDC long-lived state, then releases MPSL. Later
 * enable calls must use the identical clock configuration because SDC has no
 * uninitialize operation.
 */
int32_t nrfkit_sdc_required_memory(const struct nrfkit_sdc_config *config,
                                   size_t *required_memory);

/**
 * Initialize MPSL and enable the compile-selected controller archive.
 *
 * The caller owns @p memory for the entire enabled lifetime. It must be
 * 8-byte aligned and at least the size returned by
 * nrfkit_sdc_required_memory().
 */
int32_t nrfkit_sdc_enable(const struct nrfkit_sdc_config *config,
                          void *memory,
                          size_t memory_size);

/** Run deferred MPSL/controller/Timeslot work from main context. */
void nrfkit_sdc_process(void);

/** Return true when controller output may be available. */
bool nrfkit_sdc_hci_pending(void);

/**
 * Dispatch one raw HCI command packet and encode its Command Complete event.
 *
 * @p command starts with the little-endian opcode and parameter length (the H4
 * packet-type byte is not included). The event uses the standard HCI event
 * packet format without an H4 packet-type byte.
 */
int32_t nrfkit_sdc_hci_command(const uint8_t *command,
                               size_t command_size,
                               uint8_t *event,
                               size_t event_capacity,
                               size_t *event_size);

/** Retrieve one controller event or ACL packet; returns -NRF_EAGAIN when empty. */
int32_t nrfkit_sdc_hci_get(uint8_t *packet, uint8_t *message_type);

/** Submit one raw HCI ACL packet to the controller. */
int32_t nrfkit_sdc_hci_acl_put(const uint8_t *packet);

/**
 * Disable the controller.
 *
 * MPSL remains alive until every SDK client releases it, including open
 * Timeslot sessions and HFCLK24M requests made through nrfkit/mpsl.h.
 */
int32_t nrfkit_sdc_disable(void);

#ifdef __cplusplus
}
#endif

#endif
