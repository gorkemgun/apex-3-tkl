import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from apex3_tkl import cli, firmware as fw
from apex3_tkl.device import Apex, CONFIG_DESCRIPTOR, write_binding
from apex3_tkl.keymap import factory_binding, load_profile, make_plan, parse_key, validate_binding
from tests.support import synthetic_stock


class KeymapTests(unittest.TestCase):
    def setUp(self):
        self.stock = synthetic_stock()
        guard = patch.object(fw, "STOCK_SHA256", fw.digest(self.stock))
        guard.start()
        self.addCleanup(guard.stop)

    def test_named_keys_and_hex_usages(self):
        self.assertEqual(parse_key("caps_lock"), 0x39)
        self.assertEqual(parse_key("ESC"), 0x29)
        self.assertEqual(parse_key("0xe0"), 0xE0)
        for key in ("steelseries", "fn", "0xf0", "0x00", "ctrl+c", "hello", 42):
            with self.subTest(key=key), self.assertRaises(ValueError):
                parse_key(key)

    def test_profiles_allow_layers_but_reject_ambiguous_entries(self):
        plan = make_plan(self.stock, profile={"normal": {"caps-lock": "escape"}, "fn": {"f6": "home"}})
        self.assertEqual([(x["layer"],x["source"],x["binding"][1]) for x in plan], [(0,0x39,0x29),(1,0x3F,0x4A)])
        for profile in ({}, {"macro": {}}, {"normal": []}, {"normal": {"a": ["b"]}}):
            with self.assertRaises(ValueError):
                make_plan(self.stock, profile=profile)
        with self.assertRaises(ValueError):
            make_plan(self.stock, ["esc=a", "escape=b"])
        with self.assertRaises(ValueError):
            make_plan(self.stock, ["a=b"], profile={"normal": {"c": "d"}})

    def test_restore_preserves_builtin_fn_functions(self):
        plan = make_plan(self.stock, fn=["f12=default", "left-win=default"])
        self.assertEqual(plan[0]["binding"], [0x62,4,1,0,0])
        self.assertEqual(plan[1]["binding"], [0x62,5,0,0,0])
        with self.assertRaises(ValueError):
            validate_binding(self.stock, 1, 0x04, plan[0]["binding"])

    def test_wire_packet_is_one_validated_binding(self):
        device = MagicMock()
        device.handle.send_feature_report.return_value = 257
        device.handle.get_feature_report.return_value = bytes([0,0x2A,0]) + bytes(254)
        with patch("apex3_tkl.device.time.sleep"):
            write_binding(device, self.stock, 1, 0x3F, bytes([0x51,0x4A,0,0,0]))
        packet = device.handle.send_feature_report.call_args.args[0]
        self.assertEqual(len(packet), 257)
        self.assertEqual(packet[:10], bytes.fromhex("00 2a 01 01 3f 51 4a 00 00 00"))
        with self.assertRaises(ValueError):
            write_binding(device, self.stock, 0, 0xF0, bytes([0x51,4,0,0,0]))
        self.assertEqual(device.handle.send_feature_report.call_count, 1)

    def test_linux_missing_usage_requires_exact_descriptor_before_commands(self):
        candidate = {"interface_number": 1, "usage_page": 0, "usage": 0, "path": b"1-1:1.1"}
        with patch("apex3_tkl.device.sys.platform", "linux"), \
                patch("apex3_tkl.device.hid.enumerate", return_value=[candidate]), \
                patch("apex3_tkl.device.hid.device") as create:
            handle = create.return_value
            handle.get_report_descriptor.return_value = CONFIG_DESCRIPTOR
            Apex().close()
            handle.send_feature_report.assert_not_called()
            handle.reset_mock()
            handle.get_report_descriptor.return_value = CONFIG_DESCRIPTOR[:-1]
            with self.assertRaises(RuntimeError):
                Apex()
            handle.close.assert_called_once()
            handle.send_feature_report.assert_not_called()

    def test_linux_ambiguous_devices_are_not_opened(self):
        candidate = {"interface_number": 1, "usage_page": 0, "usage": 0, "path": b"1-1:1.1"}
        with patch("apex3_tkl.device.sys.platform", "linux"), \
                patch("apex3_tkl.device.hid.enumerate", return_value=[candidate, candidate]), \
                patch("apex3_tkl.device.hid.device") as create:
            with self.assertRaises(RuntimeError):
                Apex()
            create.assert_not_called()

    def test_duplicate_json_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile.json"
            path.write_text('{"normal":{"a":"b","a":"c"}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_profile(path)

    def test_custom_cli_plan_and_key_list_do_not_access_usb(self):
        with tempfile.TemporaryDirectory() as folder:
            stock = Path(folder) / "stock.bin"
            stock.write_bytes(self.stock)
            with patch.dict("sys.modules", {"apex3_tkl.updater": None}), contextlib.redirect_stdout(io.StringIO()):
                for options in (["--map", "caps-lock=escape", "--fn-map", "f6=home"], ["--list"]):
                    self.assertEqual(cli.main(["keys", "--stock", str(stock), *options]), 0)

    def test_linux_key_operation_is_allowed_but_flash_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            stock = Path(folder) / "stock.bin"
            stock.write_bytes(self.stock)
            with patch.object(cli.sys, "platform", "linux"), patch("apex3_tkl.updater.set_keymap", return_value={}) as apply:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(["keys", "--stock", str(stock), "--map", "a=b", "--apply"]), 0)
                apply.assert_called_once()
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["restore", "--stock", str(stock), "--apply"]), 1)
