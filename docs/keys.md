# Accepted key names

These names work in `--map SOURCE=TARGET`, `--fn-map SOURCE=TARGET`, and JSON
profiles. The source is the key you press. The target is the key it sends.

```json
{
  "normal": {"caps-lock": "escape"},
  "fn": {"f6": "home"}
}
```

Here, Caps Lock sends Escape. Holding the SteelSeries logo key and pressing F6
sends Home. `normal` and `fn` are the only profile fields. Either can be omitted,
but there must be at least one mapping. Every source and target must be a string.

## Key names

All 127 names below can be targets. Most can also be sources. The source column
follows the supported firmware's table. A listed position might not exist on
your keyboard's physical layout, especially the keypad and international keys.

| Group | Names | Can be a source |
| --- | --- | --- |
| Letters | `a`, `b`, `c`, `d`, `e`, `f`, `g`, `h`, `i`, `j`, `k`, `l`, `m`, `n`, `o`, `p`, `q`, `r`, `s`, `t`, `u`, `v`, `w`, `x`, `y`, `z` | Yes |
| Number row | `0`, `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9` | Yes |
| Function keys | `f1`, `f2`, `f3`, `f4`, `f5`, `f6`, `f7`, `f8`, `f9`, `f10`, `f11`, `f12` | Yes |
| Extra function keys | `f13`, `f14`, `f15`, `f16`, `f17`, `f18`, `f19`, `f20`, `f21`, `f22`, `f23`, `f24` | No |
| Typing controls | `enter`, `escape`, `backspace`, `tab`, `space`, `caps-lock` | Yes |
| Punctuation | `minus`, `equal`, `left-bracket`, `right-bracket`, `backslash`, `semicolon`, `quote`, `grave`, `comma`, `period`, `slash` | Yes |
| Navigation | `insert`, `delete`, `home`, `end`, `page-up`, `page-down`, `left`, `right`, `up`, `down` | Yes |
| Other controls | `print-screen`, `scroll-lock`, `pause` | Yes |
| Menu | `menu` | No |
| Left modifiers | `left-ctrl`, `left-shift`, `left-alt`, `left-win` | Yes |
| Right modifiers | `right-ctrl`, `right-shift`, `right-alt`, `right-win` | Yes |
| Keypad digits | `keypad-0`, `keypad-1`, `keypad-2`, `keypad-3`, `keypad-4`, `keypad-5`, `keypad-6`, `keypad-7`, `keypad-8`, `keypad-9` | Yes |
| Keypad controls | `num-lock`, `keypad-divide`, `keypad-multiply`, `keypad-minus`, `keypad-plus`, `keypad-enter`, `keypad-period`, `keypad-comma` | Yes |
| Keypad equal | `keypad-equal` | No |
| International | `non-us-hash`, `non-us-backslash`, `international-1`, `international-2`, `international-3`, `international-4`, `international-5`, `lang-1`, `lang-2` | Yes |

Names are case-insensitive, and underscores can replace hyphens. For example,
`CAPS_LOCK` and `caps-lock` mean the same key. `left-win` and `right-win` refer
to the Windows/Super keys, not the SteelSeries logo key.

Punctuation names follow US HID key positions. The active OS layout determines
the character you get. A mapping to `quote`, for example, does not guarantee a
literal quote character on every layout.

The TKL has no physical keypad, but you can send keypad codes from another key.
For example, `--map f6=keypad-1` makes F6 send keypad 1. Num Lock affects how
your OS handles that code. Choosing a keypad key as the source does not give
you an extra physical key to press.

F13 to F24 are additional function-key codes. Use `--fn-map f6=f13` to send F13
with SteelSeries + F6. Apps that recognize it can use it as a separate shortcut.

## Short names

| Accepted alias | Same as |
| --- | --- |
| `esc` | `escape` |
| `capslock` | `caps-lock` |
| `prtsc`, `printscreen` | `print-screen` |
| `pgup` | `page-up` |
| `pgdn` | `page-down` |
| `ctrl` | `left-ctrl` |
| `shift` | `left-shift` |
| `alt` | `left-alt` |
| `win`, `super` | `left-win` |

## The default target

`default` restores the factory binding for that source and layer:

```json
{
  "normal": {"caps-lock": "default"},
  "fn": {"f12": "default"}
}
```

This restores normal Caps Lock and the built-in SteelSeries + F12 brightness
action. It does not restore your previous custom setting. `default` is only a
target, never a source.

## HID values

You can use a two-digit hexadecimal HID usage instead of a name, such as
`0x49=0x46` for Insert to Print Screen. Only usages represented in the table
above are accepted. The source restrictions still apply. JSON values must
remain strings, for example `"0x49": "0x46"`.

To see every name, its HID usage, and whether it can be a source:

```sh
python -m apex3_tkl keys --stock firmware/stock.bin --list
```

This command does not access USB.

## Unsupported values

The SteelSeries logo key itself cannot be used as a source or target. Use the
`fn` object or `--fn-map` to assign a key on its layer.

Targets must be a single key or `default`. Chords such as `ctrl+c`, media actions
such as `volume-up`, text strings, timed macros, arrays, and `null` are not
supported. There is no disable-key target.

See [mapping examples](usage.md#choose-your-own-mappings) for how to preview,
save, and restore a profile.
