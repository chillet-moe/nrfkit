# Changelog

All notable changes to this project are documented in this file.

## 0.1.0-rc.2 - 2026-09-05

- Fix cold-start SDC initialization by preparing GRTC before enabling
  SYSCOUNTER.

## 0.1.0-rc.1 - 2026-09-05

First release candidate for the nRF54LM20A application core:

- pure-CMake Clang/LLD and GNU Arm build paths with C and C++23 firmware support;
- traceable startup, system initialization, linker, nrfx, CherryUSB, MPSL, and
  SoftDevice Controller inputs;
- guarded image inspection, application-RRAM programming, reset, serial, GDB,
  USB, raw-HCI, and dual-board radio validation workflows;
- target-scoped LM20 nrfx, USBHS HID, SDC/MPSL, and 1/2/4 Mbit proprietary-radio
  integration, including MPSL Timeslot coexistence;
- source-tree and installed-package consumers, with a reproducible offline TGZ
  package containing the supported dependency closure.

This is an experimental prerelease. It supports only the nRF54LM20A application
core. Open BLE Host/profile support and production boot/provisioning are outside
this release. USB remote wake, external-instrument power measurements, and product
key-matrix input validation remain deferred and are not claimed.
