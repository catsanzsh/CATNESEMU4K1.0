"""
EMUNES 1.0B – single‑file "zero‑shot" build that merges:
  • Cycle‑accurate CPU fix (from the previous patch)
  • Visible checkerboard test pattern in the PPU render() method

Drop a small NROM .nes file if you like; without CHR‑decoding
logic you will still see the checkerboard so the pipeline can be
verified end‑to‑end.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import time
import threading

# ---------------------------------------------------------
# Constants / Theme
# ---------------------------------------------------------
DARK_BG = "#2B2B2B"
DARK_FG = "#E0E0E0"

NES_WIDTH, NES_HEIGHT = 256, 240

INES_HEADER_SIZE = 16
PRG_PAGE = 16 * 1024
CHR_PAGE = 8 * 1024
TRAINER_SIZE = 512

# CPU flags
C_FLAG = 1 << 0
Z_FLAG = 1 << 1
I_FLAG = 1 << 2
D_FLAG = 1 << 3
B_FLAG = 1 << 4
U_FLAG = 1 << 5
V_FLAG = 1 << 6
N_FLAG = 1 << 7


# ---------------------------------------------------------
# iNES header helper
# ---------------------------------------------------------
class INESHeader:
    """Parse the 16‑byte iNES header."""

    def __init__(self, data: bytes):
        if len(data) < INES_HEADER_SIZE:
            raise ValueError("File too short for valid iNES header")
        if data[:4] != b"NES\x1A":
            raise ValueError("Not a valid iNES file")

        self.prg_pages = data[4]
        self.chr_pages = data[5]
        flags6, flags7 = data[6], data[7]

        self.mirroring = bool(flags6 & 0x01)
        self.trainer = bool(flags6 & 0x04)
        mapper_lo = (flags6 >> 4) & 0x0F
        mapper_hi = flags7 & 0xF0
        self.mapper = mapper_hi | mapper_lo
        self.is_nes2 = (flags7 & 0x0C) == 0x08

        flags9, flags10 = data[9], data[10]
        self.tv_system = "PAL" if (flags9 & 0x01 or (not self.is_nes2 and (flags10 & 0x01))) else "NTSC"

        self.prg_size = self.prg_pages * PRG_PAGE
        self.chr_size = self.chr_pages * CHR_PAGE


# ---------------------------------------------------------
# CPU – minimal 6502 core
# ---------------------------------------------------------
class CPU6502:
    def __init__(self, bus):
        self.bus = bus
        self.pc = 0x0000
        self.sp = 0xFD
        self.a = self.x = self.y = 0
        self.status = U_FLAG | I_FLAG
        self.cycles = 0  # running total so we can diff per step

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

    # --- helpers ---------------------------------------------------------
    def set_flag(self, mask: int, val: bool):
        if val:
            self.status |= mask
        else:
            self.status &= ~mask

    def update_zn(self, val: int):
        self.set_flag(Z_FLAG, val == 0)
        self.set_flag(N_FLAG, val & 0x80)

    def reset(self):
        lo = self.bus.read(0xFFFC)
        hi = self.bus.read(0xFFFD)
        self.pc = (hi << 8) | lo
        self.sp = 0xFD
        self.a = self.x = self.y = 0
        self.status = U_FLAG | I_FLAG
        self.cycles = 7
        print(f"CPU reset – PC=${self.pc:04X}")

    def fetch(self):
        val = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return val

    def step(self):
        opcode = self.fetch()
        fn = self.opcodes.get(opcode, self.op_nop)
        before = self.cycles
        fn()
        used = self.cycles - before
        if used <= 0:  # belt‑and‑braces
            used = 2
            self.cycles += 2
        if self.cycles > 1_000_000_000:  # prevent runaway int
            self.cycles = 0
        return used

    # --- opcode impls ----------------------------------------------------
    def op_nop(self):
        self.cycles += 2

    def op_lda_imm(self):
        self.a = self.fetch()
        self.update_zn(self.a)
        self.cycles += 2

    def op_lda_abs(self):
        lo = self.fetch(); hi = self.fetch()
        self.a = self.bus.read((hi << 8) | lo)
        self.update_zn(self.a)
        self.cycles += 4

    def op_sta_abs(self):
        lo = self.fetch(); hi = self.fetch()
        self.bus.write((hi << 8) | lo, self.a)
        self.cycles += 4

    def op_ldx_imm(self):
        self.x = self.fetch()
        self.update_zn(self.x)
        self.cycles += 2

    def op_txs(self):
        self.sp = self.x
        self.cycles += 2

    def op_sei(self):
        self.set_flag(I_FLAG, True)
        self.cycles += 2

    def op_jmp_abs(self):
        lo = self.fetch(); hi = self.fetch()
        self.pc = (hi << 8) | lo
        self.cycles += 3


# ---------------------------------------------------------
# PPU – stub with checkerboard test pattern
# ---------------------------------------------------------
class PPU2C02:
    def __init__(self, chr_data: bytes):
        self.chr = chr_data
        self.screen = [[0] * NES_WIDTH for _ in range(NES_HEIGHT)]
        # simple 4‑entry palette padded to 64
        self.palette = [
            (84, 84, 84),
            (0, 30, 116),
            (8, 16, 144),
            (48, 0, 136),
        ] + [(0, 0, 0)] * 60
        self.scanline = self.cycle = 0

    def reset(self):
        self.scanline = self.cycle = 0
        print("PPU reset")

    # register stubs
    def read_register(self, addr):
        return 0

    def write_register(self, addr, val):
        pass

    def tick(self, cpu_cycles):
        self.cycle += cpu_cycles  # mega‑simplified

    def render(self):
        """Return 240×256 array. Produces a 16×16 checkerboard test pattern."""
        block = 16
        for y in range(NES_HEIGHT):
            ybit = (y // block) & 1
            row = self.screen[y]
            for x in range(NES_WIDTH):
                row[x] = (x // block & 1) ^ ybit  # 0 or 1
        return self.screen


# ---------------------------------------------------------
# Bus – ties CPU and PPU together with 2 KB RAM + ROM
# ---------------------------------------------------------
class Bus:
    def __init__(self, prg: bytes, chr_: bytes):
        if not prg:
            raise ValueError("PRG data missing – bad ROM")
        self.prg = prg
        self.ram = bytearray(0x0800)
        self.ppu = PPU2C02(chr_)

    # memory map (very trimmed)
    def read(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x07FF]
        if 0x2000 <= addr < 0x4000:
            return self.ppu.read_register(addr & 7)
        if addr >= 0x8000:
            return self.prg[(addr - 0x8000) % len(self.prg)]
        return 0

    def write(self, addr, val):
        addr &= 0xFFFF; val &= 0xFF
        if addr < 0x2000:
            self.ram[addr & 0x07FF] = val
        elif 0x2000 <= addr < 0x4000:
            self.ppu.write_register(addr & 7, val)
        # other ranges stubbed


# ---------------------------------------------------------
# Tk GUI wrapper
# ---------------------------------------------------------
class EMUNESApp:
    def __init__(self, root):
        self.root = root
        root.title("EMUNES test pattern build")
        root.configure(bg=DARK_BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style(); style.theme_use("clam")
        style.configure("TButton", background=DARK_FG, foreground=DARK_BG)
        style.configure("TLabel", background=DARK_BG, foreground=DARK_FG)

        bar = ttk.Frame(root, padding=10); bar.pack(fill="x")
        ttk.Button(bar, text="Load ROM", command=self._load_dialog).pack(side="left")
        self.run_btn = ttk.Button(bar, text="Run", state="disabled", command=self._toggle)
        self.run_btn.pack(side="left", padx=5)
        self.status = ttk.Label(bar, text="No ROM loaded"); self.status.pack(side="left", padx=5)

        self.canvas = tk.Canvas(root, width=NES_WIDTH*2, height=NES_HEIGHT*2, bg="black", highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)
        self.photo = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        img = self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.scale(img, 0, 0, 2, 2)

        self.bus = self.cpu = None
        self.is_running = False

    # --- gui helpers -----------------------------------------------------
    def _on_close(self):
        self.is_running = False
        self.root.destroy()

    def _load_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("NES ROM", "*.nes")])
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        try:
            self._load_rom(data, path)
        except Exception as exc:
            messagebox.showerror("Load error", str(exc))

    def _load_rom(self, data: bytes, name=""):
        hdr = INESHeader(data[:INES_HEADER_SIZE])
        off = INES_HEADER_SIZE + (TRAINER_SIZE if hdr.trainer else 0)
        prg = data[off : off + hdr.prg_size]
        chr_ = data[off + hdr.prg_size : off + hdr.prg_size + hdr.chr_size] if hdr.chr_size else b""

        self.bus = Bus(prg, chr_)
        self.cpu = CPU6502(self.bus)
        self.cpu.reset(); self.bus.ppu.reset()

        self.run_btn.config(state="normal")
        self.status.config(text=f"ROM loaded: {name if name else '[mem]'}")

    def _toggle(self):
        if not self.cpu:
            return
        self.is_running = not self.is_running
        self.run_btn.config(text="Pause" if self.is_running else "Run")
        if self.is_running:
            threading.Thread(target=self._loop, daemon=True).start()

    # --- main emulation loop --------------------------------------------
    def _loop(self):
        colors = [f"#{r:02x}{g:02x}{b:02x}" for r,g,b in self.bus.ppu.palette]
        frame_cycles_target = 29781  # NTSC approx
        frame_time_target = 1/60

        while self.is_running:
            t0 = time.perf_counter()
            cyc = 0
            while cyc < frame_cycles_target and self.is_running:
                cyc += self.cpu.step()
                self.bus.ppu.tick(cyc)

            frame = self.bus.ppu.render()
            try:
                for y in range(NES_HEIGHT):
                    self.photo.put("{" + " ".join(colors[p] for p in frame[y]) + "}", to=(0, y))
            except tk.TclError:
                break

            dt = time.perf_counter() - t0
            if (sleep := frame_time_target - dt) > 0:
                time.sleep(sleep)


# ---------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    EMUNESApp(root)
    root.mainloop()
