import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Scale
import struct
import random
import time
import threading

# --- Constants for "EMUNES" Dark Theme ---
DARK_BG = "#2B2B2B"
DARK_FG = "#E0E0E0"
DARK_ACCENT = "#8B0000"
DARK_BORDER = "#444444"
DARK_CANVAS_BG = "#000000"
DARK_BUTTON_BG = "#4A4A4A"
DARK_BUTTON_FG = "#E0E0E0"
DARK_BUTTON_ACTIVE_BG = "#6A6A6A"
DARK_BUTTON_ACTIVE_FG = "#FFFFFF"
DARK_TEXT_BG = "#1E1E1E"
DARK_TEXT_FG = "#E0E0E0"
DARK_ENTRY_BG = "#3E3E3E"
DARK_ENTRY_FG = "#E0E0E0"
DARK_SCROLLBAR_TROUGH = "#3A3A3A"
DARK_SCROLLBAR_BG = "#6B6B6B"
DARK_SCROLLBAR_ACTIVE_BG = "#8B8B8B"

# NES Screen dimensions
NES_WIDTH = 256
NES_HEIGHT = 240

# iNES Header Constants
INES_HEADER_SIZE = 16
PRG_ROM_PAGE_SIZE = 16 * 1024  # 16KB
CHR_ROM_PAGE_SIZE = 8 * 1024   # 8KB
TRAINER_SIZE = 512

