import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import struct
import time
import threading

# --- Constants for "EMUNES" Dark Theme ---
DARK_BG = "#2B2B2B"
DARK_FG = "#E0E0E0"

# NES Screen dimensions
NES_WIDTH = 256
NES_HEIGHT = 240

# iNES Header Constants
INES_HEADER_SIZE = 16
PRG_PAGE = 16 * 1024
CHR_PAGE = 8 * 1024
TRAINER_SIZE = 512

# -----------------------------------
#       iNES Header Parser
# -----------------------------------
class INESHeader:
    def __init__(self, data: bytes):
        if len(data) < INES_HEADER_SIZE:
            raise ValueError("Too short for iNES header")
        if data[0:4] != b"NES\x1a":
            raise ValueError("Invalid iNES signature")
        self.prg_pages = data[4]
        self.chr_pages = data[5]
        flags6 = data[6]; flags7 = data[7]
        self.mirroring   = bool(flags6 & 1)
        self.battery     = bool(flags6 & 2)
        self.trainer     = bool(flags6 & 4)
        self.four_screen = bool(flags6 & 8)
        mapper_lo = flags6 >> 4; mapper_hi = flags7 & 0xF0
        self.mapper      = mapper_hi | mapper_lo
        self.is_nes2     = ((flags7 & 0x0C) == 0x08)
        flags9 = data[9]; flags10 = data[10]
        self.prg_size    = self.prg_pages * PRG_PAGE
        self.chr_size    = self.chr_pages * CHR_PAGE
        self.tv_system   = 1 if (flags9 & 1 or flags10 & 1) else 0

    def __str__(self):
        return (f"iNES Header:\n"
                f" PRG pages: {self.prg_pages}\n"
                f" CHR pages: {self.chr_pages}\n"
                f" Mapper: {self.mapper}\n"
                f" Mirroring: {'Vertical' if self.mirroring else 'Horizontal'}\n"
                f" Battery: {self.battery}\n"
                f" Trainer: {self.trainer}\n"
                f" Four-screen: {self.four_screen}\n"
                f" NES2.0: {self.is_nes2}\n"
                f" PRG size: {self.prg_size} bytes\n"
                f" CHR size: {self.chr_size} bytes\n"
                f" TV system: {'PAL' if self.tv_system else 'NTSC'}")

# -----------------------------------
#       CPU 6502 with basic opcodes
# -----------------------------------
class CPU6502:
    def __init__(self, bus):
        self.bus = bus
        self.pc = 0; self.sp = 0xFD
        self.a = self.x = self.y = 0
        self.status = 0x24; self.cycles = 0
        self.opcodes = {0xEA: self.op_nop, 0xA9: self.op_lda_imm}

    def reset(self):
        lo = self.bus.read(0xFFFC); hi = self.bus.read(0xFFFD)
        self.pc = (hi << 8) | lo; self.cycles = 7

    def fetch(self):
        val = self.bus.read(self.pc); self.pc = (self.pc + 1) & 0xFFFF
        return val

    def step(self):
        opcode = self.fetch(); handler = self.opcodes.get(opcode, self.op_nop)
        handler(); return self.cycles

    def op_nop(self): self.cycles += 2
    def op_lda_imm(self): value = self.fetch(); self.a = value; self.cycles += 2

