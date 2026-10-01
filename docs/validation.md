# Testing

## Run the test suite

```sh
python -m pip install '.[device]'
python -m unittest discover -s tests -v
```

The default tests use fake firmware data and simulated USB devices. They check
firmware validation, writes, recovery, mapping profiles, and device selection.
They do not access your keyboard or need a stock firmware file.

To include the real-firmware integration tests locally, in PowerShell:

```powershell
$env:APEX3_TKL_STOCK = (Resolve-Path firmware/stock.bin).Path
python -m unittest discover -s tests -v
```

In Bash or Zsh:

```sh
APEX3_TKL_STOCK=firmware/stock.bin python -m unittest discover -s tests -v
```

With a stock file, the tests also run firmware code in an emulator. They check
colors, brightness, mapping commands, and factory bindings on both layers.

## Coverage limits

Hardware testing covers the green firmware and saved mappings on one Apex 3
TKL running 3.0.4. Other colors and hardware revisions have not been physically
tested. Failed-write recovery is tested in simulation only. Passing the tests
does not guarantee a successful flash or recovery on another keyboard.