class NESRom:
    """Parses and stores information from an iNES ROM file header."""
    def __init__(self, data: bytes = b""):
        self.raw_data = data
        self.header_data = b""
        self.trainer_data = b""
        self.prg_rom_data = b""
        self.chr_rom_data = b""

        # Header fields - initialized to default/empty values
        self.magic_nes = ""
        self.prg_rom_pages = 0  # Number of 16KB PRG ROM pages
        self.chr_rom_pages = 0  # Number of 8KB CHR ROM pages
        self.flags6 = 0
        self.flags7 = 0
        self.flags8_prg_ram_size = 0 # Archaic: PRG RAM size in 8KB units. NES 2.0: Mapper MSB / Submapper
        self.flags9_tv_system = 0    # Archaic: TV system. NES 2.0: PRG RAM/CHR RAM size
        self.flags10_tv_ram = 0      # Archaic: TV system & RAM presence. NES 2.0: Timing/PPU
        self.padding = b""           # Bytes 11-15, usually zero for iNES 1.0

        # Derived properties
        self.mapper = 0
        self.mirroring = 0  # 0: horizontal, 1: vertical
        self.has_battery_ram = False
        self.has_trainer = False
        self.four_screen_vram = False
        self.is_nes2 = False
        self.tv_system = 0 # 0: NTSC, 1: PAL
        self.prg_ram_size = 0 # Actual size in bytes
        self.chr_ram_size = 0 # Actual size in bytes (for NES 2.0)
        self.submapper = 0 # For NES 2.0

        if not data or len(data) < INES_HEADER_SIZE:
            print("Warning: ROM data is too short or empty.")
            # Set some defaults for the stub UI to show something
            self.prg_rom_size = 32 * 1024
            self.chr_rom_size = 8 * 1024
            self.mapper = 0
            return

        self.header_data = data[:INES_HEADER_SIZE]
        self._parse_header()

        # Calculate actual PRG/CHR ROM sizes
        self.prg_rom_size = self.prg_rom_pages * PRG_ROM_PAGE_SIZE
        self.chr_rom_size = self.chr_rom_pages * CHR_ROM_PAGE_SIZE

        # Extract ROM data sections
        current_offset = INES_HEADER_SIZE
        if self.has_trainer:
            self.trainer_data = data[current_offset : current_offset + TRAINER_SIZE]
            current_offset += TRAINER_SIZE
        
        self.prg_rom_data = data[current_offset : current_offset + self.prg_rom_size]
        current_offset += self.prg_rom_size

        self.chr_rom_data = data[current_offset : current_offset + self.chr_rom_size]
        # Any remaining data is usually ignored or for other formats (e.g., PlayChoice hint screens)

    def _parse_header(self):
        """Parses the 16-byte iNES header."""
        try:
            # Unpack header fields
            # Bytes 0-3: Constant $4E $45 $53 $1A ("NES" + EOF)
            self.magic_nes = self.header_data[0:4].decode('ascii', errors='ignore')
            if self.magic_nes != "NES\x1a":
                raise ValueError("Invalid iNES header signature.")

            # Byte 4: Size of PRG ROM in 16 KB units
            self.prg_rom_pages = self.header_data[4]
            # Byte 5: Size of CHR ROM in 8 KB units (0 means CHR RAM)
            self.chr_rom_pages = self.header_data[5]
            
            # Byte 6: Flags 6
            self.flags6 = self.header_data[6]
            self.mirroring = self.flags6 & 0x01  # 0 for horizontal, 1 for vertical
            self.has_battery_ram = bool(self.flags6 & 0x02)
            self.has_trainer = bool(self.flags6 & 0x04)
            self.four_screen_vram = bool(self.flags6 & 0x08)
            mapper_lower_nybble = (self.flags6 & 0xF0) >> 4

            # Byte 7: Flags 7
            self.flags7 = self.header_data[7]
            # Bit 0: VS Unisystem (ignored for now)
            # Bit 1: PlayChoice-10 (ignored for now)
            # Bits 2-3: If equal to 2, flags 8-15 are in NES 2.0 format
            if (self.flags7 & 0x0C) == 0x08: # Check for 0b00001000 (value 8)
                self.is_nes2 = True
            mapper_upper_nybble = self.flags7 & 0xF0 # This is also used for NES 2.0 mapper bits 4-7

            # Byte 8: Flags 8
            self.flags8_prg_ram_size = self.header_data[8] # Can be PRG RAM size or Mapper MSB / Submapper for NES 2.0
            
            # Byte 9: Flags 9
            self.flags9_tv_system = self.header_data[9] # Can be TV system or PRG/CHR RAM size for NES 2.0

            # Byte 10: Flags 10 (rarely used consistently for iNES 1.0)
            self.flags10_tv_ram = self.header_data[10]

            # Bytes 11-15: Padding (usually zero)
            self.padding = self.header_data[11:16]

            # --- Determine Mapper ---
            if self.is_nes2:
                mapper_msb_nes2 = (self.flags8_prg_ram_size & 0x0F) << 8 # Mapper bits 8-11 from Flags 8 lower nybble
                self.mapper = mapper_lower_nybble | mapper_upper_nybble | mapper_msb_nes2
                self.submapper = (self.flags8_prg_ram_size & 0xF0) >> 4
            else:
                # Archaic iNES: Mapper is combined from flags 6 and 7
                self.mapper = mapper_lower_nybble | mapper_upper_nybble

            # --- Determine PRG RAM Size ---
            if self.is_nes2:
                prg_ram_shift = self.flags9_tv_system & 0x0F
                if prg_ram_shift > 0:
                    self.prg_ram_size = 64 << prg_ram_shift # Size = 64 bytes << shift count
                else:
                    self.prg_ram_size = 0
            else:
                # Archaic iNES: Flags 8 gives PRG RAM size in 8KB units.
                # Value 0 often means 8KB for compatibility.
                # Some emulators might ignore this if battery RAM flag is not set.
                if self.flags8_prg_ram_size > 0:
                    self.prg_ram_size = self.flags8_prg_ram_size * 8 * 1024
                elif self.has_battery_ram: # If battery flag is set and size is 0, assume 8KB
                    self.prg_ram_size = 8 * 1024
                else:
                    self.prg_ram_size = 0


            # --- Determine CHR RAM Size (NES 2.0 only for this field) ---
            if self.is_nes2:
                chr_ram_shift = (self.flags9_tv_system & 0xF0) >> 4
                if chr_ram_shift > 0:
                    self.chr_ram_size = 64 << chr_ram_shift # Size = 64 bytes << shift count
                else:
                    self.chr_ram_size = 0
            elif self.chr_rom_pages == 0: # Archaic iNES: if CHR ROM pages is 0, it implies CHR RAM
                self.chr_ram_size = 8 * 1024 # Common default assumption for CHR RAM
            else:
                self.chr_ram_size = 0


            # --- Determine TV System ---
            if self.is_nes2:
                # NES 2.0 Flags 12 (part of padding in iNES 1.0) specifies console region/video standard
                # For simplicity, we'll just check Flags 10 if available for NES 2.0,
                # but a full NES 2.0 parser would look at byte 12.
                tv_system_nes2 = self.flags10_tv_ram & 0x03 # Lower 2 bits
                if tv_system_nes2 == 0: self.tv_system = 0 # NTSC
                elif tv_system_nes2 == 1: self.tv_system = 1 # PAL
                elif tv_system_nes2 == 2: self.tv_system = 0 # NTSC (Multi-region)
                elif tv_system_nes2 == 3: self.tv_system = 1 # PAL (Dendy)
            else:
                # Archaic iNES: Flags 9 or Flags 10
                if self.flags10_tv_ram & 0x01: # Check Flags 10 first (if used)
                    self.tv_system = 1 # PAL
                elif self.flags9_tv_system & 0x01: # Then check Flags 9
                    self.tv_system = 1 # PAL
                else:
                    self.tv_system = 0 # NTSC

        except Exception as e:
            print(f"Error parsing iNES header: {e}")
            # Fallback to stub values if parsing fails badly
            self.prg_rom_size = 32 * 1024
            self.chr_rom_size = 8 * 1024
            self.mapper = 0


