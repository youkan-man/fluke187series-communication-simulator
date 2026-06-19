import unittest

from fluke187_simulator import ACK_ERROR, ACK_OK, DEFAULT_IDENTITY, Fluke187Simulator


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
        self.assertEqual(sim.execute_command("ID\r"), f"{ACK_OK}{DEFAULT_IDENTITY}\r")

    def test_qm_command_prefixes_measurement_with_command_name(self):
        sim = Fluke187Simulator()
        self.assertEqual(sim.execute_command("QM\r"), f"{ACK_OK}QM,+12.34 VDC\r")

    def test_ds_resets_measurement_state(self):
        sim = Fluke187Simulator()
        sim.execute_command("SF 16\r")

        self.assertEqual(sim.execute_command("QM\r"), f"{ACK_OK}QM,+60.00 Hz\r")
        self.assertEqual(sim.execute_command("DS\r"), ACK_OK)
        self.assertEqual(sim.execute_command("QM\r"), f"{ACK_OK}QM,+12.34 VDC\r")

    def test_sf_rejects_undefined_key_codes(self):
        sim = Fluke187Simulator()
        self.assertEqual(sim.execute_command("SF 24\r"), ACK_ERROR)

    def test_serve_once_reads_and_writes_cr_terminated_protocol(self):
        sim = Fluke187Simulator()
        fake = _FakeSerial(b"QM\r")

        response = sim.serve_once(fake)

        self.assertEqual(response, f"{ACK_OK}QM,+12.34 VDC\r")
        self.assertEqual(fake.written, b"0\rQM,+12.34 VDC\r")


if __name__ == "__main__":
    unittest.main()
