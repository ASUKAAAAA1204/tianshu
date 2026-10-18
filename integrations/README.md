# MAVLink SITL adapter

This is a read-only first-phase integration for ArduPilot SITL. It listens for
MAVLink telemetry, maps it to the Liangping normalized telemetry contract, and
posts to the controlled `POST /api/missions/{mission_id}/telemetry` endpoint.

No arming, takeoff, landing, mode change, return-to-home, or route command is
implemented here. Use `--fixture` to verify the platform contract before SITL
is available, then use `--connection udp:127.0.0.1:14550` for SITL.
