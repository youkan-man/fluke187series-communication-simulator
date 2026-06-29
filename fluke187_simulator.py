"""Fluke 187 series serial communication simulator."""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


ACK_OK = "0\r"
ACK_ERROR = "1\r"

DEFAULT_IDENTITY = "FLUKE 187,V1.00,SIM000001"

# 仕様上のQM例・単位候補に寄せて、VDCではなく V DC にしておく
DEFAULT_PRIMARY_READING = "+12.34 V DC"

VALID_KEY_CODES = {
    "10", "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30",
}


class ReadingMode(str, Enum):
    FIXED = "fixed"
    RANDOM = "random"


@dataclass(frozen=True)
class ReadingProfile:
    unit: str
    min_value: float
    max_value: float
    decimals: int = 2
    allow_negative: bool = True
    out_of_range_probability: float = 0.0


DEFAULT_RANDOM_PROFILES: Dict[str, ReadingProfile] = {
    "voltage_dc": ReadingProfile("V DC", -60.0, 60.0, 2),
    "voltage_ac": ReadingProfile("V AC", 0.0, 250.0, 2, allow_negative=False),
    "millivoltage_dc": ReadingProfile("mV DC", -999.0, 999.0, 2),
    "millivoltage_ac": ReadingProfile("mV AC", 0.0, 999.0, 2, allow_negative=False),
    "ohms": ReadingProfile("Ohms", 0.0, 9999.0, 2, allow_negative=False),
    "kohms": ReadingProfile("KOhms", 0.0, 999.0, 2, allow_negative=False),
    "hz": ReadingProfile("Hz", 45.0, 65.0, 2, allow_negative=False),
    "deg_c": ReadingProfile("Deg C", -20.0, 80.0, 1),
    "duty": ReadingProfile("%", 0.0, 100.0, 1, allow_negative=False),
}


@dataclass
class Fluke187Simulator:
    """Fluke 187 remote interface simulator."""

    identity: str = DEFAULT_IDENTITY
    default_primary_reading: str = DEFAULT_PRIMARY_READING
    reading_mode: ReadingMode = ReadingMode.FIXED
    random_profile_name: str = "voltage_dc"
    seed: Optional[int] = None

    fixed_function_readings: Dict[str, str] = field(
        default_factory=lambda: {
            # Hz
            "16": "+60.00 Hz",

            # Range / Down Arrow は実機では状態遷移だが、シミュレータでは表示値変化として扱う
            "17": "+12.34 V DC",
            "18": "+123.40 mV DC",

            # Setup / Save は本来表示値とは限らないが、テスト用に現状維持でOK
            "29": "+12.34 V DC",
            "30": "+12.34 V DC",
        }
    )

    key_profile_map: Dict[str, str] = field(
        default_factory=lambda: {
            "16": "hz",
            "17": "voltage_dc",
            "18": "millivoltage_dc",
        }
    )

    random_profiles: Dict[str, ReadingProfile] = field(
        default_factory=lambda: dict(DEFAULT_RANDOM_PROFILES)
    )

    primary_reading: str = field(init=False)
    _random: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._random = random.Random(self.seed)
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
            if self.reading_mode == ReadingMode.RANDOM:
                self.primary_reading = self.generate_random_reading()
            return f"{ACK_OK}QM,{self.primary_reading}\r"

        if normalized.startswith("SF "):
            key_code = normalized[3:].strip()

            if key_code not in VALID_KEY_CODES:
                return ACK_ERROR

            self.apply_set_function(key_code)
            return ACK_OK

        return ACK_ERROR

    def apply_set_function(self, key_code: str) -> None:
        if self.reading_mode == ReadingMode.FIXED:
            self.primary_reading = self.fixed_function_readings.get(
                key_code,
                self.primary_reading,
            )
            return

        profile_name = self.key_profile_map.get(key_code, self.random_profile_name)
        self.primary_reading = self.generate_random_reading(profile_name)

    def generate_random_reading(self, profile_name: Optional[str] = None) -> str:
        name = profile_name or self.random_profile_name
        profile = self.random_profiles.get(name)

        if profile is None:
            profile = self.random_profiles["voltage_dc"]

        if (
            profile.out_of_range_probability > 0.0
            and self._random.random() < profile.out_of_range_probability
        ):
            return f"Out of Range {profile.unit}"

        value = self._random.uniform(profile.min_value, profile.max_value)

        if not profile.allow_negative:
            value = abs(value)

        sign = "+" if value >= 0 else "-"
        magnitude = abs(value)

        return f"{sign}{magnitude:.{profile.decimals}f} {profile.unit}"

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


def run_serial_simulator(
    port: str,
    baudrate: int = 9600,
    timeout: float = 1.0,
    reading_mode: ReadingMode = ReadingMode.FIXED,
    random_profile_name: str = "voltage_dc",
    seed: Optional[int] = None,
) -> None:
    try:
        import serial  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "pyserial is required to run the serial simulator. "
            "Install it with: pip install pyserial"
        ) from exc

    simulator = Fluke187Simulator(
        reading_mode=reading_mode,
        random_profile_name=random_profile_name,
        seed=seed,
    )

    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
    ) as conn:
        while True:
            simulator.serve_once(conn)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fluke 187 serial communication simulator"
    )

    parser.add_argument(
        "--port",
        required=True,
        help="Serial port path, for example /dev/ttyUSB0 or COM3",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=9600,
        help="Baud rate",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Serial read timeout seconds",
    )
    parser.add_argument(
        "--reading-mode",
        choices=[mode.value for mode in ReadingMode],
        default=ReadingMode.FIXED.value,
        help="fixed: deterministic readings, random: randomized QM readings",
    )
    parser.add_argument(
        "--random-profile",
        default="voltage_dc",
        choices=sorted(DEFAULT_RANDOM_PROFILES.keys()),
        help="Random reading profile used when --reading-mode random",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible random readings",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    run_serial_simulator(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        reading_mode=ReadingMode(args.reading_mode),
        random_profile_name=args.random_profile,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()