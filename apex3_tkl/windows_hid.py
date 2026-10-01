"""Windows HID capability checks and unambiguous device discovery."""
import ctypes
from ctypes import wintypes as w
import time
import hid


class Caps(ctypes.Structure):
    _fields_ = [(n, w.USHORT) for n in [
        'Usage', 'UsagePage', 'InputReportByteLength', 'OutputReportByteLength',
        'FeatureReportByteLength']] + [('Reserved', w.USHORT * 17)] + [
        (n, w.USHORT) for n in ['NumberLinkCollectionNodes', 'NumberInputButtonCaps',
        'NumberInputValueCaps', 'NumberInputDataIndices', 'NumberOutputButtonCaps',
        'NumberOutputValueCaps', 'NumberOutputDataIndices', 'NumberFeatureButtonCaps',
        'NumberFeatureValueCaps', 'NumberFeatureDataIndices']]


def report_sizes(path):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    library = ctypes.WinDLL('hid')
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p,
                                  w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    library.HidD_GetPreparsedData.argtypes = [w.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    library.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    library.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(Caps)]
    handle = kernel.CreateFileW(path.decode(), 0, 3, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    preparsed = ctypes.c_void_p()
    caps = Caps()
    try:
        if not library.HidD_GetPreparsedData(handle, ctypes.byref(preparsed)):
            raise ctypes.WinError(ctypes.get_last_error())
        if library.HidP_GetCaps(preparsed, ctypes.byref(caps)) != 0x110000:
            raise RuntimeError('HID capabilities unavailable')
        return {name: getattr(caps, name) for name in (
            'InputReportByteLength', 'OutputReportByteLength', 'FeatureReportByteLength')}
    finally:
        if preparsed:
            library.HidD_FreePreparsedData(preparsed)
        kernel.CloseHandle(handle)


def find_device(pid, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = [d for d in hid.enumerate(0x1038, pid)
                 if d['usage_page'] == 0xffc0 and d['usage'] == 1]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise RuntimeError('Multiple matching devices; refusing to choose')
        time.sleep(0.1)
    raise TimeoutError(f'Keyboard PID {pid:04x} did not appear')
