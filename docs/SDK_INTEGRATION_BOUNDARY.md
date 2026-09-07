<!-- =============================================================================
HYDRA-UMC-OS - SDK interoperability boundary
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-SDK interoperability boundary

HYDRA-UMC-OS and HYDRA-UMC-SDK are independent repositories and releases. OS
does not import the SDK package, vendor its source, or require its checkout at
runtime. The shared boundary is a published contract name and schema version.

OS emits self-contained `DeviceDescriptor` and `HealthReport` JSON documents.
SDK owns the schema and validates OS producer fixtures in its own conformance
suite. Compatibility is proved by fixtures and tests, never a runtime project
dependency.

## Local workspace verification

With sibling `HYDRA-UMC-OS` and `HYDRA-UMC-SDK` checkouts, run:

```bash
python3 tools/verify_sdk_contracts.py
```

The command starts the read-only agent twice (`describe` and `health`) and
validates its JSON output with the SDK reference client. It does not change the
host, the project manifest, or either repository's version.
