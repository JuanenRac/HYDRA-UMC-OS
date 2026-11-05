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

## Nothing is open, not even the health routes

With the key on, every route asks for an identity, `GET /health` and `GET /stats` (the health path of a service) included, and from this machine too. The two health routes keep their own switches: `/health` still answers `404` until its switch opens it. The rule when the key is off is the one of every service today.

A container health check that used to read `/stats` or `/health` without a credential can no longer do that once the key is on. The Python services carry a probe that signs a short-lived token of its own (role `viewer`, sixty seconds) with the key file the service already holds, so nothing is pasted and nothing leaves the machine:

```
python -m hydra_umc_<service>.server_identity probe --port PORT [--path /health] --key-file /etc/hydra-umc/<service>-identity.key
```

It exits `0` when the service answers `200`. A `HEALTHCHECK` or a `healthcheck.test` in a compose file runs that command instead of `urlopen('http://127.0.0.1:PORT/stats')`; a systemd watchdog does the same. The Go and Rust services have no probe of their own: use `curl` with a token signed by the probe of any Python service of the same machine, or the token of the service itself (`--token`), which they also accept. Without the key nothing changes and the earlier health checks keep working.

The calls that the SERVER makes to a service (the family status and the health probes, the relays to the AI, data and speech services, the stop relay, the takeover, the reload of the job dispatcher) carry the token of the SERVER when its own switch is on: `auth.serviceIdentity.enabled` of Server Admin (or `HYDRA_UMC_SERVICE_IDENTITY=1`), off by default. The server signs one short token (HS256, sixty seconds, the role the request needs) with its `JWT_SECRET`; a service that has a token of its own keeps receiving that one. The two halves of the switch are separate on purpose, and the order matters:

1. **The SERVER first.** Turn `auth.serviceIdentity.enabled` on in Server Admin of STUDIO or SUITE (it asks for a confirmation), or set `HYDRA_UMC_SERVICE_IDENTITY=1` in `/etc/hydra-umc/server.env` and restart the server. The screen "Identity of the services" says whether the server is presenting its token (`presenting`) or cannot (`idle_no_key`: `JWT_SECRET` is unset, an example value or too short).
2. **Then one service at a time.** On the machine, as root: `python3 provisioning/service_identity.py --enable NAME` (a dry run), then again with `--apply`; restart that unit; `--status` lists which services have it on. Check that the family status still shows the service as `ok`, and go on to the next one.
3. **Back out the same way, in the opposite order.** `--disable NAME --apply` and a restart for the services first; turn the switch of the server off last. With the switch of the server off and a key still on in a service, the service refuses the server.

Nothing in the SERVER can run step 2: the key is handed out as a file by root on the machine, and the API of the server never does it.

## Services that take it

All of them read the key from a file (`config/service_identity.json` lists the unit, the variable and the group of each one) and accept the token of the server next to their own token:

* Python on the standard library server: COGNITIVE-NODE, VISION-NODE, VLA-ENGINE, ANOMALY-DETECTOR, DATALAKE, DETECTION-HEF, DOCS-QA, PRODUCTION-REPORTS, SAFETY-ZONES, SEMANTIC-PLANNER, VISUAL-SERVOING-API and DEV-SERVER (one canonical copy, `server_identity.py` of the SDK).
* Go: JOB-DISPATCHER and TELEMETRY-COLLECTOR (a verifier of the same format and with the same checks).
* Rust: ORCHESTRATOR, HIL-BRIDGE and TWIN (a verifier of the same format and with the same checks; the interlock routes of the twin keep asking for the certify token).

Left, each with its reason:

* CONNECTOR-HUB takes the token of the server too, from the same key file and variable as the others (`HYDRA_UMC_CONNECTOR_HUB_IDENTITY_KEY_FILE`), and keeps its own verifier next to it: it already refuses every caller without a signed token (the gate service has no off position) and it also takes the EdDSA key set of the server, which the shared copy does not.
* The gRPC health service of JOB-DISPATCHER and ORCHESTRATOR keeps its own token.
* The gateway and its broker credentials (`GATEWAY_JWT_SECRET`, MQTT, OPC UA administrator) are a different kind of secret and follow `generate_secrets.py`; whether they should also take the server's identity is a decision for the owner. The design that is proposed: the gateway verifies the same token as the other services, and the broker and OPC UA credentials stay what they are because a field device cannot sign in.
