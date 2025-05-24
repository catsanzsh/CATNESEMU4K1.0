import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import struct
import time
import threading

# --- Constants for "EMUNES" Dark Theme ---
DARK_BG = "#2B2B2B"
DARK_FG = "#E0E0E0"  # Text color

# NES Screen dimensions
NES_WIDTH = 256
NES_HEIGHT = 240

# iNES Header Constants
INES_HEADER_SIZE = 16
PRG_PAGE = 16 * 1024
CHR_PAGE = 8 * 1024
TRAINER_SIZE = 512

# CPU Status Flags
C_FLAG = 1 << 0
Z_FLAG = 1 << 1
I_FLAG = 1 << 2
D_FLAG = 1 << 3
B_FLAG = 1 << 4
U_FLAG = 1 << 5
V_FLAG = 1 << 6
N_FLAG = 1 << 7


class INESHeader:
    """Represents the parsed iNES header of a NES ROM."""
    def __init__(self, data: bytes):
        if len(data) < INES_HEADER_SIZE:
            raise ValueError("File too short for valid iNES header")
        if data[0:4] != b"NES\x1a":
            raise ValueError("Not a valid iNES file")

        self.prg_pages = data[4]
        self.chr_pages = data[5]
        flags6, flags7 = data[6], data[7]

        self.mirroring = bool(flags6 & 0x01)
        self.battery = bool(flags6 & 0x02)
        self.trainer = bool(flags6 & 0x04)
        self.four_screen = bool(flags6 & 0x08)
        mapper_lo = (flags6 >> 4) & 0x0F
        mapper_hi = flags7 & 0xF0
        self.mapper = mapper_hi | mapper_lo
        self.is_nes2 = ((flags7 & 0x0C) == 0x08)

        flags9, flags10 = data[9], data[10]
        self.prg_size = self.prg_pages * PRG_PAGE
        # If CHR pages is zero, some ROMs still have no CHR data. This sets to 0 if no CHR.
        self.chr_size = self.chr_pages * CHR_PAGE
        # For older iNES, assume NTSC unless flags indicate PAL
        self.tv_system = 'PAL' if (flags9 & 0x01 or (not self.is_nes2 and (flags10 & 0x01))) else 'NTSC'

    def __str__(self):
        return (f"iNES: PRG={self.prg_pages*16}KB, CHR={self.chr_pages*8}KB, "
                f"Mapper={self.mapper}, Mirroring={'V' if self.mirroring else 'H'}, "
                f"Trainer={self.trainer}, NES2={self.is_nes2}, TV={self.tv_system}")


class CPU6502:
    """A very minimal 6502 CPU emulator with a partial opcode set."""
    def __init__(self, bus):
        self.bus = bus
        self.pc = 0x0000
        self.sp = 0xFD
        self.a = self.x = self.y = 0
        self.status = U_FLAG | I_FLAG
        self.cycles = 0

        # Partial opcode table
        self.opcodes = {
            0xEA: self.op_nop,
            0xA9: self.op_lda_imm,
            0xAD: self.op_lda_abs,
            0x8D: self.op_sta_abs,
            0xA2: self.op_ldx_imm,
            0x9A: self.op_txs,
            0x78: self.op_sei,
            0x4C: self.op_jmp_abs,
        }

    def set_flag(self, mask, value):
        """Set or clear a status flag."""
        if value:
            self.status |= mask
        else:
            self.status &= ~mask

    def update_zn(self, val):
        """Update Zero and Negative flags based on val."""
        self.set_flag(Z_FLAG, val == 0)
        self.set_flag(N_FLAG, bool(val & 0x80))

    def reset(self):
        """Reset CPU registers and load PC from the reset vector."""
        lo = self.bus.read(0xFFFC)
        hi = self.bus.read(0xFFFD)
        self.pc = (hi << 8) | lo
        self.a = self.x = self.y = 0
        self.sp = 0xFD
        self.status = U_FLAG | I_FLAG
        self.cycles = 7
        print(f"CPU Reset! PC=${self.pc:04X}")

    def fetch(self):
        """Fetch the next opcode or operand byte from memory."""
        val = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return val

    def step(self):
        """Execute one instruction and return the number of CPU cycles used."""
        opcode = self.fetch()
        handler = self.opcodes.get(opcode, self.op_nop)
        handler()
        return self.cycles

    # --- Opcodes Implementation ---
    def op_nop(self):
        self.cycles += 2

    def op_lda_imm(self):
        val = self.fetch()
        self.a = val
        self.update_zn(self.a)
        self.cycles += 2

    def op_lda_abs(self):
        lo = self.fetch()
        hi = self.fetch()
        addr = (hi << 8) | lo
        self.a = self.bus.read(addr)
        self.update_zn(self.a)
        self.cycles += 4

    def op_sta_abs(self):
        lo = self.fetch()
        hi = self.fetch()
        addr = (hi << 8) | lo
        self.bus.write(addr, self.a)
        self.cycles += 4

    def op_ldx_imm(self):
        val = self.fetch()
        self.x = val
        self.update_zn(self.x)
        self.cycles += 2

    def op_txs(self):
        self.sp = self.x
        self.cycles += 2

    def op_sei(self):
        self.set_flag(I_FLAG, True)
        self.cycles += 2

    def op_jmp_abs(self):
        lo = self.fetch()
        hi = self.fetch()
        self.pc = (hi << 8) | lo
        self.cycles += 3


