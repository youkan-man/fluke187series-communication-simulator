import unittest

from fluke187_simulator import Fluke187Simulator


class _FakeSerial:
    def __init__(self, incoming: bytes):
        self._incoming = incoming
        self.written = bytearray()

    def readline(self):
        value = self._incoming
        self._incoming = b""
        return value

    def write(self, data: bytes):
        self.written.extend(data)


class Fluke187SimulatorTests(unittest.TestCase):
    def test_process_known_commands(self):
        sim = Fluke187Simulator()

        self.assertEqual(sim.process_command("*IDN?"), "FLUKE,187,SIM,1.0")
        self.assertEqual(sim.process_command("meas:volt?"), "12.34")
        self.assertEqual(sim.process_command("SYST:ERR?"), "0,No error")

    def test_process_unknown_command(self):
        sim = Fluke187Simulator()
        self.assertEqual(sim.process_command("FOO?"), "ERR:UNKNOWN COMMAND")

    def test_serve_once_reads_and_writes_ascii_line(self):
        sim = Fluke187Simulator()
        fake = _FakeSerial(b"ID?\r\n")

        response = sim.serve_once(fake)

        self.assertEqual(response, "FLUKE,187,SIM,1.0")
        self.assertEqual(fake.written, b"FLUKE,187,SIM,1.0\r\n")


if __name__ == "__main__":
    unittest.main()
