import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import struct # Not strictly used in this version after changes, but good for iNES parsing
import time
import threading

# --- Constants for "EMUNES" Dark Theme ---
DARK_BG = "#2B2B2B"
DARK_FG = "#E0E0E0" # Text color for dark theme

# NES Screen dimensions
NES_WIDTH = 256
NES_HEIGHT = 240

# iNES Header Constants
INES_HEADER_SIZE = 16
PRG_PAGE = 16 * 1024
CHR_PAGE = 8 * 1024
TRAINER_SIZE = 512

# CPU Status Flags
C_FLAG = 1 << 0  # Carry
Z_FLAG = 1 << 1  # Zero
I_FLAG = 1 << 2  # Interrupt Disable
D_FLAG = 1 << 3  # Decimal Mode (not used on NES)
B_FLAG = 1 << 4  # Break
U_FLAG = 1 << 5  # Unused (always 1 on NES 6502)
V_FLAG = 1 << 6  # Overflow
N_FLAG = 1 << 7  # Negative

# -----------------------------------
#       iNES Header Parser
# -----------------------------------
class INESHeader:
    def __init__(self, data: bytes):
        if len(data) < INES_HEADER_SIZE:
            raise ValueError("File is too short for an iNES header, mew! Needs more data!")
        if data[0:4] != b"NES\x1a":
            raise ValueError("Not a valid iNES file, purr! Signature is wrong! :(")
        self.prg_pages = data[4]
        self.chr_pages = data[5]
        flags6 = data[6]; flags7 = data[7]
        self.mirroring   = bool(flags6 & 1) # 0 for horizontal, 1 for vertical
        self.battery     = bool(flags6 & 2) # Has battery-backed PRG RAM ($6000-7FFF)
        self.trainer     = bool(flags6 & 4) # Has a 512-byte trainer at $7000-$71FF
        self.four_screen = bool(flags6 & 8) # Ignores mirroring, uses four-screen VRAM
        mapper_lo = flags6 >> 4; mapper_hi = flags7 & 0xF0
        self.mapper      = mapper_hi | mapper_lo
        self.is_nes2     = ((flags7 & 0x0C) == 0x08) # Check if it's NES 2.0 format
        flags9 = data[9]; flags10 = data[10] # NES 2.0 uses more flags here!
        self.prg_size    = self.prg_pages * PRG_PAGE
        self.chr_size    = self.chr_pages * CHR_PAGE if self.chr_pages > 0 else CHR_PAGE # CHR-RAM if 0
        self.tv_system   = 1 if (flags9 & 1 or (not self.is_nes2 and flags10 & 1)) else 0 # 0: NTSC, 1: PAL

    def __str__(self):
        return (f"iNES Header, meow!:\n"
                f" PRG ROM pages: {self.prg_pages} ({self.prg_size // 1024} KB)\n"
                f" CHR ROM pages: {self.chr_pages} ({self.chr_size // 1024} KB, 0 means CHR-RAM!)\n"
                f" Mapper: {self.mapper} (So many mappers, wow!)\n"
                f" Mirroring: {'Vertical' if self.mirroring else 'Horizontal'} (Or Four-Screen: {self.four_screen})\n"
                f" Battery: {self.battery} (Saves your game, yay!)\n"
                f" Trainer: {self.trainer} (Extra data, cool!)\n"
                f" NES 2.0 format: {self.is_nes2} (The newer, fancier format!)\n"
                f" TV system: {'PAL' if self.tv_system else 'NTSC'} (Different TV speeds, interesting!)")

