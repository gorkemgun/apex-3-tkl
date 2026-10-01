"""Native mappings on Windows/Linux and firmware updates on Windows."""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import hid

from .bootloader import Bootloader, program_with_rollback
from .device import Apex, snapshot, write_exact, write_binding
from .firmware import crc, digest, identify_image, validate_stock
from .keymap import validate_binding
from .windows_hid import find_device


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def new_run(state_dir, mode):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = Path(state_dir) / f"{stamp}-{mode}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def require_engine_closed():
    if sys.platform.startswith("linux"):
        return
    listing = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True).lower()
    for name in ("steelseriesengine.exe", "steelseriesprism.exe", "steelseriesgg.exe"):
        if f'"{name}"' in listing:
            raise RuntimeError("Exit SteelSeries GG, Engine, and Prism before device operations")


def application_crc(device):
    import struct

    raw = device.get([0x84, 0, 0])
    if len(raw) < 9 or raw[0] != 0:
        raise IOError("Application CRC request failed")
    return struct.unpack_from("<II", raw, 1)


def inspect_device(stock):
    validate_stock(stock)
    device = Apex()
    try:
        device.require_known_version()
        result = snapshot(device, stock)
        result["brightness"] = device.get([0xA3])[0]
        result["crc_words"] = [f"0x{x:08X}" for x in application_crc(device)]
        result["note"] = "CRC and version alone do not identify a supported application image."
        return result
    finally:
        device.close()


def update(stock, target, mode, state_dir):
    if sys.platform != "win32":
        raise RuntimeError("Bootloader operations require Windows")
    if mode not in ("check", "flash", "restore"):
        raise ValueError("Unsupported update mode")
    validate_stock(stock)
    identify_image(stock, target)
    if mode == "restore" and target != stock:
        raise ValueError("Recovery mode only accepts stock firmware")
    require_engine_closed()
    folder = new_run(state_dir, mode)
    result = {"mode": mode, "target_sha256": digest(target),
              "firmware_erase_or_write_attempted": False,
              "physical_power_cycle_verified": False}
    before = None
    boot = None
    reset_allowed = False
    entered = False
    verified = None
    try:
        devices = [d for pid in (0x1622, 0x1623) for d in hid.enumerate(0x1038, pid)
                   if d["usage_page"] == 0xFFC0 and d["usage"] == 1]
        if len(devices) != 1:
            raise RuntimeError("Connect exactly one Apex 3 TKL; refusing ambiguous device selection")
        already_boot = devices[0]["product_id"] == 0x1623
        if already_boot and mode != "restore":
            raise RuntimeError("Already in bootloader: use restore --apply with the verified stock file")
        if not already_boot:
            device = Apex()
            try:
                device.require_known_version()
                before = snapshot(device, stock)
                write_json(folder / "keymaps-before.json", before)
                result["brightness_before"] = device.get([0xA3])[0]
                # USB disconnect may race the transfer completion. Verify re-enumeration.
                entered = True
                reset_allowed = True
                try:
                    count = device.handle.send_feature_report(b"\x00\x01\x01" + bytes(254))
                    if count != 257:
                        result["entry_transport_error"] = f"Write returned {count}"
                except OSError as error:
                    result["entry_transport_error"] = str(error)
            finally:
                device.close()
        boot = Bootloader(stock)
        print("Bootloader connected; reading and validating the application.", flush=True)
        if not already_boot:
            live = boot.read_image()
            boot.verify(live, full_read=False)
            (folder / "application-before.bin").write_bytes(live)
            result["before_sha256"] = digest(live)
            verified = live
        if mode != "check":
            reset_allowed = False
            recovery = stock if already_boot else live
            result["recovery_sha256"] = digest(recovery)
            verified = program_with_rollback(boot, target, recovery, result)
            result["verified_sha256"] = digest(verified)
            reset_allowed = True
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        try:
            if boot is not None:
                try:
                    if reset_allowed:
                        try:
                            boot.send(b"\x01\x00")
                        except OSError as error:
                            result["reset_transport_error"] = str(error)
                finally:
                    boot.close()
            elif entered:
                # No erase was possible before a bootloader handle was opened.
                try:
                    recovery_boot = Bootloader(stock)
                    try:
                        try:
                            recovery_boot.send(b"\x01\x00")
                        except OSError:
                            pass
                    finally:
                        recovery_boot.close()
                except Exception as error:
                    result["return_attempt_error"] = repr(error)
            if reset_allowed:
                find_device(0x1622)
                device = Apex()
                try:
                    device.require_known_version()
                    after = snapshot(device, stock)
                    write_json(folder / "keymaps-after.json", after)
                    result["normal_device_returned"] = True
                    if before is not None:
                        result["keymaps_unchanged"] = after == before
                        if after != before:
                            raise RuntimeError("Keymaps changed; see the before-state backup")
                    if verified is not None:
                        actual_crc = application_crc(device)
                        result["application_crc_verified"] = actual_crc == (crc(verified), crc(verified))
                        if not result["application_crc_verified"]:
                            raise RuntimeError("Application CRC differs after reboot")
                    result["brightness_after"] = device.get([0xA3])[0]
                    print("Application returned; firmware CRC and native bindings checked.", flush=True)
                finally:
                    device.close()
            elif result["firmware_erase_or_write_attempted"]:
                print("Firmware not verified; left in bootloader. Run restore --apply.", flush=True)
        except BaseException as error:
            result["return_error"] = repr(error)
            raise
        finally:
            write_json(folder / "result.json", result)
            print(f"Local backup and result: {folder}", flush=True)
    if result.get("target_error"):
        raise RuntimeError("Target failed; the recovery image was restored and verified")
    return result


