import unittest

from fluke187_simulator import (
    ACK_ERROR,
    ACK_OK,
    DEFAULT_IDENTITY,
    DEFAULT_PRIMARY_READING,
    Fluke187Simulator,
    ReadingMode,
)


class _FakeSerial:
    def __init__(self, incoming: bytes):
        self._incoming = incoming
        self.written = bytearray()

    def read_until(self, expected: bytes):
        if expected not in self._incoming:
            value = self._incoming
            self._incoming = b""
            return value

        end = self._incoming.index(expected) + len(expected)
        value = self._incoming[:end]
        self._incoming = self._incoming[end:]
        return value

    def write(self, data: bytes):
        self.written.extend(data)


class Fluke187SimulatorTests(unittest.TestCase):
    def test_id_command_uses_cmd_ack_and_identity_string(self):
        sim = Fluke187Simulator()

        self.assertEqual(
            sim.execute_command("ID\r"),
            f"{ACK_OK}{DEFAULT_IDENTITY}\r",
        )

    def test_qm_command_prefixes_measurement_with_command_name(self):
        sim = Fluke187Simulator()

        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,{DEFAULT_PRIMARY_READING}\r",
        )

    def test_qm_accepts_lowercase_command(self):
        sim = Fluke187Simulator()

        self.assertEqual(
            sim.execute_command("qm\r"),
            f"{ACK_OK}QM,{DEFAULT_PRIMARY_READING}\r",
        )

    def test_empty_command_returns_error(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("\r"), ACK_ERROR)
        self.assertEqual(sim.execute_command(""), ACK_ERROR)

    def test_unknown_command_returns_error(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("ZZ\r"), ACK_ERROR)

    def test_ds_resets_measurement_state(self):
        sim = Fluke187Simulator()

        sim.execute_command("SF 16\r")

        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,+60.00 Hz\r",
        )

        self.assertEqual(sim.execute_command("DS\r"), ACK_OK)

        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,{DEFAULT_PRIMARY_READING}\r",
        )

    def test_ri_resets_measurement_state(self):
        sim = Fluke187Simulator()

        sim.execute_command("SF 16\r")

        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,+60.00 Hz\r",
        )

        self.assertEqual(sim.execute_command("RI\r"), ACK_OK)

        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,{DEFAULT_PRIMARY_READING}\r",
        )

    def test_sf_16_changes_measurement_to_hz_in_fixed_mode(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF 16\r"), ACK_OK)
        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,+60.00 Hz\r",
        )

    def test_sf_17_changes_measurement_to_voltage_dc_in_fixed_mode(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF 17\r"), ACK_OK)
        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,+12.34 V DC\r",
        )

    def test_sf_18_changes_measurement_to_millivoltage_dc_in_fixed_mode(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF 18\r"), ACK_OK)
        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,+123.40 mV DC\r",
        )

    def test_sf_rejects_not_used_key_codes(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF 24\r"), ACK_ERROR)
        self.assertEqual(sim.execute_command("SF 25\r"), ACK_ERROR)
        self.assertEqual(sim.execute_command("SF 26\r"), ACK_ERROR)

    def test_sf_rejects_out_of_range_key_codes(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF 09\r"), ACK_ERROR)
        self.assertEqual(sim.execute_command("SF 31\r"), ACK_ERROR)
        self.assertEqual(sim.execute_command("SF XX\r"), ACK_ERROR)

    def test_sf_requires_space_before_key_code(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF16\r"), ACK_ERROR)

    def test_sf_trims_extra_spaces_after_key_code(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.execute_command("SF 16   \r"), ACK_OK)
        self.assertEqual(
            sim.execute_command("QM\r"),
            f"{ACK_OK}QM,+60.00 Hz\r",
        )

    def test_serve_once_reads_and_writes_cr_terminated_protocol(self):
        sim = Fluke187Simulator()
        fake = _FakeSerial(b"QM\r")

        response = sim.serve_once(fake)

        self.assertEqual(response, f"{ACK_OK}QM,{DEFAULT_PRIMARY_READING}\r")
        self.assertEqual(
            fake.written,
            f"{ACK_OK}QM,{DEFAULT_PRIMARY_READING}\r".encode("ascii"),
        )

    def test_serve_once_returns_none_when_no_data(self):
        sim = Fluke187Simulator()
        fake = _FakeSerial(b"")

        response = sim.serve_once(fake)

        self.assertIsNone(response)
        self.assertEqual(fake.written, bytearray())

    def test_serve_once_returns_none_for_blank_command(self):
        sim = Fluke187Simulator()
        fake = _FakeSerial(b"\r")

        response = sim.serve_once(fake)

        self.assertIsNone(response)
        self.assertEqual(fake.written, bytearray())

    def test_random_mode_returns_valid_voltage_dc_shape(self):
        sim = Fluke187Simulator(
            reading_mode=ReadingMode.RANDOM,
            random_profile_name="voltage_dc",
            seed=123,
        )

        response = sim.execute_command("QM\r")

        self.assertTrue(response.startswith(f"{ACK_OK}QM,"))
        self.assertTrue(response.endswith(" V DC\r"))

        measurement = response.removeprefix(f"{ACK_OK}QM,").removesuffix("\r")
        self.assertRegex(measurement, r"^[+-]\d+\.\d{2} V DC$")

    def test_random_mode_with_same_seed_is_reproducible(self):
        sim1 = Fluke187Simulator(
            reading_mode=ReadingMode.RANDOM,
            random_profile_name="voltage_dc",
            seed=123,
        )
        sim2 = Fluke187Simulator(
            reading_mode=ReadingMode.RANDOM,
            random_profile_name="voltage_dc",
            seed=123,
        )

        self.assertEqual(
            sim1.execute_command("QM\r"),
            sim2.execute_command("QM\r"),
        )

    def test_random_mode_sf_16_uses_hz_profile(self):
        sim = Fluke187Simulator(
            reading_mode=ReadingMode.RANDOM,
            random_profile_name="voltage_dc",
            seed=123,
        )

        self.assertEqual(sim.execute_command("SF 16\r"), ACK_OK)

        response = sim.execute_command("QM\r")

        self.assertTrue(response.startswith(f"{ACK_OK}QM,"))
        self.assertTrue(response.endswith(" Hz\r"))

    def test_custom_identity_is_returned(self):
        sim = Fluke187Simulator(identity="FLUKE 187,V9.99,TESTSERIAL")

        self.assertEqual(
            sim.execute_command("ID\r"),
            f"{ACK_OK}FLUKE 187,V9.99,TESTSERIAL\r",
        )


if __name__ == "__main__":
    unittest.main()