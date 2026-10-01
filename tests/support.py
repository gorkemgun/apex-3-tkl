"""Synthetic data for CI. This is not a vendor firmware image."""

from apex3_tkl import firmware as fw


def synthetic_stock():
    image = bytearray(fw.APP_SIZE)
    marker = b"SYNTHETIC TEST DATA ONLY!"
    image[:len(marker)] = marker
    image[fw.CALL_SITE - fw.BASE:fw.CALL_SITE - fw.BASE + 4] = fw.bl(fw.CALL_SITE, 0x7650)
    image[0x5F29] = 0x49
    for i, offset in enumerate(fw.COLOR_OFFSETS):
        image[offset:offset + 3] = bytes([i, 255 - i, 31])
    return fw.seal(image)
