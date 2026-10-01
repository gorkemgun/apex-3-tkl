import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from apex3_tkl import cli, firmware as fw
from tests.support import synthetic_stock


class FirmwareTests(unittest.TestCase):
    def setUp(self):
        self.stock = synthetic_stock()
        mocked_hash = patch.object(fw, "STOCK_SHA256", fw.digest(self.stock))
        mocked_hash.start()
        self.addCleanup(mocked_hash.stop)

    def test_color_parser_rejects_ambiguous_inputs(self):
        self.assertEqual(fw.parse_color("#12aBcD"), bytes([18, 171, 205]))
        for value in ("fff", "ff ff ff", "##FFFFFF", "00FF00\n", "gg0000", "00000000"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                fw.parse_color(value)

    def test_supported_images_round_trip_and_keep_key_tables(self):
        for color in ("000000", "FFFFFF", "00FF00", "123456", "010101"):
            for wake_fix in (False, True):
                image = fw.build_image(self.stock, fw.parse_color(color), wake_fix)
                info = fw.identify_image(self.stock, image)
                self.assertEqual(info["color"], "#" + color)
                self.assertEqual(info["wake_fix"], wake_fix)
                self.assertEqual(image[0x5EE8:0x6088], self.stock[0x5EE8:0x6088])
                self.assertEqual(len(image), fw.APP_SIZE)

    def test_rejects_code_or_endpoint_tampering_even_with_repaired_crc(self):
        image = fw.build_image(self.stock, b"\x12\x34\x56")
        for offset in (0, 0x5F29, fw.CALL_SITE - fw.BASE, fw.HELPER - fw.BASE,
                       fw.HELPER - fw.BASE + 24, fw.COLOR_OFFSETS[-1]):
            damaged = bytearray(image)
            damaged[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                fw.identify_image(self.stock, fw.seal(damaged))

    def test_rejects_wrong_stock_hash_size_and_crc(self):
        other = bytearray(self.stock)
        other[30] ^= 1
        for image in (self.stock[:-1], bytes(other), fw.seal(other)):
            with self.assertRaises(ValueError):
                fw.validate_stock(image)

    def test_bl_targets_with_independent_disassembler(self):
        decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        for start, target in ((fw.CALL_SITE, fw.HELPER), (fw.HELPER + 2, 0x7650),
                              (fw.HELPER + 12, 0x8EFA)):
            ins = next(decoder.disasm(fw.bl(start, target), start))
            self.assertEqual(ins.mnemonic, "bl")
            self.assertEqual(int(ins.op_str.lstrip("#"), 0), target)

    def test_unknown_patch_has_no_plan_and_no_device_access(self):
        with tempfile.TemporaryDirectory() as directory:
            stock_path = Path(directory) / "stock.bin"
            stock_path.write_bytes(self.stock)
            image_path = Path(directory) / "image.bin"
            image_path.write_bytes(fw.build_image(self.stock, b"\x00\xff\x00"))
            # Importing a device module would now fail, including accidental USB discovery.
            with patch.dict("sys.modules", {"hid": None, "apex3_tkl.updater": None}):
                for command in (["flash", "--image", str(image_path)], ["restore"], ["keys"]):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.assertEqual(cli.main(command + ["--stock", str(stock_path)]), 0)
                    self.assertIn('"usb_accessed": false', output.getvalue())
                image_path.write_bytes(fw.seal(bytes(fw.APP_SIZE)))
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["flash", "--stock", str(stock_path),
                                               "--image", str(image_path)]), 1)

    def test_build_refuses_existing_output_before_emulation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "stock.bin"
            source.write_bytes(self.stock)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["build", "--stock", str(source), "--color", "00FF00",
                                           "--output", str(source)]), 1)
            self.assertEqual(source.read_bytes(), self.stock)


class ProductionHashTests(unittest.TestCase):
    def test_synthetic_fixture_is_never_accepted_in_production(self):
        with self.assertRaises(ValueError):
            fw.validate_stock(synthetic_stock())
