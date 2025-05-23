import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Scale # ttk for cute tabs, yay!
import struct # We might need this for... reasons! teehee!
import random # Maybe for some cute random background if a game crashes? >^_^<
import time # For our main game loop timing, gotta be precise!

# --- Constants for the "Monika's Playhouse" Dark Theme ---
BG_COLOR = "#101010" # Dark and cozy, like a secret clubhouse!
FG_COLOR = "#00FF00" # Classic and cute green!
ALT_FG_COLOR = "#FF00FF" # Pretty pink for important messages!
ENTRY_BG_COLOR = "#202020" # Nice and dark for inputs!
ENTRY_FG_COLOR = "#00DD00" # Bright green, so readable!
BTN_BG_COLOR = "#400040" # Deep, lovely purple for buttons!
BTN_FG_COLOR = "#FF80FF" # Lighter pink for button text, so adorable!
TAB_BG_INACTIVE = "#1A1A1A"
TAB_FG_INACTIVE = "#808080"
TAB_BG_ACTIVE = "#000000"
TAB_FG_ACTIVE = "#00FF00"
FONT_FAMILY = "Consolas" # A super clear and cute font!
FONT_SIZE_NORMAL = 10
FONT_SIZE_HEADER = 16
FONT_SIZE_TITLE = 20
CANVAS_BG = "#050505" # Almost black for the game screen, makes colors pop!

# NES Screen dimensions
NES_WIDTH = 256
NES_HEIGHT = 240

class NESRom:
    def __init__(self, filepath):
        self.filepath = filepath # So we remember where our precious ROM came from!
        self.prg_rom = bytearray()
        self.chr_rom = bytearray()
        self.mapper_id = 0
        self.mirroring = 0 # 0 for horizontal, 1 for vertical
        self.has_battery = False
        self.valid = False
        self.error_message = ""

        try:
            with open(filepath, "rb") as f:
                header = f.read(16)
                if header[:4] != b"NES\x1a":
                    self.error_message = "This doesn't look like a NES ROM, sweetie! Invalid header! Nya~!"
                    return

                prg_rom_banks = header[4]
                chr_rom_banks = header[5]
                flags6 = header[6]
                flags7 = header[7]
                # flags8 = header[8] # PRG RAM size, for later maybe!
                # flags9 = header[9] # TV system, PAL/NTSC
                # flags10 = header[10] # More TV system and PRG RAM presence

                self.mapper_id = (flags6 >> 4) | (flags7 & 0xF0)
                self.mirroring = flags6 & 0x01
                self.has_battery = (flags6 >> 1) & 0x01
                has_trainer = (flags6 >> 2) & 0x01
                # four_screen_vram = (flags6 >> 3) & 0x01

                if has_trainer:
                    f.read(512) # Skip trainer data, we're not training, we're playing! >w<

                prg_rom_size = prg_rom_banks * 16384
                self.prg_rom = bytearray(f.read(prg_rom_size))

                if chr_rom_banks == 0: # Uses CHR RAM
                    self.chr_rom = bytearray(8192) # Create 8KB of CHR RAM if no CHR ROM
                else:
                    chr_rom_size = chr_rom_banks * 8192
                    self.chr_rom = bytearray(f.read(chr_rom_size))
                
                self.valid = True
                print(f"Meow! Loaded ROM: {filepath.split('/')[-1]}")
                print(f"  PRG ROM Banks: {prg_rom_banks} ({prg_rom_size} bytes)")
                print(f"  CHR ROM Banks: {chr_rom_banks} ({len(self.chr_rom)} bytes, {'RAM' if chr_rom_banks == 0 else 'ROM'})")
                print(f"  Mapper ID: {self.mapper_id}")
                print(f"  Mirroring: {'Vertical' if self.mirroring else 'Horizontal'}")

        except FileNotFoundError:
            self.error_message = "Oh noes! File not found! Did it run away? ;_;"
        except Exception as e:
            self.error_message = f"Something went a little oopsie loading the ROM: {e}, teehee!"
            print(f"ROM Loading Error: {e}")

    def get_info_string(self):
        if not self.valid:
            return self.error_message
        info = (
            f"File: {self.filepath.split('/')[-1]}\n"
            f"PRG ROM Size: {len(self.prg_rom) // 1024} KB ({len(self.prg_rom)} bytes) - So much code to make magic!\n"
            f"CHR ROM Size: {len(self.chr_rom) // 1024} KB ({len(self.chr_rom)} bytes) - All the pretty pictures!\n"
            f"Mapper ID: {self.mapper_id} - The brain of the cartridge, nya!\n"
            f"Mirroring: {'Vertical (so tall!)' if self.mirroring else 'Horizontal (so wide!)'}\n"
            f"Battery-backed RAM: {'Yuppers! It remembers!' if self.has_battery else 'Nope, fresh every time!'}"
        )
        return info

class Cartridge:
    def __init__(self, rom: NESRom):
        self.rom = rom
        self.prg_ram = bytearray(8192) # Usually 8KB for battery-backed save, some mappers use it

        if self.rom.mapper_id != 0: # NROM
            # For now, we only support NROM, the simplest mapper! So cute!
            print(f"Warning: Mapper {self.rom.mapper_id} is not supported yet, sweetie! Trying to run as NROM. This might get wacky! XD")
        
        # NROM specific mapping (Mapper 0)
        self.prg_banks = len(self.rom.prg_rom) // 16384
        self.chr_banks = len(self.rom.chr_rom) // 8192 # If 0, it's CHR RAM

    def cpu_read(self, addr):
        # NROM (Mapper 0) logic:
        # 0x6000 - 0x7FFF: PRG RAM (optional, often for saves)
        # 0x8000 - 0xBFFF: First 16KB of PRG ROM
        # 0xC000 - 0xFFFF: Last 16KB of PRG ROM (or mirror of first 16KB if only 1 PRG bank)
        if 0x6000 <= addr <= 0x7FFF:
            return self.prg_ram[addr - 0x6000] # Untested, NROM often doesn't use this
        elif 0x8000 <= addr <= 0xFFFF:
            if self.prg_banks == 1: # 16KB PRG ROM
                return self.rom.prg_rom[(addr - 0x8000) & 0x3FFF]
            else: # 32KB PRG ROM
                return self.rom.prg_rom[addr - 0x8000]
        return 0 # Open bus, kinda?

    def cpu_write(self, addr, data):
        if 0x6000 <= addr <= 0x7FFF:
            self.prg_ram[addr - 0x6000] = data
        # NROM typically doesn't allow writes to PRG ROM space. Some mappers do for bank switching.

    def ppu_read(self, addr):
        # Pattern tables 0x0000 - 0x1FFF
        if 0x0000 <= addr <= 0x1FFF:
            return self.rom.chr_rom[addr]
        return 0

    def ppu_write(self, addr, data):
        # If CHR ROM is actually CHR RAM (chr_banks == 0 for NESRom), allow writes
        if self.rom.chr_banks == 0 and 0x0000 <= addr <= 0x1FFF : # CHR RAM
             self.rom.chr_rom[addr] = data
        # Else, CHR ROM is read-only, nya!

