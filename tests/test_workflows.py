"""Lifecycle tests with fake devices; no USB enumeration or writes."""
import contextlib
import copy
import io
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from apex3_tkl import firmware as fw, updater
from tests.support import synthetic_stock


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.stack.enter_context(patch.object(updater.sys, "platform", "win32"))
        self.stock = synthetic_stock()
        self.stack.enter_context(patch.object(fw, "STOCK_SHA256", fw.digest(self.stock)))
        self.target = fw.build_image(self.stock, fw.parse_color("123456"))
        self.before = {"version": "3.0.4", "layers": {
            "0": {"73": [81, 73, 0, 0, 0], "4": [81, 4, 0, 0, 0]},
            "1": {"73": [0, 0, 0, 0, 0], "4": [0, 0, 0, 0, 0]}}}
        self.state = copy.deepcopy(self.before)
        self.device = MagicMock()
        self.device.handle.send_feature_report.return_value = 257
        self.device.get.return_value = bytes([16])
        self.boot = MagicMock()
        self.boot.read_image.return_value = self.stock
        self.stack.enter_context(patch.object(updater, "Apex", return_value=self.device))
        self.stack.enter_context(patch.object(updater, "Bootloader", return_value=self.boot))
        self.stack.enter_context(patch.object(updater, "snapshot", side_effect=lambda *a: copy.deepcopy(self.state)))
        self.stack.enter_context(patch.object(updater, "application_crc", return_value=(fw.crc(self.target),) * 2))
        self.stack.enter_context(patch.object(updater, "require_engine_closed"))
        self.stack.enter_context(patch.object(updater, "find_device"))
        self.enumerate = self.stack.enter_context(patch.object(updater.hid, "enumerate", side_effect=
            lambda vid, pid: [{"usage_page": 0xFFC0, "usage": 1, "product_id": pid}]
            if pid == 0x1622 else []))

    def test_success_verifies_and_returns_to_application(self):
        result = updater.update(self.stock, self.target, "flash", self.directory)
        self.boot.program.assert_called_once_with(self.target)
        self.boot.send.assert_called_once_with(b"\x01\x00")
        self.assertTrue(result["application_crc_verified"])
        self.assertTrue(result["keymaps_unchanged"])
        self.assertFalse(result["physical_power_cycle_verified"])

    def test_failed_target_and_failed_recovery_never_reset(self):
        self.boot.program.side_effect = IOError("disconnected")
        with self.assertRaises(IOError):
            updater.update(self.stock, self.target, "flash", self.directory)
        self.assertEqual(self.boot.program.call_count, 2)
        self.boot.send.assert_not_called()
        self.boot.close.assert_called_once()

    def test_unknown_live_image_is_not_erased(self):
        self.boot.read_image.side_effect = ValueError("unsupported image")
        with self.assertRaises(ValueError):
            updater.update(self.stock, self.target, "flash", self.directory)
        self.boot.program.assert_not_called()
        self.boot.send.assert_called_once_with(b"\x01\x00")

    def test_ambiguous_device_selection_has_no_mode_switch(self):
        self.enumerate.side_effect = lambda *a: [{"usage_page": 0xFFC0, "usage": 1, "product_id": a[1]}]
        with self.assertRaises(RuntimeError):
            updater.update(self.stock, self.target, "flash", self.directory)
        self.device.handle.send_feature_report.assert_not_called()
        self.boot.program.assert_not_called()

    def test_check_never_erases_or_programs(self):
        with patch.object(updater, "application_crc", return_value=(fw.crc(self.stock),) * 2):
            result = updater.update(self.stock, self.stock, "check", self.directory)
        self.boot.program.assert_not_called()
        self.boot.send.assert_called_once_with(b"\x01\x00")
        self.assertFalse(result["firmware_erase_or_write_attempted"])

    def test_keys_change_only_insert_then_save_once(self):
        requests = []
        def write(device, request):
            requests.append(request)
            if request[0] == 0x2A:
                self.state["layers"][str(request[1])]["73"] = list(request[4:])
        with patch.object(updater, "write_exact", side_effect=write):
            result = updater.set_insert_keys(self.stock, self.directory)
            again = updater.set_insert_keys(self.stock, self.directory)
        self.assertEqual(requests.count(b"\x11"), 1)
        self.assertTrue(result["bindings_verified"])
        self.assertFalse(again["save_command_attempted"])
        for layer in ("0", "1"):
            self.assertEqual(self.state["layers"][layer]["4"], self.before["layers"][layer]["4"])

    def test_keys_do_not_replace_unrelated_custom_bindings(self):
        self.state["layers"]["1"]["73"] = [81, 4, 0, 0, 0]
        with patch.object(updater, "write_exact") as write:
            with self.assertRaises(RuntimeError):
                updater.set_insert_keys(self.stock, self.directory)
            write.assert_not_called()

    def test_key_ack_failure_restores_volatile_binding_without_save(self):
        requests = []
        def write(device, request):
            requests.append(request)
            self.state["layers"][str(request[1])]["73"] = list(request[4:])
            if len(requests) == 1:
                raise IOError("write applied, acknowledgement lost")
        with patch.object(updater, "write_exact", side_effect=write):
            with self.assertRaises(IOError):
                updater.set_insert_keys(self.stock, self.directory)
        self.assertNotIn(b"\x11", requests)
        self.assertEqual(self.state, self.before)

    def test_custom_mapping_saves_both_layers_once_and_preserves_insert(self):
        from apex3_tkl.keymap import make_plan
        def write(device, stock, layer, source, binding):
            self.state["layers"][str(layer)][str(source)] = list(binding)
        plan = make_plan(self.stock, ["a=b"], ["a=c"])
        with patch.object(updater, "write_binding", side_effect=write), patch.object(updater, "write_exact") as save:
            result = updater.set_keymap(self.stock, plan, self.directory)
            again = updater.set_keymap(self.stock, plan, self.directory)
        save.assert_called_once_with(self.device, b"\x11")
        self.assertEqual(result["changed_bindings"], 2)
        self.assertEqual(again["changed_bindings"], 0)
        self.assertEqual(self.state["layers"]["0"]["73"], self.before["layers"]["0"]["73"])
        self.assertEqual(self.state["layers"]["1"]["73"], self.before["layers"]["1"]["73"])

    def test_custom_ack_failure_rolls_back_without_saving(self):
        from apex3_tkl.keymap import make_plan
        requests = []
        def write(device, stock, layer, source, binding):
            requests.append((layer, source))
            self.state["layers"][str(layer)][str(source)] = list(binding)
            if len(requests) == 2:
                raise IOError("acknowledgement lost")
        plan = make_plan(self.stock, ["a=b"], ["a=c"])
        with patch.object(updater, "write_binding", side_effect=write), patch.object(updater, "write_exact") as save:
            with self.assertRaises(IOError):
                updater.set_keymap(self.stock, plan, self.directory)
        save.assert_not_called()
        self.assertEqual(self.state, self.before)

    def test_custom_mapping_checks_every_previous_binding_before_writing(self):
        from apex3_tkl.keymap import make_plan
        self.state["layers"]["1"]["4"] = [0x71, 1, 2, 3, 4]
        plan = make_plan(self.stock, ["a=b"], ["a=c"])
        with patch.object(updater, "write_binding") as write:
            with self.assertRaises(ValueError):
                updater.set_keymap(self.stock, plan, self.directory)
        write.assert_not_called()

    def test_linux_cannot_enter_bootloader(self):
        with patch.object(updater.sys, "platform", "linux"):
            with self.assertRaises(RuntimeError):
                updater.update(self.stock, self.target, "flash", self.directory)
        self.enumerate.assert_not_called()
