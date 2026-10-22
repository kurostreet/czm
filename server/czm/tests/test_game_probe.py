import unittest
from unittest.mock import patch
from czm import game_probe

class GameProbeTests(unittest.TestCase):
    def test_source_info(self):
        payload=(b"\xff"*4+b"I"+bytes([48])+b"Good Server\x00"
                 +b"zm_example\x00"+b"cstrike\x00"+b"Counter Strike\x00"
                 +bytes([10,0,20,32,0])+b"dlw\x00")
        data=game_probe.decode(payload)
        self.assertEqual((data["players"],data["max_players"],data["map"]),(20,32,"zm_example"))

    def test_goldsrc_info(self):
        payload=(b"\xff"*4+b"m"+b"1.2.3.4:27015\x00"+b"Gold\x00"
                 +b"ze_test\x00"+b"cstrike\x00"+b"Counter Strike\x00"
                 +bytes([12,32,48]))
        self.assertEqual(game_probe.decode(payload)["players"],12)

    def test_reject_malformed(self):
        for data in [b"",b"\xff"*4+b"I",b"\xff"*4+b"I"+bytes([1])+b"ab",
                     b"\xff"*4+b"I"+bytes([48])+b"x\x00m\x00wrong\x00x\x00"+bytes([10,0,5,32,0]),
                     b"\xfe"*4+b"I"+bytes([48])]:
            with self.assertRaises(game_probe.ProbeError):
                game_probe.decode(data)

    def test_blocks_internal_destinations(self):
        for address in ["127.0.0.1:27015","10.0.0.1:27015","192.168.0.1:27015",
                        "169.254.1.1:27015","203.0.113.5:27015","8.8.8.8:0"]:
            with self.assertRaises(game_probe.ProbeError):
                game_probe.probe(address)