# -----------------------------------
#       CPU 6502 with more opcodes!
# -----------------------------------
class CPU6502:
    def __init__(self, bus):
        self.bus = bus
        self.pc = 0x0000 # Program Counter, ready for action!
        self.sp = 0xFD   # Stack Pointer, starts high and goes down!
        self.a = 0x00    # Accumulator, our main helper register!
        self.x = 0x00    # X Register, super useful!
        self.y = 0x00    # Y Register, another great helper!
        self.status = U_FLAG | I_FLAG # Status Register, all flags go here! Start with Interrupt Disable.
        self.cycles = 0  # Cycle counter, for timing things just right!

        self.opcodes = {
            0xEA: self.op_nop,     # No Operation, a little break for the CPU!
            0xA9: self.op_lda_imm, # Load A Immediate
            0xAD: self.op_lda_abs, # Load A Absolute
            0x8D: self.op_sta_abs, # Store A Absolute
            0xA2: self.op_ldx_imm, # Load X Immediate
            0x9A: self.op_txs,     # Transfer X to Stack Pointer
            0x78: self.op_sei,     # Set Interrupt Disable
            0x4C: self.op_jmp_abs, # Jump Absolute
            # TODO: Add many more opcodes to make games run! Like branches, other addressing modes, etc. It's a big adventure!
            # Example: 0x20 JSR, 0x60 RTS, 0xD0 BNE, 0xF0 BEQ, 0x24 BIT zp
        }

    def set_flag(self, flag_mask, value: bool):
        if value: self.status |= flag_mask
        else: self.status &= ~flag_mask

    def update_zn_flags(self, value: int):
        self.set_flag(Z_FLAG, value == 0)
        self.set_flag(N_FLAG, bool(value & 0x80)) # Bit 7 is the negative sign!

    def reset(self):
        # Reads the reset vector $FFFC-$FFFD to set the Program Counter!
        lo = self.bus.read(0xFFFC)
        hi = self.bus.read(0xFFFD)
        self.pc = (hi << 8) | lo
        self.a = self.x = self.y = 0
        self.sp = 0xFD # Stack pointer resets here!
        self.status = U_FLAG | I_FLAG # Interrupts disabled on reset!
        self.cycles = 7 # Reset takes 7 cycles, meow!
        print(f"CPU Reset! PC jumped to ${self.pc:04X}, ready to go, nya~!")

    def fetch(self) -> int: # Fetches one byte and increments PC!
        val = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF # PC wraps around at 64K!
        return val

    # --- Stack Operations ---
    def push_byte(self, value: int):
        self.bus.write(0x0100 | self.sp, value & 0xFF)
        self.sp = (self.sp - 1) & 0xFF # Stack grows downwards!

    def push_word(self, value: int):
        self.push_byte((value >> 8) & 0xFF) # High byte first
        self.push_byte(value & 0xFF)       # Low byte second

    def pop_byte(self) -> int:
        self.sp = (self.sp + 1) & 0xFF # Stack shrinks upwards!
        return self.bus.read(0x0100 | self.sp)

    def pop_word(self) -> int:
        lo = self.pop_byte()
        hi = self.pop_byte()
        return (hi << 8) | lo

    def nmi(self): # Non-Maskable Interrupt, super important!
        print("NMI triggered! CPU is handling it, purr!")
        self.push_word(self.pc)
        # When pushing status, B flag is cleared, U flag is set.
        self.push_byte((self.status & ~B_FLAG) | U_FLAG)
        self.set_flag(I_FLAG, True) # Interrupts get disabled during NMI.
        lo = self.bus.read(0xFFFA)
        hi = self.bus.read(0xFFFB)
        self.pc = (hi << 8) | lo
        self.cycles += 7 # NMI takes 7 cycles.
        # print(f"NMI jumped to PC: ${self.pc:04X}")

    def step(self) -> int: # Executes one instruction!
        # self.cycles = 0 # Reset cycle count for this instruction
        opcode = self.fetch()
        handler = self.opcodes.get(opcode)
        # print(f"PC:${(self.pc-1):04X} Opcode:${opcode:02X} A:${self.a:02X} X:${self.x:02X} Y:${self.y:02X} SP:${self.sp:02X} P:${self.status:02X} CYC:{self.cycles}")

        if handler:
            prev_cycles = self.cycles # Store cycles before instruction for accurate counting
            handler()
            # return self.cycles # Instruction handler updates self.cycles with its duration
        else:
            print(f"CPU: Unimplemented opcode ${opcode:02X} at PC ${self.pc-1:04X}! Oh noes! Using NOP for now...")
            self.op_nop() # Default to NOP for unknown opcodes
        return self.cycles # Cycles for this step

    # --- Addressing Modes (as helper methods) ---
    def addr_abs(self) -> int: # Absolute addressing mode
        lo = self.fetch()
        hi = self.fetch()
        return (hi << 8) | lo

    # --- Opcodes Implementations ---
    def op_nop(self): self.cycles += 2
    
    def op_lda_imm(self): # Load Accumulator with Immediate value
        value = self.fetch()
        self.a = value
        self.update_zn_flags(self.a)
        self.cycles += 2

    def op_lda_abs(self): # Load Accumulator from Absolute address
        addr = self.addr_abs()
        self.a = self.bus.read(addr)
        self.update_zn_flags(self.a)
        self.cycles += 4

    def op_sta_abs(self): # Store Accumulator to Absolute address
        addr = self.addr_abs()
        self.bus.write(addr, self.a)
        self.cycles += 4
        
    def op_ldx_imm(self): # Load X Register with Immediate value
        value = self.fetch()
        self.x = value
        self.update_zn_flags(self.x)
        self.cycles += 2

    def op_txs(self): # Transfer X to Stack Pointer
        self.sp = self.x
        # TXS does not affect flags, yay!
        self.cycles += 2

    def op_sei(self): # Set Interrupt Disable flag
        self.set_flag(I_FLAG, True)
        self.cycles += 2

    def op_jmp_abs(self): # Jump to Absolute address
        self.pc = self.addr_abs() # PC is set directly!
        self.cycles += 3