class PPU2C02:
    """A stub PPU that stores CHR data and simulates a small palette."""
    def __init__(self, chr_data: bytes):
        self.chr = chr_data
        # Create a placeholder screen: 240 rows of 256 pixels (indexes into self.palette)
        self.screen = [[0]*NES_WIDTH for _ in range(NES_HEIGHT)]

        # Very simplified palette (4 colors + pad out to 64 total)
        # Expand/replace with real NES palette as needed.
        self.palette = [
            (84,84,84),    # example gray
            (0,30,116),    # example dark blue
            (8,16,144),    # example mid-blue
            (48,0,136)     # example purple
        ] + [(0,0,0)] * 60

        self.scanline = 0
        self.cycle = 0

        # Optionally decode CHR data (stub)
        if chr_data:
            self._decode(chr_data)

    def _decode(self, data):
        # Real NES CHR decoding is more involved;
        # placeholder for future usage.
        pass

    def reset(self):
        """Reset PPU scanline, cycle, etc."""
        self.scanline = 0
        self.cycle = 0
        print("PPU Reset!")

    def read_register(self, addr):
        # Stub: real PPU has 8 registers mirrored from 0x2000-0x2007
        return 0

    def write_register(self, addr, val):
        # Stub: handle writes to PPU registers
        pass

    def tick(self, cycles):
        """Advance PPU timing by CPU cycles * 3 (on real hardware).
           Here we keep it minimal for demonstration."""
        # This is extremely simplified and doesn't replicate real NES timing.
        self.cycle += cycles
        # Add more logic if you want to handle real scanlines, sprite draws, etc.

    def render(self):
        """Return the current 2D screen buffer."""
        return self.screen


class Bus:
    """System bus that interconnects CPU, PPU, memory, and possibly APU."""
    def __init__(self, prg_data, chr_data):
        self.prg = prg_data
        self.ram = bytearray(0x0800)  # 2KB internal RAM
        self.ppu = PPU2C02(chr_data)

        # For a real emulator, you'd have more I/O devices (APU, controllers, etc.)
        self.controller = {b:False for b in ['A','B','Start','Select','Up','Down','Left','Right']}

    def read(self, addr):
        """Read a byte from the system bus."""
        addr &= 0xFFFF
        if addr < 0x2000:
            # Internal RAM, mirrored every 2KB
            return self.ram[addr & 0x07FF]
        elif 0x2000 <= addr < 0x4000:
            # PPU registers (mirrored every 8 bytes)
            return self.ppu.read_register(addr & 0x0007)
        elif 0x4000 <= addr < 0x4018:
            # APU / I/O registers
            return 0  # Stub
        elif addr >= 0x8000:
            # Cartridge PRG ROM (simple NROM mapping)
            return self.prg[(addr - 0x8000) % len(self.prg)]
        return 0

    def write(self, addr, val):
        """Write a byte to the system bus."""
        addr &= 0xFFFF
        val &= 0xFF

        if addr < 0x2000:
            # Internal RAM, mirrored
            self.ram[addr & 0x07FF] = val
        elif 0x2000 <= addr < 0x4000:
            # PPU registers
            self.ppu.write_register(addr & 0x0007, val)
        elif addr == 0x4014:
            # OAM DMA stub
            pass
        elif addr == 0x4016:
            # Controller strobe stub
            pass


