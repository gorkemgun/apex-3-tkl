"""Deterministic patches for one exact application image. No USB access."""

import hashlib
import re
import struct
import zlib

APP_SIZE = 0xB400
BASE = 0x3C00
STOCK_SHA256 = "af0c071dfad589871169af086e83402c24de5d0965ebfd4693d2bd418a2bc59e"
COLOR_OFFSETS = (0x53B5, *(0x53B8 + 4 * i for i in range(6)))
CALL_SITE = 0x45FE
HELPER = 0xE000
CACHE = 0x2000083C


def digest(image):
    return hashlib.sha256(image).hexdigest()


def crc(image):
    return (~zlib.crc32(image[:-4])) & 0xFFFFFFFF


def seal(image):
    image = bytearray(image)
    struct.pack_into("<I", image, len(image) - 4, crc(image))
    return bytes(image)


def validate_crc(image):
    if len(image) != APP_SIZE:
        raise ValueError(f"Expected {APP_SIZE} application bytes; got {len(image)}")
    if struct.unpack_from("<I", image, APP_SIZE - 4)[0] != crc(image):
        raise ValueError("Application CRC mismatch")


def validate_stock(image):
    validate_crc(image)
    if digest(image) != STOCK_SHA256:
        raise ValueError("Unsupported stock firmware: only the exact inspected 3.0.4 image is accepted")


def parse_color(value):
    if not re.fullmatch(r"#?[0-9a-fA-F]{6}", value):
        raise ValueError("Color must be six hexadecimal RGB digits, optionally preceded by #")
    return bytes.fromhex(value.removeprefix("#"))


def bl(source, target):
    """Encode a Thumb-2 branch with link; caller addresses are even."""
    delta = target - (source + 4)
    if delta & 1 or not -(1 << 24) <= delta < (1 << 24):
        raise ValueError("Invalid Thumb BL target")
    immediate = delta & ((1 << 25) - 1)
    sign = (immediate >> 24) & 1
    j1 = 1 ^ ((immediate >> 23) & 1) ^ sign
    j2 = 1 ^ ((immediate >> 22) & 1) ^ sign
    return struct.pack("<HH", 0xF000 | (sign << 10) | ((immediate >> 12) & 0x3FF),
                       0xD000 | (j1 << 13) | (j2 << 11) | ((immediate >> 1) & 0x7FF))


def build_image(stock, color, wake_fix=True):
    validate_stock(stock)
    color = bytes(color)
    if len(color) != 3:
        raise ValueError("Expected three RGB bytes")
    patched = bytearray(stock)
    for offset in COLOR_OFFSETS:
        patched[offset:offset + 3] = color
    if wake_fix:
        if stock[CALL_SITE - BASE:CALL_SITE - BASE + 4] != bl(CALL_SITE, 0x7650):
            raise ValueError("Unexpected LED-enable call")
        if any(stock[0xA8C0 - BASE:-4]):
            raise ValueError("Wake helper requires the verified unused zero-filled application area")
        helper = (bytes.fromhex("10 b5") + bl(HELPER + 2, 0x7650)
                  + bytes.fromhex("03 48 00 21 18 22") + bl(HELPER + 12, 0x8EFA)
                  + bytes.fromhex("10 bd 00 bf") + struct.pack("<I", CACHE))
        if len(helper) != 24:
            raise ValueError("Unexpected wake helper length")
        patched[CALL_SITE - BASE:CALL_SITE - BASE + 4] = bl(CALL_SITE, HELPER)
        patched[HELPER - BASE:HELPER - BASE + 24] = helper
    return seal(patched)


def identify_image(stock, image):
    """Reconstruct the entire image; CRC and changed-offset checks alone are insufficient.

    Accept stock, or one uniform color with the exact optional wake helper. No
    metadata supplied by the caller is trusted to authorize an executable image.
    """
    validate_stock(stock)
    validate_crc(image)
    if image == stock:
        return {"kind": "stock", "color": None, "wake_fix": False, "sha256": digest(image)}
    color = image[COLOR_OFFSETS[0]:COLOR_OFFSETS[0] + 3]
    for wake_fix in (True, False):
        if image == build_image(stock, color, wake_fix):
            return {"kind": "solid-color", "color": "#" + color.hex().upper(),
                    "wake_fix": wake_fix, "sha256": digest(image)}
    raise ValueError("Image differs from the exact supported color/wake patch; refusing it")


def describe(stock, image):
    result = identify_image(stock, image)
    result.update({"model": "SteelSeries Apex 3 TKL", "version": "3.0.4",
                   "stock_sha256": STOCK_SHA256, "size": len(image),
                   "crc": f"0x{crc(image):08X}", "factory_keymaps_modified": False,
                   "changes": [{"offset": f"0x{i:04X}", "before": a, "after": b}
                               for i, (a, b) in enumerate(zip(stock, image)) if a != b]})
    return result