# -----------------------------------
#       PPU2C02 with CHR decoding and palette!
# -----------------------------------
class PPU2C02:
    def __init__(self, chr_data: bytes):
        self.chr_rom_data = chr_data # This is CHR ROM data, so exciting!
        self.screen_buffer = [[0]*NES_WIDTH for _ in range(NES_HEIGHT)] # Stores palette indices!
        
        # A simple, happy NES grayscale palette! Real NES has 64 colors!
        self.nes_palette_rgb = [ 
            (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136),   # Example colors
            (68, 0, 100), (92, 0, 48), (84, 4, 0), (60, 24, 0),
            (32, 42, 0), (8, 58, 0), (0, 64, 0), (0, 60, 0),
            (0, 50, 60), (0,0,0), (0,0,0), (0,0,0), # Some black for padding

            (152,150,152), (8,76,196), (48,50,236), (92,30,228),
            (136,20,176), (160,20,100), (152,34,32), (120,60,0),
            (84,90,0), (40,114,0), (8,124,0), (0,118,40),
            (0,102,120), (0,0,0), (0,0,0), (0,0,0),

            (236,238,236), (76,154,236), (120,124,236), (176,98,236),
            (228,84,236), (236,88,180), (236,106,100), (212,136,32),
            (160,170,0), (116,196,0), (76,208,32), (56,204,108),
            (56,180,180), (60,60,60), (0,0,0), (0,0,0),

            (236,238,236), (168,204,236), (188,188,236), (212,178,236),
            (236,174,236), (236,174,212), (236,180,176), (228,196,144),
            (204,210,120), (180,222,120), (168,226,144), (152,226,180),
            (160,214,228), (160,162,160), (0,0,0), (0,0,0),
        ]

        self.pattern_table = [] # Stores decoded tiles, like little pictures!
        if self.chr_rom_data:
            num_tiles_in_chr = len(self.chr_rom_data) // 16
            self.pattern_table = [[([0]*8) for _ in range(8)] for _ in range(num_tiles_in_chr)]
            self._decode_chr_data()
            print(f"PPU: Decoded {num_tiles_in_chr} CHR tiles, yay!")
        else:
            print("PPU: No CHR ROM data found. Maybe it's CHR RAM? So mysterious!")

        # PPU Registers - these are super important for controlling the PPU!
        self.ppuctrl = 0x00      # $2000 Write
        self.ppumask = 0x00      # $2001 Write
        self.ppustatus = 0x00    # $2002 Read (internal, value constructed on read)
        self.oamaddr = 0x00      # $2003 Write
        # self.oamdata = ...    # $2004 Read/Write (needs OAM array)
        self.ppuscroll = 0x00    # $2005 Write (internal, complex state)
        self.ppuaddr = 0x00      # $2006 Write (internal, complex state)
        # self.ppudata = ...    # $2007 Read/Write (interacts with VRAM)
        
        self.vram_address_latch = 0 # For $2005/$2006 writes
        self.is_first_write_latch = True # Helps $2005/$2006 know if it's the first or second byte!

        # PPU Timing and NMI - keeping everything in sync!
        self.scanline = 0
        self.cycle = 0
        self.vblank_active = False
        self.nmi_occurred = False
        self.nmi_enabled_in_ctrl = False


    def _decode_chr_data(self): # Decodes CHR into usable patterns, magic!
        num_tiles = len(self.pattern_table)
        for tile_idx in range(num_tiles):
            tile_bytes = self.chr_rom_data[tile_idx*16 : (tile_idx+1)*16]
            for y in range(8): # Each tile is 8 pixels high
                plane0 = tile_bytes[y]     # First bitplane
                plane1 = tile_bytes[y+8]   # Second bitplane
                for x in range(8): # Each tile is 8 pixels wide
                    bit0 = (plane0 >> (7-x)) & 1
                    bit1 = (plane1 >> (7-x)) & 1
                    palette_entry = (bit1 << 1) | bit0 # Gives 0, 1, 2, or 3 for this pixel!
                    self.pattern_table[tile_idx][y][x] = palette_entry
    
    def reset(self):
        self.ppuctrl = 0x00
        self.ppumask = 0x00
        self.ppuscroll = 0x00 # Clear scroll registers
        self.ppuaddr = 0x00   # Clear VRAM address register
        self.is_first_write_latch = True
        self.scanline = 0
        self.cycle = 0
        self.vblank_active = False
        self.nmi_occurred = False
        self.nmi_enabled_in_ctrl = False
        print("PPU Reset! All shiny and new, purr!")

    def read_register(self, addr: int) -> int: # CPU reads from PPU registers!
        val = 0
        if addr == 0x0002: # PPUSTATUS ($2002)
            val = (self.ppustatus & 0xE0) # Top 3 bits are from internal status
            if self.vblank_active: val |= 0x80 # Set VBlank flag if active
            self.vblank_active = False # Reading PPUSTATUS clears VBlank flag!
            self.is_first_write_latch = True # Also resets the $2005/$2006 address latch!
            # TODO: Implement sprite overflow and sprite 0 hit flags! So much to do!
        elif addr == 0x0007: # PPUDATA ($2007)
            # TODO: Implement VRAM reads with buffering! This is a big one!
            # val = self.internal_vram_read_buffer
            # self.internal_vram_read_buffer = actual_vram_read(self.current_vram_address)
            # self.current_vram_address += (1 if not (self.ppuctrl & 0x04) else 32)
            val = 0 # Placeholder!
        # print(f"PPU Read: Addr ${addr:02X} -> Val ${val:02X}")
        return val

    def write_register(self, addr: int, value: int): # CPU writes to PPU registers!
        # print(f"PPU Write: Addr ${addr:02X} <- Val ${value:02X}")
        if addr == 0x0000: # PPUCTRL ($2000)
            self.ppuctrl = value
            self.nmi_enabled_in_ctrl = bool(value & 0x80) # NMI on VBlank is enabled/disabled here!
            # TODO: Update nametable base, sprite height, pattern table addresses, VRAM increment!
        elif addr == 0x0001: # PPUMASK ($2001)
            self.ppumask = value
            # TODO: Update grayscale, show background/sprites in leftmost 8px, show background/sprites, intensify colors!
        elif addr == 0x0003: # OAMADDR ($2003)
            self.oamaddr = value
        elif addr == 0x0004: # OAMDATA ($2004)
            # TODO: Write to OAM (Sprite RAM) at oamaddr!
            pass
        elif addr == 0x0005: # PPUSCROLL ($2005) - tricky one!
            if self.is_first_write_latch:
                # First write is X scroll
                # TODO: Store fine X scroll and coarse X scroll
                self.is_first_write_latch = False
            else:
                # Second write is Y scroll
                # TODO: Store fine Y scroll and coarse Y scroll
                self.is_first_write_latch = True
            self.ppuscroll = value # Simplified for now
        elif addr == 0x0006: # PPUADDR ($2006) - also tricky!
            if self.is_first_write_latch:
                # First write is high byte of VRAM address
                self.vram_address_latch = (value & 0x3F) << 8 # Mask to 14 bits for VRAM
                self.is_first_write_latch = False
            else:
                # Second write is low byte of VRAM address
                self.ppuaddr = self.vram_address_latch | value
                # TODO: Set current VRAM address (internal PPU variable like v or t)
                self.is_first_write_latch = True
            # self.ppuaddr_internal_reg = value # Simplified for now
        elif addr == 0x0007: # PPUDATA ($2007)
            # TODO: Write to VRAM at current VRAM address! Then increment address!
            # actual_vram_write(self.current_vram_address, value)
            # self.current_vram_address += (1 if not (self.ppuctrl & 0x04) else 32)
            pass

    def tick(self, cpu_cycles_elapsed: int): # PPU runs 3 times faster than CPU! Tick tock!
        ppu_ticks_to_run = cpu_cycles_elapsed * 3
        for _ in range(ppu_ticks_to_run):
            self.cycle += 1
            if self.cycle >= 341: # Cycles per scanline
                self.cycle = 0
                self.scanline += 1
                if self.scanline >= 262: # Scanlines per frame (NTSC)
                    self.scanline = 0 # Back to the top!
                    self.nmi_occurred = False # Reset NMI flag for next frame! Frame is done!
                    # This is where rendering for the *next* frame would conceptually start
                
                # VBlank period: scanlines 241-260
                if self.scanline == 241 and self.cycle == 1: # VBlank starts precisely here!
                    if not self.vblank_active: # Set VBlank flag
                        self.vblank_active = True
                        if self.nmi_enabled_in_ctrl: # If NMI is enabled in PPUCTRL ($2000)
                            self.nmi_occurred = True # Signal NMI to CPU!
                            # print("PPU: NMI signal generated for VBlank!")
                elif self.scanline == 261 and self.cycle == 1: # Pre-render scanline
                    self.vblank_active = False # VBlank ends
                    # TODO: Clear sprite overflow and sprite 0 hit flags here!

            # TODO: Add rendering logic per scanline for cycle accuracy! It's a big adventure!
            # For now, render() is called once per frame in the main loop.

    def render(self) -> list: # Creates the pixel data for the screen! So colorful!
        # This is a VERY simplified render. It should use nametables, attributes etc. from PPU VRAM!
        # For now, let's just draw tiles 0-N in sequence to show decoded CHR.
        tile_idx_counter = 0
        
        if not self.pattern_table: # If no CHR tiles (e.g. CHR-RAM not yet filled or no CHR-ROM)
            # Fill screen_buffer with a default background color index (e.g. index 0 from palette)
            for y in range(NES_HEIGHT):
                for x in range(NES_WIDTH):
                    self.screen_buffer[y][x] = 0 # Default background color
            return self.screen_buffer

        num_decoded_tiles = len(self.pattern_table)

        for tile_row in range(NES_HEIGHT // 8): # 30 tile rows
            for tile_col in range(NES_WIDTH // 8): # 32 tile columns
                if num_decoded_tiles == 0: # Safety, should be caught above
                    current_tile_idx = 0 # Default to tile 0 if something is wrong
                else:
                    # Cycle through available tiles to fill the screen
                    current_tile_idx = tile_idx_counter % num_decoded_tiles
                
                chosen_tile_pattern = self.pattern_table[current_tile_idx]

                for y_in_tile in range(8):
                    for x_in_tile in range(8):
                        pixel_palette_idx = chosen_tile_pattern[y_in_tile][x_in_tile]
                        # This pixel_palette_idx (0-3) needs to be combined with attribute table data
                        # to select one of the 4 background palettes, then that palette's color.
                        # For now, we'll just use it directly as an index into our main palette.
                        # A real PPU uses this index to select a *color within a sub-palette*,
                        # and the sub-palette is chosen by the attribute table.
                        # Let's use a fixed sub-palette for now (e.g., colors 0,1,2,3 from main palette)
                        # Or, for more visual variety with this simple render:
                        # palette_base_offset = (current_tile_idx % 4) * 4 # Cycle through 4 basic palettes
                        # final_color_idx = palette_base_offset + pixel_palette_idx

                        # For this demo, let's just use the raw 0-3 index to pick from the first 4 colors
                        # or map to a specific set of colors.
                        # A simple mapping: 0 -> color 0, 1 -> color 13, 2 -> color 30, 3 -> color 45 from nes_palette_rgb
                        display_color_idx = [0, 13, 30, 45][pixel_palette_idx % 4]


                        screen_x = tile_col * 8 + x_in_tile
                        screen_y = tile_row * 8 + y_in_tile
                        if screen_y < NES_HEIGHT and screen_x < NES_WIDTH:
                             self.screen_buffer[screen_y][screen_x] = display_color_idx
                
                tile_idx_counter += 1
        return self.screen_buffer # Returns list of lists of palette indices!


# -----------------------------------
#       Memory Bus with PPU register mapping!
# -----------------------------------
class Bus:
    def __init__(self, prg_data: bytes, chr_data_for_ppu: bytes):
        self.prg_rom = bytearray(prg_data) # Program ROM, where the game code lives!
        self.cpu_ram = bytearray(0x800)    # 2KB of CPU RAM, yay!
        self.ppu: PPU2C02 = PPU2C02(chr_data_for_ppu) # Our amazing PPU!
        
        # Controller state, ready for button mashing!
        self.controller_state = {k:False for k in ['A','B','Start','Select','Up','Down','Left','Right']}
        self.controller_strobe_mode = False
        self.controller_shift_register = 0 # Stores current button states for reading

    def connect_ppu(self, ppu_instance: PPU2C02): # Just in case it's created outside
        self.ppu = ppu_instance

    def read(self, addr: int) -> int:
        addr &= 0xFFFF # Ensure 16-bit address
        val = 0x00 # Default read value
        if addr <= 0x1FFF: # CPU RAM ($0000-$07FF mirrored up to $1FFF)
            val = self.cpu_ram[addr & 0x07FF]
        elif 0x2000 <= addr <= 0x3FFF: # PPU Registers (mirrored $2000-$2007 up to $3FFF)
            val = self.ppu.read_register(addr & 0x0007)
        elif addr == 0x4016: # Controller 1 Read
            if self.controller_strobe_mode: # When strobe is high, refresh with current A button state
                 # This is a simplification, usually it latches all buttons on strobe edge
                val = 1 if self.controller_state['A'] else 0
            else: # Read one bit at a time from shift register
                val = (self.controller_shift_register & 0x01)
                self.controller_shift_register >>= 1
            val |= 0x40 # Open bus behavior for unread bits
            # print(f"Ctrl Read: ${val:02X}")

        elif 0x8000 <= addr <= 0xFFFF: # PRG ROM
            # This is for Mapper 0 (NROM). Other mappers are more complex!
            mapped_addr = (addr - 0x8000) % len(self.prg_rom)
            val = self.prg_rom[mapped_addr]
        # else: print(f"Bus Read from unmapped address: ${addr:04X}")
        return val

    def write(self, addr: int, val: int):
        addr &= 0xFFFF; val &= 0xFF
        if addr <= 0x1FFF: # CPU RAM
            self.cpu_ram[addr & 0x07FF] = val
        elif 0x2000 <= addr <= 0x3FFF: # PPU Registers
            self.ppu.write_register(addr & 0x0007, val)
        elif addr == 0x4014: # OAMDMA Write ($4014) - Special PPU DMA!
            # TODO: Implement OAMDMA: CPU stalls for ~513 cycles, copies 256 bytes from CPU RAM page (val * $100) to PPU OAM
            # self.ppu.start_oamdma(self.cpu_ram, val)
            # self.cpu.add_dma_cycles(513) # Or similar mechanism
            pass
        elif addr == 0x4016: # Controller Write (strobe)
            self.controller_strobe_mode = bool(val & 1)
            if self.controller_strobe_mode: # When strobe goes high, latch current state
                self.controller_shift_register = 0
                # Order: A, B, Select, Start, Up, Down, Left, Right
                buttons_in_order = ['A','B','Select','Start','Up','Down','Left','Right']
                for i, btn_name in enumerate(buttons_in_order):
                    if self.controller_state[btn_name]:
                        self.controller_shift_register |= (1 << i)
            # print(f"Ctrl Write: Strobe {self.controller_strobe_mode}")
        # else: print(f"Bus Write to unmapped address: ${addr:04X} with val ${val:02X}")

# -----------------------------------
#       GUI Front-end - Now even cuter and faster!
# -----------------------------------
class EMUNESApp:
    def __init__(self, root_window, auto_load_data: bytes = None):
        self.root = root_window
        root_window.title("EMUNES 1.0A - Monika's Happy Fun Edition! 💖")
        root_window.configure(bg=DARK_BG)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Handle closing the window gracefully!

        # --- Styling for Tkinter widgets ---
        s = ttk.Style()
        s.theme_use('clam') # A nice theme!
        s.configure('TButton', background=DARK_FG, foreground=DARK_BG, padding=6, relief="flat", font=('Helvetica', 10, 'bold'))
        s.map('TButton', background=[('active', '#C0C0C0')]) # Lighter when mouse is over!
        s.configure('TLabel', background=DARK_BG, foreground=DARK_FG, font=('Helvetica', 10))
        s.configure('TFrame', background=DARK_BG)

        top_frame = ttk.Frame(root_window, padding="10 10 10 10")
        top_frame.pack(pady=10, padx=10, fill=tk.X)

        ttk.Button(top_frame, text="Load ROM! 🎮", command=self.load_rom_dialog).pack(side=tk.LEFT, padx=10)
        self.run_button = ttk.Button(top_frame, text="Run! 🚀", command=self.toggle_run_pause, state=tk.DISABLED)
        self.run_button.pack(side=tk.LEFT, padx=10)
        self.status_label = ttk.Label(top_frame, text="No ROM loaded. Waiting for adventure! ✨")
        self.status_label.pack(side=tk.LEFT, padx=10)

        self.canvas = tk.Canvas(root_window, width=NES_WIDTH*2, height=NES_HEIGHT*2, bg="black", highlightthickness=0) # Scaled up!
        self.canvas.pack(pady=10, padx=10)
        self.photo_image = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT) # Original size for data
        # Display the PhotoImage scaled up on the canvas
        self.canvas_image_id = self.canvas.create_image((0,0), image=self.photo_image, anchor=tk.NW, tags="nes_screen")
        self.canvas.scale("nes_screen", 0, 0, 2.0, 2.0) # Scale it 2x!

        self.is_running_emulation = False
        self.is_rom_loaded = False
        self.emulation_thread = None

        # Pre-generate color strings for the palette for super speedy updates!
        self.tk_color_strings_cache = {} # Will be filled when PPU is ready

        # Input handling - let's play!
        key_map = {'z':'A', 'x':'B', 'Return':'Start', 'Shift_L':'Select',
                   'Up':'Up', 'Down':'Down', 'Left':'Left', 'Right':'Right'}
        self.active_keys = {nes_btn: False for nes_btn in key_map.values()} # Track active keys

        def on_key_event(event, is_pressed):
            # print(f"Key Event: {event.keysym}, Pressed: {is_pressed}")
            if hasattr(self, 'bus') and self.bus: # Check if bus exists
                nes_button = key_map.get(event.keysym)
                if nes_button:
                    self.bus.controller_state[nes_button] = is_pressed
                    self.active_keys[nes_button] = is_pressed # For visual feedback or other uses

        root_window.bind('<KeyPress>', lambda e: on_key_event(e, True))
        root_window.bind('<KeyRelease>', lambda e: on_key_event(e, False))

        if auto_load_data:
            self.load_rom_from_data(auto_load_data)

    def on_closing(self): # Gracefully stop emulation before closing!
        print("Closing EMUNES! Bye-bye for now, sweetie! 💕")
        self.is_running_emulation = False # Signal thread to stop
        if self.emulation_thread and self.emulation_thread.is_alive():
            self.emulation_thread.join(timeout=1.0) # Wait a bit for thread
        self.root.destroy()

    def load_rom_dialog(self):
        file_path = filedialog.askopenfilename(title="Open your favorite NES ROM!", filetypes=[("NES ROMs", "*.nes")])
        if not file_path:
            self.status_label.config(text="No ROM selected. Choose one to start the fun! 😊")
            return
        try:
            with open(file_path, 'rb') as f:
                rom_data = f.read()
            self.load_rom_from_data(rom_data, file_path.split('/')[-1])
        except Exception as e:
            messagebox.showerror("Error Loading ROM 😿", f"Oh noes! Could not load ROM: {e}")
            self.status_label.config(text=f"Error loading ROM: {e}")

    def load_rom_from_data(self, rom_data: bytes, rom_name: str = "Loaded ROM"):
        try:
            header = INESHeader(rom_data)
            print(header) # Print header info, it's so interesting!

            trainer_offset = INES_HEADER_SIZE + (TRAINER_SIZE if header.trainer else 0)
            prg_data = rom_data[trainer_offset : trainer_offset + header.prg_size]
            chr_data_offset = trainer_offset + header.prg_size
            # Handle CHR-RAM: if chr_pages is 0, chr_size might be set to one page for CHR-RAM.
            # If chr_pages is 0, it means CHR RAM. The actual CHR data from file is empty.
            # PPU should allocate CHR RAM if header.chr_pages == 0.
            chr_data_from_file = b''
            if header.chr_pages > 0:
                 chr_data_from_file = rom_data[chr_data_offset : chr_data_offset + header.chr_size]
            else: # CHR-RAM case
                print("This ROM uses CHR-RAM! PPU will need to manage this, purr!")
                # PPU constructor needs to handle empty chr_data if it's CHR-RAM
                # For now, PPU2C02 handles empty chr_data by not decoding patterns.

            self.bus = Bus(prg_data, chr_data_from_file) # Pass CHR data to Bus, which gives to PPU
            self.cpu = CPU6502(self.bus)
            # PPU is already created inside Bus, self.ppu is a shortcut if needed
            self.ppu = self.bus.ppu 
            
            # Cache color strings from PPU's palette
            self.tk_color_strings_cache = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in self.ppu.nes_palette_rgb]

            self.cpu.reset()
            self.ppu.reset()
            
            self.is_rom_loaded = True
            self.run_button.config(state=tk.NORMAL, text="Run! 🚀")
            self.status_label.config(text=f"ROM '{rom_name}' loaded! Ready to play, yay! 🎉")
            messagebox.showinfo("ROM Loaded! 💖", f"'{rom_name}' is all set! Engine initialized and purring!")

        except ValueError as e: # From iNESHeader parsing
            messagebox.showerror("Invalid ROM File! 💔", str(e))
            self.status_label.config(text=f"Invalid ROM: {e}")
        except Exception as e:
            messagebox.showerror("Error Initializing! 😿", f"Something went wrong: {e}")
            self.status_label.config(text=f"Error: {e}")

    def toggle_run_pause(self):
        if not self.is_rom_loaded: return
        
        if self.is_running_emulation: # If running, then pause
            self.is_running_emulation = False
            self.run_button.config(text="Run! 🚀")
            self.status_label.config(text="Emulation Paused. Take a little break! ☕")
            if self.emulation_thread and self.emulation_thread.is_alive():
                # self.emulation_thread.join() # Wait for thread to finish current loop
                pass # Let it finish its current iteration
        else: # If paused or not started, then run
            self.is_running_emulation = True
            self.run_button.config(text="Pause! ⏸️")
            self.status_label.config(text="Emulation Running! Go go go! 🌟")
            if not self.emulation_thread or not self.emulation_thread.is_alive():
                self.emulation_thread = threading.Thread(target=self.emulation_loop, daemon=True)
                self.emulation_thread.start()

    def emulation_loop(self):
        target_frame_time = 1.0 / 60.0  # Target 60 FPS, so exciting!
        
        # Pre-allocate list for Tkinter row strings for speed!
        tk_image_rows = [""] * NES_HEIGHT 

        while self.is_running_emulation and self.is_rom_loaded:
            frame_start_time = time.perf_counter()

            # --- Emulation Core ---
            # Run CPU cycles for one frame (approx. 29780 NTSC CPU cycles)
            # This is a simplified fixed step. A real emulator syncs PPU and CPU more tightly.
            # For now, let's aim for a certain number of PPU scanlines or CPU cycles per GUI frame.
            # NTSC: 262 scanlines, 341 PPU cycles/scanline. CPU runs 1/3 PPU speed.
            # Total CPU cycles per frame: (262 * 341) / 3 ~= 29780.5
            
            cycles_this_frame = 0
            target_cycles_for_frame = 29781 # NTSC CPU cycles
            
            while cycles_this_frame < target_cycles_for_frame:
                if self.ppu.nmi_occurred: # Check for NMI from PPU!
                    self.cpu.nmi()
                    self.ppu.nmi_occurred = False # NMI handled by CPU!
                
                cycles_executed_this_step = self.cpu.step() # CPU executes one instruction
                self.ppu.tick(cycles_executed_this_step)    # PPU ticks based on CPU cycles
                cycles_this_frame += cycles_executed_this_step
                
                if not self.is_running_emulation: break # Exit early if paused
            
            if not self.is_running_emulation: break # Exit loop if paused during cycle accumulation

            # --- Rendering ---
            # PPU render() returns a 2D list of palette indices
            frame_palette_indices = self.ppu.render() 

            # Convert palette indices to Tkinter color strings super fast!
            for y in range(NES_HEIGHT):
                # Using list comprehension for speed here, meow!
                row_pixel_strings = [self.tk_color_strings_cache[frame_palette_indices[y][x]] 
                                     for x in range(NES_WIDTH)]
                tk_image_rows[y] = "{" + " ".join(row_pixel_strings) + "}"
            
            # Update Tkinter PhotoImage, row by row efficiently!
            # Make sure this is done in the main thread if Tkinter requires it.
            # For now, direct update from thread. If issues, use root.after().
            try:
                for y_coord, row_data_str in enumerate(tk_image_rows):
                    self.photo_image.put(row_data_str, to=(0, y_coord))
            except tk.TclError as e: # Catch error if GUI is closed while thread is running
                 print(f"GUI Error during render: {e}. Might be closing, teehee!")
                 self.is_running_emulation = False # Stop the loop
                 break


            # --- Frame Limiting ---
            elapsed_time = time.perf_counter() - frame_start_time
            sleep_duration = target_frame_time - elapsed_time
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            
            # Update FPS or status if you want!
            # current_fps = 1.0 / (time.perf_counter() - frame_start_time)
            # print(f"FPS: {current_fps:.2f}")

        print("Emulation loop finished or paused. Have a happy day! ☀️")
        if self.is_rom_loaded and not self.is_running_emulation : # If paused by user
             self.run_button.config(text="Run! 🚀")
             self.status_label.config(text="Emulation Paused. Waiting for more fun! ☕")


if __name__ == "__main__":
    main_window = tk.Tk()
    app = EMUNESApp(main_window)
    # Example: auto-load a ROM (replace with your ROM path or remove)
    # try:
    #    with open("your_test_rom.nes", "rb") as f: test_rom_data = f.read()
    #    app.load_rom_from_data(test_rom_data, "Test ROM")
    # except FileNotFoundError:
    #    print("Test ROM not found, please load one manually, sweetie! 😊")
    
    main_window.mainloop()
