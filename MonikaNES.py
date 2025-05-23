import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Scale
import struct
import random
import time

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
        self.prg_rom_size = self.header[4] * 16384  # PRG ROM size in bytes (16KB units)
        self.chr_rom_size = self.header[5] * 8192    # CHR ROM size in bytes (8KB units)

        # Mapper (iNES 1.0 format)
        self.mapper = ((self.header[7] >> 4) << 4) | (self.header[6] >> 4)
        self.mirror_mode = (self.header[6] & 0x01) # 0 for Horizontal, 1 for Vertical

        self.prg_rom_start = 16
        if (self.header[6] & 0x04): # Trainer present
            self.prg_rom_start += 512 # Skip trainer

        self.prg_rom = self.data[self.prg_rom_start : self.prg_rom_start + self.prg_rom_size]
        self.chr_rom = self.data[self.prg_rom_start + self.prg_rom_size : self.prg_rom_start + self.prg_rom_size + self.chr_rom_size]

        if not self.chr_rom: # If no CHR ROM, it's CHR RAM
            self.chr_ram = bytearray(8192) # 8KB CHR RAM

        print(f"Loaded ROM: PRG ROM {self.prg_rom_size/1024}KB, CHR ROM {self.chr_rom_size/1024}KB, Mapper {self.mapper}")

    def read_prg(self, addr):
        # Simplistic mapping for NROM (Mapper 0)
        # 0x8000 - 0xBFFF: PRG ROM (16KB or first 16KB of 32KB)
        # 0xC000 - 0xFFFF: PRG ROM (16KB or last 16KB of 32KB if 32KB ROM)
        if self.prg_rom_size == 16384: # 16KB ROM
            return self.prg_rom[addr % 16384]
        elif self.prg_rom_size == 32768: # 32KB ROM
            return self.prg_rom[addr % 32768]
        return 0 # Should not happen for NROM

    def write_prg(self, addr, data):
        pass # NROM PRG ROM is read-only

    def read_chr(self, addr):
        if self.chr_rom_size > 0:
            return self.chr_rom[addr]
        else: # CHR RAM
            return self.chr_ram[addr]

    def write_chr(self, addr, data):
        if self.chr_rom_size == 0: # CHR RAM
            self.chr_ram[addr] = data
        # CHR ROM is read-only, so no write for CHR_ROM_SIZE > 0


class Cartridge:
    def __init__(self, rom):
        self.rom = rom

    def cpu_read(self, addr):
        if 0x6000 <= addr <= 0x7FFF: # SRAM (Work RAM) - Not implemented here, just return 0
            return 0
        elif 0x8000 <= addr <= 0xFFFF: # PRG ROM
            return self.rom.read_prg(addr - 0x8000) # Translate to 0-indexed for PRG ROM
        return 0

    def cpu_write(self, addr, data):
        if 0x6000 <= addr <= 0x7FFF: # SRAM (Work RAM)
            # Not implemented for now
            pass
        elif 0x8000 <= addr <= 0xFFFF: # PRG ROM (mostly read-only)
            self.rom.write_prg(addr - 0x8000, data)

    def ppu_read(self, addr):
        if 0x0000 <= addr <= 0x1FFF: # CHR ROM/RAM
            return self.rom.read_chr(addr)
        return 0

    def ppu_write(self, addr, data):
        if 0x0000 <= addr <= 0x1FFF: # CHR ROM/RAM
            self.rom.write_chr(addr, data)


class Bus:
    def __init__(self):
        self.cpu = None # CPU instance
        self.ppu = None # PPU instance
        self.cart = None # Cartridge instance

        self.cpu_ram = bytearray(2048) # 2KB of CPU RAM

        # System clock
        self.system_clock_counter = 0

    def connect_cpu(self, cpu):
        self.cpu = cpu
        self.cpu.connect_bus(self)

    def connect_ppu(self, ppu):
        self.ppu = ppu
        self.ppu.connect_bus(self)

    def insert_cartridge(self, cartridge):
        self.cart = cartridge

    def cpu_write(self, addr, data):
        if self.cart: # Check if cart exists first for non-None return value
            if self.cart.cpu_write(addr, data):
                return True # Cartridge handled write
        
        if 0x0000 <= addr <= 0x1FFF: # 2KB internal RAM, mirrored 4 times
            self.cpu_ram[addr & 0x07FF] = data
        elif 0x2000 <= addr <= 0x3FFF: # PPU Registers (mirrored)
            self.ppu.cpu_write(addr & 0x2007, data)
        # Other addresses (APU, Joypad etc.) not implemented
        return True # Indicate write was attempted

    def cpu_read(self, addr):
        data = 0x00
        if self.cart:
            cart_data = self.cart.cpu_read(addr)
            if cart_data is not None: # Cartridge read might return None if not handled
                data = cart_data
        
        if 0x0000 <= addr <= 0x1FFF: # 2KB internal RAM, mirrored 4 times
            data = self.cpu_ram[addr & 0x07FF]
        elif 0x2000 <= addr <= 0x3FFF: # PPU Registers (mirrored)
            data = self.ppu.cpu_read(addr & 0x2007)
        # Other addresses (APU, Joypad etc.) not implemented
        return data

    def ppu_write(self, addr, data):
        if self.cart: # Check if cart exists first for non-None return value
            if self.cart.ppu_write(addr, data):
                return True # Cartridge handled write
        
        if 0x2000 <= addr <= 0x3EFF: # Nametables (VRAM)
            # Simplistic Nametable write (needs to respect mirroring)
            # This is a very rough implementation. Real Nametable is 2KB, mirrored into 4 areas.
            # Mirroring logic would be here. For now, just write to 'vram'
            self.ppu.vram[addr & 0x0FFF] = data # Basic mapping to a 4KB VRAM. Real VRAM is 2KB, mirrored.
        elif 0x3F00 <= addr <= 0x3FFF: # Palettes (32 bytes mirrored every 0x20 bytes)
            # Actual PPU palette RAM is 32 bytes (0x3F00-0x3F1F)
            # Addresses 0x3F04, 0x3F08, 0x3F0C, 0x3F10, 0x3F14, 0x3F18, 0x3F1C are mirrors of 0x3F00
            # A write to a mirror of 0x3F00 (e.g. 0x3F04) also writes to 0x3F00.
            actual_addr = addr & 0x1F # Mask to 0x00-0x1F
            if actual_addr == 0x04 or actual_addr == 0x08 or \
               actual_addr == 0x0C or actual_addr == 0x10 or \
               actual_addr == 0x14 or actual_addr == 0x18 or actual_addr == 0x1C:
                actual_addr = 0x00 # Writes to specific indices also write to universal background color

            self.ppu.palette_ram[actual_addr] = data & 0x3F # Only 6 bits used for color index
        return True

    def ppu_read(self, addr):
        data = 0x00
        if self.cart:
            cart_data = self.cart.ppu_read(addr)
            if cart_data is not None:
                data = cart_data
        
        if 0x2000 <= addr <= 0x3EFF: # Nametables (VRAM)
            data = self.ppu.vram[addr & 0x0FFF] # Basic mapping
        elif 0x3F00 <= addr <= 0x3FFF: # Palettes
            actual_addr = addr & 0x1F # Mask to 0x00-0x1F
            if actual_addr == 0x04 or actual_addr == 0x08 or \
               actual_addr == 0x0C or actual_addr == 0x10 or \
               actual_addr == 0x14 or actual_addr == 0x18 or actual_addr == 0x1C:
                actual_addr = 0x00 # Read from specific indices also reads from universal background color
            data = self.ppu.palette_ram[actual_addr] & 0x3F # Mask to 6 bits
        return data

    def clock(self):
        # PPU runs 3 times faster than CPU
        self.ppu.clock()
        self.system_clock_counter += 1

        if self.system_clock_counter % 3 == 0:
            if not self.cpu.dma_transfer:
                self.cpu.clock()
            else: # DMA transfer takes CPU cycles
                # OAM DMA: 512 cycles (256 bytes * 2 cycles per byte)
                # First cycle is wasted for alignment, second for read/write
                if self.cpu.dma_dummy: # Dummy read/write cycle
                    if self.system_clock_counter % 2 == 1: # On odd cycles
                        self.cpu.dma_dummy = False
                else: # Real read/write cycles
                    if self.system_clock_counter % 2 == 0: # On even cycles (read)
                        self.ppu.oam_data = self.cpu_read(self.cpu.dma_page * 256 + self.cpu.dma_addr)
                    else: # On odd cycles (write to OAM)
                        self.ppu.oam[self.cpu.dma_addr] = self.ppu.oam_data
                        self.cpu.dma_addr += 1
                        if self.cpu.dma_addr == 0x100: # DMA complete after 256 bytes
                            self.cpu.dma_transfer = False
                            self.cpu.dma_dummy = True
                            self.cpu.dma_addr = 0x00


