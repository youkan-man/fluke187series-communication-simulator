"""Fluke 187 series serial communication simulator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Fluke187Simulator:
    """Line-based command simulator for a Fluke 187 style device."""

    measurements: Dict[str, str] = field(
        default_factory=lambda: {
            "MEAS:VOLT?": "12.34",
            "MEAS:OHM?": "1000.0",
            "MEAS:CURR?": "0.123",
        }
    )
    idn: str = "FLUKE,187,SIM,1.0"

    def process_command(self, command: str) -> str:
        normalized = command.strip().upper()
        if not normalized:
            return ""
        if normalized in {"*IDN?", "ID?"}:
            return self.idn
        if normalized == "SYST:ERR?":
            return "0,No error"
        if normalized in self.measurements:
            return self.measurements[normalized]
        return "ERR:UNKNOWN COMMAND"

    def serve_once(self, serial_conn) -> Optional[str]:
        raw = serial_conn.readline()
        if not raw:
            return None

        command = raw.decode("ascii", errors="ignore")
        response = self.process_command(command)
        if response:
            serial_conn.write((response + "\r\n").encode("ascii"))
        return response


def run_serial_simulator(port: str, baudrate: int = 9600, timeout: float = 1.0) -> None:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required to run the serial simulator. Install it with: pip install pyserial"
        ) from exc

    simulator = Fluke187Simulator()
    with serial.Serial(port=port, baudrate=baudrate, timeout=timeout) as conn:
        while True:
            simulator.serve_once(conn)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fluke 187 serial communication simulator")
    parser.add_argument("--port", required=True, help="Serial port path (for example /dev/ttyUSB0 or COM3)")
    parser.add_argument("--baudrate", type=int, default=9600, help="Baud rate")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout seconds")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_serial_simulator(port=args.port, baudrate=args.baudrate, timeout=args.timeout)


if __name__ == "__main__":
    main()