class Cartridge:
    def __init__(self, rom: NESRom):
        self.rom = rom

class CPU6502:
    # status‑flag constants – not used by the stub implementation but kept for UI formatting
    FLAG_N = 0; FLAG_V = 1; FLAG_B = 2; FLAG_D = 3; FLAG_I = 4; FLAG_Z = 5; FLAG_C = 6

    def __init__(self):
        self.a = self.x = self.y = 0x00
        self.stkp = 0xFD
        self.pc = 0x8000
        # DMA helpers so Bus.ppu_write() doesn’t crash when the real CPU is missing
        self.dma_transfer = False
        self.dma_addr = 0
        self.dma_data = 0
        self.cycles = 0

    def reset(self):
        self.a = self.x = self.y = 0x00
        self.stkp = 0xFD
        self.pc = 0x8000
        self.cycles = 0

    def get_flag(self, flag: int):
        # always return False in the stub
        return False

class PPU2C02:
    def __init__(self):
        self.scanline = 0
        self.cycle = 0
        self.v = 0
        self.t = 0
        # 256‑colour fake frame‑buffer (all black)
        self.screen = [[0 for _ in range(NES_WIDTH)] for _ in range(NES_HEIGHT)]
        self.oam = bytearray(256)
        self.frame_complete = False

    def connect_bus(self, bus):
        self.bus = bus

class Bus:
    """In the real emulator the Bus would arbitrate all reads/writes. For GUI bring‑up we keep it minimal."""
    def __init__(self):
        self.cpu = None
        self.ppu = None
        self.cpu_ram = bytearray(2 * 1024)
        self.cart = None # Initialize cart attribute

    # --------------------------------------------------
    #   attaching helpers
    # --------------------------------------------------
    def connect_cpu(self, cpu):
        self.cpu = cpu

    def connect_ppu(self, ppu):
        self.ppu = ppu

    def insert_cartridge(self, cart: Cartridge):
        self.cart = cart  # nothing else needed for the stub

    # --------------------------------------------------
    #   dummy accessors – avoid crashes when the core isn’t there yet
    # --------------------------------------------------
    def cpu_read(self, addr: int):
        return 0x00

    def cpu_write(self, addr: int, data: int):
        pass

    def ppu_read(self, addr: int):
        return 0x00

    def ppu_write(self, addr: int, data: int):
        # very small DMA handler so index errors do not occur
        if hasattr(self.cpu, "dma_transfer") and self.cpu.dma_transfer:
            idx = self.cpu.dma_addr & 0xFF
            if 0 <= idx < 256:
                self.ppu.oam[idx] = self.cpu.dma_data
            self.cpu.dma_addr = (self.cpu.dma_addr + 1) & 0xFF
            if self.cpu.dma_addr == 0:
                self.cpu.dma_transfer = False
            return
        # real PPU write would go here
        pass

    def clock(self):
        """Single system tick. The stub does nothing but keeps the GUI loop alive."""
        pass

