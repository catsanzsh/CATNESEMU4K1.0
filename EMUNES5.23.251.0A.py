import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Scale
import struct
import random
import time
import threading

# --- Constants for "Monika's Playhouse" Dark Theme ---
DARK_BG = "#2B2B2B"  # Dark Charcoal - Main background
DARK_FG = "#E0E0E0"  # Light Gray - Main foreground (text)
DARK_ACCENT = "#8B0000"  # Dark Red (Monika's tie color) - For highlights/specific elements
DARK_BORDER = "#444444" # Darker Gray - Border color for widgets/frames
DARK_CANVAS_BG = "#000000" # Black - For the NES screen display
DARK_BUTTON_BG = "#4A4A4A" # Gray - Button background
DARK_BUTTON_FG = "#E0E0E0" # Light Gray - Button foreground
DARK_BUTTON_ACTIVE_BG = "#6A6A6A" # Lighter Gray - Button background on hover/active
DARK_BUTTON_ACTIVE_FG = "#FFFFFF" # White - Button foreground on hover/active
DARK_TEXT_BG = "#1E1E1E" # Very Dark Gray - Text widget background (e.g., console)
DARK_TEXT_FG = "#E0E0E0" # Light Gray - Text widget foreground
DARK_ENTRY_BG = "#3E3E3E" # Slightly lighter dark - Entry widget background (if any)
DARK_ENTRY_FG = "#E0E0E0" # Light Gray - Entry widget foreground
DARK_SCROLLBAR_TROUGH = "#3A3A3A" # Darker gray - Scrollbar trough color
DARK_SCROLLBAR_BG = "#6B6B6B" # Medium gray - Scrollbar slider color
DARK_SCROLLBAR_ACTIVE_BG = "#8B8B8B" # Lighter gray - Scrollbar active slider color

# NES Screen dimensions
NES_WIDTH = 256
NES_HEIGHT = 240

class NESRom:
    def __init__(self, data):
        self.data = data
        self.header = self.data[0:16]
        
        # Validate NES header
        if self.header[0:4] != b'NES\x1A':
            raise ValueError("Invalid NES ROM header")
        
        self.prg_rom_size = self.header[4] * 16384  # PRG ROM size in bytes (16KB units)
        self.chr_rom_size = self.header[5] * 8192    # CHR ROM size in bytes (8KB units)

        # Mapper (iNES 1.0 format)
        self.mapper = ((self.header[7] & 0xF0) >> 4) | (self.header[6] & 0xF0)
        self.mirror_mode = (self.header[6] & 0x01) # 0 for Horizontal, 1 for Vertical
        self.battery_backed = (self.header[6] & 0x02) != 0
        self.trainer_present = (self.header[6] & 0x04) != 0

        self.prg_rom_start = 16
        if self.trainer_present:
            self.prg_rom_start += 512

        self.prg_rom = self.data[self.prg_rom_start : self.prg_rom_start + self.prg_rom_size]
        self.chr_rom_start = self.prg_rom_start + self.prg_rom_size
        self.chr_rom = self.data[self.chr_rom_start : self.chr_rom_start + self.chr_rom_size]

        # Initialize CHR RAM if no CHR ROM
        self.chr_ram = bytearray(8192) if self.chr_rom_size == 0 else None

        print(f"Loaded ROM: PRG ROM {self.prg_rom_size/1024:.0f}KB, CHR ROM {self.chr_rom_size/1024:.0f}KB, Mapper {self.mapper}")

    def read_prg(self, addr):
        # NROM mapping
        if self.mapper == 0:
            if self.prg_rom_size == 16384:  # 16KB - mirrored
                return self.prg_rom[addr & 0x3FFF]
            else:  # 32KB
                return self.prg_rom[addr & 0x7FFF]
        return 0

    def write_prg(self, addr, data):
        # NROM has no PRG RAM/registers
        pass

    def read_chr(self, addr):
        if self.chr_rom_size > 0:
            return self.chr_rom[addr & (self.chr_rom_size - 1)]
        else:
            return self.chr_ram[addr & 0x1FFF]

    def write_chr(self, addr, data):
        if self.chr_ram is not None:
            self.chr_ram[addr & 0x1FFF] = data


class Cartridge:
    def __init__(self, rom):
        self.rom = rom

    def cpu_read(self, addr):
        if 0x8000 <= addr <= 0xFFFF:
            return self.rom.read_prg(addr - 0x8000)
        return None

    def cpu_write(self, addr, data):
        if 0x8000 <= addr <= 0xFFFF:
            self.rom.write_prg(addr - 0x8000, data)
            return True
        return False

    def ppu_read(self, addr):
        if 0x0000 <= addr <= 0x1FFF:
            return self.rom.read_chr(addr)
        return None

    def ppu_write(self, addr, data):
        if 0x0000 <= addr <= 0x1FFF:
            self.rom.write_chr(addr, data)
            return True
        return False