# -----------------------------------
#       PPU2C02 with basic rendering
# -----------------------------------
class PPU2C02:
    def __init__(self, chr_data):
        self.chr = chr_data
        self.frame = [[0]*NES_WIDTH for _ in range(NES_HEIGHT)]

    def reset(self): pass
    def tick(self, cpu_cycles): pass

    def render(self):
        tile = self.chr[0:16]
        for ty in range(NES_HEIGHT//8):
            for tx in range(NES_WIDTH//8):
                for y in range(8):
                    for x in range(8):
                        bit0 = (tile[y] >> (7-x)) & 1
                        shade = 255 if bit0 else 0
                        self.frame[ty*8+y][tx*8+x] = shade
        return self.frame

# -----------------------------------
#       Memory Bus with controller
# -----------------------------------
class Bus:
    def __init__(self, prg_data, chr_data):
        self.prg = bytearray(prg_data); self.chr = bytearray(chr_data)
        self.ram = [0]*0x800; self.ppu = None
        self.controller = {k:False for k in ['A','B','Start','Select','Up','Down','Left','Right']}
        self.strobe = False; self.shift_reg = []

    def connect_ppu(self, ppu): self.ppu = ppu

    def read(self, addr):
        if addr < 0x2000: return self.ram[addr & 0x7FF]
        if addr == 0x4016:
            if self.strobe: self.shift_reg = list(self.controller.values())
            return int(self.shift_reg.pop(0)) if self.shift_reg else 0
        if 0x8000 <= addr <= 0xFFFF: return self.prg[(addr-0x8000) % len(self.prg)]
        return 0

    def write(self, addr, val):
        if addr < 0x2000: self.ram[addr & 0x7FF] = val
        if addr == 0x4016: self.strobe = bool(val & 1)

# -----------------------------------
#       GUI Front-end with input & direct data load
# -----------------------------------
class EMUNESApp:
    def __init__(self, root, auto_load_data: bytes = None):
        self.root = root
        root.title("EMUNES 1.0A")
        root.configure(bg=DARK_BG)
        top = tk.Frame(root, bg=DARK_BG); top.pack(pady=5)
        ttk.Button(top, text="Load ROM", command=self.load_rom).pack(side=tk.LEFT, padx=5)
        self.run_btn = ttk.Button(top, text="Run", command=self.run); self.run_btn.pack(side=tk.LEFT)
        self.canvas = tk.Canvas(root, width=NES_WIDTH, height=NES_HEIGHT); self.canvas.pack()
        self.img = tk.PhotoImage(width=NES_WIDTH, height=NES_HEIGHT)
        self.canvas.create_image((0,0), image=self.img, anchor=tk.NW)
        self.running = False
        root.bind('<KeyPress>', self.on_key); root.bind('<KeyRelease>', self.on_key)

        # Directly load from provided byte data
        if auto_load_data:
            self.load_rom_data(auto_load_data)

    def on_key(self, event):
        mapping = {'z':'A','x':'B','Return':'Start','Shift_L':'Select',
                   'Up':'Up','Down':'Down','Left':'Left','Right':'Right'}
        btn = mapping.get(event.keysym)
        if btn:
            self.bus.controller[btn] = (event.type == '2')

    def load_rom(self):
        fn = filedialog.askopenfilename(filetypes=[("NES ROM","*.nes")])
        if not fn: return
        data = open(fn, 'rb').read()
        self.load_rom_data(data)

    def load_rom_data(self, data: bytes):
        # Parse header and split PRG/CHR
        hdr = INESHeader(data[:INES_HEADER_SIZE])
        offset = INES_HEADER_SIZE + (TRAINER_SIZE if hdr.trainer else 0)
        prg = data[offset:offset + hdr.prg_size]
        offset += hdr.prg_size
        chr_ = data[offset:offset + hdr.chr_size]
        # Initialize components
        self.bus = Bus(prg, chr_)
        self.cpu = CPU6502(self.bus)
        self.ppu = PPU2C02(chr_)
        self.bus.connect_ppu(self.ppu)
        self.cpu.reset(); self.ppu.reset()
        messagebox.showinfo("Loaded","ROM and engine initialized.")

    def run(self):
        if not hasattr(self, 'cpu') or self.running: return
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while self.running:
            cycles = self.cpu.step(); self.ppu.tick(cycles)
            frame = self.ppu.render()
            for y in range(NES_HEIGHT):
                row = '{' + ' '.join(f"#%02x%02x%02x" % (frame[y][x],frame[y][x],frame[y][x]) for x in range(NES_WIDTH)) + '}'
                self.img.put(row, (0,y))
            time.sleep(1/60)

if __name__ == "__main__":
    root = tk.Tk()
    # Example: pass raw bytes to auto-load
    # with open("path/to/game.nes", "rb") as f: data = f.read()
    # app = EMUNESApp(root, auto_load_data=data)
    app = EMUNESApp(root)
    root.mainloop()
