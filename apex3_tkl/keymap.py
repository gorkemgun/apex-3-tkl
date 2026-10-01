"""Named keyboard usages and bounded mapping plans. No USB access."""

import json
import re

from .firmware import validate_stock

KEYS = {chr(97 + i): 0x04 + i for i in range(26)}
KEYS.update({str((i + 1) % 10): 0x1E + i for i in range(10)})
KEYS.update({f"f{i + 1}": 0x3A + i for i in range(12)})
KEYS.update({f"f{i + 13}": 0x68 + i for i in range(12)})
KEYS.update({
    "enter": 0x28, "escape": 0x29, "backspace": 0x2A, "tab": 0x2B,
    "space": 0x2C, "minus": 0x2D, "equal": 0x2E, "left-bracket": 0x2F,
    "right-bracket": 0x30, "backslash": 0x31, "non-us-hash": 0x32,
    "semicolon": 0x33, "quote": 0x34, "grave": 0x35, "comma": 0x36,
    "period": 0x37, "slash": 0x38, "caps-lock": 0x39,
    "print-screen": 0x46, "scroll-lock": 0x47, "pause": 0x48,
    "insert": 0x49, "home": 0x4A, "page-up": 0x4B, "delete": 0x4C,
    "end": 0x4D, "page-down": 0x4E, "right": 0x4F, "left": 0x50,
    "down": 0x51, "up": 0x52, "num-lock": 0x53, "keypad-divide": 0x54,
    "keypad-multiply": 0x55, "keypad-minus": 0x56, "keypad-plus": 0x57,
    "keypad-enter": 0x58, "keypad-0": 0x62, "keypad-period": 0x63,
    "non-us-backslash": 0x64, "menu": 0x65, "keypad-equal": 0x67,
    "keypad-comma": 0x85, "international-1": 0x87, "international-2": 0x88,
    "international-3": 0x89, "international-4": 0x8A, "international-5": 0x8B,
    "lang-1": 0x90, "lang-2": 0x91, "left-ctrl": 0xE0, "left-shift": 0xE1,
    "left-alt": 0xE2, "left-win": 0xE3, "right-ctrl": 0xE4,
    "right-shift": 0xE5, "right-alt": 0xE6, "right-win": 0xE7,
})
KEYS.update({f"keypad-{i + 1}": 0x59 + i for i in range(9)})
ALIASES = {"esc": "escape", "capslock": "caps-lock", "prtsc": "print-screen",
           "printscreen": "print-screen", "pgup": "page-up", "pgdn": "page-down",
           "ctrl": "left-ctrl", "shift": "left-shift", "alt": "left-alt",
           "win": "left-win", "super": "left-win"}
NAMES = {value: key for key, value in KEYS.items()}
FN_DEFAULTS = {0x42: bytes([0x62, 1, 0, 0, 0]), 0x43: bytes([0x62, 2, 1, 0, 0]),
               0x44: bytes([0x62, 3, 1, 0, 0]), 0x45: bytes([0x62, 4, 1, 0, 0]),
               0xE3: bytes([0x62, 5, 0, 0, 0])}


def source_keys(stock):
    validate_stock(stock)
    # Keep the SteelSeries layer selector itself available.
    return {key for key, slot in enumerate(stock[0x5F88:0x6088]) if slot != 0xFF and key != 0xF0}


def parse_key(value):
    if not isinstance(value, str):
        raise ValueError("Key names must be strings")
    name = value.lower().replace("_", "-")
    name = ALIASES.get(name, name)
    if name in KEYS:
        return KEYS[name]
    if re.fullmatch(r"0x[0-9a-f]{2}", name) and int(name, 16) in NAMES:
        return int(name, 16)
    raise ValueError(f"Unknown keyboard key: {value!r}. Use keys --list. Macros and chords are not supported.")


def factory_binding(source, layer):
    if layer == 0:
        return bytes([0x51, source, 0, 0, 0])
    if layer == 1:
        return FN_DEFAULTS.get(source, bytes(5))
    raise ValueError("Layer must be 0 or 1")


def validate_binding(stock, layer, source, binding):
    if type(layer) is not int or layer not in (0, 1) or type(source) is not int or source not in source_keys(stock):
        raise ValueError("Unsupported source key or layer")
    binding = bytes(binding)
    if binding == factory_binding(source, layer):
        return binding
    if len(binding) == 5 and binding[0] == 0x51 and binding[1] in NAMES and binding[2:] == bytes(3):
        return binding
    raise ValueError("Only single keyboard keys and the source's factory binding are supported")


def make_plan(stock, normal=(), fn=(), profile=None):
    allowed = source_keys(stock)
    entries = [(0, item) for item in normal] + [(1, item) for item in fn]
    if profile is not None:
        if entries:
            raise ValueError("Use either --profile or inline mappings")
        if not isinstance(profile, dict) or not profile or set(profile) - {"normal", "fn"}:
            raise ValueError("Profile must contain only normal and/or fn mapping objects")
        for name, mapping in profile.items():
            if not isinstance(mapping, dict):
                raise ValueError(f"{name} must be an object mapping source names to target names")
            for source, target in mapping.items():
                if not isinstance(source, str) or not isinstance(target, str):
                    raise ValueError("Profile key names and targets must be strings")
                entries.append((0 if name == "normal" else 1, f"{source}={target}"))
    result = []
    seen = set()
    for layer, entry in entries:
        if entry.count("=") != 1:
            raise ValueError("Mapping must be SOURCE=TARGET, for example caps-lock=escape")
        source_name, target_name = entry.split("=")
        source = parse_key(source_name)
        if source not in allowed:
            raise ValueError(f"{source_name} cannot be used as a source on this firmware")
        if (layer, source) in seen:
            raise ValueError(f"Duplicate source in the same layer: {source_name}")
        seen.add((layer, source))
        binding = factory_binding(source, layer) if target_name.lower() == "default" else bytes([0x51, parse_key(target_name), 0, 0, 0])
        validate_binding(stock, layer, source, binding)
        result.append({"layer": layer, "source": source, "binding": list(binding),
                       "source_name": NAMES[source], "target": "default" if target_name.lower() == "default" else NAMES[binding[1]]})
    if not result:
        raise ValueError("Select at least one mapping")
    return result


def load_profile(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate profile field: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)


def list_keys(stock):
    sources = source_keys(stock)
    return [{"name": name, "hid_usage": f"0x{usage:02X}", "can_be_source": usage in sources}
            for usage, name in sorted(NAMES.items())]
