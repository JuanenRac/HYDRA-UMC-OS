# HYDRA-UMC-SDK interoperability boundary

HYDRA-UMC-OS and HYDRA-UMC-SDK are independent repositories and releases. OS
does not import the SDK package, vendor its source, or require its checkout at
runtime. The shared boundary is a published contract name and schema version.

OS emits self-contained `DeviceDescriptor` and `HealthReport` JSON documents.
SDK owns the schema and validates OS producer fixtures in its own conformance
suite. Compatibility is proved by fixtures and tests, never a runtime project
dependency.