class Bus:
    def __init__(self):
        self.cpu = None
        self.ppu = None
        self.cart = None
        self.cpu_ram = bytearray(2048)
        self.system_clock_counter = 0
        
        # Controller state
        self.controller1_state = 0x00
        self.controller1_shift = 0x00

    def connect_cpu(self, cpu):
        self.cpu = cpu
        self.cpu.connect_bus(self)

    def connect_ppu(self, ppu):
        self.ppu = ppu
        self.ppu.connect_bus(self)

    def insert_cartridge(self, cartridge):
        self.cart = cartridge

    def cpu_write(self, addr, data):
        addr &= 0xFFFF  # Ensure 16-bit address
        
        # Check cartridge first
        if self.cart and self.cart.cpu_write(addr, data):
            return
        
        if 0x0000 <= addr <= 0x1FFF:  # RAM (mirrored)
            self.cpu_ram[addr & 0x07FF] = data
        elif 0x2000 <= addr <= 0x3FFF:  # PPU registers (mirrored every 8 bytes)
            self.ppu.cpu_write(addr & 0x2007, data)
        elif addr == 0x4014:  # OAM DMA
            self.cpu.dma_page = data
            self.cpu.dma_addr = 0x00
            self.cpu.dma_transfer = True
            self.cpu.dma_dummy = True
        elif addr == 0x4016:  # Controller
            if data & 0x01:
                self.controller1_shift = self.controller1_state
        # APU and other I/O registers not implemented

    def cpu_read(self, addr):
        addr &= 0xFFFF
        data = 0x00
        
        # Check cartridge first
        if self.cart:
            cart_data = self.cart.cpu_read(addr)
            if cart_data is not None:
                return cart_data
        
        if 0x0000 <= addr <= 0x1FFF:  # RAM
            data = self.cpu_ram[addr & 0x07FF]
        elif 0x2000 <= addr <= 0x3FFF:  # PPU registers
            data = self.ppu.cpu_read(addr & 0x2007)
        elif addr == 0x4016:  # Controller 1
            data = 0x40 | (self.controller1_shift & 0x01)
            self.controller1_shift >>= 1
        
        return data

    def ppu_write(self, addr, data):
        addr &= 0x3FFF  # 14-bit PPU address space
        
        if self.cart and self.cart.ppu_write(addr, data):
            return
        
        if 0x2000 <= addr <= 0x3EFF:  # Nametables
            # Simplified mirroring - should respect cartridge mirroring mode
            if self.cart.rom.mirror_mode == 0:  # Horizontal
                mirror_addr = ((addr & 0x0800) >> 1) | (addr & 0x03FF)
            else:  # Vertical
                mirror_addr = addr & 0x07FF
            self.ppu.vram[mirror_addr] = data
        elif 0x3F00 <= addr <= 0x3FFF:  # Palette
            palette_addr = addr & 0x1F
            # Mirror background color
            if palette_addr == 0x10:
                palette_addr = 0x00
            elif palette_addr == 0x14:
                palette_addr = 0x04
            elif palette_addr == 0x18:
                palette_addr = 0x08
            elif palette_addr == 0x1C:
                palette_addr = 0x0C
            self.ppu.palette_ram[palette_addr] = data & 0x3F

    def ppu_read(self, addr):
        addr &= 0x3FFF
        data = 0x00
        
        if self.cart:
            cart_data = self.cart.ppu_read(addr)
            if cart_data is not None:
                return cart_data
        
        if 0x2000 <= addr <= 0x3EFF:  # Nametables
            if self.cart.rom.mirror_mode == 0:  # Horizontal
                mirror_addr = ((addr & 0x0800) >> 1) | (addr & 0x03FF)
            else:  # Vertical
                mirror_addr = addr & 0x07FF
            data = self.ppu.vram[mirror_addr]
        elif 0x3F00 <= addr <= 0x3FFF:  # Palette
            palette_addr = addr & 0x1F
            if palette_addr == 0x10:
                palette_addr = 0x00
            elif palette_addr == 0x14:
                palette_addr = 0x04
            elif palette_addr == 0x18:
                palette_addr = 0x08
            elif palette_addr == 0x1C:
                palette_addr = 0x0C
            data = self.ppu.palette_ram[palette_addr] & 0x3F
        
        return data

    def clock(self):
        # PPU runs 3x faster than CPU
        self.ppu.clock()
        
        if self.system_clock_counter % 3 == 0:
            # DMA transfer handling
            if self.cpu.dma_transfer:
                if self.cpu.dma_dummy:
                    if self.system_clock_counter % 2 == 1:
                        self.cpu.dma_dummy = False
                else:
                    if self.system_clock_counter % 2 == 0:
                        self.cpu.dma_data = self.cpu_read((self.cpu.dma_page << 8) | self.cpu.dma_addr)
                    else:
                        self.ppu.oam[self.cpu.dma_addr] = self.cpu.dma_data
                        self.cpu.dma_addr += 1
                        if self.cpu.dma_addr == 0:  # Wrapped around
                            self.cpu.dma_transfer = False
                            self.cpu.dma_dummy = True
            else:
                self.cpu.clock()
        
        self.system_clock_counter += 1


