"""Optional local tests against a user-supplied stock image; never opens USB."""
import os
from pathlib import Path
import struct
import unittest

from apex3_tkl.firmware import build_image, digest, parse_color, validate_stock
from apex3_tkl.emulator import Firmware, validate_emulation
from apex3_tkl.keymap import factory_binding, make_plan, source_keys


@unittest.skipUnless(os.environ.get("APEX3_TKL_STOCK"), "Set APEX3_TKL_STOCK to run real-firmware emulation")
class RealFirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = Path(os.environ["APEX3_TKL_STOCK"]).read_bytes()
        validate_stock(cls.stock)

    def test_reproduce_hardware_flashes_byte_for_byte(self):
        for wake, expected in (
            (False, "8bedc980b44cbd0e76cc2f792255c7be8344db6062be206a014950e810d53bdf"),
            (True, "bc781d63906f3ce1d232281dd88cb431370aca1c81af0d9db84f6af609a541b1"),
        ):
            self.assertEqual(digest(build_image(self.stock, parse_color("00FF00"), wake)), expected)

    def test_colors_keymaps_and_wake_with_real_arm_code(self):
        for color in ("00FF00", "FF0000", "0000FF", "123456", "FFFFFF", "000000", "010101"):
            with self.subTest(color=color):
                image = build_image(self.stock, parse_color(color))
                result = validate_emulation(self.stock, image)
                self.assertEqual(result["color_and_keys"]["changed_key_layers"], [])
                self.assertEqual(result["color_and_keys"]["rgb_zone_time_samples"], 96)
                self.assertEqual(result["wake"]["wake_path_brightness_scenarios_passed"], 8)

    def test_factory_bindings_and_mapping_handler(self):
        firmware = Firmware(self.stock)
        firmware.call(0x4AA4)
        for source in source_keys(self.stock):
            for layer in (0, 1):
                self.assertEqual(firmware.binding(source, layer), factory_binding(source, layer))
        before = {(source, layer): firmware.binding(source, layer)
                  for source in source_keys(self.stock) for layer in (0, 1)}
        plan = make_plan(self.stock, ["caps-lock=escape", "a=b", "f8=f13", "right-alt=left-ctrl"],
                         ["f6=home", "f12=default"])
        for entry in plan:
            request = bytes([0x2A, entry["layer"], 1, entry["source"]]) + bytes(entry["binding"])
            firmware.uc.mem_write(0x2000C000, request)
            firmware.uc.mem_write(0x2000C400, struct.pack("<I", len(request)))
            firmware.call(0x6C60, 0x2000C000, 0x2000C200, 0x2000C400)
            before[(entry["source"], entry["layer"])] = bytes(entry["binding"])
        for (source, layer), expected in before.items():
            self.assertEqual(firmware.binding(source, layer), expected)
