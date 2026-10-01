# Going back

Keep your original stock file and the `state/` directory from your update.
Close GG, Engine, and Prism, and connect only one Apex 3 TKL. Firmware recovery
uses the Windows updater.

## Restore the original firmware

```sh
# Inspect the plan first. No USB access.
python -m apex3_tkl restore --stock firmware/stock.bin

# Perform the restore.
python -m apex3_tkl restore --stock firmware/stock.bin --apply
```

This works when the keyboard is running normally or appears as bootloader USB
ID `1038:1623`. In normal mode, the installed firmware must be a supported image
so it can be backed up. In bootloader mode, the tool can restore the stock file
even if the installed firmware is incomplete.

The tool checks the full restored image before restarting the keyboard. Saved
key mappings stay in place. Use the commands below to reset those separately.

## Restore the stock Insert bindings

```sh
python -m apex3_tkl keys --stock firmware/stock.bin --restore --apply
```

This restores normal Insert and removes the added Fn+Insert binding. Other
keys are left alone.

## Restore other key bindings

Use `default` for each source and layer you want to reset:

```sh
python -m apex3_tkl keys --stock firmware/stock.bin --map caps-lock=default --fn-map f6=default --apply
```

This restores the factory settings for those keys, including built-in Fn
actions. To return to a previous custom setup, apply the profile you used for
it. Backups in `state/` show the previous bindings, but the tool cannot import
device dumps or GG macros.

## If a firmware write fails

Read `state/<run>/result.json`. If restoring the backup worked, the keyboard
returns to its previous firmware. The command still reports the failed update.
If both writes failed, the keyboard stays in its bootloader. Try the stock
restore command above.

If the keyboard no longer appears as a USB device, this tool cannot recover it.
A backup does not guarantee recovery and does not include the bootloader or
all configuration storage. Use the matching stock file and keep the version
checks in place. See [test coverage](validation.md#coverage-limits).