class EMUNESApp:
    """Tkinter-based GUI for a simple NES emulator demonstration."""
    def __init__(self, root, auto_load=None):
        self.root = root
        root.title("EMUNES 1.0A - Happy Edition")
        root.configure(bg=DARK_BG)
        root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Dark theme styling
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', background=DARK_FG, foreground=DARK_BG, padding=6)
        style.configure('TLabel', background=DARK_BG, foreground=DARK_FG)

        # Top-bar frame
        top_frame = ttk.Frame(root, padding=10)
        top_frame.pack(fill=tk.X)

        load_button = ttk.Button(top_frame, text="Load ROM!", command=self.load_rom_dialog)
        load_button.pack(side=tk.LEFT, padx=5)

        self.run_btn = ttk.Button(top_frame, text="Run!", command=self.toggle_run, state=tk.DISABLED)
        self.run_btn.pack(side=tk.LEFT, padx=5)

        self.status_label = ttk.Label(top_frame, text="No ROM loaded.")
        self.status_label.pack(side=tk.LEFT, padx=5)

        # NES canvas
        self.canvas = tk.Canvas(root, width=NES_WIDTH * 2, height=NES_HEIGHT * 2,
                                bg="black", highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # We store the actual pixel data in a PhotoImage
        self.photo = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        self.canvas_image = self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)
        # Scale it up for easy viewing
        self.canvas.scale(self.canvas_image, 0, 0, 2.0, 2.0)

        # Emulation state
        self.is_running = False
        self.is_loaded = False

        # Auto-load a ROM if provided
        if auto_load:
            self.load_rom_from_data(auto_load)

    def on_closing(self):
        """Handle window closing."""
        self.is_running = False
        self.root.destroy()
        print("Closing EMUNES. Bye-bye!")

    def load_rom_dialog(self):
        """Open a dialog to select and load a .nes file."""
        path = filedialog.askopenfilename(filetypes=[("NES ROM", "*.nes")])
        if not path:
            self.status_label.config(text="No ROM selected.")
            return
        try:
            with open(path, 'rb') as f:
                data = f.read()
            self.load_rom_from_data(data, path)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_label.config(text="Error loading ROM")

    def load_rom_from_data(self, rom: bytes, name: str = ""):
        """Load a ROM from raw data and initialize CPU/PPU."""
        header = INESHeader(rom[:INES_HEADER_SIZE])
        offset = INES_HEADER_SIZE + (TRAINER_SIZE if header.trainer else 0)

        # Extract PRG data
        prg_data = rom[offset : offset + header.prg_size]
        # Extract CHR data (if any)
        chr_offset = offset + header.prg_size
        chr_data = rom[chr_offset : chr_offset + header.chr_size] if header.chr_size > 0 else b''

        # Create bus, CPU, PPU
        self.bus = Bus(prg_data, chr_data)
        self.cpu = CPU6502(self.bus)
        self.ppu = self.bus.ppu

        # Reset CPU and PPU
        self.cpu.reset()
        self.ppu.reset()

        # Update GUI state
        self.is_loaded = True
        self.run_btn.config(state=tk.NORMAL)
        display_name = name if name else "ROM data"
        self.status_label.config(text=f"ROM loaded: {display_name}")
        messagebox.showinfo("Loaded", f"{display_name} loaded!")

    def toggle_run(self):
        """Start or pause emulation."""
        if not self.is_loaded:
            return
        self.is_running = not self.is_running
        self.run_btn.config(text="Pause" if self.is_running else "Run")
        if self.is_running:
            threading.Thread(target=self.run_loop, daemon=True).start()

    def run_loop(self):
        """
        Main emulation loop.  
        Tries to render ~60 frames per second.
        """
        target_frame_time = 1 / 60
        colors = [f"#{r:02x}{g:02x}{b:02x}" for (r, g, b) in self.ppu.palette]

        while self.is_running:
            start_time = time.perf_counter()
            cycles = 0
            # ~29,781 CPU cycles per frame is approximate for NTSC.
            while cycles < 29781 and self.is_running:
                cyc = self.cpu.step()
                self.ppu.tick(cyc)
                cycles += cyc

            # Render frame from PPU
            frame = self.ppu.render()

            # Convert the frame to PhotoImage data
            try:
                for y in range(NES_HEIGHT):
                    row_pixels = "{" + " ".join(colors[frame[y][x]] for x in range(NES_WIDTH)) + "}"
                    self.photo.put(row_pixels, to=(0, y))
            except tk.TclError:
                # Thrown if the window is closed mid-update
                break

            # Sleep until next frame for ~60 FPS
            elapsed = time.perf_counter() - start_time
            time.sleep(max(0, target_frame_time - elapsed))


if __name__ == '__main__':
    root = tk.Tk()
    app = EMUNESApp(root)
    root.mainloop()
