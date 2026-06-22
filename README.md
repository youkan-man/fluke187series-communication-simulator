# fluke187series-communication-simulator

Python-based Fluke 187 series communication simulator for serial port testing.

## What this app does

This app simulates the Fluke 187 remote interface over a serial port using:

- 9600 baud
- no parity
- 8 data bits
- 1 stop bit

The implemented command protocol follows the Fluke 189/187 remote interface note:

- `DS<CR>` → `0<CR>`
- `ID<CR>` → `0<CR>FLUKE 187,V1.00,SIM000001<CR>`
- `RI<CR>` → `0<CR>`
- `QM<CR>` → `0<CR>QM,+12.34 VDC<CR>`
- `SF <keycode><CR>` → `0<CR>` for supported key codes, otherwise `1<CR>`

## Run

```bash
python /home/runner/work/fluke187series-communication-simulator/fluke187series-communication-simulator/fluke187_simulator.py --port /dev/ttyUSB0
```

> Requires `pyserial` to access serial ports (`pip install pyserial`).

## Notes

- Commands are carriage-return terminated.
- Responses use the Fluke command acknowledge format:
  - `0<CR>` = success
  - `1<CR>` = syntax or generic error
