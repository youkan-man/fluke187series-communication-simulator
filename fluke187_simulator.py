"""Fluke 187 series serial communication simulator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Dict, Optional


ACK_OK = "0\r"
ACK_ERROR = "1\r"
DEFAULT_IDENTITY = "FLUKE 187,V1.00,SIM000001"
DEFAULT_PRIMARY_READING = "+12.34 VDC"
VALID_KEY_CODES = {
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "27",
    "28",
    "29",
    "30",
}


@dataclass
class Fluke187Simulator:
    """Fluke 187 remote interface simulator."""

    identity: str = DEFAULT_IDENTITY
    default_primary_reading: str = DEFAULT_PRIMARY_READING
    function_readings: Dict[str, str] = field(
        default_factory=lambda: {
            "16": "+60.00 Hz",
            "17": "+12.34 VDC",
            "18": "+12.34 VDC",
            "29": "+12.34 VDC",
            "30": "+12.34 VDC",
        }
    )
    primary_reading: str = field(init=False)

    def __post_init__(self) -> None:
        self.primary_reading = self.default_primary_reading

    def reset(self) -> None:
        self.primary_reading = self.default_primary_reading

    def execute_command(self, command: str) -> str:
        normalized = command.strip().upper()
        if not normalized:
            return ACK_ERROR

        if normalized == "DS":
            self.reset()
            return ACK_OK

        if normalized == "ID":
            return f"{ACK_OK}{self.identity}\r"

        if normalized == "RI":
            self.reset()
            return ACK_OK

        if normalized == "QM":
            return f"{ACK_OK}QM,{self.primary_reading}\r"

        if normalized.startswith("SF "):
            key_code = normalized[3:]
            if key_code not in VALID_KEY_CODES:
                return ACK_ERROR
            self.primary_reading = self.function_readings.get(key_code, self.primary_reading)
            return ACK_OK

        return ACK_ERROR

    def serve_once(self, serial_conn) -> Optional[str]:
        raw = serial_conn.read_until(b"\r")
        if not raw:
            return None

        command = raw.decode("ascii", errors="ignore").strip("\r\n")
        if not command:
            return None

        response = self.execute_command(command)
        serial_conn.write(response.encode("ascii"))
        return response


def run_serial_simulator(port: str, baudrate: int = 9600, timeout: float = 1.0) -> None:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required to run the serial simulator. Install it with: pip install pyserial"
        ) from exc

    simulator = Fluke187Simulator()
    with serial.Serial(port=port, baudrate=baudrate, bytesize=8, parity="N", stopbits=1, timeout=timeout) as conn:
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
