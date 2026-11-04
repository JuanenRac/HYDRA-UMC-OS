# One identity for the services: the signed token of HYDRA-UMC-SERVER

HYDRA-UMC-SERVER is the one issuer of identity of the family. Every other service used to keep a bearer token of its own, or none on loopback. A service can now also verify the signed token that the server issues at login, so a person or a program signs in once and the services ask the same issuer who is calling.

It is a switch, and it is off. Nothing about a service changes until an operator turns it on for that service.

## The design in short

* **Format.** The token is the one the server already issues: an HS256 JWT with the claims `username`, `role` (`admin`, `operator` or `viewer`) and `exp`. A service only verifies it; it never issues one.
* **Key.** The signing key of the server (`JWT_SECRET`, at least 32 characters). It is handed to a service as a file, never on the command line, readable only by the group of that service.
* **Switch.** `--identity-key-file FILE` on the service, or `HYDRA_UMC_<SERVICE>_IDENTITY_KEY_FILE`. Without it the service behaves exactly as before.
* **When it is on.** A valid token of the server is accepted next to the token of the service. A viewer may read but not change (`admin` and `operator` may). A request with no credential is refused, even on loopback and even on a service that had no token: the switch is how an operator closes a service that was open on loopback. An address that is not loopback no longer needs a token of the service.
* **What is checked.** The algorithm is exactly HS256 (`none` and any other are refused), the signature (constant time), a present and future `exp`, an `nbf` that has passed, a user name and a known role.
* **What is not.** A revocation the server keeps on its side (a changed password, a deleted account) cannot be seen by a service: keep `JWT_EXPIRES_IN` short for the accounts that call services. The signature is symmetric, so a service that can verify a token could forge one; that is why the key file is private to the group of the service. A change to an asymmetric signature would remove that limit and is a decision of the server, not of the services.

## Where each part lives

| Part | Where |
| --- | --- |
| The verifier for Python services (one canonical copy) | `tools/canonical/server_identity.py` of HYDRA-UMC-SDK, vendored by `tools/sync_repo_tools.py` |
| The key and the switch of a deployment | `provisioning/service_identity.py` of this repository, with the services listed in `config/service_identity.json` |
| The key itself | `JWT_SECRET` of `/etc/hydra-umc/server.env`, made by `provisioning/generate_secrets.py` |

`provisioning/service_identity.py --enable NAME ...` copies the key of the server into `/etc/hydra-umc/<name>-identity.key` (mode 0640, group of the service) and writes a systemd drop-in `20-server-identity.conf` that sets the variable of the service. `--disable NAME ...` renames the drop-in to `.conf.off`; `--status` lists which services have it on. It runs as a dry run unless `--apply` is given, never prints the key and refuses a server env file whose `JWT_SECRET` is missing, empty, an example value or too short. Restart the unit after changing the switch.

## Services that take it today and the batch that is left

Done: HYDRA-UMC-COGNITIVE-NODE, HYDRA-UMC-VISION-NODE and HYDRA-UMC-VLA-ENGINE (Python, standard library HTTP server).

Left, in the order they should follow (each one is a small change with its own tests: add the service to `PER_REPOSITORY_FILES` in the SDK, call `accepts(handler, token, key)` where the token is compared, add `--identity-key-file`, add the service to `config/service_identity.json`):

* Python on the standard library server: ANOMALY-DETECTOR, DATALAKE, DETECTION-HEF, DOCS-QA, PRODUCTION-REPORTS, SAFETY-ZONES, SEMANTIC-PLANNER, VISUAL-SERVOING-API, DEV-SERVER, CONNECTOR-HUB (the hub already verifies the same token with its own copy; move it to the canonical one).
* Go: JOB-DISPATCHER, TELEMETRY-COLLECTOR (a Go verifier of the same format, with the same tests).
* Rust: ORCHESTRATOR, HIL-BRIDGE, TWIN (a Rust verifier of the same format, with the same tests).
* The gateway and its broker credentials (`GATEWAY_JWT_SECRET`, MQTT, OPC UA administrator) are a different kind of secret and follow `generate_secrets.py`; whether they should also take the server's identity is a decision for the owner.
