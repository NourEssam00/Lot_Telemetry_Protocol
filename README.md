# UDP Telemetry 

This repository contains a lightweight UDP-based telemetry protocol
implementation and its accompanying Mini-RFC.

The protocol supports:
- Batched sensor data transmission
- Sequence-based loss and duplicate detection
- Optional ACK-based reliability
- Adaptive heartbeat monitoring
- Reordering of out-of-order packets
- Performance and CPU metrics collection

## Repository Structure

- `server/` : UDP telemetry server
- `sensors/` : Humidity and light sensor implementations
- `scripts/` : Reproducible experiment scripts
- `results/` : Experimental output artifacts

## Requirements

- Python 3.9+
- Linux (for tc netem)

## How to Run

### Start Server
```bash
python3 server/server_oop.py
