"""
EMUNES **GIGA** 1.0C (test.py)
===============================
One‑file NES playground that now includes:

✔️  Cycle‑accurate 6502 core (minimal subset)
✔️  16×16 checkerboard fallback **plus** CHR tile‑set viewer
    ‑ load any NROM (.nes) ROM and click **Tileset** to view its graphic tiles
✔️  Clean Tkinter GUI with **Run/Pause** and **Tileset/Pattern** toggle

Still a learning / debug build – no scrolling, sprites or audio yet – but a solid
platform for adding features.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import time
import threading

# ---------------------------------------------------------
# Theme / Constants
# ---------------------------------------------------------
DARK_BG = "#2B2B2B"
DARK_FG = "#E0E0E0"

NES_WIDTH, NES_HEIGHT = 256, 240
TILE_W = TILE_H = 8
MAP_W, MAP_H = NES_WIDTH // TILE_W, NES_HEIGHT // TILE_H  # 32 × 30 tiles

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
    """Parse a 16‑byte iNES header."""

    def __init__(self, hdr: bytes):
        if len(hdr) < INES_HEADER_SIZE or hdr[:4] != b"NES\x1A":
            raise ValueError("Invalid iNES header")
        self.prg_pages = hdr[4]
        self.chr_pages = hdr[5]
        self.trainer = bool(hdr[6] & 0x04)
        self.prg_size = self.prg_pages * PRG_PAGE
        self.chr_size = self.chr_pages * CHR_PAGE


# ---------------------------------------------------------
# Minimal 6502 core (enough to tick / demo)
# ---------------------------------------------------------
class CPU6502:
    def __init__(self, bus):
        self.bus = bus
        self.pc = 0
        self.sp = 0xFD
        self.a = self.x = self.y = 0
        self.status = U_FLAG | I_FLAG
        self.cycles = 0

        # opcode dispatch table
        self.ops = {
            0xEA: self.op_nop,
            0xA9: self.op_lda_imm,
            0xA2: self.op_ldx_imm,
            0xAD: self.op_lda_abs,
            0x8D: self.op_sta_abs,
            0x9A: self.op_txs,
            0x78: self.op_sei,
            0x4C: self.op_jmp_abs,
        }

    # flag helpers ------------------------------------------------------
    def _set(self, m, v):
        if v:
            self.status |= m
        else:
            self.status &= ~m

    def _update_zn(self, v):
        self._set(Z_FLAG, v == 0)
        self._set(N_FLAG, v & 0x80)

    # bus helpers -------------------------------------------------------
    def _fetch(self):
        b = self.bus.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return b

    def reset(self):
        lo = self.bus.read(0xFFFC)
        hi = self.bus.read(0xFFFD)
        self.pc = (hi << 8) | lo
        self.cycles = 7
        print(f"CPU reset: PC=${self.pc:04X}")

    def step(self):
        op = self._fetch()
        before = self.cycles
        self.ops.get(op, self.op_nop)()
        used = self.cycles - before or 2
        return used

    # opcode implementations -------------------------------------------
    def op_nop(self):
        self.cycles += 2

    def op_lda_imm(self):
        self.a = self._fetch()
        self._update_zn(self.a)
        self.cycles += 2

    def op_ldx_imm(self):
        self.x = self._fetch()
        self._update_zn(self.x)
        self.cycles += 2

    def op_lda_abs(self):
        lo = self._fetch()
        hi = self._fetch()
        addr = (hi << 8) | lo
        self.a = self.bus.read(addr)
        self._update_zn(self.a)
        self.cycles += 4

    def op_sta_abs(self):
        lo = self._fetch()
        hi = self._fetch()
        addr = (hi << 8) | lo
        self.bus.write(addr, self.a)
        self.cycles += 4

    def op_txs(self):
        self.sp = self.x
        self.cycles += 2

    def op_sei(self):
        self._set(I_FLAG, True)
        self.cycles += 2

    def op_jmp_abs(self):
        lo = self._fetch()
        hi = self._fetch()
        self.pc = (hi << 8) | lo
        self.cycles += 3


# ---------------------------------------------------------
# PPU stub – checkerboard / tileset view
# ---------------------------------------------------------
class PPU2C02:
    def __init__(self, chr_data: bytes):
        self.chr = chr_data
        self.screen = [[0] * NES_WIDTH for _ in range(NES_HEIGHT)]
        # Some basic palette stub
        self.palette = [
            (84, 84, 84), (0, 30, 116), (8, 16, 144), (48, 0, 136)
        ] + [(0, 0, 0)] * 60
        self.show_tileset = False

    def _decode_tile(self, idx: int):
        # Each tile is 16 bytes (8 for plane0, 8 for plane1)
        off = idx * 16
        if off + 16 > len(self.chr):
            return [[0]*TILE_W for _ in range(TILE_H)]
        tile = []
        for y in range(8):
            p0 = self.chr[off + y]
            p1 = self.chr[off + y + 8]
            row = []
            for b in range(8):
                bit0 = (p0 >> (7 - b)) & 1
                bit1 = (p1 >> (7 - b)) & 1
                row.append(bit0 | (bit1 << 1))
            tile.append(row)
        return tile

    def tick(self, _cyc):
        # Not implementing PPU timing for this minimal test
        pass

    def render(self):
        """Render either a checkerboard background or the CHR as a tileset."""
        if self.show_tileset and self.chr:
            for ty in range(MAP_H):
                for tx in range(MAP_W):
                    idx = ty * MAP_W + tx
                    tile = self._decode_tile(idx)
                    for py in range(TILE_H):
                        row_dst = self.screen[ty * TILE_H + py]
                        row_src = tile[py]
                        for px in range(TILE_W):
                            row_dst[tx * TILE_W + px] = row_src[px]
        else:
            # Draw simple checkerboard
            blk = 16
            for y in range(NES_HEIGHT):
                yb = (y // blk) & 1
                row = self.screen[y]
                for x in range(NES_WIDTH):
                    row[x] = ((x // blk) & 1) ^ yb
        return self.screen


# ---------------------------------------------------------
# Bus – 2 KB RAM + PRG mirror + PPU
# ---------------------------------------------------------
class Bus:
    def __init__(self, prg: bytes, chr_: bytes):
        self.prg = prg
        self.ram = bytearray(0x0800)
        self.ppu = PPU2C02(chr_)

    def read(self, addr):
        addr &= 0xFFFF
        if addr < 0x2000:
            return self.ram[addr & 0x07FF]
        elif addr >= 0x8000:
            # Mirror if PRG is smaller than 0x8000 block
            return self.prg[(addr - 0x8000) % len(self.prg)]
        else:
            # Not handling PPU registers, etc. in this minimal test
            return 0

    def write(self, addr, val):
        addr &= 0xFFFF
        val &= 0xFF
        if addr < 0x2000:
            self.ram[addr & 0x07FF] = val
        # Not writing to PPU registers in minimal test


# ---------------------------------------------------------
# Tkinter GUI wrapper
# ---------------------------------------------------------
class EMUNESApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("EMUNES GIGA build – test.py")
        self.root.configure(bg=DARK_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", background=DARK_FG, foreground=DARK_BG)
        style.configure("TLabel", background=DARK_BG, foreground=DARK_FG)

        bar = ttk.Frame(root, padding=10)
        bar.pack(fill="x")

        ttk.Button(bar, text="Load ROM", command=self._load_rom).pack(side="left")
        self.run_btn = ttk.Button(bar, text="Run", state="disabled", command=self._toggle_run)
        self.run_btn.pack(side="left", padx=5)

        self.view_btn = ttk.Button(bar, text="Tileset", state="disabled", command=self._toggle_view)
        self.view_btn.pack(side="left", padx=5)

        self.status_lbl = ttk.Label(bar, text="No ROM loaded")
        self.status_lbl.pack(side="left", padx=5)

        # Canvas is double-sized (2x) so we scale up the 256×240.
        self.canvas = tk.Canvas(root, width=NES_WIDTH*2, height=NES_HEIGHT*2,
                                bg="black", highlightthickness=0)
        self.canvas.pack(padx=10, pady=10)

        # PhotoImage for pixel-by-pixel updates (actual resolution: 256×240)
        self.photo = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        self.canvas.create_image((0, 0), image=self.photo, anchor="nw")

        self.bus = None
        self.cpu = None
        self.running = False
        self.thread = None

    def _load_rom(self):
        path = filedialog.askopenfilename(filetypes=[("NES ROMs", "*.nes")])
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            hdr = INESHeader(data[:INES_HEADER_SIZE])
            offset = INES_HEADER_SIZE + (TRAINER_SIZE if hdr.trainer else 0)
            prg = data[offset : offset + hdr.prg_size]
            offset += hdr.prg_size
            chr_ = data[offset : offset + hdr.chr_size]

            self.bus = Bus(prg, chr_)
            self.cpu = CPU6502(self.bus)
            self.cpu.reset()

            self.status_lbl.config(text=f"Loaded: {path.split('/')[-1]}")
            self.run_btn.state(["!disabled"])
            self.view_btn.state(["!disabled"])
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _toggle_run(self):
        if not self.running:
            self.running = True
            self.run_btn.config(text="Pause")
            self.thread = threading.Thread(target=self._emulation_loop, daemon=True)
            self.thread.start()
        else:
            self.running = False
            self.run_btn.config(text="Run")

    def _toggle_view(self):
        if not self.bus:
            return
        ppu = self.bus.ppu
        ppu.show_tileset = not ppu.show_tileset
        new_text = "Pattern" if ppu.show_tileset else "Tileset"
        self.view_btn.config(text=new_text)
        # Force a refresh of the screen
        self._draw_frame()

    def _emulation_loop(self):
        """Runs CPU in a loop while self.running is True."""
        while self.running:
            if self.cpu:
                # Step ~30,000 cycles to keep CPU busy,
                # then draw a frame
                cyc_target = 30000
                cyc_count = 0
                while cyc_count < cyc_target:
                    used = self.cpu.step()
                    cyc_count += used
                    self.bus.ppu.tick(used)
                # Once we exit that small loop, we draw the screen
                self._draw_frame()

    def _draw_frame(self):
        """Renders the current PPU screen into the PhotoImage."""
        if not self.bus:
            return
        scr = self.bus.ppu.render()  # 2D array of palette indices
        ppu = self.bus.ppu
        pal = ppu.palette

        # Construct one giant string of pixel data in PPM style
        # for PhotoImage's put() method. This is usually faster than
        # calling put() per pixel in a loop.
        data_rows = []
        for row in scr:
            row_data = []
            for pix_val in row:
                r, g, b = pal[pix_val]
                row_data.append(f"#{r:02x}{g:02x}{b:02x}")
            data_rows.append(" ".join(row_data))
        # Put this into PhotoImage
        self.photo.put(" ".join(data_rows), to=(0, 0))

        # Force the canvas to redraw
        self.canvas.update()

    def _quit(self):
        self.running = False
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = EMUNESApp(root)
    root.mainloop()
