# Firmware reference

These addresses and commands refer to the stock 3.0.4 application listed in
[usage](usage.md). The bootloader is not patched.

## Color patch

The 46,080-byte ARM Thumb application is loaded at `0x3C00`. The final four bytes
store `(~zlib.crc32(image[:-4])) & 0xffffffff` in little-endian order.

All eight lighting zones reference the same first animation. Its initial RGB
is at file offset `0x53B5`. Its six RGB endpoints are at `0x53B8 + 4*i` for
`i = 0..5`. Giving them the same RGB value makes the built-in animation constant.
The duration bytes stay unchanged. The firmware version string also remains
`3.0.4`, so use image hashes and CRCs to distinguish builds.

The complete patch is defined in [firmware.py](../apex3_tkl/firmware.py).
Verification rebuilds the image from the matching stock file and compares
every byte. A matching checksum alone is not enough.

## Native key mappings

Configuration is loaded from flash at `0x3400` into RAM at `0x20000010`.
The normal keymap starts at `0x2000001C`. The Fn map starts at `0x2000033C`.
Each has 160 five-byte slots, of which 114 can be addressed via the known lookup
table. The HID-to-slot lookup is at application file offset `0x5F88`.
The mapping tool leaves usage `0xF0`, the SteelSeries layer selector, protected.
The other 113 entries can be selected as sources, though not every position
exists on every physical layout.

HID Insert is `0x49`, Print Screen is `0x46`, and an ordinary key binding is
`51 <HID usage> 00 00 00`. The commands used here are:

| Operation | Payload |
| --- | --- |
| Normal Insert → Print Screen | `2A 00 01 49 51 46 00 00 00` |
| Fn+Insert → Insert | `2A 01 01 49 51 49 00 00 00` |
| Restore normal Insert | `2A 00 01 49 51 49 00 00 00` |
| Clear Fn+Insert | `2A 01 01 49 00 00 00 00 00` |
| Save configuration | `11` |

The general single-key command is `2A <layer> 01 <source> 51 <target> 00 00 00`.
Layer zero is normal and layer one is SteelSeries/Fn. The target is a keyboard
HID usage, including ordinary modifier keys. Consumer/media usages and macros
are not handled by this tool.

Factory normal bindings send their own HID usage. Most factory Fn bindings are
five zero bytes. Fn+F9 through Fn+F12 and Fn+Left Windows have built-in actions
using type `0x62`. The `default` target restores that source and layer's factory
binding, including these built-in actions.

Getter `AA` queries binding entries. Its first response-body byte can be stale.
The tool validates the echoed key IDs instead. Feature requests wait 80 ms,
with retries for mismatched responses. Saved mappings take precedence over
factory defaults, which is why the color builder leaves key tables alone.

## Bootloader transport

Normal mode is `1038:1622`, config interface MI_01, usage page `0xFFC0`, usage 1.
The feature report has a 256-byte payload plus hidapi's report-ID placeholder.
When a Linux backend omits usage metadata, the tool requires interface 1 and
checks its complete HID report descriptor before sending configuration requests.
Sending payload `01 01` enters bootloader `1038:1623`.

Bootloader output reports have a 64-byte payload plus a zero report-ID byte.
Unnumbered input reports are returned by hidapi without that placeholder.

| Command | Payload |
| --- | --- |
| Erase application | `02 00 00` |
| Program application | `03 00 00 <u16 size> <u32 offset> <data>` |
| Read application | `83 00 00 <u16 size> <u32 offset>` |
| Query computed and stored CRC | `84 00 00` |
| Return to application | `01 00` |

Sizes and offsets are little-endian and relative to the application. Writes use
52-byte aligned chunks, a final eight-byte chunk, and 10 ms pacing. Reads use at
most 55 bytes. Only file ID zero and addresses within the application are
accepted. The full image and both CRC words are checked after writing.

A reset may disconnect USB before a write returns, producing a transport error
even when the transition succeeded. Re-enumeration, version, application CRC,
and keymap checks establish the result.