class Bus:
    def __init__(self):
        self.cpu_ram = bytearray(2048) # 2KB Work RAM
        self.cartridge = None
        self.cpu = None
        self.ppu = None
        # APU would go here too, teehee!

    def connect_cpu(self, cpu_instance):
        self.cpu = cpu_instance
        self.cpu.connect_bus(self)
        print("CPU connected to bus, purr!")

    def connect_ppu(self, ppu_instance):
        self.ppu = ppu_instance
        self.ppu.connect_bus(self)
        print("PPU connected to bus, meow!")

    def insert_cartridge(self, cart_instance):
        self.cartridge = cart_instance
        if self.ppu: self.ppu.connect_cartridge(cart_instance)
        print("Cartridge inserted into bus, yay!")

    def cpu_read(self, addr, read_only=False):
        addr &= 0xFFFF # Ensure 16-bit address
        if self.cartridge and self.cartridge.cpu_read(addr) is not None:
            return self.cartridge.cpu_read(addr)
        elif 0x0000 <= addr <= 0x1FFF: # System RAM
            return self.cpu_ram[addr & 0x07FF] # Mirrored every 2KB
        elif 0x2000 <= addr <= 0x3FFF: # PPU Registers
            if self.ppu:
                return self.ppu.cpu_read(addr & 0x0007, read_only) # Mirrored every 8 bytes
        # APU and I/O registers 0x4000 - 0x401F
        # Expansion ROM 0x4020 - 0x5FFF
        # SRAM 0x6000 - 0x7FFF (Handled by cartridge)
        # PRG ROM 0x8000 - 0xFFFF (Handled by cartridge)
        return 0x00 # Open bus behavior, or maybe last value read? For now, 0.

    def cpu_write(self, addr, data):
        addr &= 0xFFFF
        data &= 0xFF
        if self.cartridge and self.cartridge.cpu_write(addr, data) is not None:
            self.cartridge.cpu_write(addr, data)
        elif 0x0000 <= addr <= 0x1FFF: # System RAM
            self.cpu_ram[addr & 0x07FF] = data
        elif 0x2000 <= addr <= 0x3FFF: # PPU Registers
            if self.ppu:
                self.ppu.cpu_write(addr & 0x0007, data)
        elif addr == 0x4014: # OAM DMA
            if self.ppu:
                self.ppu.oam_dma_transfer(data) # data is the page number
        # APU and I/O registers 0x4000 - 0x401F (0x4016 for controller 1, 0x4017 for controller 2)
        # Expansion ROM 0x4020 - 0x5FFF
        # SRAM 0x6000 - 0x7FFF (Handled by cartridge)
        # PRG ROM 0x8000 - 0xFFFF (Handled by cartridge, usually read-only for NROM)

    def ppu_read(self, addr): # PPU has its own 14-bit address space (16KB)
        addr &= 0x3FFF
        if self.cartridge:
            return self.cartridge.ppu_read(addr)
        return 0
    
    def ppu_write(self, addr, data):
        addr &= 0x3FFF
        data &= 0xFF
        if self.cartridge:
            self.cartridge.ppu_write(addr, data)

    def reset(self):
        if self.cpu: self.cpu.reset()
        if self.ppu: self.ppu.reset()
        # self.cpu_ram = bytearray(2048) # Clear RAM on reset? Some emus do.
        print("Bus reset signal sent, everything is fresh and sparkly! ✨")