class CPU6502:
    # Status flags
    FLAG_C = 0x01  # Carry
    FLAG_Z = 0x02  # Zero
    FLAG_I = 0x04  # Interrupt Disable
    FLAG_D = 0x08  # Decimal (unused in NES)
    FLAG_B = 0x10  # Break
    FLAG_U = 0x20  # Unused (always 1)
    FLAG_V = 0x40  # Overflow
    FLAG_N = 0x80  # Negative

    def __init__(self):
        self.bus = None
        
        # Registers
        self.a = 0x00
        self.x = 0x00
        self.y = 0x00
        self.stkp = 0xFD
        self.pc = 0x0000
        self.status = 0x24  # I and U flags set
        
        # Internal
        self.fetched = 0x00
        self.addr_abs = 0x0000
        self.addr_rel = 0x00
        self.opcode = 0x00
        self.cycles = 0
        
        # DMA
        self.dma_page = 0x00
        self.dma_addr = 0x00
        self.dma_data = 0x00
        self.dma_transfer = False
        self.dma_dummy = True
        
        # Initialize instruction lookup table
        self._init_lookup_table()

    def _init_lookup_table(self):
        # Complete 6502 instruction set
        self.lookup = [None] * 256
        
        # Format: (addressing_mode, operation, base_cycles)
        instructions = {
            0x00: (self.IMP, self.BRK, 7), 0x01: (self.IZX, self.ORA, 6), 0x05: (self.ZP0, self.ORA, 3),
            0x06: (self.ZP0, self.ASL, 5), 0x08: (self.IMP, self.PHP, 3), 0x09: (self.IMM, self.ORA, 2),
            0x0A: (self.ACC, self.ASL, 2), 0x0D: (self.ABS, self.ORA, 4), 0x0E: (self.ABS, self.ASL, 6),
            
            0x10: (self.REL, self.BPL, 2), 0x11: (self.IZY, self.ORA, 5), 0x15: (self.ZPX, self.ORA, 4),
            0x16: (self.ZPX, self.ASL, 6), 0x18: (self.IMP, self.CLC, 2), 0x19: (self.ABY, self.ORA, 4),
            0x1D: (self.ABX, self.ORA, 4), 0x1E: (self.ABX, self.ASL, 7),
            
            0x20: (self.ABS, self.JSR, 6), 0x21: (self.IZX, self.AND, 6), 0x24: (self.ZP0, self.BIT, 3),
            0x25: (self.ZP0, self.AND, 3), 0x26: (self.ZP0, self.ROL, 5), 0x28: (self.IMP, self.PLP, 4),
            0x29: (self.IMM, self.AND, 2), 0x2A: (self.ACC, self.ROL, 2), 0x2C: (self.ABS, self.BIT, 4),
            0x2D: (self.ABS, self.AND, 4), 0x2E: (self.ABS, self.ROL, 6),
            
            0x30: (self.REL, self.BMI, 2), 0x31: (self.IZY, self.AND, 5), 0x35: (self.ZPX, self.AND, 4),
            0x36: (self.ZPX, self.ROL, 6), 0x38: (self.IMP, self.SEC, 2), 0x39: (self.ABY, self.AND, 4),
            0x3D: (self.ABX, self.AND, 4), 0x3E: (self.ABX, self.ROL, 7),
            
            0x40: (self.IMP, self.RTI, 6), 0x41: (self.IZX, self.EOR, 6), 0x45: (self.ZP0, self.EOR, 3),
            0x46: (self.ZP0, self.LSR, 5), 0x48: (self.IMP, self.PHA, 3), 0x49: (self.IMM, self.EOR, 2),
            0x4A: (self.ACC, self.LSR, 2), 0x4C: (self.ABS, self.JMP, 3), 0x4D: (self.ABS, self.EOR, 4),
            0x4E: (self.ABS, self.LSR, 6),
            
            0x50: (self.REL, self.BVC, 2), 0x51: (self.IZY, self.EOR, 5), 0x55: (self.ZPX, self.EOR, 4),
            0x56: (self.ZPX, self.LSR, 6), 0x58: (self.IMP, self.CLI, 2), 0x59: (self.ABY, self.EOR, 4),
            0x5D: (self.ABX, self.EOR, 4), 0x5E: (self.ABX, self.LSR, 7),
            
            0x60: (self.IMP, self.RTS, 6), 0x61: (self.IZX, self.ADC, 6), 0x65: (self.ZP0, self.ADC, 3),
            0x66: (self.ZP0, self.ROR, 5), 0x68: (self.IMP, self.PLA, 4), 0x69: (self.IMM, self.ADC, 2),
            0x6A: (self.ACC, self.ROR, 2), 0x6C: (self.IND, self.JMP, 5), 0x6D: (self.ABS, self.ADC, 4),
            0x6E: (self.ABS, self.ROR, 6),
            
            0x70: (self.REL, self.BVS, 2), 0x71: (self.IZY, self.ADC, 5), 0x75: (self.ZPX, self.ADC, 4),
            0x76: (self.ZPX, self.ROR, 6), 0x78: (self.IMP, self.SEI, 2), 0x79: (self.ABY, self.ADC, 4),
            0x7D: (self.ABX, self.ADC, 4), 0x7E: (self.ABX, self.ROR, 7),
            
            0x81: (self.IZX, self.STA, 6), 0x84: (self.ZP0, self.STY, 3), 0x85: (self.ZP0, self.STA, 3),
            0x86: (self.ZP0, self.STX, 3), 0x88: (self.IMP, self.DEY, 2), 0x8A: (self.IMP, self.TXA, 2),
            0x8C: (self.ABS, self.STY, 4), 0x8D: (self.ABS, self.STA, 4), 0x8E: (self.ABS, self.STX, 4),
            
            0x90: (self.REL, self.BCC, 2), 0x91: (self.IZY, self.STA, 6), 0x94: (self.ZPX, self.STY, 4),
            0x95: (self.ZPX, self.STA, 4), 0x96: (self.ZPY, self.STX, 4), 0x98: (self.IMP, self.TYA, 2),
            0x99: (self.ABY, self.STA, 5), 0x9A: (self.IMP, self.TXS, 2), 0x9D: (self.ABX, self.STA, 5),
            
            0xA0: (self.IMM, self.LDY, 2), 0xA1: (self.IZX, self.LDA, 6), 0xA2: (self.IMM, self.LDX, 2),
            0xA4: (self.ZP0, self.LDY, 3), 0xA5: (self.ZP0, self.LDA, 3), 0xA6: (self.ZP0, self.LDX, 3),
            0xA8: (self.IMP, self.TAY, 2), 0xA9: (self.IMM, self.LDA, 2), 0xAA: (self.IMP, self.TAX, 2),
            0xAC: (self.ABS, self.LDY, 4), 0xAD: (self.ABS, self.LDA, 4), 0xAE: (self.ABS, self.LDX, 4),
            
            0xB0: (self.REL, self.BCS, 2), 0xB1: (self.IZY, self.LDA, 5), 0xB4: (self.ZPX, self.LDY, 4),
            0xB5: (self.ZPX, self.LDA, 4), 0xB6: (self.ZPY, self.LDX, 4), 0xB8: (self.IMP, self.CLV, 2),
            0xB9: (self.ABY, self.LDA, 4), 0xBA: (self.IMP, self.TSX, 2), 0xBC: (self.ABX, self.LDY, 4),
            0xBD: (self.ABX, self.LDA, 4), 0xBE: (self.ABY, self.LDX, 4),
            
            0xC0: (self.IMM, self.CPY, 2), 0xC1: (self.IZX, self.CMP, 6), 0xC4: (self.ZP0, self.CPY, 3),
            0xC5: (self.ZP0, self.CMP, 3), 0xC6: (self.ZP0, self.DEC, 5), 0xC8: (self.IMP, self.INY, 2),
            0xC9: (self.IMM, self.CMP, 2), 0xCA: (self.IMP, self.DEX, 2), 0xCC: (self.ABS, self.CPY, 4),
            0xCD: (self.ABS, self.CMP, 4), 0xCE: (self.ABS, self.DEC, 6),
            
            0xD0: (self.REL, self.BNE, 2), 0xD1: (self.IZY, self.CMP, 5), 0xD5: (self.ZPX, self.CMP, 4),
            0xD6: (self.ZPX, self.DEC, 6), 0xD8: (self.IMP, self.CLD, 2), 0xD9: (self.ABY, self.CMP, 4),
            0xDD: (self.ABX, self.CMP, 4), 0xDE: (self.ABX, self.DEC, 7),
            
            0xE0: (self.IMM, self.CPX, 2), 0xE1: (self.IZX, self.SBC, 6), 0xE4: (self.ZP0, self.CPX, 3),
            0xE5: (self.ZP0, self.SBC, 3), 0xE6: (self.ZP0, self.INC, 5), 0xE8: (self.IMP, self.INX, 2),
            0xE9: (self.IMM, self.SBC, 2), 0xEA: (self.IMP, self.NOP, 2), 0xEC: (self.ABS, self.CPX, 4),
            0xED: (self.ABS, self.SBC, 4), 0xEE: (self.ABS, self.INC, 6),
            
            0xF0: (self.REL, self.BEQ, 2), 0xF1: (self.IZY, self.SBC, 5), 0xF5: (self.ZPX, self.SBC, 4),
            0xF6: (self.ZPX, self.INC, 6), 0xF8: (self.IMP, self.SED, 2), 0xF9: (self.ABY, self.SBC, 4),
            0xFD: (self.ABX, self.SBC, 4), 0xFE: (self.ABX, self.INC, 7),
        }
        
        for opcode, (addr_mode, operation, cycles) in instructions.items():
            self.lookup[opcode] = (addr_mode, operation, cycles)
        
        # Fill in illegal opcodes as NOPs for stability
        for i in range(256):
            if self.lookup[i] is None:
                self.lookup[i] = (self.IMP, self.NOP, 2)

    def connect_bus(self, bus):
        self.bus = bus

    def read(self, addr):
        return self.bus.cpu_read(addr)

    def write(self, addr, data):
        self.bus.cpu_write(addr, data)

    def get_flag(self, flag):
        return (self.status & flag) != 0

    def set_flag(self, flag, value):
        if value:
            self.status |= flag
        else:
            self.status &= ~flag

    def reset(self):
        self.a = 0x00
        self.x = 0x00
        self.y = 0x00
        self.stkp = 0xFD
        self.status = 0x24  # I and U set
        
        # Read reset vector at 0xFFFC-0xFFFD
        lo = self.read(0xFFFC)
        hi = self.read(0xFFFD)
        self.pc = (hi << 8) | lo
        
        self.addr_rel = 0x00
        self.addr_abs = 0x0000
        self.fetched = 0x00
        self.cycles = 8

    def interrupt_request(self):
        if not self.get_flag(self.FLAG_I):
            self.push_word(self.pc)
            self.push(self.status & ~self.FLAG_B)
            self.set_flag(self.FLAG_I, True)
            
            self.pc = self.read(0xFFFE) | (self.read(0xFFFF) << 8)
            self.cycles = 7

    def non_maskable_interrupt(self):
        self.push_word(self.pc)
        self.push(self.status & ~self.FLAG_B)
        self.set_flag(self.FLAG_I, True)
        
        self.pc = self.read(0xFFFA) | (self.read(0xFFFB) << 8)
        self.cycles = 8

    def push(self, data):
        self.write(0x0100 + self.stkp, data)
        self.stkp = (self.stkp - 1) & 0xFF

    def pop(self):
        self.stkp = (self.stkp + 1) & 0xFF
        return self.read(0x0100 + self.stkp)

    def push_word(self, data):
        self.push((data >> 8) & 0xFF)
        self.push(data & 0xFF)

    def pop_word(self):
        lo = self.pop()
        hi = self.pop()
        return (hi << 8) | lo

    # Addressing modes
    def IMP(self): return 0
    def ACC(self): return 0
    
    def IMM(self):
        self.addr_abs = self.pc
        self.pc += 1
        return 0
    
    def ZP0(self):
        self.addr_abs = self.read(self.pc)
        self.pc += 1
        return 0
    
    def ZPX(self):
        self.addr_abs = (self.read(self.pc) + self.x) & 0xFF
        self.pc += 1
        return 0
    
    def ZPY(self):
        self.addr_abs = (self.read(self.pc) + self.y) & 0xFF
        self.pc += 1
        return 0
    
    def REL(self):
        self.addr_rel = self.read(self.pc)
        self.pc += 1
        if self.addr_rel & 0x80:
            self.addr_rel |= 0xFF00
        return 0
    
    def ABS(self):
        lo = self.read(self.pc)
        self.pc += 1
        hi = self.read(self.pc)
        self.pc += 1
        self.addr_abs = (hi << 8) | lo
        return 0
    
    def ABX(self):
        lo = self.read(self.pc)
        self.pc += 1
        hi = self.read(self.pc)
        self.pc += 1
        self.addr_abs = ((hi << 8) | lo) + self.x
        
        # Page boundary crossing
        if (self.addr_abs & 0xFF00) != (hi << 8):
            return 1
        return 0
    
    def ABY(self):
        lo = self.read(self.pc)
        self.pc += 1
        hi = self.read(self.pc)
        self.pc += 1
        self.addr_abs = ((hi << 8) | lo) + self.y
        
        # Page boundary crossing
        if (self.addr_abs & 0xFF00) != (hi << 8):
            return 1
        return 0
    
    def IND(self):
        ptr_lo = self.read(self.pc)
        self.pc += 1
        ptr_hi = self.read(self.pc)
        self.pc += 1
        ptr = (ptr_hi << 8) | ptr_lo
        
        # 6502 bug - page boundary wrap
        if ptr_lo == 0xFF:
            self.addr_abs = (self.read(ptr & 0xFF00) << 8) | self.read(ptr)
        else:
            self.addr_abs = (self.read(ptr + 1) << 8) | self.read(ptr)
        return 0
    
    def IZX(self):
        t = self.read(self.pc)
        self.pc += 1
        lo = self.read((t + self.x) & 0xFF)
        hi = self.read((t + self.x + 1) & 0xFF)
        self.addr_abs = (hi << 8) | lo
        return 0
    
    def IZY(self):
        t = self.read(self.pc)
        self.pc += 1
        lo = self.read(t & 0xFF)
        hi = self.read((t + 1) & 0xFF)
        self.addr_abs = ((hi << 8) | lo) + self.y
        
        # Page boundary crossing
        if (self.addr_abs & 0xFF00) != (hi << 8):
            return 1
        return 0

    def fetch(self):
        if self.lookup[self.opcode][0] not in [self.IMP, self.ACC]:
            self.fetched = self.read(self.addr_abs)
        else:
            self.fetched = self.a
        return self.fetched

    # Instructions
    def ADC(self):
        self.fetch()
        temp = self.a + self.fetched + (1 if self.get_flag(self.FLAG_C) else 0)
        self.set_flag(self.FLAG_C, temp > 255)
        self.set_flag(self.FLAG_Z, (temp & 0xFF) == 0)
        self.set_flag(self.FLAG_V, (~(self.a ^ self.fetched) & (self.a ^ temp) & 0x80) != 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        self.a = temp & 0xFF
        return 1

    def AND(self):
        self.fetch()
        self.a &= self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 1

    def ASL(self):
        if self.lookup[self.opcode][0] == self.ACC:
            self.set_flag(self.FLAG_C, self.a & 0x80)
            self.a = (self.a << 1) & 0xFF
            self.set_flag(self.FLAG_Z, self.a == 0)
            self.set_flag(self.FLAG_N, self.a & 0x80)
        else:
            self.fetch()
            self.set_flag(self.FLAG_C, self.fetched & 0x80)
            temp = (self.fetched << 1) & 0xFF
            self.write(self.addr_abs, temp)
            self.set_flag(self.FLAG_Z, temp == 0)
            self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def BCC(self): return self._branch(not self.get_flag(self.FLAG_C))
    def BCS(self): return self._branch(self.get_flag(self.FLAG_C))
    def BEQ(self): return self._branch(self.get_flag(self.FLAG_Z))
    def BMI(self): return self._branch(self.get_flag(self.FLAG_N))
    def BNE(self): return self._branch(not self.get_flag(self.FLAG_Z))
    def BPL(self): return self._branch(not self.get_flag(self.FLAG_N))
    def BVC(self): return self._branch(not self.get_flag(self.FLAG_V))
    def BVS(self): return self._branch(self.get_flag(self.FLAG_V))

    def _branch(self, condition):
        if condition:
            self.cycles += 1
            self.addr_abs = self.pc + self.addr_rel
            
            if (self.addr_abs & 0xFF00) != (self.pc & 0xFF00):
                self.cycles += 1
            
            self.pc = self.addr_abs
        return 0

    def BIT(self):
        self.fetch()
        temp = self.a & self.fetched
        self.set_flag(self.FLAG_Z, temp == 0)
        self.set_flag(self.FLAG_N, self.fetched & 0x80)
        self.set_flag(self.FLAG_V, self.fetched & 0x40)
        return 0

    def BRK(self):
        self.pc += 1
        self.push_word(self.pc)
        self.push(self.status | self.FLAG_B | self.FLAG_U)
        self.set_flag(self.FLAG_I, True)
        self.pc = self.read(0xFFFE) | (self.read(0xFFFF) << 8)
        return 0

    def CLC(self): self.set_flag(self.FLAG_C, False); return 0
    def CLD(self): self.set_flag(self.FLAG_D, False); return 0
    def CLI(self): self.set_flag(self.FLAG_I, False); return 0
    def CLV(self): self.set_flag(self.FLAG_V, False); return 0

    def CMP(self):
        self.fetch()
        temp = self.a - self.fetched
        self.set_flag(self.FLAG_C, self.a >= self.fetched)
        self.set_flag(self.FLAG_Z, (temp & 0xFF) == 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        return 1

    def CPX(self):
        self.fetch()
        temp = self.x - self.fetched
        self.set_flag(self.FLAG_C, self.x >= self.fetched)
        self.set_flag(self.FLAG_Z, (temp & 0xFF) == 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def CPY(self):
        self.fetch()
        temp = self.y - self.fetched
        self.set_flag(self.FLAG_C, self.y >= self.fetched)
        self.set_flag(self.FLAG_Z, (temp & 0xFF) == 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def DEC(self):
        self.fetch()
        temp = (self.fetched - 1) & 0xFF
        self.write(self.addr_abs, temp)
        self.set_flag(self.FLAG_Z, temp == 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def DEX(self):
        self.x = (self.x - 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.x == 0)
        self.set_flag(self.FLAG_N, self.x & 0x80)
        return 0

    def DEY(self):
        self.y = (self.y - 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.y == 0)
        self.set_flag(self.FLAG_N, self.y & 0x80)
        return 0

    def EOR(self):
        self.fetch()
        self.a ^= self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 1

    def INC(self):
        self.fetch()
        temp = (self.fetched + 1) & 0xFF
        self.write(self.addr_abs, temp)
        self.set_flag(self.FLAG_Z, temp == 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def INX(self):
        self.x = (self.x + 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.x == 0)
        self.set_flag(self.FLAG_N, self.x & 0x80)
        return 0

    def INY(self):
        self.y = (self.y + 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.y == 0)
        self.set_flag(self.FLAG_N, self.y & 0x80)
        return 0

    def JMP(self):
        self.pc = self.addr_abs
        return 0

    def JSR(self):
        self.push_word(self.pc - 1)
        self.pc = self.addr_abs
        return 0

    def LDA(self):
        self.fetch()
        self.a = self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 1

    def LDX(self):
        self.fetch()
        self.x = self.fetched
        self.set_flag(self.FLAG_Z, self.x == 0)
        self.set_flag(self.FLAG_N, self.x & 0x80)
        return 1

    def LDY(self):
        self.fetch()
        self.y = self.fetched
        self.set_flag(self.FLAG_Z, self.y == 0)
        self.set_flag(self.FLAG_N, self.y & 0x80)
        return 1

    def LSR(self):
        if self.lookup[self.opcode][0] == self.ACC:
            self.set_flag(self.FLAG_C, self.a & 0x01)
            self.a >>= 1
            self.set_flag(self.FLAG_Z, self.a == 0)
            self.set_flag(self.FLAG_N, False)
        else:
            self.fetch()
            self.set_flag(self.FLAG_C, self.fetched & 0x01)
            temp = self.fetched >> 1
            self.write(self.addr_abs, temp)
            self.set_flag(self.FLAG_Z, temp == 0)
            self.set_flag(self.FLAG_N, False)
        return 0

    def NOP(self):
        return 0

    def ORA(self):
        self.fetch()
        self.a |= self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 1

    def PHA(self):
        self.push(self.a)
        return 0

    def PHP(self):
        self.push(self.status | self.FLAG_B | self.FLAG_U)
        return 0

    def PLA(self):
        self.a = self.pop()
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 0

    def PLP(self):
        self.status = self.pop()
        self.set_flag(self.FLAG_U, True)
        self.set_flag(self.FLAG_B, False)
        return 0

    def ROL(self):
        if self.lookup[self.opcode][0] == self.ACC:
            temp = (self.a << 1) | (1 if self.get_flag(self.FLAG_C) else 0)
            self.set_flag(self.FLAG_C, temp & 0x100)
            self.a = temp & 0xFF
            self.set_flag(self.FLAG_Z, self.a == 0)
            self.set_flag(self.FLAG_N, self.a & 0x80)
        else:
            self.fetch()
            temp = (self.fetched << 1) | (1 if self.get_flag(self.FLAG_C) else 0)
            self.set_flag(self.FLAG_C, temp & 0x100)
            temp &= 0xFF
            self.write(self.addr_abs, temp)
            self.set_flag(self.FLAG_Z, temp == 0)
            self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def ROR(self):
        if self.lookup[self.opcode][0] == self.ACC:
            temp = self.a | (0x100 if self.get_flag(self.FLAG_C) else 0)
            self.set_flag(self.FLAG_C, temp & 0x01)
            self.a = temp >> 1
            self.set_flag(self.FLAG_Z, self.a == 0)
            self.set_flag(self.FLAG_N, self.a & 0x80)
        else:
            self.fetch()
            temp = self.fetched | (0x100 if self.get_flag(self.FLAG_C) else 0)
            self.set_flag(self.FLAG_C, temp & 0x01)
            temp >>= 1
            self.write(self.addr_abs, temp)
            self.set_flag(self.FLAG_Z, temp == 0)
            self.set_flag(self.FLAG_N, temp & 0x80)
        return 0

    def RTI(self):
        self.status = self.pop()
        self.set_flag(self.FLAG_U, True)
        self.set_flag(self.FLAG_B, False)
        self.pc = self.pop_word()
        return 0

    def RTS(self):
        self.pc = self.pop_word() + 1
        return 0

    def SBC(self):
        self.fetch()
        value = self.fetched ^ 0xFF
        temp = self.a + value + (1 if self.get_flag(self.FLAG_C) else 0)
        self.set_flag(self.FLAG_C, temp > 255)
        self.set_flag(self.FLAG_Z, (temp & 0xFF) == 0)
        self.set_flag(self.FLAG_V, ((temp ^ self.a) & (temp ^ value) & 0x80) != 0)
        self.set_flag(self.FLAG_N, temp & 0x80)
        self.a = temp & 0xFF
        return 1

    def SEC(self): self.set_flag(self.FLAG_C, True); return 0
    def SED(self): self.set_flag(self.FLAG_D, True); return 0
    def SEI(self): self.set_flag(self.FLAG_I, True); return 0

    def STA(self):
        self.write(self.addr_abs, self.a)
        return 0

    def STX(self):
        self.write(self.addr_abs, self.x)
        return 0

    def STY(self):
        self.write(self.addr_abs, self.y)
        return 0

    def TAX(self):
        self.x = self.a
        self.set_flag(self.FLAG_Z, self.x == 0)
        self.set_flag(self.FLAG_N, self.x & 0x80)
        return 0

    def TAY(self):
        self.y = self.a
        self.set_flag(self.FLAG_Z, self.y == 0)
        self.set_flag(self.FLAG_N, self.y & 0x80)
        return 0

    def TSX(self):
        self.x = self.stkp
        self.set_flag(self.FLAG_Z, self.x == 0)
        self.set_flag(self.FLAG_N, self.x & 0x80)
        return 0

    def TXA(self):
        self.a = self.x
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 0

    def TXS(self):
        self.stkp = self.x
        return 0

    def TYA(self):
        self.a = self.y
        self.set_flag(self.FLAG_Z, self.a == 0)
        self.set_flag(self.FLAG_N, self.a & 0x80)
        return 0

    def clock(self):
        if self.cycles == 0:
            self.opcode = self.read(self.pc)
            self.pc = (self.pc + 1) & 0xFFFF
            
            addr_mode, operation, cycles = self.lookup[self.opcode]
            self.cycles = cycles
            
            additional_cycle1 = addr_mode()
            additional_cycle2 = operation()
            
            self.cycles += additional_cycle1 & additional_cycle2
        
        self.cycles -= 1


class PPU2C02:
    def __init__(self):
        self.bus = None
        
        # Registers
        self.ppuctrl = 0x00
        self.ppumask = 0x00
        self.ppustatus = 0x00
        self.oamaddr = 0x00
        
        # Internal registers
        self.v = 0x0000  # Current VRAM address
        self.t = 0x0000  # Temporary VRAM address
        self.x = 0x00    # Fine X scroll
        self.w = 0x00    # Write toggle
        self.f = 0x00    # Even/odd frame flag
        
        # PPU bus
        self.ppudata_buffer = 0x00
        
        # Memory
        self.vram = bytearray(2048)  # 2KB VRAM
        self.palette_ram = bytearray(32)
        self.oam = bytearray(256)
        
        # Rendering
        self.scanline = 0
        self.cycle = 0
        self.frame_complete = False
        
        # Background rendering
        self.bg_next_tile_id = 0x00
        self.bg_next_tile_attrib = 0x00
        self.bg_next_tile_lsb = 0x00
        self.bg_next_tile_msb = 0x00
        self.bg_shifter_pattern_lo = 0x0000
        self.bg_shifter_pattern_hi = 0x0000
        self.bg_shifter_attrib_lo = 0x0000
        self.bg_shifter_attrib_hi = 0x0000
        
        # NES color palette (NTSC)
        self.palette = [
            0x666666, 0x002A88, 0x1412A7, 0x3B00A4, 0x5C007E, 0x6E0040, 0x6C0600, 0x561D00,
            0x333500, 0x0B4800, 0x005200, 0x004F08, 0x00404D, 0x000000, 0x000000, 0x000000,
            0xADADAD, 0x155FD9, 0x4240FF, 0x7527FE, 0xA01ACC, 0xB71E7B, 0xB53120, 0x994E00,
            0x6B6D00, 0x388700, 0x0C9300, 0x008F32, 0x007C8D, 0x000000, 0x000000, 0x000000,
            0xFFFEFF, 0x64B0FF, 0x9290FF, 0xC676FF, 0xF36AFF, 0xFE6ECC, 0xFE8170, 0xEA9E22,
            0xBCBE00, 0x88D800, 0x5CE430, 0x45E082, 0x48CDDE, 0x4F4F4F, 0x000000, 0x000000,
            0xFFFEFF, 0xC0DFFF, 0xD3D2FF, 0xE8C8FF, 0xFBC2FF, 0xFEC4EA, 0xFECCC5, 0xF7D8A5,
            0xE4E594, 0xCFEF96, 0xBDF4AB, 0xB3F3CC, 0xB5EBF2, 0xB8B8B8, 0x000000, 0x000000,
        ]
        
        # Screen buffer
        self.screen = [[0] * NES_WIDTH for _ in range(NES_HEIGHT)]

    def connect_bus(self, bus):
        self.bus = bus

    def cpu_read(self, addr):
        data = 0x00
        
        if addr == 0x2002:  # PPUSTATUS
            data = (self.ppustatus & 0xE0) | (self.ppudata_buffer & 0x1F)
            self.ppustatus &= ~0x80  # Clear vblank
            self.w = 0  # Clear address latch
        elif addr == 0x2004:  # OAMDATA
            data = self.oam[self.oamaddr]
        elif addr == 0x2007:  # PPUDATA
            data = self.ppudata_buffer
            self.ppudata_buffer = self.bus.ppu_read(self.v)
            
            # Palette data doesn't use buffer
            if self.v >= 0x3F00:
                data = self.ppudata_buffer
            
            # Increment VRAM address
            self.v += 32 if (self.ppuctrl & 0x04) else 1
            self.v &= 0x3FFF
        
        return data

    def cpu_write(self, addr, data):
        if addr == 0x2000:  # PPUCTRL
            self.ppuctrl = data
            self.t = (self.t & 0xF3FF) | ((data & 0x03) << 10)
        elif addr == 0x2001:  # PPUMASK
            self.ppumask = data
        elif addr == 0x2003:  # OAMADDR
            self.oamaddr = data
        elif addr == 0x2004:  # OAMDATA
            self.oam[self.oamaddr] = data
            self.oamaddr = (self.oamaddr + 1) & 0xFF
        elif addr == 0x2005:  # PPUSCROLL
            if self.w == 0:
                self.t = (self.t & 0xFFE0) | (data >> 3)
                self.x = data & 0x07
                self.w = 1
            else:
                self.t = (self.t & 0x8FFF) | ((data & 0x07) << 12)
                self.t = (self.t & 0xFC1F) | ((data & 0xF8) << 2)
                self.w = 0
        elif addr == 0x2006:  # PPUADDR
            if self.w == 0:
                self.t = (self.t & 0x80FF) | ((data & 0x3F) << 8)
                self.w = 1
            else:
                self.t = (self.t & 0xFF00) | data
                self.v = self.t
                self.w = 0
        elif addr == 0x2007:  # PPUDATA
            self.bus.ppu_write(self.v, data)
            self.v += 32 if (self.ppuctrl & 0x04) else 1
            self.v &= 0x3FFF

    def increment_scroll_x(self):
        if self.ppumask & 0x18:  # Rendering enabled
            if (self.v & 0x001F) == 31:
                self.v &= ~0x001F
                self.v ^= 0x0400
            else:
                self.v += 1

    def increment_scroll_y(self):
        if self.ppumask & 0x18:  # Rendering enabled
            if (self.v & 0x7000) != 0x7000:
                self.v += 0x1000
            else:
                self.v &= ~0x7000
                y = (self.v & 0x03E0) >> 5
                if y == 29:
                    y = 0
                    self.v ^= 0x0800
                elif y == 31:
                    y = 0
                else:
                    y += 1
                self.v = (self.v & ~0x03E0) | (y << 5)

    def transfer_address_x(self):
        if self.ppumask & 0x18:
            self.v = (self.v & ~0x041F) | (self.t & 0x041F)

    def transfer_address_y(self):
        if self.ppumask & 0x18:
            self.v = (self.v & ~0x7BE0) | (self.t & 0x7BE0)

    def load_background_shifters(self):
        self.bg_shifter_pattern_lo = (self.bg_shifter_pattern_lo & 0xFF00) | self.bg_next_tile_lsb
        self.bg_shifter_pattern_hi = (self.bg_shifter_pattern_hi & 0xFF00) | self.bg_next_tile_msb
        
        self.bg_shifter_attrib_lo = (self.bg_shifter_attrib_lo & 0xFF00) | (0xFF if (self.bg_next_tile_attrib & 0b01) else 0)
        self.bg_shifter_attrib_hi = (self.bg_shifter_attrib_hi & 0xFF00) | (0xFF if (self.bg_next_tile_attrib & 0b10) else 0)

    def update_shifters(self):
        if self.ppumask & 0x08:  # Background rendering enabled
            self.bg_shifter_pattern_lo <<= 1
            self.bg_shifter_pattern_hi <<= 1
            self.bg_shifter_attrib_lo <<= 1
            self.bg_shifter_attrib_hi <<= 1

    def clock(self):
        # Visible scanlines (0-239)
        if 0 <= self.scanline <= 239:
            if self.scanline == 0 and self.cycle == 0:
                self.cycle = 1  # Skip cycle 0
            
            if 2 <= self.cycle <= 257 or 321 <= self.cycle <= 336:
                self.update_shifters()
                
                # Fetch background data every 8 cycles
                cycle_phase = (self.cycle - 1) % 8
                
                if cycle_phase == 0:  # Nametable byte
                    self.load_background_shifters()
                    nametable_addr = 0x2000 | (self.v & 0x0FFF)
                    self.bg_next_tile_id = self.bus.ppu_read(nametable_addr)
                
                elif cycle_phase == 2:  # Attribute byte
                    attr_addr = 0x23C0 | (self.v & 0x0C00) | ((self.v >> 4) & 0x38) | ((self.v >> 2) & 0x07)
                    attr_byte = self.bus.ppu_read(attr_addr)
                    
                    if self.v & 0x0040:
                        attr_byte >>= 4
                    if self.v & 0x0002:
                        attr_byte >>= 2
                    
                    self.bg_next_tile_attrib = attr_byte & 0x03
                
                elif cycle_phase == 4:  # Pattern table tile low
                    bg_pattern_addr = ((self.ppuctrl & 0x10) << 8) + (self.bg_next_tile_id << 4) + ((self.v >> 12) & 0x07)
                    self.bg_next_tile_lsb = self.bus.ppu_read(bg_pattern_addr)
                
                elif cycle_phase == 6:  # Pattern table tile high
                    bg_pattern_addr = ((self.ppuctrl & 0x10) << 8) + (self.bg_next_tile_id << 4) + ((self.v >> 12) & 0x07) + 8
                    self.bg_next_tile_msb = self.bus.ppu_read(bg_pattern_addr)
                
                elif cycle_phase == 7:  # Increment X
                    self.increment_scroll_x()
            
            if self.cycle == 256:
                self.increment_scroll_y()
            
            if self.cycle == 257:
                self.load_background_shifters()
                self.transfer_address_x()
            
            if self.cycle == 338 or self.cycle == 340:
                self.bg_next_tile_id = self.bus.ppu_read(0x2000 | (self.v & 0x0FFF))
            
            # Render pixel
            if 1 <= self.cycle <= 256:
                # Background pixel
                bg_pixel = 0x00
                bg_palette = 0x00
                
                if self.ppumask & 0x08:
                    bit_mux = 0x8000 >> self.x
                    
                    p0_pixel = (self.bg_shifter_pattern_lo & bit_mux) > 0
                    p1_pixel = (self.bg_shifter_pattern_hi & bit_mux) > 0
                    bg_pixel = (p1_pixel << 1) | p0_pixel
                    
                    bg_pal0 = (self.bg_shifter_attrib_lo & bit_mux) > 0
                    bg_pal1 = (self.bg_shifter_attrib_hi & bit_mux) > 0
                    bg_palette = (bg_pal1 << 1) | bg_pal0
                
                # Get color from palette memory
                palette_addr = 0x3F00 + (bg_palette << 2) + bg_pixel
                color = self.bus.ppu_read(palette_addr) & 0x3F
                
                # Draw pixel
                self.screen[self.scanline][self.cycle - 1] = self.palette[color]
        
        # Post-render scanline
        elif self.scanline == 240:
            pass
        
        # Vertical blanking scanlines
        elif 241 <= self.scanline <= 260:
            if self.scanline == 241 and self.cycle == 1:
                self.ppustatus |= 0x80
                if self.ppuctrl & 0x80:
                    self.bus.cpu.non_maskable_interrupt()
        
        # Pre-render scanline
        elif self.scanline == 261:
            if self.cycle == 1:
                self.ppustatus &= ~0xE0
            
            if 280 <= self.cycle <= 304:
                self.transfer_address_y()
            
            if self.cycle == 339 and self.f:
                self.cycle = 340
        
        # Sprite evaluation (simplified - no actual sprite rendering)
        # This is a placeholder for sprite zero hit detection
        if self.ppumask & 0x18 and self.scanline < 240:
            if self.oam[0] <= self.scanline < self.oam[0] + 8:
                if self.oam[3] <= self.cycle - 1 < self.oam[3] + 8:
                    if self.ppumask & 0x18 == 0x18:  # Both sprites and background enabled
                        if not (self.ppumask & 0x06 == 0 and self.cycle < 9):
                            self.ppustatus |= 0x40  # Sprite zero hit
        
        # Advance counters
        self.cycle += 1
        if self.cycle > 340:
            self.cycle = 0
            self.scanline += 1
            
            if self.scanline > 261:
                self.scanline = 0
                self.frame_complete = True
                self.f ^= 1


class MonikaEmulatorApp:
    def __init__(self, root):
        self.root = root
        root.title("Monika's NES Playhouse 💕")
        root.geometry("1000x800")
        root.resizable(False, False)
        root.configure(bg=DARK_BG)

        # Initialize emulator components
        self.bus = Bus()
        self.cpu = CPU6502()
        self.ppu = PPU2C02()
        self.bus.connect_cpu(self.cpu)
        self.bus.connect_ppu(self.ppu)

        self.running = False
        self.rom_loaded = False
        self.frame_skip = 0
        self.target_fps = 60
        
        # PhotoImage for screen - reuse instead of recreating
        self.screen_image = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        
        # Create UI
        self._create_ui()
        
        # Log welcome message
        self.log_message("Welcome to Monika's NES Playhouse! 💕 Load a ROM to begin~")

    def _create_ui(self):
        # Top frame - controls
        top_frame = tk.Frame(self.root, bg=DARK_BG)
        top_frame.pack(pady=10)

        ttk.Button(top_frame, text="Load ROM", command=self.load_rom).pack(side=tk.LEFT, padx=5)
        
        self.run_button = ttk.Button(top_frame, text="Run", command=self.toggle_run, state="disabled")
        self.run_button.pack(side=tk.LEFT, padx=5)
        
        self.reset_button = ttk.Button(top_frame, text="Reset", command=self.reset, state="disabled")
        self.reset_button.pack(side=tk.LEFT, padx=5)
        
        self.step_button = ttk.Button(top_frame, text="Step", command=self.step, state="disabled")
        self.step_button.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(top_frame, text="No ROM loaded", background=DARK_BG, foreground=DARK_FG)
        self.status_label.pack(side=tk.LEFT, padx=20)

        # Middle frame - screen and console
        middle_frame = tk.Frame(self.root, bg=DARK_BG)
        middle_frame.pack(expand=True, fill=tk.BOTH, padx=10)

        # NES screen
        self.screen_canvas = tk.Canvas(middle_frame, width=NES_WIDTH*2, height=NES_HEIGHT*2, 
                                      bg=DARK_CANVAS_BG, highlightthickness=0)
        self.screen_canvas.pack(side=tk.LEFT, padx=(0, 10))
        
        # Create screen image holder
        self.screen_item = self.screen_canvas.create_image(0, 0, anchor=tk.NW, image=self.screen_image)
        self.screen_canvas.scale(self.screen_item, 0, 0, 2, 2)

        # Console output
        console_frame = tk.Frame(middle_frame, bg=DARK_BG)
        console_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        self.console = tk.Text(console_frame, bg=DARK_TEXT_BG, fg=DARK_TEXT_FG, wrap='word',
                              height=20, width=40, state='disabled')
        self.console.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(console_frame, command=self.console.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.console['yscrollcommand'] = scrollbar.set

        # Bottom frame - info
        bottom_frame = tk.Frame(self.root, bg=DARK_BG)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)

        self.cpu_info = ttk.Label(bottom_frame, text="CPU: [Not running]", 
                                 background=DARK_BG, foreground=DARK_FG, font=('Consolas', 10))
        self.cpu_info.pack(anchor=tk.W)

        self.ppu_info = ttk.Label(bottom_frame, text="PPU: [Not running]", 
                                 background=DARK_BG, foreground=DARK_FG, font=('Consolas', 10))
        self.ppu_info.pack(anchor=tk.W)

        # Speed control
        speed_frame = tk.Frame(bottom_frame, bg=DARK_BG)
        speed_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(speed_frame, text="Speed:", background=DARK_BG, foreground=DARK_FG).pack(side=tk.LEFT)
        
        self.speed_scale = tk.Scale(speed_frame, from_=1, to=200, orient=tk.HORIZONTAL, 
                                   bg=DARK_BG, fg=DARK_FG, length=200,
                                   troughcolor=DARK_BORDER, highlightthickness=0)
        self.speed_scale.set(100)
        self.speed_scale.pack(side=tk.LEFT, padx=10)

    def log_message(self, message):
        self.console.configure(state='normal')
        self.console.insert(tk.END, f"{message}\n")
        self.console.see(tk.END)
        self.console.configure(state='disabled')

    def load_rom(self):
        filename = filedialog.askopenfilename(
            title="Select NES ROM",
            filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'rb') as f:
                    rom_data = f.read()
                
                rom = NESRom(rom_data)
                cart = Cartridge(rom)
                self.bus.insert_cartridge(cart)
                
                self.rom_loaded = True
                self.reset()
                
                # Enable controls
                self.run_button.configure(state='normal')
                self.reset_button.configure(state='normal')
                self.step_button.configure(state='normal')
                
                # Update status
                rom_name = filename.split('/')[-1]
                self.status_label.configure(text=f"Loaded: {rom_name}")
                self.log_message(f"ROM loaded successfully: {rom_name}")
                self.log_message(f"Mapper: {rom.mapper}, PRG: {rom.prg_rom_size//1024}KB, CHR: {rom.chr_rom_size//1024}KB")
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load ROM: {e}")
                self.log_message(f"Error loading ROM: {e}")

    def reset(self):
        self.cpu.reset()
        self.ppu.__init__()
        self.ppu.connect_bus(self.bus)
        self.update_display()
        self.log_message("System reset")

    def toggle_run(self):
        self.running = not self.running
        if self.running:
            self.run_button.configure(text="Pause")
            self.step_button.configure(state='disabled')
            self.run_emulation()
        else:
            self.run_button.configure(text="Run")
            self.step_button.configure(state='normal')

    def step(self):
        if not self.rom_loaded or self.running:
            return
        
        # Execute one CPU instruction
        while self.cpu.cycles > 0:
            self.bus.clock()
        
        # Execute next instruction fetch
        self.bus.clock()
        
        self.update_display()

    def run_emulation(self):
        if not self.running:
            return
        
        # Run one frame
        start_time = time.time()
        
        while not self.ppu.frame_complete:
            self.bus.clock()
        
        self.ppu.frame_complete = False
        self.frame_skip = (self.frame_skip + 1) % 2
        
        # Update display every other frame for performance
        if self.frame_skip == 0:
            self.update_display()
        
        # Calculate timing
        elapsed = time.time() - start_time
        speed_factor = self.speed_scale.get() / 100.0
        target_time = (1.0 / self.target_fps) / speed_factor
        delay = max(1, int((target_time - elapsed) * 1000))
        
        # Schedule next frame
        self.root.after(delay, self.run_emulation)

    def update_display(self):
        # Update screen
        self.render_screen()
        
        # Update CPU info
        flags = ""
        flags += "N" if self.cpu.get_flag(self.cpu.FLAG_N) else "-"
        flags += "V" if self.cpu.get_flag(self.cpu.FLAG_V) else "-"
        flags += "-"  # Unused
        flags += "B" if self.cpu.get_flag(self.cpu.FLAG_B) else "-"
        flags += "D" if self.cpu.get_flag(self.cpu.FLAG_D) else "-"
        flags += "I" if self.cpu.get_flag(self.cpu.FLAG_I) else "-"
        flags += "Z" if self.cpu.get_flag(self.cpu.FLAG_Z) else "-"
        flags += "C" if self.cpu.get_flag(self.cpu.FLAG_C) else "-"
        
        self.cpu_info.configure(
            text=f"CPU: A={self.cpu.a:02X} X={self.cpu.x:02X} Y={self.cpu.y:02X} "
                 f"SP={self.cpu.stkp:02X} PC={self.cpu.pc:04X} P={flags}"
        )
        
        # Update PPU info
        self.ppu_info.configure(
            text=f"PPU: Scanline={self.ppu.scanline:3d} Cycle={self.ppu.cycle:3d} "
                 f"V={self.ppu.v:04X} T={self.ppu.t:04X}"
        )

    def render_screen(self):
        # Convert screen data to PhotoImage format
        # This is more efficient than creating a new PhotoImage each frame
        for y in range(NES_HEIGHT):
            row_data = []
            for x in range(NES_WIDTH):
                color = self.ppu.screen[y][x]
                # Convert to hex color string
                row_data.append(f"#{color:06X}")
            # Put entire row at once
            self.screen_image.put("{" + " ".join(row_data) + "}", (0, y))


if __name__ == "__main__":
    root = tk.Tk()
    
    # Configure ttk styles
    style = ttk.Style()
    style.theme_use('clam')
    
    # Configure styles for dark theme
    style.configure("TButton", 
                   background=DARK_BUTTON_BG,
                   foreground=DARK_BUTTON_FG,
                   borderwidth=0,
                   focuscolor=DARK_ACCENT,
                   lightcolor=DARK_BUTTON_BG,
                   darkcolor=DARK_BUTTON_BG)
    
    style.map("TButton",
             background=[('active', DARK_BUTTON_ACTIVE_BG), ('pressed', DARK_ACCENT)],
             foreground=[('active', DARK_BUTTON_ACTIVE_FG)])
    
    style.configure("TLabel",
                   background=DARK_BG,
                   foreground=DARK_FG)
    
    style.configure("Vertical.TScrollbar",
                   background=DARK_SCROLLBAR_BG,
                   troughcolor=DARK_SCROLLBAR_TROUGH,
                   bordercolor=DARK_BORDER,
                   arrowcolor=DARK_FG,
                   lightcolor=DARK_SCROLLBAR_BG,
                   darkcolor=DARK_SCROLLBAR_BG)
    
    app = MonikaEmulatorApp(root)
    root.mainloop()
