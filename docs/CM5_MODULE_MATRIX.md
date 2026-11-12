<!-- Printed by tools/verify_profiles.py --write from config/profiles and provisioning/install_plan.json; do not edit by hand. -->

# CM5 module matrix

Which service each profile declares. A profile is a declaration the preflight reads, never a switch: nothing here
installs or starts a service, and a capability under "Needs" is checked on the node before the profile is used.

| Service | Installer | base | control | dsi | fleet | industrial | laboratory | vision |
|---|---|---|---|---|---|---|---|---|
| `hydra-umc-agent` | `install_local_agent.sh` | yes | yes | yes | yes | yes | yes | yes |
| `hydra-umc-anomaly-detector` | `install_anomaly_detector.sh` |  |  |  |  |  | yes |  |
| `hydra-umc-datalake` | `install_datalake.sh` |  |  |  |  |  | yes |  |
| `hydra-umc-job-dispatcher` | `install_job_dispatcher.sh` |  |  |  |  | yes |  |  |
| `hydra-umc-node-healing` | `install_node_healing.sh` |  |  |  | yes |  |  |  |
| `hydra-umc-orchestrator` | `install_orchestrator.sh` |  |  |  | yes |  |  |  |
| `hydra-umc-safety-zones` | `install_safety_zones.sh` |  |  |  |  | yes |  |  |
| `hydra-umc-server` | `install_server.sh` |  | yes | yes | yes | yes | yes |  |
| `hydra-umc-swarm-sync` | `install_swarm_sync.sh` |  |  |  | yes |  |  |  |
| `hydra-umc-telemetry-collector` | `install_telemetry_collector.sh` |  |  |  |  |  | yes |  |
| **Needs** | | - | `cm5_mcu_adapter` | `dsi_display` | - | `industrial_network` | - | `camera`<br>`hailo` |
