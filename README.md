# apex-3-tkl

I just wanted my keyboard to remember its color without keeping another app
running.

I use a SteelSeries Apex 3 TKL. I wanted green lights, Insert as Print Screen,
and the SteelSeries logo key + Insert as regular Insert. Set it once, close GG,
plug it into another computer, and have the keyboard remember it. That was the
whole idea. :)

The macro I had set up in GG needed GG to stay running. These tools replace it
with a native key remap saved on the keyboard, so those two key functions work
without GG. The startup color comes from a small firmware patch. This repo is
the tooling from that project, so you can pick your own color and key mappings.

## What it does

- Builds a firmware image with your choice of one solid RGB color.
- Remaps individual keys on the normal and SteelSeries layers, saved on the keyboard.
- Includes **Insert → Print Screen** and **SteelSeries + Insert → Insert** as a preset.
- Backs up your firmware before flashing and checks the result afterward.

This is for **Apex 3 TKL firmware 3.0.4**. You need your own matching stock
firmware file, which is not included in this repo.

## Try a build

Install Python 3.10+ and copy your original firmware to `firmware/stock.bin`.
The [setup guide](docs/usage.md#get-the-original-file) explains where to find it.
Then, from your clone in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install '.[device]'
.\.venv\Scripts\python.exe -m apex3_tkl build --stock firmware/stock.bin --color 00FF00 --output build/green.bin
```

Change `00FF00` to your color. This creates the firmware file without changing
anything on your keyboard. Follow the [flashing guide](docs/usage.md#flash)
when you're ready to install it.

## Pick your keys

For example, make Caps Lock send Escape and SteelSeries + F6 send Home:

```powershell
.\.venv\Scripts\python.exe -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=escape --fn-map f6=home
```

That shows the plan. Add `--apply` to save it. Repeat `--map` or `--fn-map` for
more keys, or use a [JSON profile](examples/keymap.json). These are single-key
remaps. Text macros, key sequences, and shortcuts like Ctrl+C are not supported.
See [all accepted key names and values](docs/keys.md) when making your profile.

For the rest:

- [Build, inspect, flash, and set the keys](docs/usage.md)
- [Linux setup](docs/linux.md)
- [Restore the original firmware or key bindings](docs/recovery.md)
- [Testing](docs/validation.md)
- [Addresses, commands, and how the patch works](docs/internals.md)

MIT for the code here. SteelSeries firmware is separate. No affiliation with
SteelSeries. I just wanted fewer apps running.