def set_insert_keys(stock, state_dir, restore=False):
    validate_stock(stock)
    require_engine_closed()
    folder = new_run(state_dir, "keys-restore" if restore else "keys")
    result = {"firmware_written": False, "power_cycle_verified": False,
              "save_command_attempted": False}
    device = Apex()
    originals = ([0x51, 0x49, 0, 0, 0], [0, 0, 0, 0, 0])
    remapped = ([0x51, 0x46, 0, 0, 0], [0x51, 0x49, 0, 0, 0])
    try:
        device.require_known_version()
        before = snapshot(device, stock)
        write_json(folder / "keymaps-before.json", before)
        for layer in (0, 1):
            if before["layers"][str(layer)]["73"] not in (originals[layer], remapped[layer]):
                raise RuntimeError("Insert has an unrelated custom binding; refusing to replace it")
        expected = json.loads(json.dumps(before))
        target = originals if restore else remapped
        changes = []
        try:
            for layer in (0, 1):
                expected["layers"][str(layer)]["73"] = target[layer]
                if before["layers"][str(layer)]["73"] != target[layer]:
                    # A failed acknowledgement may still follow a successful write.
                    changes.append(layer)
                    write_exact(device, bytes([0x2A, layer, 1, 0x49]) + bytes(target[layer]))
            if snapshot(device, stock) != expected:
                raise RuntimeError("Unexpected native keymap changes; configuration not saved")
        except Exception:
            for layer in changes:
                write_exact(device, bytes([0x2A, layer, 1, 0x49])
                            + bytes(before["layers"][str(layer)]["73"]))
            raise
        if changes:
            result["save_command_attempted"] = True
            write_exact(device, bytes([0x11]))
            result["save_command_acknowledged"] = True
        after = snapshot(device, stock)
        if after != expected:
            raise RuntimeError("Keymap readback differs after save; inspect the backup before retrying")
        result["bindings_verified"] = True
        result["other_bindings_unchanged"] = True
        result["normal_insert"] = target[0]
        result["fn_insert"] = target[1]
        write_json(folder / "keymaps-after.json", after)
        return result
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        device.close()
        write_json(folder / "result.json", result)
        print(f"Local backup and result: {folder}", flush=True)


def set_keymap(stock, plan, state_dir):
    validate_stock(stock)
    if not plan:
        raise ValueError("Empty mapping plan")
    seen = set()
    for entry in plan:
        source, layer = entry["source"], entry["layer"]
        validate_binding(stock, layer, source, entry["binding"])
        if (layer, source) in seen:
            raise ValueError("Duplicate source in the same layer")
        seen.add((layer, source))
    require_engine_closed()
    folder = new_run(state_dir, "keymap")
    result = {"firmware_written": False, "power_cycle_verified": False,
              "save_command_attempted": False, "requested_mappings": plan}
    device = None
    try:
        device = Apex()
        device.require_known_version()
        before = snapshot(device, stock)
        write_json(folder / "keymaps-before.json", before)
        expected = json.loads(json.dumps(before))
        # Establish rollback support for every selected binding before any write.
        for entry in plan:
            source, layer = entry["source"], entry["layer"]
            current = before["layers"][str(layer)][str(source)]
            try:
                validate_binding(stock, layer, source, current)
            except ValueError as error:
                raise ValueError(f"Source 0x{source:02X} layer {layer} has an unsupported existing binding") from error
            expected["layers"][str(layer)][str(source)] = list(entry["binding"])
        changes = []
        try:
            for entry in plan:
                source, layer = entry["source"], entry["layer"]
                current = before["layers"][str(layer)][str(source)]
                if current != entry["binding"]:
                    changes.append((layer, source, current))
                    write_binding(device, stock, layer, source, entry["binding"])
            if snapshot(device, stock) != expected:
                raise RuntimeError("Unexpected keymap changes. Configuration not saved.")
        except BaseException:
            # Try every affected key even if restoring one fails.
            failures = []
            for layer, source, binding in reversed(changes):
                try:
                    write_binding(device, stock, layer, source, binding)
                except Exception as error:
                    failures.append(str(error))
            result["volatile_rollback_errors"] = failures
            if not failures:
                result["volatile_rollback_verified"] = snapshot(device, stock) == before
            raise
        if changes:
            result["save_command_attempted"] = True
            write_exact(device, b"\x11")
            result["save_command_acknowledged"] = True
        after = snapshot(device, stock)
        if after != expected:
            raise RuntimeError("Keymap readback differs after save. See the local backup before retrying.")
        write_json(folder / "keymaps-after.json", after)
        result["bindings_verified"] = True
        result["other_bindings_unchanged"] = True
        result["changed_bindings"] = len(changes)
        return result
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        if device is not None:
            device.close()
        write_json(folder / "result.json", result)
        print(f"Local backup and result: {folder}", flush=True)