# --- Enhanced CPU 6502 (Still simplified, but more meow-gical!) ---
class CPU6502:
    # 6502 Flags
    FLAG_C = (1 << 0) # Carry Bit
    FLAG_Z = (1 << 1) # Zero
    FLAG_I = (1 << 2) # Interrupt Disable
    FLAG_D = (1 << 3) # Decimal Mode (unused on NES)
    FLAG_B = (1 << 4) # Break Command
    FLAG_U = (1 << 5) # Unused
    FLAG_V = (1 << 6) # Overflow
    FLAG_N = (1 << 7) # Negative

    def __init__(self):
        self.bus = None

        # Registers
        self.a = 0x00     # Accumulator
        self.x = 0x00     # X Register
        self.y = 0x00     # Y Register
        self.stkp = 0xFD  # Stack Pointer (points to next free location)
        self.pc = 0x0000  # Program Counter
        self.status = 0x00 # Status Register (Processor Status)

        # Internal variables
        self.fetched = 0x00 # Fetched data
        self.addr_abs = 0x0000 # Absolute address
        self.addr_rel = 0x0000 # Relative address (for branches)
        self.opcode = 0x00 # Current opcode
        self.cycles = 0 # Remaining cycles for current instruction

        # *New*: DMA handling
        self.dma_page = 0x00
        self.dma_addr = 0x00
        self.dma_data = 0x00
        self.dma_transfer = False
        self.dma_dummy = True # True on first DMA cycle

        # *New*: Illegal Opcode Handling
        self.illegal_opcodes = {} # Dictionary to store encountered illegal opcodes

        # Lookup table for opcodes
        # Each entry: (opcode_name, address_mode_func, operation_func, cycles)
        # This is a very minimal subset for NROM
        self.lookup = [
            # --- NOP ---
            (0xEA, self.IMP, self.NOP, 2), # NOP

            # --- LDA ---
            (0xA9, self.IMM, self.LDA, 2), # LDA Immediate
            (0xA5, self.ZP0, self.LDA, 3), # LDA Zero Page
            (0xB5, self.ZPX, self.LDA, 4), # LDA Zero Page X
            (0xAD, self.ABS, self.LDA, 4), # LDA Absolute
            (0xBD, self.ABX, self.LDA, 4), # LDA Absolute X (+1 if page cross)
            (0xB9, self.ABY, self.LDA, 4), # LDA Absolute Y (+1 if page cross)
            (0xA1, self.IZX, self.LDA, 6), # LDA Indirect X
            (0xB1, self.IZY, self.LDA, 5), # LDA Indirect Y (+1 if page cross)

            # --- STA ---
            (0x85, self.ZP0, self.STA, 3), # STA Zero Page
            (0x95, self.ZPX, self.STA, 4), # STA Zero Page X
            (0x8D, self.ABS, self.STA, 4), # STA Absolute
            (0x9D, self.ABX, self.STA, 5), # STA Absolute X
            (0x99, self.ABY, self.STA, 5), # STA Absolute Y
            (0x81, self.IZX, self.STA, 6), # STA Indirect X
            (0x91, self.IZY, self.STA, 6), # STA Indirect Y

            # --- JMP ---
            (0x4C, self.ABS, self.JMP, 3), # JMP Absolute
            (0x6C, self.IND, self.JMP, 5), # JMP Indirect

            # --- JSR ---
            (0x20, self.ABS, self.JSR, 6), # JSR Absolute

            # --- RTS ---
            (0x60, self.IMP, self.RTS, 6), # RTS

            # --- Transfers ---
            (0xAA, self.IMP, self.TAX, 2), # TAX
            (0x8A, self.IMP, self.TXA, 2), # TXA
            (0xA8, self.IMP, self.TAY, 2), # TAY
            (0x98, self.IMP, self.TYA, 2), # TYA
            (0xBA, self.IMP, self.TSX, 2), # TSX
            (0x9A, self.IMP, self.TXS, 2), # TXS

            # --- Increments/Decrements ---
            (0xE8, self.IMP, self.INX, 2), # INX
            (0xCA, self.IMP, self.DEX, 2), # DEX
            (0xC8, self.IMP, self.INY, 2), # INY
            (0x88, self.IMP, self.DEY, 2), # DEY

            # --- Comparisons (CMP, CPX, CPY) ---
            (0xC9, self.IMM, self.CMP, 2), (0xC5, self.ZP0, self.CMP, 3), (0xD5, self.ZPX, self.CMP, 4),
            (0xCD, self.ABS, self.CMP, 4), (0xDD, self.ABX, self.CMP, 4), (0xD9, self.ABY, self.CMP, 4),
            (0xC1, self.IZX, self.CMP, 6), (0xD1, self.IZY, self.CMP, 5),

            (0xE0, self.IMM, self.CPX, 2), (0xE4, self.ZP0, self.CPX, 3), (0xEC, self.ABS, self.CPX, 4),

            (0xC0, self.IMM, self.CPY, 2), (0xC4, self.ZP0, self.CPY, 3), (0xCC, self.ABS, self.CPY, 4),

            # --- Logical Operations ---
            (0x29, self.IMM, self.AND, 2), (0x25, self.ZP0, self.AND, 3), (0x35, self.ZPX, self.AND, 4),
            (0x2D, self.ABS, self.AND, 4), (0x3D, self.ABX, self.AND, 4), (0x39, self.ABY, self.AND, 4),
            (0x21, self.IZX, self.AND, 6), (0x31, self.IZY, self.AND, 5),

            (0x09, self.IMM, self.ORA, 2), (0x05, self.ZP0, self.ORA, 3), (0x15, self.ZPX, self.ORA, 4),
            (0x0D, self.ABS, self.ORA, 4), (0x1D, self.ABX, self.ORA, 4), (0x19, self.ABY, self.ORA, 4),
            (0x01, self.IZX, self.ORA, 6), (0x11, self.IZY, self.ORA, 5),

            (0x49, self.IMM, self.EOR, 2), (0x45, self.ZP0, self.EOR, 3), (0x55, self.ZPX, self.EOR, 4),
            (0x4D, self.ABS, self.EOR, 4), (0x5D, self.ABX, self.EOR, 4), (0x59, self.ABY, self.EOR, 4),
            (0x41, self.IZX, self.EOR, 6), (0x51, self.IZY, self.EOR, 5),

            # --- Arithmetic Operations ---
            (0x69, self.IMM, self.ADC, 2), (0x65, self.ZP0, self.ADC, 3), (0x75, self.ZPX, self.ADC, 4),
            (0x6D, self.ABS, self.ADC, 4), (0x7D, self.ABX, self.ADC, 4), (0x79, self.ABY, self.ADC, 4),
            (0x61, self.IZX, self.ADC, 6), (0x71, self.IZY, self.ADC, 5),

            (0xE9, self.IMM, self.SBC, 2), (0xE5, self.ZP0, self.SBC, 3), (0xF5, self.ZPX, self.SBC, 4),
            (0xED, self.ABS, self.SBC, 4), (0xFD, self.ABX, self.SBC, 4), (0xF9, self.ABY, self.SBC, 4),
            (0xE1, self.IZX, self.SBC, 6), (0xF1, self.IZY, self.SBC, 5),

            # --- Shift/Rotate Operations ---
            (0x0A, self.ACC, self.ASL, 2), (0x06, self.ZP0, self.ASL, 5), (0x16, self.ZPX, self.ASL, 6),
            (0x0E, self.ABS, self.ASL, 6), (0x1E, self.ABX, self.ASL, 7),

            (0x4A, self.ACC, self.LSR, 2), (0x46, self.ZP0, self.LSR, 5), (0x56, self.ZPX, self.LSR, 6),
            (0x4E, self.ABS, self.LSR, 6), (0x5E, self.ABX, self.LSR, 7),

            (0x2A, self.ACC, self.ROL, 2), (0x26, self.ZP0, self.ROL, 5), (0x36, self.ZPX, self.ROL, 6),
            (0x2E, self.ABS, self.ROL, 6), (0x3E, self.ABX, self.ROL, 7),

            (0x6A, self.ACC, self.ROR, 2), (0x66, self.ZP0, self.ROR, 5), (0x76, self.ZPX, self.ROR, 6),
            (0x6E, self.ABS, self.ROR, 6), (0x7E, self.ABX, self.ROR, 7),

            # --- Bit Test ---
            (0x24, self.ZP0, self.BIT, 3), (0x2C, self.ABS, self.BIT, 4),

            # --- Branching (Conditional) ---
            (0x10, self.REL, self.BPL, 2), (0x30, self.REL, self.BMI, 2),
            (0x50, self.REL, self.BVC, 2), (0x70, self.REL, self.BVS, 2),
            (0x90, self.REL, self.BCC, 2), (0xB0, self.REL, self.BCS, 2),
            (0xD0, self.REL, self.BNE, 2), (0xF0, self.REL, self.BEQ, 2),

            # --- Interrupts ---
            (0x00, self.IMP, self.BRK, 7), # BRK
            (0x40, self.IMP, self.RTI, 6), # RTI

            # --- Stack Operations ---
            (0x48, self.IMP, self.PHA, 3), # PHA
            (0x68, self.IMP, self.PLA, 4), # PLA
            (0x08, self.IMP, self.PHP, 3), # PHP
            (0x28, self.IMP, self.PLP, 4), # PLP

            # --- Status Flag Changes ---
            (0x18, self.IMP, self.CLC, 2), # CLC
            (0x38, self.IMP, self.SEC, 2), # SEC
            (0x58, self.IMP, self.CLI, 2), # CLI
            (0x78, self.IMP, self.SEI, 2), # SEI
            (0xB8, self.IMP, self.CLV, 2), # CLV
            (0xD8, self.IMP, self.CLD, 2), # CLD (decimal mode unused on NES)
            (0xF8, self.IMP, self.SED, 2), # SED (decimal mode unused on NES)
        ]
        # Convert lookup list to a dictionary for faster access
        self.lookup_dict = {entry[0]: entry[1:] for entry in self.lookup}

    def connect_bus(self, n):
        self.bus = n

    def read(self, addr):
        return self.bus.cpu_read(addr)

    def write(self, addr, data):
        self.bus.cpu_write(addr, data)

    def get_flag(self, flag):
        return 1 if (self.status & flag) > 0 else 0

    def set_flag(self, flag, value):
        if value:
            self.status |= flag
        else:
            self.status &= ~flag

    def reset(self):
        # Read reset vector
        self.addr_abs = 0xFFFC
        lo = self.read(self.addr_abs)
        hi = self.read(self.addr_abs + 1)
        self.pc = (hi << 8) | lo

        # Reset registers
        self.a = 0x00
        self.x = 0x00
        self.y = 0x00
        self.stkp = 0xFD
        self.status = 0x00 | self.FLAG_U | self.FLAG_I # Set unused and interrupt disable flags

        self.addr_rel = 0x0000
        self.addr_abs = 0x0000
        self.fetched = 0x00
        self.cycles = 8 # Reset takes 8 cycles

        # Clear illegal opcode count on reset
        self.illegal_opcodes.clear()
        print("CPU Reset!")

    def interrupt_request(self): # IRQ
        if self.get_flag(self.FLAG_I) == 0: # If interrupts are enabled
            self.write(0x0100 + self.stkp, (self.pc >> 8) & 0x00FF)
            self.stkp -= 1
            self.write(0x0100 + self.stkp, self.pc & 0x00FF)
            self.stkp -= 1

            self.set_flag(self.FLAG_B, False)
            self.set_flag(self.FLAG_U, True)
            self.set_flag(self.FLAG_I, True)
            self.write(0x0100 + self.stkp, self.status)
            self.stkp -= 1

            self.addr_abs = 0xFFFE
            lo = self.read(self.addr_abs)
            hi = self.read(self.addr_abs + 1)
            self.pc = (hi << 8) | lo

            self.cycles = 7

    def non_maskable_interrupt(self): # NMI
        self.write(0x0100 + self.stkp, (self.pc >> 8) & 0x00FF)
        self.stkp -= 1
        self.write(0x0100 + self.stkp, self.pc & 0x00FF)
        self.stkp -= 1

        self.set_flag(self.FLAG_B, False)
        self.set_flag(self.FLAG_U, True)
        self.set_flag(self.FLAG_I, True)
        self.write(0x0100 + self.stkp, self.status)
        self.stkp -= 1

        self.addr_abs = 0xFFFA
        lo = self.read(self.addr_abs)
        hi = self.read(self.addr_abs + 1)
        self.pc = (hi << 8) | lo

        self.cycles = 8

    # --- Addressing Modes ---
    def IMP(self): # Implied
        self.fetched = self.a
        return 0

    def IMM(self): # Immediate
        self.addr_abs = self.pc
        self.pc += 1
        return 0

    def ZP0(self): # Zero Page
        self.addr_abs = self.read(self.pc)
        self.pc += 1
        self.addr_abs &= 0x00FF
        return 0

    def ZPX(self): # Zero Page X
        self.addr_abs = (self.read(self.pc) + self.x) & 0x00FF
        self.pc += 1
        return 0

    def ZPY(self): # Zero Page Y
        self.addr_abs = (self.read(self.pc) + self.y) & 0x00FF
        self.pc += 1
        return 0

    def ABS(self): # Absolute
        lo = self.read(self.pc)
        self.pc += 1
        hi = self.read(self.pc)
        self.pc += 1
        self.addr_abs = (hi << 8) | lo
        return 0

    def ABX(self): # Absolute X
        lo = self.read(self.pc)
        self.pc += 1
        hi = self.read(self.pc)
        self.pc += 1
        self.addr_abs = (hi << 8) | lo
        self.addr_abs += self.x
        if (self.addr_abs & 0xFF00) != (hi << 8): # Page cross check
            return 1
        return 0

    def ABY(self): # Absolute Y
        lo = self.read(self.pc)
        self.pc += 1
        hi = self.read(self.pc)
        self.pc += 1
        self.addr_abs = (hi << 8) | lo
        self.addr_abs += self.y
        if (self.addr_abs & 0xFF00) != (hi << 8): # Page cross check
            return 1
        return 0

    def IND(self): # Indirect (for JMP only)
        ptr_lo = self.read(self.pc)
        self.pc += 1
        ptr_hi = self.read(self.pc)
        self.pc += 1
        ptr = (ptr_hi << 8) | ptr_lo

        # 6502 bug: if address is 0xXXFF, it fetches high byte from 0xXX00
        if ptr_lo == 0x00FF:
            self.addr_abs = (self.read(ptr & 0xFF00) << 8) | self.read(ptr)
        else:
            self.addr_abs = (self.read(ptr + 1) << 8) | self.read(ptr)
        return 0

    def IZX(self): # Indirect X
        t = self.read(self.pc)
        self.pc += 1
        lo = self.read((t + self.x) & 0x00FF)
        hi = self.read((t + self.x + 1) & 0x00FF)
        self.addr_abs = (hi << 8) | lo
        return 0

    def IZY(self): # Indirect Y
        t = self.read(self.pc)
        self.pc += 1
        lo = self.read(t & 0x00FF)
        hi = self.read((t + 1) & 0x00FF)
        self.addr_abs = (hi << 8) | lo
        self.addr_abs += self.y
        if (self.addr_abs & 0xFF00) != (hi << 8): # Page cross check
            return 1
        return 0

    def ACC(self): # Accumulator
        # For operations like ASL, LSR, ROL, ROR on Accumulator
        return 0

    def REL(self): # Relative (for branches)
        self.addr_rel = self.read(self.pc)
        self.pc += 1
        if (self.addr_rel & 0x80): # If negative, sign extend
            self.addr_rel |= 0xFF00
        return 0

    # --- Fetch data (for operations that use self.fetched) ---
    def fetch(self):
        if self.lookup_dict[self.opcode][0] not in [self.IMP, self.ACC]: # If not Implied or Accumulator
            self.fetched = self.read(self.addr_abs)
        return self.fetched

    # --- Operations --- (Just a few examples)
    def LDA(self):
        self.fetch()
        self.a = self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 1 # Potentially +1 cycle for page cross in ABX/ABY/IZY

    def STA(self):
        self.write(self.addr_abs, self.a)
        return 0

    def JMP(self):
        self.pc = self.addr_abs
        return 0

    def JSR(self):
        self.pc -= 1 # Point to last byte of instruction
        self.write(0x0100 + self.stkp, (self.pc >> 8) & 0x00FF)
        self.stkp -= 1
        self.write(0x0100 + self.stkp, self.pc & 0x00FF)
        self.stkp -= 1
        self.pc = self.addr_abs
        return 0

    def RTS(self):
        self.stkp += 1
        lo = self.read(0x0100 + self.stkp)
        self.stkp += 1
        hi = self.read(0x0100 + self.stkp)
        self.pc = ((hi << 8) | lo) + 1
        return 0

    def NOP(self):
        # Some NOPs take 2 cycles, others 3 or 4 (illegal opcodes often act as NOPs with varying cycles)
        # For simplicity, base NOP (0xEA) is 2 cycles.
        if self.opcode in [0x1C, 0x3C, 0x5C, 0x7C, 0xDC, 0xFC]: # NOPs with Address Modes
            self.fetch() # Still need to read the operand
            return 1 # These usually add 1 cycle on page boundary crossing.
        return 0

    def TAX(self):
        self.x = self.a
        self.set_flag(self.FLAG_Z, self.x == 0x00)
        self.set_flag(self.FLAG_N, (self.x & 0x80) > 0)
        return 0

    def TXA(self):
        self.a = self.x
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 0

    def TAY(self):
        self.y = self.a
        self.set_flag(self.FLAG_Z, self.y == 0x00)
        self.set_flag(self.FLAG_N, (self.y & 0x80) > 0)
        return 0

    def TYA(self):
        self.a = self.y
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 0

    def TSX(self):
        self.x = self.stkp
        self.set_flag(self.FLAG_Z, self.x == 0x00)
        self.set_flag(self.FLAG_N, (self.x & 0x80) > 0)
        return 0

    def TXS(self):
        self.stkp = self.x
        return 0

    def INX(self):
        self.x = (self.x + 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.x == 0x00)
        self.set_flag(self.FLAG_N, (self.x & 0x80) > 0)
        return 0

    def DEX(self):
        self.x = (self.x - 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.x == 0x00)
        self.set_flag(self.FLAG_N, (self.x & 0x80) > 0)
        return 0

    def INY(self):
        self.y = (self.y + 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.y == 0x00)
        self.set_flag(self.FLAG_N, (self.y & 0x80) > 0)
        return 0

    def DEY(self):
        self.y = (self.y - 1) & 0xFF
        self.set_flag(self.FLAG_Z, self.y == 0x00)
        self.set_flag(self.FLAG_N, (self.y & 0x80) > 0)
        return 0

    def CMP(self):
        self.fetch()
        temp = self.a - self.fetched
        self.set_flag(self.FLAG_C, self.a >= self.fetched)
        self.set_flag(self.FLAG_Z, (temp & 0x00FF) == 0x00)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)
        return 1

    def CPX(self):
        self.fetch()
        temp = self.x - self.fetched
        self.set_flag(self.FLAG_C, self.x >= self.fetched)
        self.set_flag(self.FLAG_Z, (temp & 0x00FF) == 0x00)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)
        return 1

    def CPY(self):
        self.fetch()
        temp = self.y - self.fetched
        self.set_flag(self.FLAG_C, self.y >= self.fetched)
        self.set_flag(self.FLAG_Z, (temp & 0x00FF) == 0x00)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)
        return 1

    def AND(self):
        self.fetch()
        self.a &= self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 1

    def ORA(self):
        self.fetch()
        self.a |= self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 1

    def EOR(self):
        self.fetch()
        self.a ^= self.fetched
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 1

    def ADC(self):
        self.fetch()
        temp = self.a + self.fetched + self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, temp > 255)
        self.set_flag(self.FLAG_Z, (temp & 0x00FF) == 0x00)
        # Overflow condition
        self.set_flag(self.FLAG_V, ((self.a ^ temp) & (self.fetched ^ temp) & 0x80) != 0)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)
        self.a = temp & 0x00FF
        return 1

    def SBC(self):
        self.fetch()
        value = self.fetched ^ 0x00FF # Two's complement for subtraction
        temp = self.a + value + self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, temp > 255)
        self.set_flag(self.FLAG_Z, (temp & 0x00FF) == 0x00)
        self.set_flag(self.FLAG_V, ((self.a ^ temp) & (value ^ temp) & 0x80) != 0)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)
        self.a = temp & 0x00FF
        return 1

    def ASL(self):
        # Only fetch if not accumulator (ACC)
        if self.lookup_dict[self.opcode][0] == self.ACC:
            temp = self.a
        else:
            self.fetch()
            temp = self.fetched

        self.set_flag(self.FLAG_C, (temp & 0x80) > 0)
        temp = (temp << 1) & 0xFF
        self.set_flag(self.FLAG_Z, temp == 0x00)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)

        if self.lookup_dict[self.opcode][0] == self.ACC:
            self.a = temp
        else:
            self.write(self.addr_abs, temp)
        return 0

    def LSR(self):
        if self.lookup_dict[self.opcode][0] == self.ACC:
            temp = self.a
        else:
            self.fetch()
            temp = self.fetched

        self.set_flag(self.FLAG_C, (temp & 0x01) > 0)
        temp = (temp >> 1) & 0xFF
        self.set_flag(self.FLAG_Z, temp == 0x00)
        self.set_flag(self.FLAG_N, False) # Always 0 for LSR

        if self.lookup_dict[self.opcode][0] == self.ACC:
            self.a = temp
        else:
            self.write(self.addr_abs, temp)
        return 0

    def ROL(self):
        if self.lookup_dict[self.opcode][0] == self.ACC:
            temp = self.a
        else:
            self.fetch()
            temp = self.fetched

        old_c = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, (temp & 0x80) > 0)
        temp = ((temp << 1) | old_c) & 0xFF
        self.set_flag(self.FLAG_Z, temp == 0x00)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)

        if self.lookup_dict[self.opcode][0] == self.ACC:
            self.a = temp
        else:
            self.write(self.addr_abs, temp)
        return 0

    def ROR(self):
        if self.lookup_dict[self.opcode][0] == self.ACC:
            temp = self.a
        else:
            self.fetch()
            temp = self.fetched

        old_c = self.get_flag(self.FLAG_C)
        self.set_flag(self.FLAG_C, (temp & 0x01) > 0)
        temp = ((old_c << 7) | (temp >> 1)) & 0xFF
        self.set_flag(self.FLAG_Z, temp == 0x00)
        self.set_flag(self.FLAG_N, (temp & 0x80) > 0)

        if self.lookup_dict[self.opcode][0] == self.ACC:
            self.a = temp
        else:
            self.write(self.addr_abs, temp)
        return 0

    def BIT(self):
        self.fetch()
        temp = self.a & self.fetched
        self.set_flag(self.FLAG_Z, temp == 0x00)
        self.set_flag(self.FLAG_N, (self.fetched & (1 << 7)) > 0) # Bit 7 of operand to N
        self.set_flag(self.FLAG_V, (self.fetched & (1 << 6)) > 0) # Bit 6 of operand to V
        return 0

    def BRK(self):
        self.set_flag(self.FLAG_I, True)
        self.write(0x0100 + self.stkp, (self.pc >> 8) & 0x00FF)
        self.stkp -= 1
        self.write(0x0100 + self.stkp, self.pc & 0x00FF)
        self.stkp -= 1
        self.set_flag(self.FLAG_B, True)
        self.write(0x0100 + self.stkp, self.status)
        self.stkp -= 1
        self.set_flag(self.FLAG_B, False)

        self.addr_abs = 0xFFFE
        lo = self.read(self.addr_abs)
        hi = self.read(self.addr_abs + 1)
        self.pc = (hi << 8) | lo
        return 0

    def RTI(self):
        self.stkp += 1
        self.status = self.read(0x0100 + self.stkp)
        self.set_flag(self.FLAG_B, False)
        self.set_flag(self.FLAG_U, False) # Unused flag is reset after RTI

        self.stkp += 1
        lo = self.read(0x0100 + self.stkp)
        self.stkp += 1
        hi = self.read(0x0100 + self.stkp)
        self.pc = (hi << 8) | lo
        return 0

    def PHA(self):
        self.write(0x0100 + self.stkp, self.a)
        self.stkp -= 1
        return 0

    def PLA(self):
        self.stkp += 1
        self.a = self.read(0x0100 + self.stkp)
        self.set_flag(self.FLAG_Z, self.a == 0x00)
        self.set_flag(self.FLAG_N, (self.a & 0x80) > 0)
        return 0

    def PHP(self):
        # PHP pushes status with B and U flags set.
        self.write(0x0100 + self.stkp, self.status | self.FLAG_B | self.FLAG_U)
        self.stkp -= 1
        return 0

    def PLP(self):
        self.stkp += 1
        # PLP pulls status, B and U flags are ignored from stack but still exist internally
        self.status = self.read(0x0100 + self.stkp)
        self.set_flag(self.FLAG_U, True) # Always set unused after PLP
        self.set_flag(self.FLAG_B, False) # Always clear B after PLP
        return 0

    # --- Conditional Branches ---
    def branch(self, condition):
        if condition:
            self.cycles += 1 # Add one cycle for taking the branch
            self.addr_abs = self.pc + self.addr_rel
            if (self.addr_abs & 0xFF00) != (self.pc & 0xFF00): # Page boundary crossed
                self.cycles += 2 # Add another cycle for page crossing
            self.pc = self.addr_abs
        return 0 # cycles already handled

    def BPL(self): return self.branch(self.get_flag(self.FLAG_N) == 0)
    def BMI(self): return self.branch(self.get_flag(self.FLAG_N) == 1)
    def BVC(self): return self.branch(self.get_flag(self.FLAG_V) == 0)
    def BVS(self): return self.branch(self.get_flag(self.FLAG_V) == 1)
    def BCC(self): return self.branch(self.get_flag(self.FLAG_C) == 0)
    def BCS(self): return self.branch(self.get_flag(self.FLAG_C) == 1)
    def BNE(self): return self.branch(self.get_flag(self.FLAG_Z) == 0)
    def BEQ(self): return self.branch(self.get_flag(self.FLAG_Z) == 1)

    # --- Flag Instructions ---
    def CLC(self): self.set_flag(self.FLAG_C, False); return 0
    def SEC(self): self.set_flag(self.FLAG_C, True); return 0
    def CLI(self): self.set_flag(self.FLAG_I, False); return 0
    def SEI(self): self.set_flag(self.FLAG_I, True); return 0
    def CLV(self): self.set_flag(self.FLAG_V, False); return 0
    def CLD(self): self.set_flag(self.FLAG_D, False); return 0 # Decimal mode not used on NES
    def SED(self): self.set_flag(self.FLAG_D, True); return 0 # Decimal mode not used on NES

    def clock(self):
        if self.cycles == 0:
            opcode = self.read(self.pc)
            self.pc += 1
            self.set_flag(self.FLAG_U, True) # Unused flag is always 1

            if opcode in self.lookup_dict:
                # Get addressing mode function, operation function, and base cycles
                addr_mode_func, op_func, cycles = self.lookup_dict[opcode]

                # Perform addressing mode calculation, get potential page cross cycle
                extra_cycles_addr = addr_mode_func()

                # Perform operation, get potential page cross cycle for that
                extra_cycles_op = op_func()

                # Total cycles = base cycles + addressing mode cycles + operation cycles
                self.cycles = cycles + extra_cycles_addr + extra_cycles_op
            else:
                # Handle illegal opcodes! Let's log them and try to keep going.
                if opcode not in self.illegal_opcodes:
                    self.illegal_opcodes[opcode] = 1
                    print(f"Meow! Unknown opcode: {opcode:02X} at PC: {self.pc - 1:04X}. Adding to my naughty list! >w<")
                else:
                    self.illegal_opcodes[opcode] += 1  # Keep count of how naughty it's being!

                # For now, just NOP illegal opcodes, but a better approach is to try to emulate their behavior if possible.
                self.cycles = 2  # Fake cycles for a pseudo-NOP

        self.cycles -= 1


