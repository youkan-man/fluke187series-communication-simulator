# fluke187series-communication-simulator

Python-based Fluke 187 series communication simulator for serial port testing.

## What this app does

This app simulates Fluke-187 series style communication over a serial port.
It accepts simple text commands and returns simulated responses.

## Run

```bash
python /home/runner/work/fluke187series-communication-simulator/fluke187series-communication-simulator/fluke187_simulator.py --port /dev/ttyUSB0
```

> Requires `pyserial` to access serial ports (`pip install pyserial`).

## Example commands

- `ID?` or `*IDN?` → `FLUKE,187,SIM,1.0`
- `MEAS:VOLT?` → `12.34`
- `MEAS:OHM?` → `1000.0`
- `MEAS:CURR?` → `0.123`
- `SYST:ERR?` → `0,No error`
