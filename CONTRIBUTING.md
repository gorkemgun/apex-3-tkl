# Contributing

Bug reports, clearer instructions, and patches are welcome. Keep the firmware
version and hash checks in place. Adding another model needs a matching patch
and tests for its firmware.

Keep the docs plain and conversational. Use short sentences instead of em dashes
or semicolons.

For bugs, include your keyboard model, firmware version, OS, the command you
ran, and what happened. Remove personal information from logs before sharing
them. Do not upload SteelSeries firmware, device dumps, or GG databases.

Follow [testing](docs/validation.md) for code changes. Firmware patch changes
also need the emulation tests with your own stock file. Say which checks used
a real keyboard and which ran in simulation.

The MIT license covers this project's code and docs, not SteelSeries firmware.