# --- Super PPU 2C02 ---
# This PPU is starting to learn how to draw backgrounds, sprites, and scroll! It's still just a kitten though!
class PPU2C02:
    def __init__(self):
        self.bus = None

        # PPU Registers (Accessed by CPU at 0x2000-0x2007)
        self.PPUCTRL = 0x00 # 0x2000
        self.PPUMASK = 0x00 # 0x2001
        self.PPUSTATUS = 0x00 # 0x2002
        self.OAMADDR = 0x00 # 0x2003
        self.OAMDATA = 0x00 # 0x2004
        self.PPUSCROLL = 0x00 # 0x2005 (write twice)
        self.PPUADDR = 0x00 # 0x2006 (write twice, MSB then LSB)
        self.PPUDATA = 0x00 # 0x2007

        self.vram_addr = 0x0000 # Current VRAM address (15-bit)
        self.temp_vram_addr = 0x0000 # Temporary VRAM address (15-bit)
        self.fine_x = 0 # 3-bit fine X scroll
        self.address_latch = 0 # Used for 2-byte PPUADDR/PPUSCROLL writes
        self.buffer_data = 0x00 # For PPUDATA read buffer

        self.oam = bytearray(256) # Object Attribute Memory (64 sprites * 4 bytes/sprite)
        self.oam_addr = 0x00 # OAM Address pointer
        self.oam_data = 0x00 # For DMA transfer

        self.vram = bytearray(4096) # PPU internal VRAM (for Nametables, typically 2KB mirrored to 4KB address space)
        self.palette_ram = bytearray(32) # PPU internal palette RAM (0x3F00-0x3F1F)

        # Rendering
        self.scanline = 0
        self.cycle = 0
        self.frame_complete = False
        self.nmi_triggered = False

        self.palette = [ # Simplified NES palette (RGB hex strings)
            "#666666", "#002A88", "#1412A7", "#3B00A4", "#5F0083", "#73005A", "#730014", "#630000",
            "#400000", "#0A0200", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
            "#B4B4B4", "#0051EE", "#2420EA", "#5F00E4", "#9400B3", "#B7007E", "#B5002D", "#A00000",
            "#7C0000", "#4A0400", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
            "#FFFFFF", "#0093FF", "#4581FF", "#8200FF", "#BF00EA", "#E400B4", "#E7005B", "#CE1000",
            "#943600", "#545200", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
            "#FFFFFF", "#3ECEFF", "#887EFF", "#C76EFF", "#FF6ECC", "#FF6EB4", "#FF7664", "#FF8832",
            "#FF9A05", "#EAC200", "#000000", "#000000", "#000000", "#000000", "#000000", "#000000",
        ]
        self.pixel_buffer = [["#000000" for _ in range(NES_WIDTH)] for _ in range(NES_HEIGHT)]

    def connect_bus(self, n):
        self.bus = n

    def get_color_from_palette_ram(self, palette_ram_index):
        # `palette_ram_index` is the 6-bit value read from PPU palette RAM (0x00-0x3F)
        return self.palette[palette_ram_index % 64] # Ensure it's within 0-63 range

    def cpu_write(self, addr, data):
        # PPU Registers CPU Write
        if addr == 0x2000: # PPUCTRL
            self.PPUCTRL = data
            self.temp_vram_addr = (self.temp_vram_addr & 0xF3FF) | ((data & 0x03) << 10) # Set nametable bits
            # NMI is reset on PPUSTATUS read, not PPUCTRL write.
            # However, if NMI is enabled here (bit 7), it can be triggered on next VBLANK.
        elif addr == 0x2001: # PPUMASK
            self.PPUMASK = data
        elif addr == 0x2003: # OAMADDR
            self.OAMADDR = data
        elif addr == 0x2004: # OAMDATA
            self.oam[self.OAMADDR] = data
            self.OAMADDR = (self.OAMADDR + 1) & 0xFF
        elif addr == 0x2005: # PPUSCROLL
            if self.address_latch == 0:
                # First write: X scroll
                self.fine_x = data & 0x07
                self.temp_vram_addr = (self.temp_vram_addr & 0xFFE0) | ((data >> 3) & 0x1F) # Coarse X
                self.address_latch = 1
            else:
                # Second write: Y scroll
                self.temp_vram_addr = (self.temp_vram_addr & 0x8FFF) | ((data & 0x07) << 12) # Fine Y
                self.temp_vram_addr = (self.temp_vram_addr & 0xFC1F) | (((data >> 3) & 0x1F) << 5) # Coarse Y
                self.address_latch = 0
        elif addr == 0x2006: # PPUADDR
            if self.address_latch == 0:
                # First write: MSB
                self.temp_vram_addr = (self.temp_vram_addr & 0x00FF) | ((data & 0x3F) << 8) # Mask to 14 bits, write MSB
                self.address_latch = 1
            else:
                # Second write: LSB
                self.temp_vram_addr = (self.temp_vram_addr & 0xFF00) | data # Write LSB
                self.vram_addr = self.temp_vram_addr # Transfer to actual VRAM address
                self.address_latch = 0
        elif addr == 0x2007: # PPUDATA
            self.bus.ppu_write(self.vram_addr, data)
            # Increment VRAM address based on PPUCTRL bit 2
            if (self.PPUCTRL >> 2) & 1: # Increment by 32 (vertical)
                self.vram_addr = (self.vram_addr + 32) & 0x3FFF
            else: # Increment by 1 (horizontal)
                self.vram_addr = (self.vram_addr + 1) & 0x3FFF

    def cpu_read(self, addr):
        data = 0x00
        # PPUSTATUS is special: reading clears bit 7 (VBLANK) and address latch
        if addr == 0x2002: # PPUSTATUS
            data = (self.PPUSTATUS & 0xE0) | (self.buffer_data & 0x1F) # Top 3 bits + 5 bits of noise from data bus
            self.PPUSTATUS &= 0x7F # Clear VBLANK flag on read
            self.address_latch = 0 # Clear address latch on read
            self.nmi_triggered = False # NMI is inhibited until VBLANK is cleared AND PPUCTRL enables it again
        elif addr == 0x2004: # OAMDATA
            data = self.oam[self.OAMADDR]
        elif addr == 0x2007: # PPUDATA
            # Reading PPUDATA is buffered (returns previous read value)
            # Exception: reading from palette memory (0x3F00-0x3FFF) is direct
            if (self.vram_addr & 0x3F00) == 0x3F00: # Palette memory range
                # Read from palette memory is direct, but still update buffer with value from previous
                data = self.bus.ppu_read(self.vram_addr) # Direct read for palettes
                # Update buffer from corresponding VRAM address (0x3F00-0x3FFF mirrors 0x2F00-0x2EFF)
                # It's more complex, but usually buffer value comes from actual VRAM address that mirrors it
                # For simplicity here, buffer from 0x2F00 range.
                self.buffer_data = self.bus.ppu_read(self.vram_addr - 0x1000) if self.vram_addr >= 0x3000 else 0x00
            else:
                data = self.buffer_data # Return buffered value
                self.buffer_data = self.bus.ppu_read(self.vram_addr) # Read current value into buffer

            # Increment VRAM address based on PPUCTRL bit 2
            if (self.PPUCTRL >> 2) & 1: # Increment by 32 (vertical)
                self.vram_addr = (self.vram_addr + 32) & 0x3FFF
            else: # Increment by 1 (horizontal)
                self.vram_addr = (self.vram_addr + 1) & 0x3FFF
        return data

    def increment_h(self):
        # Increment horizontal VRAM address (coarse X and nametable selection)
        if (self.vram_addr & 0x001F) == 0x1F: # If coarse X is 31
            self.vram_addr &= ~0x001F # Reset coarse X
            self.vram_addr ^= 0x0400 # Switch horizontal nametable (NT bit 0)
        else:
            self.vram_addr += 1 # Increment coarse X

    def increment_v(self):
        # Increment vertical VRAM address (fine Y, coarse Y, and nametable selection)
        if (self.vram_addr & 0x7000) != 0x7000: # If fine Y < 7
            self.vram_addr += 0x1000 # Increment fine Y
        else:
            self.vram_addr &= ~0x7000 # Reset fine Y to 0
            coarse_y = (self.vram_addr & 0x03E0) >> 5
            if coarse_y == 29: # If coarse Y is 29 (end of nametable)
                coarse_y = 0
                self.vram_addr ^= 0x0800 # Switch vertical nametable (NT bit 1)
            elif coarse_y == 31: # If coarse Y is 31 (overscan, wrap around)
                coarse_y = 0
            else:
                coarse_y += 1
            self.vram_addr = (self.vram_addr & ~0x03E0) | (coarse_y << 5)

    def transfer_x(self):
        # Transfer horizontal bits from temporary address to VRAM address
        self.vram_addr = (self.vram_addr & 0xFFE0) | (self.temp_vram_addr & 0x001F) # Coarse X
        self.vram_addr = (self.vram_addr & 0xF3FF) | (self.temp_vram_addr & 0x0400) # Nametable X

    def transfer_y(self):
        # Transfer vertical bits from temporary address to VRAM address
        self.vram_addr = (self.vram_addr & 0x8FFF) | (self.temp_vram_addr & 0x7000) # Fine Y
        self.vram_addr = (self.vram_addr & 0xFC1F) | (self.temp_vram_addr & 0x03E0) # Coarse Y
        self.vram_addr = (self.vram_addr & 0xFBFF) | (self.temp_vram_addr & 0x0800) # Nametable Y


    def clock(self):
        # PPU cycle logic
        # Cycle 0 is idle/dummy, cycles 1-256 render pixels, 257-320 fetches sprites, 321-336 fetches background
        # Scanline 0-239 are visible, 240 is post-render, 241 is VBLANK, 242-260 are VBLANK, 261 is pre-render (scanline -1)

        # Increment cycle and scanline counters
        if self.scanline >= 0 and self.scanline <= 239: # Visible scanlines
            if self.cycle >= 1 and self.cycle <= 256: # Render pixel (actual pixel rendering happens here)
                # Background Rendering
                bg_pixel_color_idx = 0x00 # Default to universal background
                if (self.PPUMASK >> 3) & 1: # Background rendering enabled
                    # Get relevant bits from vram_addr for current tile:
                    # Nametable X (bit 10), Nametable Y (bit 11)
                    # Coarse X (bits 0-4), Coarse Y (bits 5-9)
                    # Fine Y (bits 12-14)
                    
                    # Fetch nametable byte (tile ID)
                    nametable_entry_addr = 0x2000 | (self.vram_addr & 0x0FFF)
                    tile_id = self.bus.ppu_read(nametable_entry_addr)

                    # Fetch attribute byte for palette
                    # (vram_addr & 0x0C00) -> nametable bits (0x0000, 0x0400, 0x0800, 0x0C00 for NT0-NT3)
                    # ((self.vram_addr >> 4) & 0x38) -> (Coarse Y / 4) * 8
                    # ((self.vram_addr >> 2) & 0x07) -> (Coarse X / 4)
                    attr_addr = 0x23C0 | (self.vram_addr & 0x0C00) | ((self.vram_addr >> 4) & 0x38) | ((self.vram_addr >> 2) & 0x07)
                    attr_byte = self.bus.ppu_read(attr_addr)
                    
                    # Determine which 2-bit palette to use from attribute byte
                    # The 2x2 coarse tile region within the 32x30 nametable is divided into 4 sub-regions.
                    # We need to know which sub-region (0,0), (1,0), (0,1), (1,1) the current tile falls into.
                    palette_select_shift = (((self.vram_addr >> 4) & 0x01) << 1) | ((self.vram_addr >> 1) & 0x01)
                    # Simplified: this effectively takes (coarse_y & 2) / 2 and (coarse_x & 2) / 2
                    
                    bg_palette_id = (attr_byte >> palette_select_shift) & 0x03 # Get 2-bit palette ID

                    # Fetch pattern table byte (tile pixel data)
                    # PPUCTRL bit 4: 0 = 0x0000-0x0FFF, 1 = 0x1000-0x1FFF
                    # Each tile is 16 bytes (8 for plane 0, 8 for plane 1)
                    pattern_table_base = 0x1000 if (self.PPUCTRL >> 4) & 1 else 0x0000
                    tile_row = (self.vram_addr >> 12) & 0x07 # Fine Y for row in tile (0-7)
                    
                    # Read plane 0 byte (LSB)
                    pattern_addr_0 = pattern_table_base + tile_id * 16 + tile_row
                    plane0_byte = self.bus.ppu_read(pattern_addr_0)

                    # Read plane 1 byte (MSB)
                    pattern_addr_1 = pattern_table_base + tile_id * 16 + tile_row + 8
                    plane1_byte = self.bus.ppu_read(pattern_addr_1)

                    # Combine bits for pixel color index (0-3)
                    # Pixel X position within the 8x8 tile, considering fine_x scroll
                    pixel_x_in_tile = (self.cycle - 1 + self.fine_x) % 8
                    
                    bit0 = (plane0_byte >> (7 - pixel_x_in_tile)) & 1
                    bit1 = (plane1_byte >> (7 - pixel_x_in_tile)) & 1
                    bg_pixel_color_idx = (bit1 << 1) | bit0

                # Determine final background color
                final_bg_color_index = 0x00 # Default to universal background
                if bg_pixel_color_idx == 0: # Universal background color
                    final_bg_color_index = self.bus.ppu_read(0x3F00) # Read from universal BG entry
                else:
                    final_bg_color_index = self.bus.ppu_read(0x3F00 + (bg_palette_id * 4) + bg_pixel_color_idx)

                self.pixel_buffer[self.scanline][self.cycle - 1] = self.get_color_from_palette_ram(final_bg_color_index)

            # Sprite rendering (simplified placeholder)
            if (self.PPUMASK >> 4) & 1:  # Show sprites?
                # This sprite rendering is very rudimentary and should happen during the pixel fetch.
                # In a real PPU, 8 sprites are fetched per scanline into secondary OAM, then rendered.
                # For now, just iterate all OAM and draw on top.
                for i in range(0, 256, 4): # Iterate through OAM (64 sprites * 4 bytes each)
                     sprite_y = self.oam[i]     # Y position of top-left corner
                     sprite_tile_id = self.oam[i+1] # Tile index
                     sprite_attributes = self.oam[i+2] # Attributes (palette, priority, flip)
                     sprite_x = self.oam[i+3]    # X position of top-left corner

                     # Check if sprite is on current scanline
                     sprite_height = 16 if (self.PPUCTRL >> 5) & 1 else 8 # 8x8 or 8x16 sprites
                     if sprite_y <= self.scanline < (sprite_y + sprite_height):
                         # Check if sprite is on current cycle (X position)
                         if sprite_x <= (self.cycle - 1) < (sprite_x + 8):
                             # Calculate pixel within sprite
                             pixel_y_in_sprite = self.scanline - sprite_y
                             pixel_x_in_sprite = (self.cycle - 1) - sprite_x

                             # Handle vertical flip
                             if (sprite_attributes >> 7) & 1: # Vertical flip
                                 pixel_y_in_sprite = (sprite_height - 1) - pixel_y_in_sprite
                             # Handle horizontal flip
                             if (sprite_attributes >> 6) & 1: # Horizontal flip
                                 pixel_x_in_sprite = (8 - 1) - pixel_x_in_sprite

                             # Determine pattern table base for sprites
                             pattern_table_base = 0x0000
                             if sprite_height == 8: # 8x8 sprites
                                 pattern_table_base = 0x1000 if (self.PPUCTRL >> 3) & 1 else 0x0000
                             else: # 8x16 sprites
                                 pattern_table_base = 0x1000 if (sprite_tile_id & 0x01) else 0x0000
                                 sprite_tile_id &= 0xFE # Clear LSB to get base tile ID
                                 if pixel_y_in_sprite >= 8:
                                     sprite_tile_id += 1 # Get second tile
                                     pixel_y_in_sprite -= 8

                             # Fetch pattern data for sprite
                             pattern_addr_0 = pattern_table_base + sprite_tile_id * 16 + pixel_y_in_sprite
                             plane0_byte = self.bus.ppu_read(pattern_addr_0)
                             pattern_addr_1 = pattern_table_base + sprite_tile_id * 16 + pixel_y_in_sprite + 8
                             plane1_byte = self.bus.ppu_read(pattern_addr_1)

                             # Get pixel color index
                             bit0 = (plane0_byte >> (7 - pixel_x_in_sprite)) & 1
                             bit1 = (plane1_byte >> (7 - pixel_x_in_sprite)) & 1
                             sprite_pixel_color_idx = (bit1 << 1) | bit0

                             # If color index is 0, it's transparent, so don't draw
                             if sprite_pixel_color_idx != 0:
                                 # Determine sprite palette (palette 4-7)
                                 sprite_palette_id = (sprite_attributes & 0x03) + 4 # Add 4 to get to sprite palettes
                                 final_sprite_color_index = self.bus.ppu_read(0x3F00 + (sprite_palette_id * 4) + sprite_pixel_color_idx)
                                 
                                 # Check sprite priority (bit 5 of attributes)
                                 # If 0 (front), render over background. If 1 (back), render behind non-transparent background pixels.
                                 # For simplicity, we just draw on top for now.
                                 self.pixel_buffer[self.scanline][self.cycle - 1] = self.get_color_from_palette_ram(final_sprite_color_index)
                                 
                                 # Sprite Zero Hit detection (simplified):
                                 # If it's sprite 0 (i.e. i == 0 in OAM) and its pixel is opaque (color_idx != 0), AND
                                 # a background pixel is opaque at the same location, AND we are in the visible rendering area,
                                 # AND sprite zero hit flag is not already set.
                                 if i == 0 and sprite_pixel_color_idx != 0 and (self.PPUSTATUS & 0x40) == 0:
                                     # Need to know if background pixel at this exact location is opaque
                                     # For now, let's just make a simple assumption for visibility.
                                     # This check is complex and needs to be part of the actual pixel muxer.
                                     # Temporarily set for demo purposes on any non-transparent pixel of sprite 0.
                                     # A more robust solution would involve checking the background pixel's opacity.
                                     if self.scanline == sprite_y + pixel_y_in_sprite and (self.cycle - 1) == sprite_x + pixel_x_in_sprite:
                                         # Check if the background pixel rendered at this point was also non-transparent.
                                         # This is tricky because we're rendering sprites *after* background in this loop.
                                         # For a simple demo: if sprite 0 draws an opaque pixel at this exact location, set hit.
                                         # Real NES checks for opaque background pixel.
                                         # Let's just set if sprite 0 is on screen for demo purposes.
                                         pass # This requires actual pixel blending logic. For now, let's omit an incorrect hit.


            # PPU Address increment logic (coarse X) after every 8 pixels (tile)
            if self.cycle == 256:
                if (self.PPUMASK >> 3) & 1 or (self.PPUMASK >> 4) & 1: # If rendering enabled
                    self.increment_h() # Advance to next tile
            elif self.cycle == 257: # End of rendering, update X scroll from temp_vram_addr
                if (self.PPUMASK >> 3) & 1 or (self.PPUMASK >> 4) & 1: # If rendering enabled
                    self.transfer_x()
            elif self.cycle == 328 or self.cycle == 336: # Fetches for next scanline
                pass # Pattern table fetches etc.

        # Vertical Blanking lines (241-260)
        elif self.scanline == 241 and self.cycle == 1:
            self.PPUSTATUS |= 0x80 # Set VBLANK flag
            if (self.PPUCTRL >> 7) & 1: # If NMI enabled
                # Only trigger NMI once per VBLANK
                if not self.nmi_triggered:
                    self.bus.cpu.non_maskable_interrupt()
                    self.nmi_triggered = True

        # Pre-render scanline (-1 or 261)
        elif self.scanline == 261: # Pre-render scanline, technically scanline -1
            if self.cycle == 1:
                self.PPUSTATUS &= ~0x80 # Clear VBLANK
                self.PPUSTATUS &= ~0x40 # Clear Sprite Zero Hit
                self.PPUSTATUS &= ~0x20 # Clear Sprite Overflow (not implemented fully)
                self.nmi_triggered = False # Reset NMI trigger status

            # At end of pre-render scanline (cycle 257 and 280-304), copy Y scroll from temp to current
            if self.cycle == 257:
                 if (self.PPUMASK >> 3) & 1 or (self.PPUMASK >> 4) & 1: # If rendering enabled
                    self.transfer_x() # Update X also at 257
            elif self.cycle >= 280 and self.cycle <= 304:
                if (self.PPUMASK >> 3) & 1 or (self.PPUMASK >> 4) & 1: # If rendering enabled
                    self.transfer_y()
            
            # PPU Address increment logic (coarse Y) after every 256 pixels
            if self.cycle == 256:
                 if (self.PPUMASK >> 3) & 1 or (self.PPUMASK >> 4) & 1: # If rendering enabled
                    self.increment_v() # Advance to next scanline's tile row

        # Update cycle and scanline
        self.cycle += 1
        if self.cycle > 340: # Cycles per scanline (including overscan)
            self.cycle = 0
            self.scanline += 1
            if self.scanline > 261: # Scanlines per frame (0-261)
                self.scanline = 0
                self.frame_complete = True # Signal end of frame