# ------------------------------------------------------------
#                               GUI front‑end
# ------------------------------------------------------------
class EMUNESApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("EMUNES 1.0A   © Team Flames‑San 20XX")
        root.geometry("1000x800")
        root.resizable(False, False)
        root.configure(bg=DARK_BG)

        # wire‑up minimal emulator back‑end
        self.bus = Bus()
        self.cpu = CPU6502()
        self.ppu = PPU2C02()
        self.bus.connect_cpu(self.cpu)
        self.bus.connect_ppu(self.ppu)
        self.ppu.connect_bus(self.bus) # PPU needs a bus reference too

        self.running = False
        self.rom_loaded = False
        self.frame_skip = 0
        self.target_fps = 60

        # image buffer for the NES screen
        self.screen_image = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)

        # build all widgets
        self._create_ui()
        # save explicit reference so Tkinter’s GC keeps the image alive
        self.screen_canvas.image_ref = self.screen_image

        self.log_message("Welcome to EMUNES! Load a ROM to begin…")

        # paint the first blank frame
        self.draw_nes_screen()

    # --------------------------------------------------
    #   UI construction
    # --------------------------------------------------
    def _create_ui(self):
        # ╭────────── top control bar ──────────╮
        top = tk.Frame(self.root, bg=DARK_BG)
        top.pack(pady=10)
        ttk.Button(top, text="Load ROM", command=self.load_rom).pack(side=tk.LEFT, padx=5)
        self.run_button = ttk.Button(top, text="Run", command=self.toggle_run, state=tk.DISABLED)
        self.run_button.pack(side=tk.LEFT, padx=5)
        self.reset_button = ttk.Button(top, text="Reset", command=self.reset_emulator, state=tk.DISABLED) # Renamed for clarity
        self.reset_button.pack(side=tk.LEFT, padx=5)
        self.step_button = ttk.Button(top, text="Step", command=self.step, state=tk.DISABLED)
        self.step_button.pack(side=tk.LEFT, padx=5)

        # ttk widgets don’t accept bg/fg options – we switch to classic tk.Labels where we need colours
        self.status_label = tk.Label(top, text="No ROM loaded", bg=DARK_BG, fg=DARK_FG)
        self.status_label.pack(side=tk.LEFT, padx=20)

        # ╭───────── main working area ─────────╮
        main = tk.Frame(self.root, bg=DARK_BG)
        main.pack(expand=True, fill=tk.BOTH, padx=10)

        # ––––– the 2×‑scaled NES frame –––––
        self.screen_canvas = tk.Canvas(main, width=NES_WIDTH*2, height=NES_HEIGHT*2,
                                       bg=DARK_CANVAS_BG, highlightthickness=0)
        self.screen_canvas.pack(side=tk.LEFT)
        img_id = self.screen_canvas.create_image(0, 0, anchor=tk.NW, image=self.screen_image)
        self.screen_canvas.scale(img_id, 0, 0, 2, 2)

        # ––––– textual console –––––
        console_frame = tk.Frame(main, bg=DARK_BG)
        console_frame.pack(side=tk.RIGHT, expand=True, fill=tk.BOTH)
        self.console = tk.Text(console_frame, bg=DARK_TEXT_BG, fg=DARK_TEXT_FG, wrap='word', state=tk.DISABLED, font=('Consolas', 10))
        self.console.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = ttk.Scrollbar(console_frame, command=self.console.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.console.config(yscrollcommand=sb.set)

        # ╭──────── bottom status bar ────────╮
        bottom = tk.Frame(self.root, bg=DARK_BG)
        bottom.pack(fill=tk.X, padx=10, pady=10)
        self.cpu_info = tk.Label(bottom, text="CPU: [Not running]", bg=DARK_BG, fg=DARK_FG, font=('Consolas', 10))
        self.cpu_info.pack(anchor=tk.W)
        self.ppu_info = tk.Label(bottom, text="PPU: [Not running]", bg=DARK_BG, fg=DARK_FG, font=('Consolas', 10))
        self.ppu_info.pack(anchor=tk.W)

        speed_frame = tk.Frame(bottom, bg=DARK_BG)
        speed_frame.pack(fill=tk.X)
        tk.Label(speed_frame, text="Speed:", bg=DARK_BG, fg=DARK_FG).pack(side=tk.LEFT)
        self.speed_scale = tk.Scale(speed_frame, from_=1, to=200, orient=tk.HORIZONTAL,
                                    bg=DARK_BG, fg=DARK_FG, troughcolor=DARK_BORDER, highlightthickness=0,
                                    sliderrelief=tk.FLAT, activebackground=DARK_ACCENT)
        self.speed_scale.set(100)
        self.speed_scale.pack(side=tk.LEFT, padx=10)

    # --------------------------------------------------
    #   log helper
    # --------------------------------------------------
    def log_message(self, msg: str):
        self.console.config(state=tk.NORMAL)
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)
        self.console.config(state=tk.DISABLED)

    # --------------------------------------------------
    #   ROM loading / system control
    # --------------------------------------------------
    def load_rom(self):
        fname = filedialog.askopenfilename(title="Select NES ROM", filetypes=[("NES ROM", "*.nes"), ("All files", "*.*")])
        if not fname:
            return
        try:
            with open(fname, 'rb') as f:
                data = f.read()
            
            rom = NESRom(data)
            if rom.magic_nes != "NES\x1a":
                 messagebox.showerror("Error", "Not a valid iNES ROM file.")
                 self.log_message(f"Failed to load ROM: Invalid iNES signature.")
                 return

            cart = Cartridge(rom)
            self.bus.insert_cartridge(cart)
            self.rom_loaded = True
            self.reset_emulator() # Reset emulator state after loading new ROM
            for btn in (self.run_button, self.reset_button, self.step_button):
                btn.config(state=tk.NORMAL)
            
            rom_file_name = fname.split('/')[-1]
            self.status_label.config(text=f"Loaded: {rom_file_name}")
            self.log_message(f"--- ROM Loaded: {rom_file_name} ---")
            self.log_message(f"  Format: {'NES 2.0' if rom.is_nes2 else 'iNES 1.0'}")
            self.log_message(f"  PRG ROM: {rom.prg_rom_size // 1024} KB ({rom.prg_rom_pages} pages)")
            self.log_message(f"  CHR ROM: {rom.chr_rom_size // 1024} KB ({rom.chr_rom_pages} pages)")
            if rom.chr_ram_size > 0:
                 self.log_message(f"  CHR RAM: {rom.chr_ram_size // 1024} KB")
            self.log_message(f"  Mapper: {rom.mapper}")
            if rom.is_nes2:
                self.log_message(f"  Submapper: {rom.submapper}")
            self.log_message(f"  Mirroring: {'Vertical' if rom.mirroring == 1 else 'Horizontal'}{' (Four-Screen)' if rom.four_screen_vram else ''}")
            self.log_message(f"  Battery RAM: {'Yes' if rom.has_battery_ram else 'No'}")
            if rom.prg_ram_size > 0 :
                 self.log_message(f"  PRG RAM: {rom.prg_ram_size // 1024} KB")
            self.log_message(f"  Trainer: {'Yes' if rom.has_trainer else 'No'}")
            self.log_message(f"  TV System: {'PAL' if rom.tv_system == 1 else 'NTSC'}")
            self.log_message("------------------------------------")

        except Exception as e:
            messagebox.showerror("Error", f"Could not load ROM: {str(e)}")
            self.log_message(f"Error loading ROM: {e}")

    def reset_emulator(self): # Renamed from reset
        if not self.rom_loaded: # Don't reset if no ROM
            self.log_message("Cannot reset: No ROM loaded.")
            return
            
        self.cpu.reset()
        self.ppu = PPU2C02()  # fresh PPU – mimics hardware reset
        self.bus.connect_ppu(self.ppu) # Reconnect new PPU to bus
        self.ppu.connect_bus(self.bus) # PPU needs bus reference
        # If you have other components like APU, reset them here too.
        # Potentially, re-initialize cartridge or parts of it if needed.
        
        self.update_display()
        self.log_message("System reset.")
        if self.running: # If it was running, stop it
            self.toggle_run() # This will change button text to "Run"

    # --------------------------------------------------
    #   run / step helpers
    # --------------------------------------------------
    def toggle_run(self):
        if not self.rom_loaded:
            return
        self.running = not self.running
        self.run_button.config(text="Pause" if self.running else "Run")
        self.step_button.config(state=tk.DISABLED if self.running else tk.NORMAL)
        self.reset_button.config(state=tk.DISABLED if self.running else tk.NORMAL) # Disable reset while running
        if self.running:
            self.log_message("Emulation started.")
            self._schedule_emulation()
        else:
            self.log_message("Emulation paused.")
            self.update_display() # Update status when paused

    def step(self):
        if not self.rom_loaded or self.running:
            return
        # In a real emulator, this would be one CPU instruction or one PPU cycle, etc.
        # For the stub, one bus clock is fine.
        try:
            self.bus.clock() # This is a stub, does nothing yet
            # Simulate some CPU/PPU activity for display
            self.cpu.pc = (self.cpu.pc + 1) & 0xFFFF
            self.cpu.cycles += 3 # Arbitrary
            self.ppu.cycle = (self.ppu.cycle + 3*3) % 341 # PPU runs 3x CPU speed
            if self.ppu.cycle < 3*3 : #Approximate new scanline
                self.ppu.scanline = (self.ppu.scanline + 1) % 262
                if self.ppu.scanline == 240: # VBlank
                    self.ppu.frame_complete = True # For a real emu
            
        except Exception as e:
            self.log_message(f"Error during step: {e}")
            self.running = False # Stop emulation on error
            self.run_button.config(text="Run")
            self.step_button.config(state=tk.NORMAL)
            self.reset_button.config(state=tk.NORMAL)

        self.update_display()

    def _emulation_loop_iteration(self):
        """Represents a small chunk of emulation, e.g., one frame."""
        # For the stub, we just advance clocks a bit.
        # A real emulator would run until a frame is complete.
        # Target is roughly 1/60th of a second of NES time.
        # NES CPU runs at ~1.79 MHz. PPU is 3x that.
        # Cycles per frame: ~29780.5 CPU cycles.
        
        # Stub behavior: just one bus clock and update display
        # In a real emulator, this loop would run many CPU/PPU clocks
        # until self.ppu.frame_complete is True.
        if self.bus.cart and self.bus.cart.rom: # Check if ROM is loaded
            # Simulate some activity for the stub
            for _ in range(1000): # Simulate a few cycles for visual feedback
                self.bus.clock() # This is a stub, does nothing yet
                self.cpu.pc = (self.cpu.pc + 1) & 0xFFFF
                self.cpu.cycles += 3
                self.ppu.cycle = (self.ppu.cycle + 3*3) % 341
                if self.ppu.cycle < 3*3:
                    self.ppu.scanline = (self.ppu.scanline + 1) % 262
                    if self.ppu.scanline == 0: # New frame
                        self.ppu.frame_complete = True
                        break # Exit loop for this frame
            
            if self.ppu.frame_complete:
                self.update_display()
                self.ppu.frame_complete = False # Reset for next frame
        else: # Should not happen if running flag is managed correctly
            self.running = False 


    def _schedule_emulation(self):
        if not self.running or not self.rom_loaded:
            self.run_button.config(text="Run")
            self.step_button.config(state=tk.NORMAL if self.rom_loaded else tk.DISABLED)
            self.reset_button.config(state=tk.NORMAL if self.rom_loaded else tk.DISABLED)
            if self.running: # If it was running but ROM somehow unloaded
                 self.log_message("Emulation stopped: ROM not available.")
            self.running = False
            return

        frame_start_time = time.perf_counter()

        try:
            self._emulation_loop_iteration() # Emulate one "frame" or chunk
        except Exception as e:
            self.log_message(f"Runtime error: {e}")
            self.running = False # Stop emulation on error
            self.run_button.config(text="Run")
            self.step_button.config(state=tk.NORMAL)
            self.reset_button.config(state=tk.NORMAL)
            self.update_display() # Show final state
            return
        
        frame_end_time = time.perf_counter()
        emulation_time = frame_end_time - frame_start_time

        speed_factor = self.speed_scale.get() / 100.0
        target_frame_duration = (1.0 / self.target_fps) / speed_factor
        
        delay_seconds = target_frame_duration - emulation_time
        delay_ms = int(delay_seconds * 1000)

        if self.running: # Check again, as an error might have stopped it
            self.root.after(max(1, delay_ms), self._schedule_emulation)
        else: # Update UI if stopped during emulation
            self.update_display()


    # --------------------------------------------------
    #   screen / status updates
    # --------------------------------------------------
    def draw_nes_screen(self):
        """Paint a completely black frame so the canvas isn’t empty before a ROM is loaded."""
        # Tkinter PhotoImage put requires hex color strings per pixel for rows
        # Format: "{#RRGGBB #RRGGBB ...}" for a row
        black_pixel = "#000000" 
        row_data = "{" + " ".join([black_pixel] * NES_WIDTH) + "}"
        for y in range(NES_HEIGHT):
            try:
                self.screen_image.put(row_data, (0, y))
            except tk.TclError as e:
                # This can happen if the image is somehow invalidated during shutdown
                print(f"TclError drawing blank screen (y={y}): {e}")
                break


    def render_screen(self):
        """Renders the PPU's screen buffer to the PhotoImage."""
        # This is a stub. A real PPU would have a palette and pixel data.
        # For now, we'll just draw random noise if running, or black if not.
        if self.running and self.rom_loaded:
            # Simulate some visual change - random colors
            for y in range(NES_HEIGHT):
                row_pixels = []
                for x in range(NES_WIDTH):
                    # Generate a random grayscale color for the stub
                    gray_val = random.randint(0, 255)
                    hex_color = f"#{gray_val:02x}{gray_val:02x}{gray_val:02x}"
                    row_pixels.append(hex_color)
                row_data = "{" + " ".join(row_pixels) + "}"
                try:
                    self.screen_image.put(row_data, (0, y))
                except tk.TclError as e:
                     # This can happen if the image is somehow invalidated during shutdown
                    print(f"TclError rendering screen (y={y}): {e}")
                    break # Stop trying to draw if image is bad
        else:
            # If not running or no ROM, draw a black screen
            self.draw_nes_screen()


    def update_display(self):
        # CPU flags – all dashes because the stub CPU doesn’t implement them yet
        # In a real CPU, you'd format self.cpu.status or call get_flag()
        flags_str = "".join([
            'N' if self.cpu.get_flag(CPU6502.FLAG_N) else '-',
            'V' if self.cpu.get_flag(CPU6502.FLAG_V) else '-',
            '-', # Unused flag
            'B' if self.cpu.get_flag(CPU6502.FLAG_B) else '-',
            'D' if self.cpu.get_flag(CPU6502.FLAG_D) else '-',
            'I' if self.cpu.get_flag(CPU6502.FLAG_I) else '-',
            'Z' if self.cpu.get_flag(CPU6502.FLAG_Z) else '-',
            'C' if self.cpu.get_flag(CPU6502.FLAG_C) else '-'
        ])
        
        # Basic check for rom data before accessing cpu/ppu registers for display
        if self.rom_loaded and self.bus.cart and self.bus.cart.rom:
            self.cpu_info.config(text=f"CPU: A={self.cpu.a:02X} X={self.cpu.x:02X} Y={self.cpu.y:02X} SP={self.cpu.stkp:02X} PC={self.cpu.pc:04X} P=[{flags_str}] CYC:{self.cpu.cycles}")
            self.ppu_info.config(text=f"PPU: Scanline={self.ppu.scanline:3d} Cycle={self.ppu.cycle:3d} V={self.ppu.v:04X} T={self.ppu.t:04X}")
        else:
            self.cpu_info.config(text="CPU: [No ROM / Halted]")
            self.ppu_info.config(text="PPU: [No ROM / Halted]")

        self.render_screen()
        self.root.update_idletasks() # Process pending UI events

