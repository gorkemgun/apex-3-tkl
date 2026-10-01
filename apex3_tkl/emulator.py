"""Execute selected stock ARM routines in an emulator; no device I/O."""
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3


class Firmware:
    def __init__(self, image):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(0, 0x20000)
        self.uc.mem_map(0x20000000, 0x10000)
        self.uc.mem_write(0x3C00, bytes(image))
        self.uc.mem_write(0x20000010, bytes(image[0x56BC:0x5D20]))

    def call(self, address, *args):
        self.uc.reg_write(UC_ARM_REG_SP, 0x2000F000)
        self.uc.reg_write(UC_ARM_REG_LR, 0x10001)
        for register, value in zip([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3], args):
            self.uc.reg_write(register, value)
        self.uc.emu_start(address | 1, 0x10000, count=1000000)
        if self.uc.reg_read(UC_ARM_REG_PC) != 0x10000:
            raise RuntimeError(f"Routine {address:#x} did not return")
        return self.uc.reg_read(UC_ARM_REG_R0)

    def binding(self, key, layer=0):
        self.call(0x663C, key, 0x2000E000)
        index = self.uc.mem_read(0x2000E000, 1)[0]
        base = 0x2000001C if layer == 0 else 0x2000033C
        return bytes(self.uc.mem_read(base + 5 * index, 5))

    def color(self, zone, tick):
        self.call(0x7AB0, tick, 0x20000974 + 12 * zone, 0x2000E000)
        return bytes(self.uc.mem_read(0x2000E000, 3))


from unicorn import UC_HOOK_CODE
from .firmware import CACHE, build_image, identify_image, parse_color

def validate(image, patched, color, remap_insert=False):
    old, new = Firmware(image), Firmware(patched)
    old.call(0x4AA4)
    new.call(0x4AA4)
    assert old.binding(0x49) == bytes([0x51, 0x49, 0, 0, 0])
    assert new.binding(0x49) == bytes([0x51, 0x46 if remap_insert else 0x49, 0, 0, 0])
    changed = []
    for key, index in enumerate(image[0x5F88:0x6088]):
        if index == 0xFF:
            continue
        for layer in (0, 1):
            if old.binding(key, layer) != new.binding(key, layer):
                changed.append((key, layer))
    assert changed == ([(0x49, 0)] if remap_insert else []), changed
    old.call(0x40D4)
    new.call(0x40D4)
    samples = 0
    original_colors = set()
    for zone in range(8):
        for tick in [0, 1, 10, 100, 999, 5000, 9999, 10000, 10001, 50000, 65535, 999999]:
            expected = bytes(color)
            actual = new.color(zone, tick)
            assert actual == expected, (zone, tick, actual.hex(), expected.hex())
            original_colors.add(old.color(zone, tick))
            samples += 1
    assert len(original_colors) > 1, "Control firmware should produce changing colors"
    return {"changed_key_layers": changed, "rgb_zone_time_samples": samples,
            "original_distinct_colors": len(original_colors),
            "limitation": "Selected routines only; not complete boot or hardware validation"}