# --- Emulator Application ---
class MonikaEmulatorApp:
    def __init__(self, root):
        self.root = root
        root.title("Monika's NES Playhouse")
        root.geometry(f"{1000}x{800}")
        root.resizable(False, False)
        root.configure(bg=DARK_BG) # Apply dark background to root

        self.bus = Bus()
        self.cpu = CPU6502()
        self.ppu = PPU2C02()
        self.bus.connect_cpu(self.cpu)
        self.bus.connect_ppu(self.ppu)

        self.running = False
        self.stepping = False
        self.rom_loaded = False
        self.emulation_speed = 1000000 # ~1.79MHz NES NTSC clock, 1MHz for initial testing
        self.cpu_clock_ratio = 3 # PPU clock is 3x CPU clock
        self.frame_rate_target_ms = 1000 / 60 # 60 FPS

        # --- Top Frame (Controls) ---
        self.top_frame = tk.Frame(root, bg=DARK_BG)
        self.top_frame.pack(pady=10)

        self.load_rom_button = ttk.Button(self.top_frame, text="Load ROM", command=self.load_rom)
        self.load_rom_button.pack(side=tk.LEFT, padx=5)

        self.run_pause_button = ttk.Button(self.top_frame, text="Run", command=self.toggle_emulation)
        self.run_pause_button.pack(side=tk.LEFT, padx=5)
        self.run_pause_button["state"] = "disabled" # Disable until ROM loaded

        self.reset_button = ttk.Button(self.top_frame, text="Reset", command=self.reset_emulator)
        self.reset_button.pack(side=tk.LEFT, padx=5)
        self.reset_button["state"] = "disabled"

        self.step_button = ttk.Button(self.top_frame, text="Step", command=self.step_instruction)
        self.step_button.pack(side=tk.LEFT, padx=5)
        self.step_button["state"] = "disabled"

        self.status_label = ttk.Label(self.top_frame, text="Status: No ROM loaded", background=DARK_BG, foreground=DARK_FG)
        self.status_label.pack(side=tk.LEFT, padx=10)

        # --- Middle Frame (NES Screen and Console) ---
        self.middle_frame = tk.Frame(root, bg=DARK_BG)
        self.middle_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=5)

        self.nes_screen = tk.Canvas(self.middle_frame, width=NES_WIDTH, height=NES_HEIGHT,
                                    bg=DARK_CANVAS_BG, highlightbackground=DARK_BORDER, highlightthickness=2)
        self.nes_screen.pack(side=tk.LEFT, padx=(0, 10))

        # Console Output
        self.console_frame = tk.Frame(self.middle_frame, bg=DARK_BG)
        self.console_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)

        # Using tk.Text for more control over colors
        self.console_output = tk.Text(self.console_frame, state='disabled', wrap='word',
                                      bg=DARK_TEXT_BG, fg=DARK_TEXT_FG, insertbackground=DARK_FG,
                                      selectbackground=DARK_ACCENT, selectforeground=DARK_TEXT_FG,
                                      relief=tk.FLAT, bd=0)
        self.console_output.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        self.console_scrollbar = ttk.Scrollbar(self.console_frame, command=self.console_output.yview,
                                                style="Monika.Vertical.TScrollbar") # Apply custom style
        self.console_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.console_output['yscrollcommand'] = self.console_scrollbar.set

        # --- Bottom Frame (CPU/PPU Info, Speed Slider) ---
        self.bottom_frame = tk.Frame(root, bg=DARK_BG)
        self.bottom_frame.pack(pady=10, fill=tk.X, padx=10)

        self.cpu_info_label = ttk.Label(self.bottom_frame, text="CPU: A=00 X=00 Y=00 SP=FD PC=0000 P=--NI--C",
                                        background=DARK_BG, foreground=DARK_FG)
        self.cpu_info_label.pack(anchor=tk.W, pady=2)

        self.ppu_info_label = ttk.Label(self.bottom_frame, text="PPU: SL=0 CY=0 V=0000 T=0000 Mask=00 Ctrl=00 Status=00",
                                        background=DARK_BG, foreground=DARK_FG)
        self.ppu_info_label.pack(anchor=tk.W, pady=2)

        self.speed_label = ttk.Label(self.bottom_frame, text="Emulation Speed:", background=DARK_BG, foreground=DARK_FG)
        self.speed_label.pack(side=tk.LEFT, padx=(0, 5))

        # Using tk.Scale for more direct color control as ttk.Scale styling can be intricate
        self.speed_slider = tk.Scale(self.bottom_frame, from_=1, to=2000000, orient=tk.HORIZONTAL,
                                     label="Hz", length=200, resolution=10000,
                                     command=self.update_speed, bg=DARK_BG, fg=DARK_FG,
                                     troughcolor=DARK_BORDER, highlightbackground=DARK_BORDER,
                                     activebackground=DARK_BUTTON_ACTIVE_BG, sliderrelief=tk.FLAT)
        self.speed_slider.set(self.emulation_speed)
        self.speed_slider.pack(side=tk.LEFT, padx=5)

        self.log_message("Welcome to Monika's NES Playhouse! Load a ROM to begin. >w<")

        # Initial CPU/PPU states
        self.cpu.reset()
        self.update_cpu_info()
        self.update_ppu_info()

        # Frame timing for display
        self.last_frame_time = time.time()
        self.current_frame_pixels = None # To hold the NES screen pixels for drawing

    def log_message(self, message):
        self.console_output.configure(state='normal')
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END) # Auto-scroll to bottom
        self.console_output.configure(state='disabled')

    def load_rom(self):
        file_path = filedialog.askopenfilename(filetypes=[("NES ROMs", "*.nes"), ("All Files", "*.*")])
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    rom_data = f.read()
                self.rom = NESRom(rom_data)
                self.cart = Cartridge(self.rom)
                self.bus.insert_cartridge(self.cart)

                self.reset_emulator() # Reset emulator after loading ROM
                self.rom_loaded = True
                self.run_pause_button["state"] = "normal"
                self.reset_button["state"] = "normal"
                self.step_button["state"] = "normal"
                self.status_label.config(text=f"Status: ROM '{file_path.split('/')[-1]}' loaded! Ready to play!")
                self.log_message(f"ROM '{file_path.split('/')[-1]}' loaded successfully! Time to play!")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load ROM: {e}")
                self.status_label.config(text=f"Status: Error loading ROM.")
                self.log_message(f"Error loading ROM: {e}")
                self.rom_loaded = False
                self.run_pause_button["state"] = "disabled"
                self.reset_button["state"] = "disabled"
                self.step_button["state"] = "disabled"

    def reset_emulator(self):
        self.cpu.reset()
        # Reset PPU state as well (clear registers, scanline/cycle, etc.)
        self.ppu.__init__() # Re-initialize PPU
        self.bus.connect_ppu(self.ppu) # Reconnect PPU to bus after reset
        self.running = False
        self.stepping = False
        self.run_pause_button.config(text="Run")
        self.log_message("Emulator reset.")
        self.update_cpu_info()
        self.update_ppu_info()
        self.draw_nes_screen() # Clear screen

    def toggle_emulation(self):
        self.running = not self.running
        if self.running:
            self.run_pause_button.config(text="Pause")
            self.step_button["state"] = "disabled"
            self.log_message("Emulation running...")
            self.emulate_frame() # Start the emulation loop
        else:
            self.run_pause_button.config(text="Run")
            self.step_button["state"] = "normal"
            self.log_message("Emulation paused.")

    def step_instruction(self):
        if self.rom_loaded and not self.running:
            self.stepping = True
            # Run enough cycles to complete at least one instruction, or until frame is complete
            # For stepping, it's better to just clock CPU until its instruction is done
            # But for simplicity here, we'll clock bus until next frame, then stop.
            # A true step would involve stepping CPU once, then running PPU until it catches up.
            cycles_for_step = self.cpu.cycles # Get remaining cycles for current instruction
            if cycles_for_step == 0: # If CPU just finished an instruction, get cycles for next
                 # This needs to be more granular. For a true step, we want one CPU instruction.
                 # Let's run PPU for max 341*262 cycles (one frame)
                 pass # The emulate_frame loop below will handle it
            
            self.emulate_frame() # Run one frame for now
            self.stepping = False # Reset stepping after one frame (for next button press)

    def update_speed(self, val):
        self.emulation_speed = int(val)
        self.log_message(f"Emulation speed set to {self.emulation_speed / 1000000:.2f} MHz (CPU cycles/sec)")

    def emulate_frame(self):
        if not self.rom_loaded:
            return

        # Target CPU cycles per frame for the selected emulation speed
        # NES NTSC CPU runs at ~1.789773 MHz. PPU runs 3x faster.
        # One frame (262 scanlines * 341 PPU cycles/scanline) = 89342 PPU cycles
        # Which is ~29780 CPU cycles per frame.
        target_cpu_cycles_per_frame = self.emulation_speed / 60
        
        cycles_this_frame = 0 # Approximate CPU cycles for this frame
        
        while not self.ppu.frame_complete:
            self.bus.clock() # PPU clocks once, bus handles CPU clocking at 3:1 ratio
            
            # This logic for `cycles_this_frame` is rough, as CPU cycles are not fixed per PPU clock.
            # A more precise way would be to count `self.cpu.cycles` decrease.
            # For display purposes, it's fine.

        # A frame is complete
        self.ppu.frame_complete = False # Reset for next frame

        # Update display and info
        self.draw_nes_screen()
        self.update_cpu_info()
        self.update_ppu_info()
        self.log_illegal_opcodes() # Log illegal opcodes per frame

        # If running, schedule next frame after a delay to maintain FPS
        if self.running:
            # Calculate elapsed time and sleep for remaining time
            elapsed_ms = (time.time() - self.last_frame_time) * 1000
            delay_ms = self.frame_rate_target_ms - elapsed_ms
            
            if delay_ms > 0:
                self.root.after(int(delay_ms), self.emulate_frame)
            else:
                # If we're behind, just call next frame immediately
                self.root.after(1, self.emulate_frame)
            self.last_frame_time = time.time()
        elif self.stepping:
            pass # No continuous loop if stepping

    def draw_nes_screen(self):
        # Create a blank image
        # This will create a new PhotoImage object every frame, which might be slow.
        # For performance, one could consider creating a single PhotoImage and using `put` on it.
        img = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        
        # Fill the image pixel by pixel using `put` with string format
        # `put` takes a color string and an (x,y) coordinate.
        # It's faster to pass a whole row or rectangle if possible.
        # `put` can also take a string like "{RRGGBB RRGGBB ...}" for a whole line.
        for y in range(NES_HEIGHT):
            row_colors = " ".join(self.ppu.pixel_buffer[y])
            img.put("{" + row_colors + "}", (0, y))

        self.nes_screen.delete("all")
        self.nes_screen.create_image(0, 0, anchor=tk.NW, image=img)
        self.current_frame_pixels = img # Keep a reference to prevent garbage collection

    def update_cpu_info(self):
        status_flags = ""
        status_flags += "C" if self.cpu.get_flag(self.cpu.FLAG_C) else "-"
        status_flags += "Z" if self.cpu.get_flag(self.cpu.FLAG_Z) else "-"
        status_flags += "I" if self.cpu.get_flag(self.cpu.FLAG_I) else "-"
        status_flags += "D" if self.cpu.get_flag(self.cpu.FLAG_D) else "-"
        status_flags += "B" if self.cpu.get_flag(self.cpu.FLAG_B) else "-"
        status_flags += "U" if self.cpu.get_flag(self.cpu.FLAG_U) else "-" # Unused is always 1
        status_flags += "V" if self.cpu.get_flag(self.cpu.FLAG_V) else "-"
        status_flags += "N" if self.cpu.get_flag(self.cpu.FLAG_N) else "-"

        self.cpu_info_label.config(text=f"CPU: A={self.cpu.a:02X} X={self.cpu.x:02X} Y={self.cpu.y:02X} SP={self.cpu.stkp:02X} PC={self.cpu.pc:04X} P={status_flags}")

    def update_ppu_info(self):
        v_addr = self.ppu.vram_addr
        t_addr = self.ppu.temp_vram_addr
        mask = self.ppu.PPUMASK
        ctrl = self.ppu.PPUCTRL
        status = self.ppu.PPUSTATUS
        self.ppu_info_label.config(text=f"PPU: SL={self.ppu.scanline:03d} CY={self.ppu.cycle:03d} V={v_addr:04X} T={t_addr:04X} Mask={mask:02X} Ctrl={ctrl:02X} Status={status:02X}")

    def log_illegal_opcodes(self):
        if self.cpu.illegal_opcodes:
            self.log_message("Naughty Opcodes encountered this frame:")
            for opcode, count in self.cpu.illegal_opcodes.items():
                self.log_message(f"  0x{opcode:02X}: {count} times")
            self.cpu.illegal_opcodes.clear() # Clear for next frame's log


