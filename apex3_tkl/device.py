"""Apex 3 TKL reads and bounded native keyboard mapping writes.

No firmware erase/write operations. USB requests use MI_01 (usage page 0xffc0),
256-byte feature reports. Configuration saves are separate from firmware updates.
"""
import struct
import sys
import time

import hid

from .firmware import APP_SIZE, validate_stock
from .keymap import validate_binding

# Exact MI_01 descriptor for the supported keyboard. Some Linux libusb builds
# omit usage metadata during enumeration, so verify the descriptor after opening.
CONFIG_DESCRIPTOR = bytes.fromhex(
    "06 c0 ff 09 01 a1 01 06 c1 ff 15 00 26 ff 00 75 08 "
    "09 f0 95 40 81 02 09 f1 95 40 91 02 09 f2 96 00 01 b1 02 c0"
)


class Apex:
    def __init__(self):
        candidates = [d for d in hid.enumerate(0x1038, 0x1622)
                      if d["interface_number"] == 1 and
                      ((d["usage_page"], d["usage"]) == (0xFFC0, 1) or
                       (sys.platform.startswith("linux") and
                        (d["usage_page"], d["usage"]) == (0, 0)))]
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one matching keyboard, found {len(candidates)}")
        self.handle = hid.device()
        try:
            self.handle.open_path(candidates[0]["path"])
            if candidates[0]["usage_page"] == 0:
                if bytes(self.handle.get_report_descriptor()) != CONFIG_DESCRIPTOR:
                    raise RuntimeError("Unexpected configuration HID report descriptor")
        except BaseException:
            self.handle.close()
            raise

    def close(self):
        self.handle.close()

    def get(self, request):
        request = bytes(request)
        if not request or request[0] not in (0x83, 0x84, 0x90, 0xA3, 0xAA, 0xAC):
            raise ValueError("Command is not an approved read operation")
        if len(request) > 256:
            raise ValueError("Request exceeds feature report size")
        # Byte zero is hidapi's report-ID placeholder; the keyboard has no IDs.
        packet = bytes([0]) + request + bytes(256 - len(request))
        for attempt in range(3):
            count = self.handle.send_feature_report(packet)
            if count != 257:
                raise IOError(f"Incomplete feature request: {count}")
            time.sleep(0.08)
            result = bytes(self.handle.get_feature_report(0, 257))
            if len(result) == 257 and result[:2] == bytes([0, request[0]]):
                return result[2:]
        raise IOError("Unexpected response; another program may be using the interface")

    def version(self):
        return self.get([0x90, 0]).split(b"\0", 1)[0].decode("ascii")

    def require_known_version(self):
        if self.version() != "3.0.4":
            raise RuntimeError("Only firmware 3.0.4 has been inspected")
        build = self.get([0x90, 1]).split(b"\0", 1)[0].decode("ascii")
        if build != "+d2c45ea7":
            raise RuntimeError(f"Unexpected firmware build: {build}")

    def read_application(self, offset, size):
        if not 0 <= offset < APP_SIZE or not 1 <= size <= 55 or offset + size > APP_SIZE:
            raise ValueError("Read must stay inside the known application image")
        response = self.get(bytes([0x83, 0, 0]) + struct.pack("<HI", size, offset))
        if response[0] != 0:
            raise IOError(f"Application read returned status {response[0]}")
        return response[1:1 + size]

    def key_bindings(self, keys, layer=0):
        if layer not in (0, 1) or not 1 <= len(keys) <= 40:
            raise ValueError("Invalid binding query")
        request = bytes([0xAA, layer, len(keys)]) + b"".join(bytes([key, 0, 0, 0, 0, 0]) for key in keys)
        for attempt in range(4):
            response = self.get(request)
            # response[0] is uninitialized/stale in this firmware: ignore it.
            bindings = {}
            for index, key in enumerate(keys):
                entry = response[1 + index * 6:7 + index * 6]
                if len(entry) != 6 or entry[0] != key:
                    break
                bindings[str(key)] = list(entry[1:])
            if len(bindings) == len(keys):
                return bindings
            time.sleep(0.15)
        raise IOError("Mismatched key-binding response")



def snapshot(device, image):
    validate_stock(image)
    keys = [key for key, index in enumerate(image[0x5F88:0x6088]) if index != 0xFF]
    result = {"version": device.version(), "layers": {}}
    for layer in (0, 1):
        result["layers"][str(layer)] = {}
        for start in range(0, len(keys), 30):
            result["layers"][str(layer)].update(device.key_bindings(keys[start:start+30], layer))
    return result


def write_exact(device, request):
    if request not in (bytes([0x11]), bytes([0x2A, 0, 1, 0x49, 0x51, 0x46, 0, 0, 0]),
                       bytes([0x2A, 0, 1, 0x49, 0x51, 0x49, 0, 0, 0]),
                       bytes([0x2A, 1, 1, 0x49, 0x51, 0x49, 0, 0, 0]),
                       bytes([0x2A, 1, 1, 0x49, 0, 0, 0, 0, 0])):
        raise ValueError("Only saving configuration and changing Insert are allowed")
    _write_config(device, request)


def write_binding(device, stock, layer, source, binding):
    binding = validate_binding(stock, layer, source, binding)
    _write_config(device, bytes([0x2A, layer, 1, source]) + binding)


def _write_config(device, request):
    packet = bytes([0]) + request + bytes(256-len(request))
    if device.handle.send_feature_report(packet) != 257:
        raise IOError("Incomplete command")
    time.sleep(0.25)
    response = bytes(device.handle.get_feature_report(0, 257))
    if response[:3] != bytes([0, request[0], 0]):
        raise IOError(f"Unexpected command acknowledgement: {response[:3].hex()}")