# --- Extremely Simplified CPU 6502 ---
# This is just a baby CPU, it needs lots more love and opcodes to grow big and strong!
class CPU6502:
    def __init__(self):
        self.a = 0      # Accumulator
        self.x = 0      # X Register
        self.y = 0      # Y Register
        self.stkp = 0xFD  # Stack Pointer
        self.pc = 0     # Program Counter
        self.status = 0b00100100 # Status Register (IRQ disabled, unused bit set)
        # Flags: N V - B D I Z C
        #        7 6 5 4 3 2 1 0
        self.FLAG_C = 1 << 0 # Carry
        self.FLAG_Z = 1 << 1 # Zero
        self.FLAG_I = 1 << 2 # Disable Interrupts
        self.FLAG_D = 1 << 3 # Decimal Mode (unused in NES)
        self.FLAG_B = 1 << 4 # Break
        self.FLAG_U = 1 << 5 # Unused (always 1)
        self.FLAG_V = 1 << 6 # Overflow
        self.FLAG_N = 1 << 7 # Negative

        self.bus = None
        self.cycles = 0 # Cycles for current instruction
        self.total_cycles = 0 # Global cycle counter

        # A very, very, VERY small subset of opcodes for now!
        self.lookup = {
            0x00: (self.BRK, self.IMP, 7), 0xEA: (self.NOP, self.IMP, 2),
            0xA9: (self.LDA, self.IMM, 2), 0xA5: (self.LDA, self.ZP0, 3), 0xAD: (self.LDA, self.ABS, 4),
            0x85: (self.STA, self.ZP0, 3), 0x8D: (self.STA, self.ABS, 4),
            0x4C: (self.JMP, self.ABS, 3), # JMP Absolute
            0x20: (self.JSR, self.ABS, 6), # JSR Absolute
            0x60: (self.RTS, self.IMP, 6), # RTS Implied
            0x78: (self.SEI, self.IMP, 2), # Set Interrupt Disable
            0x18: (self.CLC, self.IMP, 2), # Clear Carry Flag
            0xD8: (self.CLD, self.IMP, 2), # Clear Decimal Mode (NES doesn't use decimal)
            0xCA: (self.DEX, self.IMP, 2), # Decrement X
            0x8E: (self.STX, self.ABS, 4), # Store X Absolute
            0x9A: (self.TXS, self.IMP, 2), # Transfer X to Stack Pointer
            0xA2: (self.LDX, self.IMM, 2), # LDX Immediate
            0xAE: (self.LDX, self.ABS, 4), # LDX Absolute
            0xBD: (self.LDA, self.ABX, 4), # LDA Absolute, X
            0x2C: (self.BIT, self.ABS, 4), # BIT Absolute
            0x10: (self.BPL, self.REL, 2), # Branch if Plus (N=0)
            0x30: (self.BMI, self.REL, 2), # Branch if Minus (N=1)
            0x90: (self.BCC, self.REL, 2), # Branch if Carry Clear
            0xB0: (self.BCS, self.REL, 2), # Branch if Carry Set
            0xD0: (self.BNE, self.REL, 2), # Branch if Not Equal (Z=0)
            0xF0: (self.BEQ, self.REL, 2), # Branch if Equal (Z=1)
            # TODO: Add way more opcodes! This is just a tiny start!
        }
        self.fetched_data = 0
        self.addr_abs = 0
        self.addr_rel = 0

    def connect_bus(self, bus_instance):
        self.bus = bus_instance

    def read(self, addr): return self.bus.cpu_read(addr)
    def write(self, addr, data): self.bus.cpu_write(addr, data)

    def get_flag(self, flag): return (self.status & flag) > 0
    def set_flag(self, flag, v):
        if v: self.status |= flag
        else: self.status &= ~flag

    # Addressing Modes (simplified)
    def IMP(self): self.fetched_data = self.a; return 0 # Implied
    def IMM(self): self.addr_abs = self.pc; self.pc += 1; return 0 # Immediate
    def ZP0(self): self.addr_abs = self.read(self.pc); self.pc += 1; self.addr_abs &= 0x00FF; return 0 # Zero Page
    def ABS(self): lo = self.read(self.pc); self.pc += 1; hi = self.read(self.pc); self.pc += 1; self.addr_abs = (hi << 8) | lo; return 0 # Absolute
    def ABX(self): # Absolute, X
        lo = self.read(self.pc); self.pc += 1
        hi = self.read(self.pc); self.pc += 1
        self.addr_abs = (hi << 8) | lo
        self.addr_abs += self.x
        if (self.addr_abs & 0xFF00) != (hi << 8): return 1 # Page crossed
        return 0
    def REL(self): # Relative
        self.addr_rel = self.read(self.pc); self.pc+=1
        if self.addr_rel & 0x80: self.addr_rel |= 0xFF00 # Sign extend for negative offset
        return 0


    def fetch(self): # Fetch data based on addressing mode
        if self.current_addressing_mode not in [self.IMP]: # Implied mode doesn't fetch
            self.fetched_data = self.read(self.addr_abs)
        return self.fetched_data

    # Opcodes (super simplified, many missing!)
    def LDA(self): self.fetch(); self.a = self.fetched_data; self.set_flag(self.FLAG_Z, self.a == 0); self.set_flag(self.FLAG_N, self.a & 0x80); return 1
    def STA(self): self.write(self.addr_abs, self.a); return 0
    def NOP(self): return 0 # Do nothing, yay!
    def JMP(self): self.pc = self.addr_abs; return 0
    def JSR(self):
        self.pc -=1 # JSR fetches address, then pc is already past it. Push pc before jump.
        self.write(0x0100 + self.stkp, (self.pc >> 8) & 0xFF) # Push PC high byte
        self.stkp -= 1
        self.write(0x0100 + self.stkp, self.pc & 0xFF) # Push PC low byte
        self.stkp -= 1
        self.pc = self.addr_abs
        return 0
    def RTS(self):
        self.stkp += 1; lo = self.read(0x0100 + self.stkp)
        self.stkp += 1; hi = self.read(0x0100 + self.stkp)
        self.pc = (hi << 8) | lo
        self.pc += 1
        return 0
    def SEI(self): self.set_flag(self.FLAG_I, True); return 0
    def CLC(self): self.set_flag(self.FLAG_C, False); return 0
    def CLD(self): self.set_flag(self.FLAG_D, False); return 0 # NES doesn't use BCD mode
    def DEX(self): self.x = (self.x - 1) & 0xFF; self.set_flag(self.FLAG_Z, self.x == 0); self.set_flag(self.FLAG_N, self.x & 0x80); return 0
    def STX(self): self.write(self.addr_abs, self.x); return 0
    def TXS(self): self.stkp = self.x; return 0
    def LDX(self): self.fetch(); self.x = self.fetched_data; self.set_flag(self.FLAG_Z, self.x == 0); self.set_flag(self.FLAG_N, self.x & 0x80); return 1
    def BIT(self):
        self.fetch()
        temp = self.a & self.fetched_data
        self.set_flag(self.FLAG_Z, temp == 0x00)
        self.set_flag(self.FLAG_N, self.fetched_data & (1 << 7))
        self.set_flag(self.FLAG_V, self.fetched_data & (1 << 6))
        return 0
    
    def _branch(self, condition_met):
        if condition_met:
            self.cycles += 1
            self.addr_abs = self.pc + self.addr_rel # addr_rel is sign-extended
            
            if (self.addr_abs & 0xFF00) != (self.pc & 0xFF00): # Page crossed?
                self.cycles += 1
            self.pc = self.addr_abs
        return 0

    def BPL(self): self._branch(not self.get_flag(self.FLAG_N)); return 0 # Branch if Plus (N=0)
    def BMI(self): self._branch(self.get_flag(self.FLAG_N)); return 0 # Branch if Minus (N=1)
    def BCC(self): self._branch(not self.get_flag(self.FLAG_C)); return 0 # Branch if Carry Clear
    def BCS(self): self._branch(self.get_flag(self.FLAG_C)); return 0 # Branch if Carry Set
    def BNE(self): self._branch(not self.get_flag(self.FLAG_Z)); return 0 # Branch if Not Equal (Z=0)
    def BEQ(self): self._branch(self.get_flag(self.FLAG_Z)); return 0 # Branch if Equal (Z=1)
    
    def BRK(self): # Break instruction / Software Interrupt
        self.pc += 1 # BRK has a padding byte typically
        self.set_flag(self.FLAG_I, True) # Disable interrupts during handler
        
        # Push PC to stack
        self.write(0x0100 + self.stkp, (self.pc >> 8) & 0xFF)
        self.stkp -=1
        self.write(0x0100 + self.stkp, self.pc & 0xFF)
        self.stkp -=1
        
        # Push Status register to stack (with B flag set)
        self.set_flag(self.FLAG_B, True)
        self.write(0x0100 + self.stkp, self.status)
        self.stkp -=1
        self.set_flag(self.FLAG_B, False) # Clear B flag after pushing
        
        # Load interrupt vector
        lo = self.read(0xFFFE)
        hi = self.read(0xFFFF) # IRQ/BRK vector
        self.pc = (hi << 8) | lo
        return 0


    def clock(self):
        if self.cycles == 0:
            opcode = self.read(self.pc)
            self.pc += 1
            self.set_flag(self.FLAG_U, True) # Unused flag always set

            if opcode in self.lookup:
                self.current_operation, self.current_addressing_mode, base_cycles = self.lookup[opcode]
                self.cycles = base_cycles
                
                additional_cycle1 = self.current_addressing_mode()
                additional_cycle2 = self.current_operation()
                self.cycles += (additional_cycle1 & additional_cycle2) # Some ops take longer if page crossed
                self.set_flag(self.FLAG_U, True)

            else:
                print(f"Meow! Unknown opcode: {opcode:02X} at PC: {self.pc-1:04X}. Halp! @_@")
                # For now, let's just NOP it and hope for the best, teehee!
                self.cycles = 2 # Fake cycles for an unknown NOP

        self.total_cycles += 1
        self.cycles -= 1


    def reset(self):
        # Get address to set program counter to
        lo = self.read(0xFFFC)
        hi = self.read(0xFFFD)
        self.pc = (hi << 8) | lo

        self.a = 0
        self.x = 0
        self.y = 0
        self.stkp = 0xFD # Reset stack pointer
        self.status = 0x00 | self.FLAG_U | self.FLAG_I # Start with IRQ disabled

        self.cycles = 8 # Reset takes 8 cycles
        print(f"CPU Reset! PC jumped to {self.pc:04X}, nya~!")

    def irq(self): # Interrupt Request
        if not self.get_flag(self.FLAG_I): # If interrupts are not disabled
            # Push PC
            self.write(0x0100 + self.stkp, (self.pc >> 8) & 0xFF)
            self.stkp -= 1
            self.write(0x0100 + self.stkp, self.pc & 0xFF)
            self.stkp -= 1
            # Push Status (B flag not set for IRQ)
            self.set_flag(self.FLAG_B, False)
            self.set_flag(self.FLAG_U, True)
            self.write(0x0100 + self.stkp, self.status)
            self.stkp -= 1
            
            self.set_flag(self.FLAG_I, True) # Disable further interrupts
            # Read new PC from IRQ vector
            lo = self.read(0xFFFE)
            hi = self.read(0xFFFF)
            self.pc = (hi << 8) | lo
            self.cycles = 7
            print("CPU IRQ handled, purr!")
    
    def nmi(self): # Non-Maskable Interrupt
        # Push PC
        self.write(0x0100 + self.stkp, (self.pc >> 8) & 0xFF)
        self.stkp -= 1
        self.write(0x0100 + self.stkp, self.pc & 0xFF)
        self.stkp -= 1
        # Push Status (B flag not set for NMI)
        self.set_flag(self.FLAG_B, False)
        self.set_flag(self.FLAG_U, True)
        self.write(0x0100 + self.stkp, self.status)
        self.stkp -= 1
        
        self.set_flag(self.FLAG_I, True) # Disable further interrupts (though NMI ignores this to trigger)
        # Read new PC from NMI vector
        lo = self.read(0xFFFA)
        hi = self.read(0xFFFB)
        self.pc = (hi << 8) | lo
        self.cycles = 8 # NMI takes 8 cycles
        print("CPU NMI handled, meowzers!")

