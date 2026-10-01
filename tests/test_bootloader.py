"""Offline protocol/error-path tests. Never opens a real HID device."""
import struct
import unittest
from unittest.mock import patch
from apex3_tkl import bootloader as updater, firmware as fw
from tests.support import synthetic_stock


class FakeHid:
    """In-memory transport only; cannot open or enumerate a USB device."""
    def __init__(self, original, fail_once=False, corrupt_first=False):
        self.image = bytearray(original)
        self.replies = []
        self.erases = 0
        self.writes = 0
        self.fail_once = fail_once
        self.corrupt_first = corrupt_first

    def write(self, packet):
        assert len(packet) == 65 and packet[0] == 0
        request = packet[1:]
        assert request[1:3] == b'\x00\x00'
        if request[0] == 2:
            self.image[:] = bytes([255])*len(self.image)
            self.erases += 1
            self.replies.append(bytes([2,0])+bytes(62))
        elif request[0] == 3:
            size, offset = struct.unpack_from('<HI', request, 3)
            assert size % 4 == 0 and offset % 4 == 0
            assert 0 < size <= 52 and offset+size <= updater.APP_SIZE
            if self.fail_once and offset > 1024:
                self.fail_once = False
                raise IOError('Simulated transport failure during target write')
            chunk = request[9:9+size]
            self.image[offset:offset+size] = chunk
            if self.corrupt_first and self.erases == 1 and offset == 0:
                self.image[4] ^= 1
            self.writes += 1
        elif request[0] == 0x83:
            size, offset = struct.unpack_from('<HI', request, 3)
            self.replies.append(bytes([0x83,0])+bytes(self.image[offset:offset+size])+bytes(62-size))
        elif request[0] == 0x84:
            self.replies.append(bytes([0x84,0])+struct.pack('<II', updater.crc(self.image),
                struct.unpack_from('<I',self.image,len(self.image)-4)[0])+bytes(54))
        else:
            raise AssertionError(f'Unexpected command {request[0]:02x}')
        return len(packet)

    def read(self, size, timeout):
        return self.replies.pop(0) if self.replies else []


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.original = synthetic_stock()
        mock_hash = patch.object(fw, 'STOCK_SHA256', fw.digest(self.original))
        mock_hash.start()
        self.addCleanup(mock_hash.stop)
        rollback_hash = patch.object(updater, 'STOCK_SHA256', fw.digest(self.original))
        rollback_hash.start()
        self.addCleanup(rollback_hash.stop)
        self.candidate = fw.build_image(self.original, fw.parse_color('123456'))
        self.boot = updater.Bootloader.__new__(updater.Bootloader)
        self.fake = FakeHid(self.original)
        self.boot.handle = self.fake
        self.boot.stock = self.original
        self.sleep = patch('apex3_tkl.bootloader.time.sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def test_program_and_full_readback(self):
        self.boot.program(self.candidate)
        self.assertEqual(bytes(self.fake.image), self.candidate)
        self.assertEqual(self.fake.erases, 1)
        self.assertEqual(self.fake.writes, (updater.APP_SIZE+51)//52)

    def test_write_failure_restores_exact_stock(self):
        self.fake.fail_once = True
        result = {}
        returned = updater.program_with_rollback(self.boot,self.candidate,self.original,result)
        self.assertEqual(returned,self.original)
        self.assertEqual(bytes(self.fake.image),self.original)
        self.assertEqual(self.fake.erases,2)
        self.assertTrue(result['stock_rollback_verified'])

    def test_crc_failure_restores_exact_stock(self):
        self.fake.corrupt_first = True
        result = {}
        updater.program_with_rollback(self.boot,self.candidate,self.original,result)
        self.assertEqual(bytes(self.fake.image),self.original)
        self.assertTrue(result['stock_rollback_verified'])

    def test_wake_failure_restores_previous_green(self):
        previous = fw.build_image(self.original, fw.parse_color('00FF00'), wake_fix=False)
        self.fake.fail_once = True
        result = {}
        returned = updater.program_with_rollback(self.boot,self.candidate,previous,result)
        self.assertEqual(returned,previous)
        self.assertEqual(bytes(self.fake.image),previous)
        self.assertTrue(result['rollback_verified'])
        self.assertFalse(result['stock_rollback_verified'])
        self.assertEqual(result['rollback_sha256'],fw.digest(previous))

    def test_rejects_unreviewed_image_and_out_of_bounds_commands(self):
        for request in (b'\x03\x00\x01'+struct.pack('<HI',4,0)+bytes(4),
                        b'\x03\x00\x00'+struct.pack('<HI',4,updater.APP_SIZE)+bytes(4),
                        b'\x03\x00\x00'+struct.pack('<HI',4,1)+bytes(4),
                        b'\x02\x00\x01', b'\x13'):
            with self.assertRaises(ValueError):
                self.boot.send(request)
        with self.assertRaises(ValueError):
            self.boot.program(bytes(updater.APP_SIZE))
        self.assertEqual(self.fake.erases,0)
        self.assertEqual(self.fake.writes,0)

    def test_failed_rollback_does_not_claim_verified_firmware(self):
        result = {}
        with patch.object(self.boot, 'program', side_effect=IOError('Device disconnected')):
            with self.assertRaises(IOError):
                updater.program_with_rollback(self.boot,self.candidate,self.original,result)
        self.assertTrue(result['firmware_erase_or_write_attempted'])
        self.assertNotIn('stock_rollback_verified',result)
        self.assertNotIn('full_readback_and_crc_verified',result)


if __name__ == '__main__':
    unittest.main()