# ------------------------------------------------------------
#                               main‑program
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()

    # Basic ttk dark theme tweaks
    s = ttk.Style()
    try:
        s.theme_use('clam') # 'clam', 'alt', 'default', 'classic'
    except tk.TclError:
        print("Clam theme not available, using default.")
        pass # Fallback to default if clam is not available

    # Style ttk buttons for dark theme
    s.configure('TButton', 
                background=DARK_BUTTON_BG, 
                foreground=DARK_BUTTON_FG,
                bordercolor=DARK_BORDER,
                lightcolor=DARK_BUTTON_BG, # For 3D effect
                darkcolor=DARK_BUTTON_BG) # For 3D effect
    s.map('TButton',
          background=[('active', DARK_BUTTON_ACTIVE_BG), ('disabled', '#555555')],
          foreground=[('active', DARK_BUTTON_ACTIVE_FG), ('disabled', '#999999')])

    # Style ttk scrollbars
    s.configure('Vertical.TScrollbar', 
                troughcolor=DARK_SCROLLBAR_TROUGH, 
                background=DARK_SCROLLBAR_BG,
                bordercolor=DARK_BORDER,
                arrowcolor=DARK_FG)
    s.map('Vertical.TScrollbar',
          background=[('active', DARK_SCROLLBAR_ACTIVE_BG)])


    app = EMUNESApp(root)
    root.mainloop()
