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

# ------------------------------------------------------------
#                Minimal stub components
# ------------------------------------------------------------
class NESRom:
    """Very small placeholder so the GUI can be tested without a full emulator core"""
    def __init__(self, data: bytes = b""):
        self.data = data
        # fake header values so the UI can show something sensible
        self.mapper = 0
        self.prg_rom_size = 32 * 1024
        self.chr_rom_size = 8 * 1024

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

    # --------------------------------------------------
    #  attaching helpers
    # --------------------------------------------------
    def connect_cpu(self, cpu):
        self.cpu = cpu

    def connect_ppu(self, ppu):
        self.ppu = ppu

    def insert_cartridge(self, cart: Cartridge):
        self.cart = cart  # nothing else needed for the stub

    # --------------------------------------------------
    #  dummy accessors – avoid crashes when the core isn’t there yet
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
#                         GUI front‑end
# ------------------------------------------------------------
class EMUNESApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("EMUNES 1.0A   © Team Flames‑San 20XX")
        root.geometry("1000x800")
        root.resizable(False, False)
        root.configure(bg=DARK_BG)

        # wire‑up minimal emulator back‑end
        self.bus = Bus()
        self.cpu = CPU6502()
        self.ppu = PPU2C02()
        self.bus.connect_cpu(self.cpu)
        self.bus.connect_ppu(self.ppu)

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
    #  UI construction
    # --------------------------------------------------
    def _create_ui(self):
        # ╭────────── top control bar ──────────╮
        top = tk.Frame(self.root, bg=DARK_BG)
        top.pack(pady=10)
        ttk.Button(top, text="Load ROM", command=self.load_rom).pack(side=tk.LEFT, padx=5)
        self.run_button = ttk.Button(top, text="Run", command=self.toggle_run, state=tk.DISABLED)
        self.run_button.pack(side=tk.LEFT, padx=5)
        self.reset_button = ttk.Button(top, text="Reset", command=self.reset, state=tk.DISABLED)
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
        self.console = tk.Text(console_frame, bg=DARK_TEXT_BG, fg=DARK_TEXT_FG, wrap='word', state=tk.DISABLED)
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
                                     bg=DARK_BG, fg=DARK_FG, troughcolor=DARK_BORDER, highlightthickness=0)
        self.speed_scale.set(100)
        self.speed_scale.pack(side=tk.LEFT, padx=10)

    # --------------------------------------------------
    #  log helper
    # --------------------------------------------------
    def log_message(self, msg: str):
        self.console.config(state=tk.NORMAL)
        self.console.insert(tk.END, msg + "\n")
        self.console.see(tk.END)
        self.console.config(state=tk.DISABLED)

    # --------------------------------------------------
    #  ROM loading / system control
    # --------------------------------------------------
    def load_rom(self):
        fname = filedialog.askopenfilename(title="Select NES ROM", filetypes=[("NES ROM", "*.nes"), ("All files", "*.*")])
        if not fname:
            return
        try:
            with open(fname, 'rb') as f:
                data = f.read()
            rom = NESRom(data)
            cart = Cartridge(rom)
            self.bus.insert_cartridge(cart)
            self.rom_loaded = True
            self.reset()
            for btn in (self.run_button, self.reset_button, self.step_button):
                btn.config(state=tk.NORMAL)
            self.status_label.config(text=f"Loaded: {fname.split('/')[-1]}")
            self.log_message(f"ROM loaded successfully: {fname}")
            self.log_message(f"Mapper: {rom.mapper}, PRG: {rom.prg_rom_size//1024}KB, CHR: {rom.chr_rom_size//1024}KB")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.log_message(f"Error loading ROM: {e}")

    def reset(self):
        self.cpu.reset()
        self.ppu = PPU2C02()  # fresh PPU – mimics hardware reset
        self.bus.connect_ppu(self.ppu)
        self.update_display()
        self.log_message("System reset")

    # --------------------------------------------------
    #  run / step helpers
    # --------------------------------------------------
    def toggle_run(self):
        if not self.rom_loaded:
            return
        self.running = not self.running
        self.run_button.config(text="Pause" if self.running else "Run")
        self.step_button.config(state=tk.DISABLED if self.running else tk.NORMAL)
        if self.running:
            self._schedule_emulation()

    def step(self):
        if not self.rom_loaded or self.running:
            return
        self.bus.clock()
        self.update_display()

    def _schedule_emulation(self):
        if not self.running:
            return
        # emulate a single frame – the stub just clocks once
        self.bus.clock()
        self.update_display()
        # re‑schedule according to the speed slider
        sf = self.speed_scale.get() / 100.0
        delay_ms = int((1.0 / self.target_fps) / sf * 1000)
        self.root.after(max(1, delay_ms), self._schedule_emulation)

    # --------------------------------------------------
    #  screen / status updates
    # --------------------------------------------------
    def draw_nes_screen(self):
        """Paint a completely black frame so the canvas isn’t empty before a ROM is loaded."""
        black = "{" + " ".join("#000000" for _ in range(NES_WIDTH)) + "}"
        for y in range(NES_HEIGHT):
            self.screen_image.put(black, (0, y))

    def render_screen(self):
        buf = self.ppu.screen
        for y in range(NES_HEIGHT):
            row = "{" + " ".join(f"#{buf[y][x]:06X}" for x in range(NES_WIDTH)) + "}"
            self.screen_image.put(row, (0, y))

    def update_display(self):
        # CPU flags – all dashes because the stub CPU doesn’t implement them yet
        flags = "--------"
        self.cpu_info.config(text=f"CPU: A={self.cpu.a:02X} X={self.cpu.x:02X} Y={self.cpu.y:02X} SP={self.cpu.stkp:02X} PC={self.cpu.pc:04X} P={flags}")
        self.ppu_info.config(text=f"PPU: Scanline={self.ppu.scanline:3d} Cycle={self.ppu.cycle:3d}")
        self.render_screen()

# ------------------------------------------------------------
#                         main‑program
# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()

    # basic ttk dark theme tweaks – we leave ttk colours mostly default
    s = ttk.Style()
    try:
        s.theme_use('clam')
    except tk.TclError:
        pass

    app = EMUNESApp(root)
    root.mainloop()
