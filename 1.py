import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

class NESRom:
    def __init__(self, filepath):
        with open(filepath, "rb") as f:
            self.data = f.read()
        self.header = self.data[:16]
        self.valid = self.parse_header()
        if self.valid:
            self.extract_rom_data()

    def parse_header(self):
        if self.header[:4] != b"NES\x1a":
            return False
        self.prg_rom_size = self.header[4] * 16384  # 16 KB units
        self.chr_rom_size = self.header[5] * 8192   # 8 KB units
        self.mapper = (self.header[6] >> 4) | (self.header[7] & 0xF0)
        self.mirroring = "Vertical" if (self.header[6] & 1) else "Horizontal"
        self.battery = bool(self.header[6] & 2)
        self.trainer = bool(self.header[6] & 4)
        return True

    def extract_rom_data(self):
        start = 16 + (512 if self.trainer else 0)
        self.prg_rom = self.data[start : start + self.prg_rom_size]
        self.chr_rom = self.data[start + self.prg_rom_size : start + self.prg_rom_size + self.chr_rom_size]

    def get_opcodes(self, count=16):
        # Get first `count` opcodes from PRG ROM
        if not hasattr(self, "prg_rom"):
            return []
        return [f"${byte:02X}" for byte in self.prg_rom[:count]]

class CatNESApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🐾 CATNES – Cat-san's NES ROM Inspector 🐾")
        self.geometry("480x340")
        self.configure(bg="#e9eafc")

        tk.Label(self, text="🐱 CATNES – NES ROM Inspector", font=("Segoe UI", 18, "bold"), bg="#e9eafc").pack(pady=10)
        tk.Button(self, text="Open NES ROM", font=("Segoe UI", 12), command=self.load_rom, bg="#a6b1ff").pack(pady=6)

        self.info_text = tk.Label(self, text="No ROM loaded.", font=("Segoe UI", 11), bg="#e9eafc", justify="left")
        self.info_text.pack(pady=5)

        self.opcode_area = scrolledtext.ScrolledText(self, width=44, height=8, font=("Consolas", 12), bg="#fff8f2")
        self.opcode_area.pack(pady=7)

        self.cat_footer = tk.Label(self, text="=＾● ⋏ ●＾=   Powered by Cat-san!", font=("Segoe UI", 10), bg="#e9eafc", fg="#9c6cc1")
        self.cat_footer.pack(side="bottom", pady=3)

    def load_rom(self):
        file_path = filedialog.askopenfilename(title="Select NES ROM", filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")])
        if not file_path:
            return

        try:
            rom = NESRom(file_path)
            if not rom.valid:
                raise ValueError("Not a valid NES ROM (Missing header)")

            info = (
                f"File: {file_path.split('/')[-1]}\n"
                f"PRG ROM: {rom.prg_rom_size // 1024} KB\n"
                f"CHR ROM: {rom.chr_rom_size // 1024} KB\n"
                f"Mapper: {rom.mapper}\n"
                f"Mirroring: {rom.mirroring}\n"
                f"Battery: {'Yes' if rom.battery else 'No'}\n"
                f"Trainer: {'Yes' if rom.trainer else 'No'}"
            )
            self.info_text.config(text=info)

            opcodes = rom.get_opcodes(16)
            self.opcode_area.delete(1.0, tk.END)
            self.opcode_area.insert(tk.END, "First 16 PRG ROM bytes (hex):\n" + " ".join(opcodes))
        except Exception as e:
            messagebox.showerror("CATNES", f"Error loading ROM:\n{e}")

if __name__ == "__main__":
    app = CatNESApp()
    app.mainloop()
