"""Offline by default. USB operations require an explicit device subcommand."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .firmware import build_image, describe, identify_image, parse_color, validate_stock
from .keymap import list_keys, load_profile, make_plan


def parser():
    root = argparse.ArgumentParser(description="Experimental Apex 3 TKL 3.0.4 firmware tools")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Build and ARM-emulate a custom image, without USB access")
    build.add_argument("--stock", type=Path, required=True)
    build.add_argument("--color", required=True, help="Six hexadecimal RGB digits, e.g. 00FF00")
    build.add_argument("--output", type=Path, required=True, help="New .bin file (will not overwrite)")
    build.add_argument("--no-wake-fix", action="store_true", help=argparse.SUPPRESS)
    verify = commands.add_parser("verify", help="Check an image against the exact supported patches without USB access")
    verify.add_argument("--stock", type=Path, required=True)
    verify.add_argument("--image", type=Path, required=True)
    for name, help_text in (
        ("inspect", "Read firmware version, brightness, CRC, and keymaps on Windows/Linux"),
        ("check", "Back up via bootloader and return without writing firmware (Windows)"),
        ("flash", "Plan a custom image update. --apply writes it on Windows"),
        ("restore", "Plan a stock firmware restore. --apply writes it on Windows"),
        ("keys", "Plan native key mappings. --apply saves them on Windows/Linux"),
    ):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("--stock", type=Path, required=True)
        if name != "inspect":
            sub.add_argument("--state-dir", type=Path, default=Path("state"))
        if name == "flash":
            sub.add_argument("--image", type=Path, required=True)
        if name in ("flash", "restore", "keys"):
            sub.add_argument("--apply", action="store_true", help="Actually perform the device operation")
        if name == "keys":
            sub.add_argument("--restore", action="store_true", help="Restore stock Insert bindings in both layers")
            sub.add_argument("--map", action="append", default=[], metavar="SOURCE=TARGET", help="Normal-layer mapping. Repeat for more keys.")
            sub.add_argument("--fn-map", action="append", default=[], metavar="SOURCE=TARGET", help="SteelSeries-layer mapping. TARGET=default restores that binding.")
            sub.add_argument("--profile", type=Path, help="JSON file with normal and fn mapping objects")
            sub.add_argument("--list", action="store_true", help="List supported key names without USB access")
    return root


def print_json(value):
    print(json.dumps(value, indent=2))


def run(args):
    stock = args.stock.read_bytes()
    validate_stock(stock)
    if args.command == "build":
        color = parse_color(args.color)
        output = args.output
        manifest_path = output.with_suffix(".json")
        if output.suffix.lower() != ".bin":
            raise ValueError("Output must have a .bin extension")
        if output.exists() or manifest_path.exists():
            raise ValueError("Output or manifest already exists; choose a new filename")
        from .emulator import validate_emulation

        image = build_image(stock, color, wake_fix=not args.no_wake_fix)
        validation = validate_emulation(stock, image)
        result = describe(stock, image)
        result.update({"tool_version": __version__, "status": "BUILT_OFFLINE_NOT_FLASHED",
                       "validation": validation, "physical_shutdown_test_pending": True})
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects the source from accidental overwrite.
        with output.open("xb") as handle:
            handle.write(image)
        with manifest_path.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
            handle.write("\n")
        print_json({"image": str(output), "manifest": str(manifest_path),
                    "sha256": result["sha256"], "validation": validation})
        return
    if args.command == "verify":
        print_json(describe(stock, args.image.read_bytes()))
        return
    plan = None
    key_description = None
    if args.command == "keys":
        custom = bool(args.map or args.fn_map or args.profile)
        if args.list:
            if custom or args.restore or args.apply:
                raise ValueError("--list cannot be combined with mapping operations")
            print_json(list_keys(stock))
            return
        if custom:
            if args.restore:
                raise ValueError("Use TARGET=default to restore selected keys. --restore is for the Insert preset.")
            plan = make_plan(stock, args.map, args.fn_map,
                             load_profile(args.profile) if args.profile else None)
        key_description = plan if plan is not None else (
            "stock Insert in both layers" if args.restore else
            "Insert -> Print Screen, SteelSeries + Insert -> Insert")
    target = args.image.read_bytes() if args.command == "flash" else stock
    info = identify_image(stock, target)
    if args.command in ("flash", "restore", "keys") and not args.apply:
        print_json({"mode": "PLAN_ONLY", "usb_accessed": False, "command": args.command,
                    "image": info if args.command != "keys" else None,
                    "keys": key_description,
                    "next_step": "Repeat with --apply to perform this operation",
                    "recovery": "See saved bindings in the local before-state backup" if args.command == "keys"
                    else "Exact verified previous image, or stock when already in bootloader"})
        return
    if sys.platform != "win32" and not (sys.platform.startswith("linux") and args.command in ("keys", "inspect")):
        raise RuntimeError("Key mappings and inspection require Windows or Linux. Bootloader operations require Windows.")
    if not __debug__ or os.environ.get("PYTHONOPTIMIZE"):
        raise RuntimeError("Device commands require Python without -O / PYTHONOPTIMIZE")
    from .updater import inspect_device, set_insert_keys, set_keymap, update

    if args.command == "inspect":
        print_json(inspect_device(stock))
    elif args.command == "keys":
        print_json(set_keymap(stock, plan, args.state_dir) if plan is not None else
                   set_insert_keys(stock, args.state_dir, restore=args.restore))
    else:
        # Re-run the executable-routine checks before entering the bootloader.
        if args.command == "flash" and info["kind"] == "solid-color":
            from .emulator import validate_emulation
            validate_emulation(stock, target)
        print_json(update(stock, target, args.command, args.state_dir))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, ImportError, AssertionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. If an update was in progress, check its local result and recovery guide.", file=sys.stderr)
        return 130
    return 0