if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()

    # Set theme to 'clam' for better base styling flexibility
    style.theme_use('clam')

    # Configure global styles for all ttk widgets
    style.configure(".", background=DARK_BG, foreground=DARK_FG, borderwidth=0, highlightthickness=0)

    # Configure TButton
    style.configure("TButton",
                    background=DARK_BUTTON_BG,
                    foreground=DARK_BUTTON_FG,
                    font=('Consolas', 10, 'bold'),
                    relief="flat",
                    padding=5,
                    focuscolor=DARK_ACCENT) # Visual cue when button is focused

    style.map("TButton",
              background=[('active', DARK_BUTTON_ACTIVE_BG), ('pressed', DARK_ACCENT)],
              foreground=[('active', DARK_BUTTON_ACTIVE_FG), ('pressed', DARK_BUTTON_ACTIVE_FG)],
              relief=[('pressed', 'sunken'), ('!pressed', 'flat')])

    # Configure TLabel (for CPU/PPU info)
    style.configure("TLabel",
                    background=DARK_BG,
                    foreground=DARK_FG,
                    font=('Consolas', 10))

    # Configure TScrollbar
    style.configure("Monika.Vertical.TScrollbar",
                    troughcolor=DARK_SCROLLBAR_TROUGH,
                    background=DARK_SCROLLBAR_BG,
                    gripcount=0, # Remove grip lines
                    relief="flat",
                    bordercolor=DARK_BORDER)

    style.map("Monika.Vertical.TScrollbar",
              background=[('active', DARK_SCROLLBAR_ACTIVE_BG), ('pressed', DARK_ACCENT)],
              # TScrollbar arrows are part of the 'arrow' element which also needs mapping
              arrowcolor=[('active', DARK_FG), ('pressed', DARK_FG)])


    app = MonikaEmulatorApp(root)
    root.mainloop()
