# Contributing

## README translation parity (required)

Every change to `README.md` that affects content, structure, diagrams, links,
badges, status, milestones, repository layout, relationships, or licensing
must be applied in the same change to `README_spa.md`, `README_fra.md`,
`README_ita.md`, `README_deu.md`, `README_zho.md`, and `README_jpn.md`.
The pull request is incomplete until all seven README files have equivalent
information in their respective languages.

Keep Raspberry Pi OS as the base: do not add custom kernels or replacements
for systemd, apt, NetworkManager, or official hardware APIs without an ADR.
Changes require tests, documentation, and a clear failure mode. Do not merge a
service that can issue MCU commands without SDK contracts and HIL coverage.
