# fluke187series-communication-simulator

Python-based Fluke 187 series communication simulator for serial port testing.

## What this app does

This app simulates the Fluke 187 remote interface over one or more serial ports using:

- 9600 baud by default
- no parity
- 8 data bits
- 1 stop bit

The implemented command protocol follows the Fluke 189/187 remote interface note:

- `DS<CR>` → `0<CR>`
- `ID<CR>` → `0<CR>FLUKE 187,V1.00,SIM000001<CR>`
- `RI<CR>` → `0<CR>`
- `QM<CR>` → `0<CR>QM,+12.34 V DC<CR>`
- `SF <keycode><CR>` → `0<CR>` for supported key codes, otherwise `1<CR>`

## Requirements

Serial access requires `pyserial`:

```bash
pip install pyserial
```

The web UI itself uses Python's standard library, but serial-port discovery and serial services need `pyserial`.

## Run a single console service

```bash
python fluke187_simulator.py --port /dev/ttyUSB0
```

Windows example:

```powershell
python fluke187_simulator.py --port COM3
```

## Run the web UI for multiple services

```bash
python fluke187_web.py --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> in a browser.

The web page provides a stacked service list:

- Existing service records stay visible after stop, so status, counters, and recent logs remain available.
- Stopped or errored records can be deleted with the delete button.
- New service settings are entered only from the final row at the bottom of the list.
- Serial ports discovered by `pyserial` are offered in a dropdown.
- Ports already present in the service list are hidden from the new-service dropdown until their record is deleted.
- If discovery is unavailable, enter a port manually, such as `COM3`, `/dev/ttyUSB0`, or a WSL-accessible serial path.
- Communication status includes service state, start/stop timestamps, request/response counters, last activity, errors, and recent bounded logs.

## Notes

- Commands are carriage-return terminated.
- Responses use the Fluke command acknowledge format:
  - `0<CR>` = success
  - `1<CR>` = syntax or generic error
- The service manager is intended for local development and hardware-mock testing on Windows, WSL, and Ubuntu; it is not hardened for public internet exposure.