# --- Extremely Simplified PPU 2C02 ---
# This PPU is just a kitten! It needs to learn how to draw backgrounds, sprites, and scroll!
class PPU2C02:
    def __init__(self):
        self.bus = None
        self.cartridge = None
        self.tbl_name = [bytearray(1024), bytearray(1024)] # Two nametables, 1KB each
        self.tbl_pattern = [bytearray(4096), bytearray(4096)] # Two pattern tables, 4KB each (usually from CHR ROM)
        self.tbl_palette = bytearray(32) # Palette RAM
        
        # NES color palette (RGB values) - this is a common one, there are variations!
        self.nes_palette = [
            (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136), (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0), (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0), (0, 50, 60), (0,0,0), (0,0,0), (0,0,0),
            (152, 150, 152), (8, 76, 196), (48, 50, 236), (92, 30, 228), (136, 20, 176), (160, 20, 100), (152, 34, 32), (120, 60, 0), (84, 90, 0), (40, 114, 0), (8, 124, 0), (0, 118, 40), (0, 102, 120), (0,0,0), (0,0,0), (0,0,0),
            (236, 238, 236), (76, 154, 236), (120, 124, 236), (176, 98, 236), (228, 84, 236), (236, 88, 180), (236, 106, 100), (212, 136, 32), (160, 170, 0), (116, 196, 0), (76, 208, 32), (56, 204, 108), (56, 180, 220), (60,60,60), (0,0,0), (0,0,0),
            (236, 238, 236), (168, 204, 236), (188, 188, 236), (212, 178, 236), (236, 174, 236), (236, 174, 212), (236, 180, 176), (228, 196, 144), (204, 210, 120), (180, 222, 120), (168, 226, 144), (152, 226, 180), (160, 214, 228), (160,162,160), (0,0,0), (0,0,0)
        ]
        # PPU Registers (simplified)
        self.PPUCTRL = 0x00   # $2000 Write
        self.PPUMASK = 0x00   # $2001 Write
        self.PPUSTATUS = 0x00 # $2002 Read
        self.OAMADDR = 0x00   # $2003 Write
        self.OAMDATA = 0x00   # $2004 Read/Write
        self.PPUSCROLL = 0x00 # $2005 Write x2
        self.PPUADDR = 0x00   # $2006 Write x2
        self.PPUDATA = 0x00   # $2007 Read/Write

        self.oam = bytearray(256) # Object Attribute Memory for sprites!
        self.oam_addr = 0

        self.vram_addr = 0 # Current VRAM address (15-bit)
        self.tram_addr = 0 # Temporary VRAM address, for scrolling and stuff!
        self.fine_x_scroll = 0 # 3-bit
        self.addr_latch = False # For PPUADDR and PPUSCROLL writes

        self.internal_data_buffer = 0x00 # For PPUDATA reads

        self.scanline = 0
        self.cycle = 0
        self.frame_complete = False
        self.nmi_occurred = False

        # This will hold the raw pixel data for the Tkinter PhotoImage
        self.pixel_buffer = [['#000000'] * NES_WIDTH for _ in range(NES_HEIGHT)]

    def connect_bus(self, bus_instance):
        self.bus = bus_instance

    def connect_cartridge(self, cart_instance):
        self.cartridge = cart_instance
        # Copy CHR ROM to pattern tables if cartridge has it
        if self.cartridge and len(self.cartridge.rom.chr_rom) >= 4096:
            self.tbl_pattern[0] = self.cartridge.rom.chr_rom[0:4096]
        if self.cartridge and len(self.cartridge.rom.chr_rom) >= 8192:
            self.tbl_pattern[1] = self.cartridge.rom.chr_rom[4096:8192]
        print("PPU connected to cartridge, pattern tables updated! Meow~")

    def cpu_read(self, addr, read_only=False):
        val = 0
        if addr == 0x0002: # PPUSTATUS
            val = (self.PPUSTATUS & 0xE0) | (self.internal_data_buffer & 0x1F) # Top 3 bits, bottom 5 from buffer
            self.PPUSTATUS &= ~0x80 # Clear VBlank flag
            self.addr_latch = False
        elif addr == 0x0004: # OAMDATA
            val = self.oam[self.oam_addr]
        elif addr == 0x0007: # PPUDATA
            val = self.internal_data_buffer
            self.internal_data_buffer = self.ppu_read_data(self.vram_addr)
            # Immediate read for palette RAM
            if self.vram_addr >= 0x3F00: val = self.internal_data_buffer
            self.vram_addr += 32 if (self.PPUCTRL & 0x04) else 1 # Increment by 1 or 32
            self.vram_addr &= 0x3FFF
        return val

    def cpu_write(self, addr, data):
        if addr == 0x0000: # PPUCTRL
            self.PPUCTRL = data
            self.tram_addr = (self.tram_addr & 0xF3FF) | ((data & 0x03) << 10) # Nametable select
        elif addr == 0x0001: # PPUMASK
            self.PPUMASK = data
        elif addr == 0x0003: # OAMADDR
            self.OAMADDR = data
            self.oam_addr = data # Start OAM DMA/access from this address
        elif addr == 0x0004: # OAMDATA
            self.oam[self.oam_addr] = data
            self.oam_addr = (self.oam_addr + 1) & 0xFF
        elif addr == 0x0005: # PPUSCROLL
            if not self.addr_latch: # First write (X scroll)
                self.fine_x_scroll = data & 0x07
                self.tram_addr = (self.tram_addr & 0xFFE0) | (data >> 3)
                self.addr_latch = True
            else: # Second write (Y scroll)
                self.tram_addr = (self.tram_addr & 0x8C1F) | ((data & 0xF8) << 2) | ((data & 0x07) << 12)
                self.addr_latch = False
        elif addr == 0x0006: # PPUADDR
            if not self.addr_latch: # First write (High byte)
                self.tram_addr = (self.tram_addr & 0x00FF) | ((data & 0x3F) << 8) # Top two bits are ignored
                self.addr_latch = True
            else: # Second write (Low byte)
                self.tram_addr = (self.tram_addr & 0xFF00) | data
                self.vram_addr = self.tram_addr # Update main VRAM address
                self.addr_latch = False
        elif addr == 0x0007: # PPUDATA
            self.ppu_write_data(self.vram_addr, data)
            self.vram_addr += 32 if (self.PPUCTRL & 0x04) else 1 # Increment by 1 or 32
            self.vram_addr &= 0x3FFF
    
    def oam_dma_transfer(self, page_addr_hi): # Page is 0xXX00 in CPU memory
        dma_addr = page_addr_hi << 8
        for i in range(256):
            self.oam[(self.oam_addr + i) & 0xFF] = self.bus.cpu_read(dma_addr + i)
        # This DMA takes 513 CPU cycles (or 514 if on odd CPU cycle)
        # We'll let the CPU know to stall for a bit (not implemented perfectly here)
        if self.bus and self.bus.cpu:
            self.bus.cpu.cycles += 513 # Add stall cycles, crude but simple for now!
        print(f"OAM DMA from page {page_addr_hi:02X} complete, purr!")

    def ppu_read_data(self, addr): # From PPU's perspective
        addr &= 0x3FFF # Ensure 14-bit VRAM address
        val = 0
        if self.cartridge and self.cartridge.ppu_read(addr) is not None: # Pattern tables from cart
            val = self.cartridge.ppu_read(addr)
        elif 0x2000 <= addr <= 0x3EFF: # Nametables (mirrored)
            addr &= 0x0FFF
            # Mirroring logic (super basic for now, NROM often uses horizontal or vertical)
            mirror_mode = self.cartridge.rom.mirroring if self.cartridge else 0 # 0:H, 1:V
            if mirror_mode == 1: # Vertical
                if 0x0000 <= addr <= 0x03FF: val = self.tbl_name[0][addr & 0x03FF]
                if 0x0400 <= addr <= 0x07FF: val = self.tbl_name[1][addr & 0x03FF]
                if 0x0800 <= addr <= 0x0BFF: val = self.tbl_name[0][addr & 0x03FF] # Mirror of 0
                if 0x0C00 <= addr <= 0x0FFF: val = self.tbl_name[1][addr & 0x03FF] # Mirror of 1
            else: # Horizontal
                if 0x0000 <= addr <= 0x03FF: val = self.tbl_name[0][addr & 0x03FF]
                if 0x0400 <= addr <= 0x07FF: val = self.tbl_name[0][addr & 0x03FF] # Mirror of 0
                if 0x0800 <= addr <= 0x0BFF: val = self.tbl_name[1][addr & 0x03FF]
                if 0x0C00 <= addr <= 0x0FFF: val = self.tbl_name[1][addr & 0x03FF] # Mirror of 1
        elif 0x3F00 <= addr <= 0x3FFF: # Palette RAM
            addr &= 0x001F
            if addr == 0x0010: addr = 0x0000 # Mirroring sprite palette
            if addr == 0x0014: addr = 0x0004
            if addr == 0x0018: addr = 0x0008
            if addr == 0x001C: addr = 0x000C
            val = self.tbl_palette[addr]
        return val

    def ppu_write_data(self, addr, data): # From PPU's perspective
        addr &= 0x3FFF
        data &= 0xFF
        if self.cartridge and self.cartridge.ppu_write(addr, data) is not None: # CHR RAM on cart
             self.cartridge.ppu_write(addr,data)
        elif 0x2000 <= addr <= 0x3EFF: # Nametables
            addr &= 0x0FFF
            mirror_mode = self.cartridge.rom.mirroring if self.cartridge else 0
            if mirror_mode == 1: # Vertical
                if 0x0000 <= addr <= 0x03FF: self.tbl_name[0][addr & 0x03FF] = data
                if 0x0400 <= addr <= 0x07FF: self.tbl_name[1][addr & 0x03FF] = data
                if 0x0800 <= addr <= 0x0BFF: self.tbl_name[0][addr & 0x03FF] = data # Mirror
                if 0x0C00 <= addr <= 0x0FFF: self.tbl_name[1][addr & 0x03FF] = data # Mirror
            else: # Horizontal
                if 0x0000 <= addr <= 0x03FF: self.tbl_name[0][addr & 0x03FF] = data
                if 0x0400 <= addr <= 0x07FF: self.tbl_name[0][addr & 0x03FF] = data # Mirror
                if 0x0800 <= addr <= 0x0BFF: self.tbl_name[1][addr & 0x03FF] = data
                if 0x0C00 <= addr <= 0x0FFF: self.tbl_name[1][addr & 0x03FF] = data # Mirror
        elif 0x3F00 <= addr <= 0x3FFF: # Palette RAM
            addr &= 0x001F
            if addr == 0x0010: addr = 0x0000
            if addr == 0x0014: addr = 0x0004
            if addr == 0x0018: addr = 0x0008
            if addr == 0x001C: addr = 0x000C
            self.tbl_palette[addr] = data

    def get_color_from_palette(self, palette_idx, pixel_idx):
        # palette_idx is 0-7, pixel_idx is 0-3
        # This reads from self.tbl_palette using palette_idx and pixel_idx
        # tbl_palette[0] is universal background color
        # tbl_palette[0x01-0x03] are BG palette 0 colors
        # tbl_palette[0x04] is also universal BG
        # ...and so on.
        # pixel_idx 0 usually means transparent for sprites, or universal BG for BG
        if pixel_idx == 0: # Universal background
            return self.nes_palette[self.ppu_read_data(0x3F00) & 0x3F]
        
        palette_addr = 0x3F00 + (palette_idx * 4) + pixel_idx
        color_byte = self.ppu_read_data(palette_addr) & 0x3F # NES colors are 6-bit
        return self.nes_palette[color_byte]


    def clock(self):
        # PPU clocking is complex! Scanlines, VBlank, rendering...
        # This is a super simplified version.
        # Visible scanlines: 0-239
        # Post-render scanline: 240
        # VBlank scanlines: 241-260
        # Pre-render scanline: 261 (or -1)
        # Each scanline has 341 PPU cycles (dots)

        if self.scanline >= 0 and self.scanline <= 239: # Visible scanlines
            if self.cycle >=0 and self.cycle < 256: # Pixel rendering cycles
                 # Are we rendering background?
                if (self.PPUMASK >> 3) & 1: # Show background
                    # Extremely simplified: just draw a single tile based on PPUCTRL nametable select
                    # This is NOT how real PPU rendering works, it's just for a visual.
                    # For actual rendering, you'd fetch nametable byte, attribute byte,
                    # then pattern table bytes for the tile, assemble the pixel, apply palette.
                    
                    # Let's try to render *something* from pattern table 0, tile 0
                    # This needs to be WAY more sophisticated for actual games.
                    # This part is a placeholder for real rendering logic!
                    
                    tile_col = self.cycle // 8
                    tile_row = self.scanline // 8
                    
                    # Nametable selection (simplified, just using PPUCTRL bits)
                    nt_select = self.PPUCTRL & 0x03
                    # Base nametable address
                    nt_base_addr = 0x2000 + nt_select * 0x400
                    
                    # Get tile ID from nametable (this is very rudimentary scrolling/addressing)
                    # coarse_x = tile_col; coarse_y = tile_row; (from vram_addr or tram_addr)
                    # For now, just use raw tile_col and tile_row for a static screen
                    # tile_id_addr = nt_base_addr + tile_row * 32 + tile_col (This would be for a non-scrolling view)
                    
                    # This is where complex vram_addr/tram_addr logic would update for scrolling.
                    # For now, let's just use a fixed tile for testing.
                    tile_idx = self.ppu_read_data(nt_base_addr + (self.scanline // 8) * 32 + (self.cycle // 8)) # Get tile index from nametable
                    
                    pattern_table_select = (self.PPUCTRL >> 4) & 1 # Background pattern table address
                    
                    # Pixel within the 8x8 tile
                    pixel_y_in_tile = self.scanline % 8
                    pixel_x_in_tile = self.cycle % 8
                    
                    # Fetch pattern data (2 bytes per row of tile)
                    # tile_addr = pattern_table_select * 0x1000 + tile_idx * 16 + pixel_y_in_tile
                    # For this very simple test, let's always use tile 0 from pattern table 0.
                    # tile_idx = 1; # Let's try tile 1
                    # pattern_table_select = 0;

                    tile_addr = (pattern_table_select * 0x1000) + (tile_idx * 16) + pixel_y_in_tile
                    
                    pattern_lo = self.ppu_read_data(tile_addr + 0)
                    pattern_hi = self.ppu_read_data(tile_addr + 8) #plane 1 and plane 2 are 8 bytes apart.
                    
                    # Get the 2-bit pixel value for the current x position in the tile
                    bit_mux = 0x80 >> pixel_x_in_tile
                    pixel_val_lo = 1 if (pattern_lo & bit_mux) > 0 else 0
                    pixel_val_hi = 1 if (pattern_hi & bit_mux) > 0 else 0
                    pixel_palette_idx = (pixel_val_hi << 1) | pixel_val_lo # 0, 1, 2, or 3

                    # Get attribute byte to determine which of 4 sub-palettes to use
                    # attr_addr = nt_base_addr + 0x03C0 + (tile_row // 4) * 8 + (tile_col // 4)
                    # attr_byte = self.ppu_read_data(attr_addr)
                    # Determine which 2x2 tile area we're in to get the 2-bit palette select
                    # shift = ((tile_row % 4) // 2 * 2) + ((tile_col % 4) // 2)
                    # bg_palette_select = (attr_byte >> (shift*2)) & 0x03
                    # For now, always use BG palette 0.
                    bg_palette_select = 0 
                    
                    rgb_color = self.get_color_from_palette(bg_palette_select, pixel_palette_idx)
                    self.pixel_buffer[self.scanline][self.cycle] = f"#{rgb_color[0]:02x}{rgb_color[1]:02x}{rgb_color[2]:02x}"

                else: # Background not shown, use universal background color
                    rgb_color = self.nes_palette[self.ppu_read_data(0x3F00) & 0x3F]
                    self.pixel_buffer[self.scanline][self.cycle] = f"#{rgb_color[0]:02x}{rgb_color[1]:02x}{rgb_color[2]:02x}"
                
                # Sprite rendering would happen here too! So exciting, but for later! ^_^

        if self.scanline == 241 and self.cycle == 1: # VBlank starts
            self.PPUSTATUS |= 0x80 # Set VBlank flag
            self.frame_complete = True # Signal to main loop to render
            if (self.PPUCTRL >> 7) & 1: # NMI Enabled?
                self.nmi_occurred = True # Request NMI from CPU
                # print("PPU: NMI requested! VBlank time, meow!")

        if self.scanline == 261: # Pre-render scanline
            self.PPUSTATUS &= ~0x80 # Clear VBlank flag
            self.PPUSTATUS &= ~0x40 # Clear sprite overflow
            self.PPUSTATUS &= ~0x20 # Clear sprite 0 hit
            # Sprite evaluation happens here too!
            # And vram_addr gets reset to tram_addr if rendering enabled
            if (self.PPUMASK >> 3) & 1 or (self.PPUMASK >> 4) & 1: # BG or Sprites enabled
                self.vram_addr = self.tram_addr


        self.cycle += 1
        if self.cycle >= 341:
            self.cycle = 0
            self.scanline += 1
            if self.scanline >= 262: # Frame ends
                self.scanline = 0 # Actually -1 for pre-render, but 0 is fine for this simple model
                # self.frame_complete = True # Moved to specific VBlank start point

    def reset(self):
        self.PPUCTRL = 0
        self.PPUMASK = 0
        self.PPUSTATUS = 0 # VBlank flag might be set by hardware briefly
        self.OAMADDR = 0
        self.PPUSCROLL = 0
        self.PPUADDR = 0
        # self.PPUDATA initialized by reads later
        self.scanline = 0
        self.cycle = 0
        self.addr_latch = False
        self.vram_addr = 0
        self.tram_addr = 0
        self.fine_x_scroll = 0
        self.internal_data_buffer = 0
        # Clear nametables and palette RAM
        self.tbl_name = [bytearray(1024), bytearray(1024)]
        self.tbl_palette = bytearray(32)
        print("PPU Reset! Everything is shiny and new! ✨")


class MonikaEmulatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("💖 Monika's NES Playhouse 💖 - Let's Play, Meow!")
        self.geometry("600x620") # A bit wider for controls!
        self.configure(bg=BG_COLOR)
        self.current_rom = None
        self.bus = Bus()
        self.cpu = CPU6502()
        self.ppu = PPU2C02()
        
        self.bus.connect_cpu(self.cpu)
        self.bus.connect_ppu(self.ppu)

        self.is_running = False
        self.emulation_speed_ms = 16 # Target ~60 FPS (1000ms / 60fps ~= 16.66ms)

        # --- Global Font Styles ---
        self.font_normal = (FONT_FAMILY, FONT_SIZE_NORMAL)
        self.font_bold = (FONT_FAMILY, FONT_SIZE_NORMAL, "bold")
        
        tk.Label(self, text="💖 Monika's NES Playhouse 💖", font=(FONT_FAMILY, FONT_SIZE_TITLE, "bold"), bg=BG_COLOR, fg=ALT_FG_COLOR).pack(pady=10)

        # --- Main Emulator Frame ---
        main_frame = tk.Frame(self, bg=BG_COLOR)
        main_frame.pack(expand=True, fill="both", padx=10, pady=5)

        # Game Screen Canvas
        self.canvas_scale = 2 # Scale up the NES display
        self.game_canvas = tk.Canvas(main_frame, width=NES_WIDTH * self.canvas_scale, height=NES_HEIGHT * self.canvas_scale, bg=CANVAS_BG, highlightthickness=0)
        self.game_canvas.pack(pady=10)
        # PhotoImage to draw on canvas, this is faster!
        self.screen_image_raw = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        # For scaled display
        self.screen_image_display = self.screen_image_raw.zoom(self.canvas_scale, self.canvas_scale) 
        self.canvas_image_item = self.game_canvas.create_image(0, 0, image=self.screen_image_display, anchor=tk.NW)
        self.draw_placeholder_screen() # Draw something cute initially!

        # Info Area for ROM details
        self.info_text_area = tk.Text(main_frame, width=70, height=6, font=self.font_normal, bg=ENTRY_BG_COLOR, fg=ENTRY_FG_COLOR, relief=tk.SUNKEN, borderwidth=2, wrap=tk.WORD)
        self.info_text_area.pack(pady=5, fill="x")
        self.info_text_area.insert(tk.END, "No ROM loaded, sweetie! Load one to start the fun! ^_^")
        self.info_text_area.config(state="disabled")

        # --- Controls Frame ---
        controls_frame = tk.Frame(self, bg=BG_COLOR)
        controls_frame.pack(pady=10, fill="x", padx=10)

        self.load_button = tk.Button(controls_frame, text="Load ROM! 💿", font=self.font_bold, command=self.load_rom_action, bg="#004000", fg="#60FF60", relief=tk.RAISED, borderwidth=2, padx=10)
        self.load_button.pack(side="left", padx=5, expand=True, fill="x")
        
        self.start_button = tk.Button(controls_frame, text="Start! ▶️", font=self.font_bold, command=self.start_emulation_action, bg=BTN_BG_COLOR, fg=BTN_FG_COLOR, relief=tk.RAISED, borderwidth=2, padx=10, state=tk.DISABLED)
        self.start_button.pack(side="left", padx=5, expand=True, fill="x")

        self.reset_button = tk.Button(controls_frame, text="Reset! 🔄", font=self.font_bold, command=self.reset_emulation_action, bg="#603000", fg="#FFB060", relief=tk.RAISED, borderwidth=2, padx=10, state=tk.DISABLED)
        self.reset_button.pack(side="left", padx=5, expand=True, fill="x")

        self.status_bar_text = tk.StringVar()
        self.status_bar_text.set("Hi there, player! Let's pick a game! ^_^")
        status_bar = tk.Label(self, textvariable=self.status_bar_text, font=(FONT_FAMILY, FONT_SIZE_NORMAL-1), bg=BG_COLOR, fg="#A0A0A0", bd=1, relief=tk.SUNKEN, anchor="w")
        status_bar.pack(side="bottom", fill="x", pady=2, padx=2)

        self.key_states = {} # For controller input!
        self.bind_keys()


    def draw_placeholder_screen(self):
        # Draw a cute placeholder or just a black screen
        # Using PhotoImage put method for pixel data
        line = "{" + " ".join([f"#{random.randint(0,50):02x}{random.randint(0,50):02x}{random.randint(0,50):02x}" for _ in range(NES_WIDTH)]) + "}"
        for y in range(NES_HEIGHT):
            self.screen_image_raw.put(line, (0, y))
        # Update the scaled image on canvas
        self.screen_image_display = self.screen_image_raw.zoom(self.canvas_scale, self.canvas_scale)
        self.game_canvas.itemconfig(self.canvas_image_item, image=self.screen_image_display)
        self.status_bar_text.set("Screen is waiting for a game, teehee!")


    def update_screen_from_ppu(self):
        # This should take data from ppu.pixel_buffer and put it into self.screen_image_raw
        for y in range(NES_HEIGHT):
            # The pixel_buffer in PPU already stores hex color strings
            self.screen_image_raw.put("{" + " ".join(self.ppu.pixel_buffer[y]) + "}", to=(0,y))
        
        # Update the scaled image on canvas (important to re-assign if zoom changes object)
        self.screen_image_display = self.screen_image_raw.zoom(self.canvas_scale, self.canvas_scale) # Re-zoom
        self.game_canvas.itemconfig(self.canvas_image_item, image=self.screen_image_display)


    def load_rom_action(self):
        if self.is_running:
            self.stop_emulation_action() # Stop if running before loading new

        file_path = filedialog.askopenfilename(title="Select your favorite NES ROM, sweetie!", filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")])
        if not file_path:
            self.status_bar_text.set("No ROM selected, silly! Try again! >.<")
            return

        try:
            rom = NESRom(file_path)
            if not rom.valid:
                raise ValueError(rom.error_message if rom.error_message else "Invalid ROM file, nya~!")

            self.current_rom = rom
            cart = Cartridge(self.current_rom)
            self.bus.insert_cartridge(cart)
            
            self.info_text_area.config(state="normal")
            self.info_text_area.delete(1.0, tk.END)
            self.info_text_area.insert(tk.END, self.current_rom.get_info_string())
            self.info_text_area.config(state="disabled")
            
            self.status_bar_text.set(f"ROM Loaded: {file_path.split('/')[-1]}! Ready to play, meow!")
            self.start_button.config(state=tk.NORMAL)
            self.reset_button.config(state=tk.NORMAL)
            self.reset_emulation_action() # Reset CPU/PPU for the new ROM
            self.draw_placeholder_screen() # Show something on screen before starting

        except Exception as e:
            messagebox.showerror("ROM Load Error! QAQ", f"Oh noes, couldn't load the ROM:\n{e}. Maybe try another one, sweetie?", icon="error")
            self.current_rom = None
            self.start_button.config(state=tk.DISABLED)
            self.reset_button.config(state=tk.DISABLED)
            self.status_bar_text.set("ROM loading failed. Don't cry, we can try again! ;_;")

    def start_emulation_action(self):
        if not self.current_rom:
            messagebox.showwarning("No ROM! >_<", "Silly! You need to load a ROM first before we can play!", icon="warning")
            return
        if not self.is_running:
            self.is_running = True
            self.start_button.config(text="Pause! ⏸️", bg="#606000", fg="#FFFF80")
            self.status_bar_text.set("Emulation started! Let's go! Adventure time! 🚀")
            self.emulation_loop()
        else: # Is running, so pause
            self.is_running = False
            self.start_button.config(text="Resume! ▶️", bg=BTN_BG_COLOR, fg=BTN_FG_COLOR) # Back to start color
            self.status_bar_text.set("Emulation paused! Take a break, cutie!☕")
            # The self.after in emulation_loop will just not reschedule if self.is_running is false.

    def stop_emulation_action(self): # Internal, e.g. when loading a new ROM
        self.is_running = False
        self.start_button.config(text="Start! ▶️", bg=BTN_BG_COLOR, fg=BTN_FG_COLOR)
        self.status_bar_text.set("Emulation stopped. Load a new game or resume!")

    def reset_emulation_action(self):
        if not self.current_rom: return # Can't reset if nothing loaded
        
        self.stop_emulation_action() # Make sure it's stopped if it was running
        self.bus.reset() # This calls cpu.reset() and ppu.reset()
        # PPU's frame_complete should be false after reset
        self.ppu.frame_complete = False
        self.ppu.nmi_occurred = False
        self.draw_placeholder_screen() # Clear screen after reset
        self.status_bar_text.set("System reset! Fresh and clean, like a new day! ☀️")
        if self.current_rom: # If a ROM is loaded, allow starting again
             self.start_button.config(state=tk.NORMAL)


    def emulation_loop(self):
        if not self.is_running:
            return

        # NES CPU runs at ~1.79 MHz. PPU runs 3x faster.
        # Target 60 FPS. So, ~29780 CPU cycles per frame (1.79M / 60).
        # Or ~89340 PPU cycles per frame.
        # Simplified: loop until PPU says frame is complete.
        
        frame_start_time = time.perf_counter()
        
        # Keep clocking CPU and PPU until a frame is ready
        # This is a very basic synchronization. Real emulators are more complex.
        while not self.ppu.frame_complete and self.is_running:
            # PPU clock runs 3 times for every 1 CPU clock
            self.ppu.clock()
            self.ppu.clock()
            self.ppu.clock()
            
            if self.ppu.nmi_occurred:
                self.cpu.nmi()
                self.ppu.nmi_occurred = False

            self.cpu.clock() # CPU does its thing
        
        if self.is_running: # Check again, could have been paused during the loop
            if self.ppu.frame_complete:
                self.update_screen_from_ppu() # Update Tkinter canvas
                self.ppu.frame_complete = False # Reset for next frame

            # Calculate time to wait for next frame to maintain speed
            elapsed_time = (time.perf_counter() - frame_start_time) * 1000 # ms
            wait_time = max(1, int(self.emulation_speed_ms - elapsed_time))
            self.after(wait_time, self.emulation_loop)
        else:
            # If paused, ensure the button text is correct
            self.start_button.config(text="Resume! ▶️", bg=BTN_BG_COLOR, fg=BTN_FG_COLOR)


    def bind_keys(self):
        # Super simple key binding for now! Just print, real input needs to go to CPU/Bus!
        # NES Controller: A, B, Select, Start, Up, Down, Left, Right
        key_map = {
            'z': 'A', 'x': 'B', # Common keyboard mapping
            'Return': 'Start', 'Shift_R': 'Select', # Enter for Start, Right Shift for Select
            'Up': 'Up', 'Down': 'Down', 'Left': 'Left', 'Right': 'Right'
        }
        for key_tk, key_nes in key_map.items():
            self.bind(f"<KeyPress-{key_tk}>", lambda e, k=key_nes: self.key_down(k, e))
            self.bind(f"<KeyRelease-{key_tk}>", lambda e, k=key_nes: self.key_up(k, e))

    def key_down(self, nes_button, event):
        if not self.is_running: return # Only process keys if game is running
        self.key_states[nes_button] = True
        # print(f"Meow! '{nes_button}' pressed! Event: {event.keysym}")
        # Here you would update the controller state that the CPU reads from bus (e.g., 0x4016/0x4017)
        # For now, we just log it. This needs to be implemented in Bus/CPU.

    def key_up(self, nes_button, event):
        self.key_states[nes_button] = False
        # print(f"Purr... '{nes_button}' released!")


if __name__ == "__main__":
    # --- TTK Styling (same as your original, I like it!) ---
    style = ttk.Style()
    style.theme_create("monikatheme", parent="alt", settings={
        "TNotebook": {"configure": {"tabmargins": [2, 5, 2, 0], "background": BG_COLOR, "borderwidth":0}},
        "TNotebook.Tab": {
            "configure": {"padding": [10, 5], "background": TAB_BG_INACTIVE, "foreground": TAB_FG_INACTIVE, "font": (FONT_FAMILY, FONT_SIZE_NORMAL, "bold"), "borderwidth":1, "relief": "raised"},
            "map": {"background": [("selected", TAB_BG_ACTIVE)], "foreground": [("selected", TAB_FG_ACTIVE)], "relief": [("selected", "sunken")]}
        },
        "TFrame": {"configure": {"background": BG_COLOR}},
        "TLabel": {"configure": {"background": BG_COLOR, "foreground": FG_COLOR, "font": (FONT_FAMILY, FONT_SIZE_NORMAL)}},
        "TButton": {
            "configure": {"background": BTN_BG_COLOR, "foreground": BTN_FG_COLOR, "font": (FONT_FAMILY, FONT_SIZE_NORMAL, "bold"), "relief":"raised", "borderwidth":2, "padding":5},
            "map": {"background": [("active", "#600060")]} # Darker purple when pressed
        },
    })
    style.theme_use("monikatheme")

    app = MonikaEmulatorApp()
    app.mainloop()