class Renderer(Firmware):
    """Run real ARM render/wake code; model only peripheral I/O and delay."""
    def __init__(self,image,brightness=16):
        super().__init__(image)
        self.uc.mem_map(0x40000000,0x100000)
        self.output = [bytes(3)]*8
        self.updates = []
        self.i2c_writes = []
        self.uc.hook_add(UC_HOOK_CODE,self.intercept)
        self.call(0x4aa4)
        self.uc.mem_write(0x20000015,bytes([brightness]))
        self.call(0x40d4)

    def intercept(self,uc,address,size,unused):
        if address == 0x7664:
            zone = uc.reg_read(UC_ARM_REG_R1)
            rgb = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0),3))
            self.output[zone] = rgb
            self.updates.append((zone,rgb))
        elif address == 0x7318:
            register = uc.reg_read(UC_ARM_REG_R2)
            value = bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R3)))
            self.i2c_writes.append((register,value))
            # The initializer resets the LED IC. Model PWM register loss.
            if register == 0x7f:
                self.output = [bytes(3)]*8
        elif address == 0x4c54:
            pass  # Millisecond busy-wait needs a hardware tick, irrelevant here.
        else:
            return
        uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))

    def render_frame(self):
        self.updates = []
        for _ in range(8):
            self.call(0x426c)
        return list(self.updates)

    def reconnect(self):
        self.uc.mem_write(0x200006d8,b'\x00')
        self.uc.mem_write(0x20001142,b'\x00')
        self.call(0x5880)  # actual USB lifecycle state machine: disable
        assert bytes(self.uc.mem_read(0x200006d8,1)) == b'\x01'
        self.uc.mem_write(0x20001142,b'\x06')
        self.call(0x5880)  # actual reinitialize/enable path, including 45FC
        assert bytes(self.uc.mem_read(0x200006d8,1)) == b'\x00'
        assert self.i2c_writes, 'LED initializer should have accessed its peripheral'


def test_wake(source,patched,color):
    old = Renderer(source)
    assert len(old.render_frame()) == 8
    old.reconnect()
    assert old.render_frame() == [], 'Control must reproduce the stale-cache bug'
    assert old.output == [bytes(3)]*8
    scenarios = 0
    for brightness in (0,1,8,16):
        for path in ('usb_reconnect','resume_only'):
            new = Renderer(patched,brightness)
            new.render_frame()
            keys = bytes(new.uc.mem_read(0x2000001c,0x640))
            # Assert writes are confined to the 24-byte RGB cache, not neighbors.
            neighbors = (bytes(new.uc.mem_read(CACHE-1,1)),bytes(new.uc.mem_read(CACHE+24,1)))
            if path == 'usb_reconnect':
                new.reconnect()
            else:
                new.output = [bytes(3)]*8  # simulate lost peripheral state
                new.call(0x45fc)
                assert neighbors == (bytes(new.uc.mem_read(CACHE-1,1)),bytes(new.uc.mem_read(CACHE+24,1)))
            assert bytes(new.uc.mem_read(CACHE,24)) == bytes(24)
            new.render_frame()
            expected = bytes((component*brightness)//16 for component in color)
            assert new.output == [expected]*8,(brightness,path,new.output)
            assert bytes(new.uc.mem_read(0x2000001c,0x640)) == keys
            assert new.render_frame() == [], 'Steady unchanged colors should still skip writes'
            scenarios += 1
    # A host-supplied non-green color also survives the resume-only path.
    new = Renderer(patched)
    direct = bytes.fromhex('21 ff')+bytes([12,34,56])*8
    new.uc.mem_write(0x2000c000,direct)
    new.uc.mem_write(0x2000c400,struct.pack('<I',len(direct)))
    new.call(0x6874,0x2000c000,0x2000c200,0x2000c400)
    new.render_frame()
    new.output = [bytes(3)]*8
    new.call(0x45fc)
    new.render_frame()
    assert new.output == [bytes([12,34,56])]*8
    return {'old_green_reconnect_reproduces_dark_output':True,
            'wake_path_brightness_scenarios_passed':scenarios,
            'custom_direct_color_resume_passed':True,
            'keymaps_preserved':True,'steady_state_write_optimization_preserved':True,
            'limitation':'Actual ARM routines executed; LED register loss modeled, not a physical shutdown/reboot test.'}


def validate_emulation(stock, image):
    if not __debug__:
        raise RuntimeError("ARM validation requires Python without -O / PYTHONOPTIMIZE")
    info = identify_image(stock, image)
    if info["kind"] != "solid-color":
        raise ValueError("Emulation expects a supported solid-color image")
    color = parse_color(info["color"])
    result = {"color_and_keys": validate(stock, image, color)}
    if info["wake_fix"]:
        control = build_image(stock, bytes([0, 255, 0]), wake_fix=False)
        result["wake"] = test_wake(control, image, color)
    else:
        result["wake"] = {"tested": False, "reason": "Wake fix was explicitly disabled"}
    return result
