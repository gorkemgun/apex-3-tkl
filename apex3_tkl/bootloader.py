"""Bounded application-only bootloader protocol. Windows hardware access."""
import struct
import time
import hid
from .firmware import APP_SIZE, STOCK_SHA256, crc, digest, identify_image, validate_stock
from .windows_hid import find_device, report_sizes


class Bootloader:
    def __init__(self, stock):
        validate_stock(stock)
        self.stock = stock
        entry = find_device(0x1623)
        sizes = report_sizes(entry['path'])
        if sizes['InputReportByteLength'] != 65 or sizes['OutputReportByteLength'] != 65:
            raise RuntimeError('Unexpected bootloader HID report lengths')
        self.handle = hid.device()
        self.handle.open_path(entry['path'])

    def close(self):
        self.handle.close()

    def send(self, request):
        request = bytes(request)
        allowed = request in (b'\x01\x00', b'\x02\x00\x00', b'\x84\x00\x00')
        if request[:3] in (b'\x03\x00\x00', b'\x83\x00\x00') and len(request) >= 9:
            size, offset = struct.unpack_from('<HI', request, 3)
            if request[0] == 3:
                allowed = (len(request) == 9+size and 0 < size <= 52
                           and size % 4 == 0 and offset % 4 == 0
                           and offset+size <= APP_SIZE)
            else:
                allowed = len(request) == 9 and 0 < size <= 55 and offset+size <= APP_SIZE
        if not allowed or len(request) > 64:
            raise ValueError('Command/address/length outside the reviewed update protocol')
        count = self.handle.write(b'\x00'+request+bytes(64-len(request)))
        if count != 65:
            raise IOError(f'Incomplete bootloader output report: {count}/65')

    def query(self, request):
        self.send(request)
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            raw = bytes(self.handle.read(65, 500))
            # No report-ID byte in hidapi input for this unnumbered endpoint.
            if len(raw) >= 2 and raw[0] == request[0]:
                if raw[1] != 0:
                    raise IOError(f'Bootloader command {request[0]:02x} status {raw[1]:02x}')
                return raw[2:]
        raise TimeoutError(f'Bootloader command {request[0]:02x} did not respond')

    def read_image(self, expected_images=None):
        result = bytearray()
        for offset in range(0, APP_SIZE, 55):
            size = min(55, APP_SIZE-offset)
            request = b'\x83\x00\x00'+struct.pack('<HI', size, offset)
            for attempt in range(3):
                chunk = self.query(request)[:size]
                if len(chunk) == size and (expected_images is None or any(
                        chunk == image[offset:offset+size] for image in expected_images)):
                    break
            else:
                raise IOError(f'Firmware readback differs at application offset {offset:#x}')
            result.extend(chunk)
        image = bytes(result)
        if expected_images is not None and image not in expected_images:
            raise IOError('Whole-image readback differs from all expected images')
        identify_image(self.stock, image)
        return image

    def verify(self, image, full_read=True):
        raw = self.query(b'\x84\x00\x00')
        if len(raw) < 8 or struct.unpack_from('<II', raw) != (crc(image), crc(image)):
            raise IOError('Bootloader computed/stored CRC mismatch')
        if full_read:
            self.read_image([image])

    def program(self, image):
        identify_image(self.stock, image)
        self.query(b'\x02\x00\x00')
        for offset in range(0, APP_SIZE, 52):
            chunk = image[offset:offset+52]
            self.send(b'\x03\x00\x00'+struct.pack('<HI', len(chunk), offset)+chunk)
            time.sleep(0.01)  # Same 10 ms pacing as FlashFirmwareFizz.
        self.verify(image)


def program_with_rollback(boot, target, recovery_image, result):
    # Any interrupted update needs a verified recovery image before reset.
    result['firmware_erase_or_write_attempted'] = True
    try:
        boot.program(target)
        result['programmed_sha256'] = digest(target)
        result['full_readback_and_crc_verified'] = True
        return target
    except Exception as error:
        result['target_error'] = str(error)
        print('Target update failed; restoring the previous verified firmware.', flush=True)
        boot.program(recovery_image)
        result['rollback_sha256'] = digest(recovery_image)
        result['rollback_verified'] = True
        result['stock_rollback_verified'] = digest(recovery_image) == STOCK_SHA256
        return recovery_image
