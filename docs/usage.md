# Making your own firmware

You'll need an **Apex 3 TKL running firmware 3.0.4, build `+d2c45ea7`**, and the
matching stock file below. Other models and firmware versions are not supported.

## Get the original file

Find `firmware-apex-3-tkl-3.0.4.bin` in your SteelSeries GG installation.
In PowerShell:

```powershell
Get-ChildItem 'C:\Program Files\SteelSeries\GG\apps\engine\firmware' -Recurse -Filter 'firmware-apex-3-tkl-3.0.4.bin'
```

Copy it to `firmware/stock.bin` inside your clone. The tool checks its size and
hash, so another firmware version won't work. You'll need to find the matching
file in your own GG installation. It isn't included or downloaded by this tool.

| Check | Expected value |
| --- | --- |
| Size | 46,080 bytes (`0xB400`) |
| SHA-256 | `af0c071dfad589871169af086e83402c24de5d0965ebfd4693d2bd418a2bc59e` |
| Application load address | `0x3C00` |
| Normal USB ID | `1038:1622` |
| Bootloader USB ID | `1038:1623` |

## Install

Python 3.10 or newer is required. From your clone on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install '.[device]'
```

For a shell such as Bash or Zsh:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m apex3_tkl --help
```

The examples below use `python`. If you haven't activated the environment, use
its Python executable instead, such as `.\.venv\Scripts\python.exe` or
`.venv/bin/python`.

For Linux USB access, use the [Linux setup guide](linux.md).

| Commands | Supported systems |
| --- | --- |
| `build`, `verify`, `flash`/`restore`/`keys` previews | Windows, Linux, macOS |
| `inspect`, `keys --apply` | Windows, Linux |
| `check`, `flash --apply`, `restore --apply` | Windows |

## Build and verify

```sh
python -m apex3_tkl build --stock firmware/stock.bin --color 00FF00 --output build/green.bin
python -m apex3_tkl verify --stock firmware/stock.bin --image build/green.bin
```

Use any six-digit RGB color. All eight zones get that same color. Per-zone
colors and custom animations are not supported. `000000` means lights off.
Your existing brightness setting still applies.

This creates a `.bin` firmware file and a JSON report. Existing files are not
overwritten. Building checks the original file, applies the color, and checks
the result with ARM emulation. It does not access your keyboard.

`verify` checks a firmware file against the supported patch and its checksum.
Run the tool without Python's `-O` option so all checks stay enabled.

## Inspect and back up

Exit GG, Engine, and Prism. Connect exactly one Apex 3 TKL. A second keyboard is
useful while this one is in its bootloader.

```sh
python -m apex3_tkl inspect --stock firmware/stock.bin
python -m apex3_tkl check --stock firmware/stock.bin
```

`inspect` reads the version, checksum, brightness, and mappings. `check`
briefly disconnects the keyboard to back up its firmware and both key layers,
then reconnects it. It does not erase or write firmware.

Backups and results go under `state/<timestamp>-<command>/`. Keep that directory.
The backup contains the application firmware and readable mappings. It does
not include the bootloader or a full copy of configuration storage.

## Flash

Read [recovery](recovery.md) first. A failed firmware update can leave the
keyboard unusable.

```sh
# Show a plan. This does not access USB.
python -m apex3_tkl flash --stock firmware/stock.bin --image build/green.bin

# Actually back up, erase, write, verify, and restart the keyboard.
python -m apex3_tkl flash --stock firmware/stock.bin --image build/green.bin --apply
```

The updater checks both the new file and the installed firmware, backs up the
installed copy, and flashes the new one. It reads the whole image back and
checks the checksum and key mappings afterward.

If writing fails, it tries to restore the backup. If that fails too, it leaves
the keyboard in the bootloader for [recovery](recovery.md). Interrupting an
update can also leave it there.

After a successful update, close GG and check that your chosen color and key
bindings work as expected.

## Make Insert your screenshot key

This is separate from the color firmware. It uses the keyboard's native saved
configuration and works on the supported stock firmware too:

```sh
python -m apex3_tkl keys --stock firmware/stock.bin
python -m apex3_tkl keys --stock firmware/stock.bin --apply
```

That gives you **Insert → Print Screen** and **SteelSeries logo + Insert →
Insert**. Your OS decides what happens when it receives Print Screen. If Insert
already has a different custom binding, this preset stops without replacing it.

## Choose your own mappings

Map individual keys on either layer. `--fn-map` means holding the SteelSeries
logo key while pressing the source key. See the [key reference](keys.md) for
all accepted names, aliases, HID values, and source restrictions.

```sh
# Preview without USB access.
python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=escape --fn-map f6=home

# Save those two mappings on the keyboard.
python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=escape --fn-map f6=home --apply

# More than one mapping in a layer.
python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=escape --map insert=print-screen --fn-map insert=insert --apply

# Show key names and which ones can be used as sources. No USB access.
python -m apex3_tkl keys --stock firmware/stock.bin --list
```

For a reusable setup, copy [examples/keymap.json](../examples/keymap.json) and
edit it. A profile can contain either or both layers:

```json
{
  "normal": {
    "caps-lock": "escape",
    "insert": "print-screen"
  },
  "fn": {
    "insert": "insert",
    "f6": "home"
  }
}
```

```sh
python -m apex3_tkl keys --stock firmware/stock.bin --profile examples/keymap.json
python -m apex3_tkl keys --stock firmware/stock.bin --profile examples/keymap.json --apply
```

A profile only changes the listed bindings. Do not combine `--profile` with
inline mappings. `--map` and `--fn-map` also leave every unlisted binding alone.
They do not automatically add the Insert preset.

Use `default` to put a selected binding back to its factory setting:

```sh
python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=default --fn-map f6=default --apply
```

This also restores built-in Fn functions, such as the F11/F12 brightness
controls. It is not an undo command for a previous custom mapping.

The tool backs up both layers and checks all bindings before saving. If a
selected key already has an unsupported macro or special binding, it stops
before writing. If the requested mappings already match, it skips the save.

Only single keyboard keys are supported as targets. Text macros, timed
sequences, multi-key shortcuts like Ctrl+C, and media actions are not supported.
The SteelSeries logo key itself cannot be remapped, so it remains available
to select the Fn layer.

Color and key mappings are separate. Changing one leaves the other alone.
GG can still override settings while running, and a GG firmware update can
replace your custom firmware.
