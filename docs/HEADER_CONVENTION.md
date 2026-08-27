<!--
=============================================================================
HYDRA-UMC-OS - Documentation header convention
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
CC BY-SA 4.0 - see LICENSE.md
=============================================================================
-->

# Header convention

Use this header at the beginning of new source and documentation files.

Executable `.sh` and `.bat` files must also print a visible banner at launch:
project name, script filename, concise operation, copyright, email and license.

| File type | Comment form | License line |
| --- | --- | --- |
| Source code, systemd, packaging | `#` or the native comment syntax | `GPL-3.0-or-later - see LICENSE` |
| Markdown documentation | `<!-- ... -->` | `CC BY-SA 4.0 - see LICENSE.md` |
| JSON / JSON Schema | No comment header; comments would invalidate JSON | Keep licensing in repository metadata and adjacent documentation. |

The second line must name the full project, never `HYDRA` alone, followed by a
short description of the file's responsibility.
