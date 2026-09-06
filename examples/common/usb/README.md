# USB example configuration

These files provide endpoint/FIFO configuration and CherryUSB core/class selection
for SDK examples and consumer tests. `reference.cmake` is included explicitly; it
is not part of the public CMake API or loaded by `find_package(NrfKit)`.

The actual built-in port is maintained under `src/usb/` and selected by linking
`NrfKit::usb_port`. Consumers may instead link a self-maintained local port target.
The installed package includes this example configuration and the selected
CherryUSB input so the source and installed SDK can run the same build checks.

The helper's `MPSL` option explicitly selects the shared-clock path. Endpoint
parameters generate an image-local `usb_config.h`. Applications own both choices;
SDK finalization does not infer them from the other linked capabilities.
