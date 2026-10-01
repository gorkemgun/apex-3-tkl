# Linux

Use this guide to install the tool and save mappings from Linux. See the
[command support table](usage.md#install) before running other device commands.

## Install on Ubuntu

From your clone, with the [matching stock file](usage.md#get-the-original-file)
at `firmware/stock.bin`:

```sh
sudo apt update
sudo apt install python3-venv libusb-1.0-0 usbutils
python3 -m venv ~/.venvs/apex3-tkl
~/.venvs/apex3-tkl/bin/python -m pip install '.[device]'
```

Connect exactly one Apex 3 TKL to your computer:

```sh
lsusb -d 1038:1622
sudo ~/.venvs/apex3-tkl/bin/python -m apex3_tkl inspect --stock firmware/stock.bin
```

These examples use `sudo` for USB access. It is unnecessary if your account
already has permission to open the device. Building files and previewing
mapping plans do not need it.

```sh
# Preview.
~/.venvs/apex3-tkl/bin/python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=escape --fn-map f6=home

# Save to the keyboard.
sudo ~/.venvs/apex3-tkl/bin/python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=escape --fn-map f6=home --apply

# Restore those two factory bindings.
sudo ~/.venvs/apex3-tkl/bin/python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=default --fn-map f6=default --apply
```

Profiles and the Insert preset work the same way. See [key mapping](usage.md#choose-your-own-mappings).
