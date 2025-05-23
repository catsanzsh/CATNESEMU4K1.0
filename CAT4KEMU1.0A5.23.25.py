import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk # We're using ttk for super cute tabs now! So much more organized!
import struct # For potential future binary operations, maybe for endianness for hex editor, how exciting!

class NESRom:
    def __init__(self, filepath):
        self.filepath = filepath # Store original path for saving later! Purr-fect for keeping track!
        with open(filepath, "rb") as f:
            self.data = bytearray(f.read()) # Use bytearray for mutability! So much fun to change things!
        self.header = self.data[:16]
        self.valid = self.parse_header()
        if self.valid:
            self.extract_rom_data()

    def parse_header(self):
        if self.header[:4] != b"NES\x1a":
            return False
        # Let's decode those super secret header bytes, meow!
        self.prg_rom_size = self.header[4] * 16384  # 16 KB units, woah!
        self.chr_rom_size = self.header[5] * 8192   # 8 KB units, so much data to play with!
        self.mapper = (self.header[6] >> 4) | (self.header[7] & 0xF0) # Mapper magic, so fascinating!
        self.mirroring = "Vertical" if (self.header[6] & 1) else "Horizontal"
        self.battery = bool(self.header[6] & 2) # Does it save? Purr-haps for your high scores!
        self.trainer = bool(self.header[6] & 4) # Secret trainer data? Wow, let's explore it!
        return True

    def extract_rom_data(self):
        # Time to slice and dice that ROM data, nyah! We're becoming data ninjas!
        self.trainer_size = 512 if self.trainer else 0
        self.prg_rom_offset = 16 + self.trainer_size
        self.chr_rom_offset = self.prg_rom_offset + self.prg_rom_size

        self.prg_rom = self.data[self.prg_rom_offset : self.prg_rom_offset + self.prg_rom_size]
        self.chr_rom = self.data[self.chr_rom_offset : self.chr_rom_offset + self.chr_rom_size]

    def get_opcodes(self, count=16):
        # Peeking at the very first bytes of PRG ROM! So intriguing, like a secret message!
        if not hasattr(self, "prg_rom"):
            return []
        return [f"${byte:02X}" for byte in self.prg_rom[:count]]

    def get_hex_dump(self, offset, length, rom_type="PRG"):
        # Let's get a super cool hex dump, yay! It's like seeing the ROM's inner thoughts!
        data_to_dump = None
        start_addr = 0
        if rom_type == "PRG" and hasattr(self, "prg_rom"):
            data_to_dump = self.prg_rom
            start_addr = self.prg_rom_offset
        elif rom_type == "CHR" and hasattr(self, "chr_rom"):
            data_to_dump = self.chr_rom
            start_addr = self.chr_rom_offset
        else:
            return "No data to dump, meow! Select a ROM type first!"

        if not data_to_dump:
            return "No data available, try loading a ROM first, kitty! We need bytes to play with!"

        dump_str = ""
        actual_offset = max(0, min(offset, len(data_to_dump)))
        actual_length = min(length, len(data_to_dump) - actual_offset)

        for i in range(actual_offset, actual_offset + actual_length, 16):
            chunk = data_to_dump[i:i+16]
            hex_part = " ".join([f"{byte:02X}" for byte in chunk])
            ascii_part = "".join([chr(byte) if 32 <= byte < 127 else "." for byte in chunk])
            dump_str += f"{start_addr + i:08X}: {hex_part:<48} {ascii_part}\n"
        return dump_str

    def modify_byte(self, rom_type, address_in_rom, new_value):
        # Oh my goodness, we're changing bytes! Super powerful, you're a byte-bending wizard now!
        try:
            new_byte = int(new_value, 16) # Expecting hex string input, so cool and precise!
            if not (0 <= new_byte <= 255):
                raise ValueError("Byte value must be 00-FF, nya! Just like magic numbers!")

            abs_address = -1
            if rom_type == "PRG":
                if not hasattr(self, "prg_rom"): raise ValueError("PRG ROM not loaded! Can't poke what's not there!")
                if not (0 <= address_in_rom < self.prg_rom_size): raise ValueError("Address out of PRG ROM bounds! Stay within the lines, kitty!")
                abs_address = self.prg_rom_offset + address_in_rom
            elif rom_type == "CHR":
                if not hasattr(self, "chr_rom"): raise ValueError("CHR ROM not loaded! No graphics to sparkle yet!")
                if not (0 <= address_in_rom < self.chr_rom_size): raise ValueError("Address out of CHR ROM bounds! Watch your step!")
                abs_address = self.chr_rom_offset + address_in_rom
            else:
                raise ValueError("Invalid ROM type specified, meow! PRG or CHR, those are our choices!")

            if abs_address != -1 and 0 <= abs_address < len(self.data):
                self.data[abs_address] = new_byte # The actual byte modification! Woohoo!
                self.extract_rom_data() # Re-extract to update PRG/CHR views! Yay, changes everywhere!
                return f"Byte at {rom_type} address {address_in_rom:04X} changed to {new_value.upper()}! Woohoo, you did it!"
            else:
                return "Something went wrong with the address, meow! Double check your input!"
        except ValueError as e:
            return f"Purr-fect error: {e}"
        except Exception as e:
            return f"An unexpected oopsie happened: {e}"

    def save_rom(self, new_filepath):
        # We're saving our super awesome modified ROM! This is making history, one byte at a time!
        with open(new_filepath, "wb") as f:
            f.write(self.data)
        self.filepath = new_filepath # Update the path! Meow! Your masterpiece is saved!
        return "ROM saved successfully! Paw-some! You've officially hacked it!"

class CatNESApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🐾 CATNES – Cat-san's Purr-fect NES ROM Hacker! 🐾")
        self.geometry("680x580") # A bit bigger for all our awesome features! More room for fun!
        self.configure(bg="#e9eafc") # A lovely pastel background, purr!
        self.current_rom = None # Our little ROM buddy, waiting to be loaded!

        tk.Label(self, text="🐱 CATNES – NES ROM Hacking Adventure! 🐾", font=("Segoe UI", 20, "bold"), bg="#e9eafc").pack(pady=10)

        # Let's make some super fun tabs with a Notebook widget! Purr-fect for organization and ease of use!
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=5)

        self.create_info_tab()
        self.create_hex_editor_tab()
        self.create_hacking_tab()
        self.create_ripper_tab()

        tk.Button(self, text="Open NES ROM", font=("Segoe UI", 12), command=self.load_rom, bg="#a6b1ff", fg="#333").pack(pady=6)
        tk.Button(self, text="Save Modified ROM", font=("Segoe UI", 12), command=self.save_rom, bg="#ffc1e3", fg="#333").pack(pady=4)

        self.cat_footer = tk.Label(self, text="=＾● ⋏ ●＾=   Powered by Cat-san's Hacking Prowess! You're a hacking god now, meow!", font=("Segoe UI", 10), bg="#e9eafc", fg="#9c6cc1")
        self.cat_footer.pack(side="bottom", pady=3)

        self.update_ui_state() # Initial state setup! Making sure everything is purr-fectly ready!

    def create_info_tab(self):
        self.info_frame = ttk.Frame(self.notebook, padding="10", style='TFrame')
        self.notebook.add(self.info_frame, text="🐾 ROM Info")

        tk.Label(self.info_frame, text="Here's the scoop on your ROM, meow! All the juicy details!", font=("Segoe UI", 14, "bold"), bg="#e9eafc").pack(pady=5)
        self.info_text = tk.Label(self.info_frame, text="No ROM loaded. Let's find one, purr!", font=("Segoe UI", 11), bg="#e9eafc", justify="left")
        self.info_text.pack(pady=5, anchor="nw")

        tk.Label(self.info_frame, text="First few bytes, so exciting! Like a secret code!", font=("Segoe UI", 12, "bold"), bg="#e9eafc").pack(pady=5, anchor="nw")
        self.opcode_area = scrolledtext.ScrolledText(self.info_frame, width=70, height=8, font=("Consolas", 12), bg="#fff8f2", state="disabled")
        self.opcode_area.pack(pady=7)

    def create_hex_editor_tab(self):
        self.hex_frame = ttk.Frame(self.notebook, padding="10", style='TFrame')
        self.notebook.add(self.hex_frame, text="😻 Hex Editor")

        tk.Label(self.hex_frame, text="Time to peek and poke at bytes! So much fun to be a data sculptor!", font=("Segoe UI", 14, "bold"), bg="#e9eafc").pack(pady=5)

        rom_type_frame = tk.Frame(self.hex_frame, bg="#e9eafc")
        rom_type_frame.pack(pady=5)
        tk.Label(rom_type_frame, text="Select ROM Type:", bg="#e9eafc").pack(side="left", padx=5)
        self.hex_rom_type = ttk.Combobox(rom_type_frame, values=["PRG", "CHR"], state="readonly", width=8)
        self.hex_rom_type.set("PRG")
        self.hex_rom_type.pack(side="left", padx=5)
        self.hex_rom_type.bind("<<ComboboxSelected>>", self.refresh_hex_view) # Auto-refresh! So convenient!

        view_frame = tk.Frame(self.hex_frame, bg="#e9eafc")
        view_frame.pack(pady=5)
        tk.Label(view_frame, text="Offset (hex):", bg="#e9eafc").pack(side="left", padx=5)
        self.hex_offset_entry = tk.Entry(view_frame, width=10, font=("Consolas", 10))
        self.hex_offset_entry.insert(0, "0000")
        self.hex_offset_entry.pack(side="left", padx=5)
        tk.Label(view_frame, text="Length (dec):", bg="#e9eafc").pack(side="left", padx=5)
        self.hex_length_entry = tk.Entry(view_frame, width=10, font=("Consolas", 10))
        self.hex_length_entry.insert(0, "256")
        self.hex_length_entry.pack(side="left", padx=5)
        tk.Button(view_frame, text="Refresh View", command=self.refresh_hex_view, bg="#a6b1ff").pack(side="left", padx=5)

        self.hex_display = scrolledtext.ScrolledText(self.hex_frame, width=80, height=15, font=("Consolas", 10), bg="#fff8f2", state="disabled")
        self.hex_display.pack(pady=7)

        edit_frame = tk.Frame(self.hex_frame, bg="#e9eafc")
        edit_frame.pack(pady=5)
        tk.Label(edit_frame, text="Address (hex, relative to ROM type):", bg="#e9eafc").pack(side="left", padx=5)
        self.edit_address_entry = tk.Entry(edit_frame, width=10, font=("Consolas", 10))
        self.edit_address_entry.pack(side="left", padx=5)
        tk.Label(edit_frame, text="New Value (hex, 00-FF):", bg="#e9eafc").pack(side="left", padx=5)
        self.edit_value_entry = tk.Entry(edit_frame, width=5, font=("Consolas", 10))
        self.edit_value_entry.pack(side="left", padx=5)
        tk.Button(edit_frame, text="Modify Byte! (Super Power!)", command=self.modify_byte_action, bg="#ffc1e3").pack(side="left", padx=5)

    def create_hacking_tab(self):
        self.hacking_frame = ttk.Frame(self.notebook, padding="10", style='TFrame')
        self.notebook.add(self.hacking_frame, text="😈 Hacking Fun")

        tk.Label(self.hacking_frame, text="Become a hacking purr-fessor! Find those secrets! It's like a treasure hunt!", font=("Segoe UI", 14, "bold"), bg="#e9eafc").pack(pady=5)

        # Simple Byte Search, for finding amazing cheat codes or hidden messages!
        search_frame = tk.Frame(self.hacking_frame, bg="#e9eafc")
        search_frame.pack(pady=10)
        tk.Label(search_frame, text="Search Bytes (hex, e.g., C903F0):", bg="#e9eafc").pack(side="left", padx=5)
        self.search_bytes_entry = tk.Entry(search_frame, width=20, font=("Consolas", 10))
        self.search_bytes_entry.pack(side="left", padx=5)
        tk.Button(search_frame, text="Find Bytes!", command=self.find_bytes_action, bg="#a6b1ff").pack(side="left", padx=5)

        self.search_results_text = scrolledtext.ScrolledText(self.hacking_frame, width=70, height=10, font=("Consolas", 10), bg="#fff8f2", state="disabled")
        self.search_results_text.pack(pady=7)

        tk.Label(self.hacking_frame, text="Wow! Imagine all the cool cheats you can find and make! You're a true hacking god!", font=("Segoe UI", 12), bg="#e9eafc", fg="#6cc19c").pack(pady=10)

    def create_ripper_tab(self):
        self.ripper_frame = ttk.Frame(self.notebook, padding="10", style='TFrame')
        self.notebook.add(self.ripper_frame, text="🌟 Asset Ripper")

        tk.Label(self.ripper_frame, text="Rip those assets! For ultimate purr-sonal use! Grab whatever you want!", font=("Segoe UI", 14, "bold"), bg="#e9eafc").pack(pady=5)

        rip_prg_frame = tk.Frame(self.ripper_frame, bg="#e9eafc")
        rip_prg_frame.pack(pady=10)
        tk.Label(rip_prg_frame, text="Want to rip the PRG ROM? It's like magic, extracting programs!", bg="#e9eafc").pack(side="left", padx=10)
        tk.Button(rip_prg_frame, text="Rip PRG ROM! (RAW)", command=lambda: self.rip_rom_section("PRG"), bg="#ffc1e3").pack(side="left", padx=10)

        rip_chr_frame = tk.Frame(self.ripper_frame, bg="#e9eafc")
        rip_chr_frame.pack(pady=10)
        tk.Label(rip_chr_frame, text="Or maybe the CHR ROM? Graphics everywhere, just grab them!", bg="#e9eafc").pack(side="left", padx=10)
        tk.Button(rip_chr_frame, text="Rip CHR ROM! (RAW)", command=lambda: self.rip_rom_section("CHR"), bg="#ffc1e3").pack(side="left", padx=10)

        tk.Label(self.ripper_frame, text="Remember, with great power comes great responsibility... to make awesome stuff! Meow! This is so cool!", font=("Segoe UI", 12), bg="#e9eafc", fg="#6cc19c").pack(pady=20)


    def update_ui_state(self):
        # Enable/disable buttons based on ROM loaded state! Super smart to keep things tidy!
        is_rom_loaded = self.current_rom is not None and self.current_rom.valid
        state = "normal" if is_rom_loaded else "disabled"

        self.find_child_buttons(self, state) # Helper to disable all buttons initially

        # Specific elements that should be disabled if no ROM
        self.hex_rom_type.config(state=state)
        self.hex_offset_entry.config(state=state)
        self.hex_length_entry.config(state=state)
        self.edit_address_entry.config(state=state)
        self.edit_value_entry.config(state=state)
        self.search_bytes_entry.config(state=state)
        # The save button is outside tabs, manage directly
        save_button = [w for w in self.winfo_children() if isinstance(w, tk.Button) and w.cget("text") == "Save Modified ROM"]
        if save_button:
            save_button[0].config(state=state)

        # Always enable the "Open NES ROM" button, of course! We need to start somewhere!
        open_button = [w for w in self.winfo_children() if isinstance(w, tk.Button) and w.cget("text") == "Open NES ROM"]
        if open_button:
            open_button[0].config(state="normal")

        if not is_rom_loaded:
            self.info_text.config(text="No ROM loaded. Let's find one, purr! Your hacking adventure awaits!")
            self.opcode_area.config(state="normal")
            self.opcode_area.delete(1.0, tk.END)
            self.opcode_area.insert(tk.END, "Come on, open a ROM and see some cool bytes! Meow! Get ready for fun!")
            self.opcode_area.config(state="disabled")

            self.hex_display.config(state="normal")
            self.hex_display.delete(1.0, tk.END)
            self.hex_display.insert(tk.END, "Load a ROM to unleash the hex editor! Purrr! It's so exciting!")
            self.hex_display.config(state="disabled")

            self.search_results_text.config(state="normal")
            self.search_results_text.delete(1.0, tk.END)
            self.search_results_text.insert(tk.END, "Search for secrets once a ROM is loaded! Woohoo! The power is yours!")
            self.search_results_text.config(state="disabled")

    def find_child_buttons(self, widget, state):
        for child in widget.winfo_children():
            if isinstance(child, tk.Button):
                # Don't disable the Open button, it's special!
                if child.cget("text") != "Open NES ROM":
                    child.config(state=state)
            elif isinstance(child, ttk.Frame) or isinstance(child, tk.Frame):
                self.find_child_buttons(child, state) # Recurse into frames! So systematic!

    def load_rom(self):
        file_path = filedialog.askopenfilename(title="Select NES ROM, kitty! Let's get this party started!", filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")])
        if not file_path:
            return

        try:
            rom = NESRom(file_path)
            if not rom.valid:
                raise ValueError("Uh oh! Not a valid NES ROM (Missing header), meow! Try another one!")

            self.current_rom = rom # Store our lovely ROM object! It's our new best friend!

            info = (
                f"File: {file_path.split('/')[-1]}\n"
                f"PRG ROM Size: {rom.prg_rom_size // 1024} KB\n"
                f"CHR ROM Size: {rom.chr_rom_size // 1024} KB\n"
                f"Mapper: {rom.mapper}\n"
                f"Mirroring: {rom.mirroring}\n"
                f"Battery-backed RAM: {'Yes' if rom.battery else 'No'}\n"
                f"Trainer Present: {'Yes' if rom.trainer else 'No'}"
            )
            self.info_text.config(text=info)

            opcodes = rom.get_opcodes(16)
            self.opcode_area.config(state="normal")
            self.opcode_area.delete(1.0, tk.END)
            self.opcode_area.insert(tk.END, "First 16 PRG ROM bytes (hex):\n" + " ".join(opcodes))
            self.opcode_area.config(state="disabled")

            self.refresh_hex_view() # Load up the hex editor too! So cool, instant data view!
            self.update_ui_state() # Now all our awesome buttons are active! Yay, hacking time!

        except Exception as e:
            messagebox.showerror("CATNES ERROR", f"Mrow! Error loading ROM:\n{e}. Don't worry, we'll try again!")
            self.current_rom = None # Clear the ROM if it failed
            self.update_ui_state() # Disable buttons again, ready for a new try!

    def refresh_hex_view(self, event=None): # event argument for combobox binding, how handy!
        if not self.current_rom:
            return

        try:
            rom_type = self.hex_rom_type.get()
            offset = int(self.hex_offset_entry.get(), 16) # Hex input for offset, so precise!
            length = int(self.hex_length_entry.get()) # Decimal input for length, easy peasy!

            dump = self.current_rom.get_hex_dump(offset, length, rom_type)
            self.hex_display.config(state="normal")
            self.hex_display.delete(1.0, tk.END)
            self.hex_display.insert(tk.END, dump)
            self.hex_display.config(state="disabled")
        except ValueError as e:
            messagebox.showerror("CATNES Hex Editor", f"Oopsie! Input error: {e}. Please use valid hex for offset and decimal for length, meow! You got this!")
        except Exception as e:
            messagebox.showerror("CATNES Hex Editor", f"An unexpected error occurred while dumping: {e}. We'll fix it!")

    def modify_byte_action(self):
        if not self.current_rom:
            messagebox.showwarning("CATNES Modify", "No ROM loaded to modify, purr! Load one to begin your hacking journey!")
            return

        try:
            rom_type = self.hex_rom_type.get()
            address_str = self.edit_address_entry.get()
            new_value_str = self.edit_value_entry.get()

            address = int(address_str, 16) # Hex address! So advanced!
            
            # Perform the modification! This is where the real hacking fun begins! You're so powerful!
            result = self.current_rom.modify_byte(rom_type, address, new_value_str)
            messagebox.showinfo("CATNES Modify Result", result)
            self.refresh_hex_view() # Super important to see our changes! Yay, instant feedback!

        except ValueError as e:
            messagebox.showerror("CATNES Modify Error", f"Mrow! Input error: {e}. Check your hex values, kitty! You're almost a master!")
        except Exception as e:
            messagebox.showerror("CATNES Modify Error", f"An unexpected error occurred: {e}. Let's try again, meow!")

    def save_rom(self):
        if not self.current_rom:
            messagebox.showwarning("CATNES Save", "No ROM loaded to save, meow! Load one, make some changes, and save your masterpiece!")
            return

        # Let the user choose a new path, or overwrite! So much control, you're a true decision-maker!
        original_filename = self.current_rom.filepath.split('/')[-1]
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

        save_path = filedialog.asksaveasfilename(
            defaultextension=".nes",
            filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")],
            initialfile=f"hacked_{base_name}.nes", # A super cool default name!
            title="Save your hacked ROM! So exciting, make it official!"
        )
        if save_path:
            try:
                result = self.current_rom.save_rom(save_path)
                messagebox.showinfo("CATNES Save", result + " You are now a true ROM arch-mage! Purrr! So impressive!")
            except Exception as e:
                messagebox.showerror("CATNES Save Error", f"Oh no! Couldn't save the ROM:\n{e}. We'll figure it out!")

    def find_bytes_action(self):
        if not self.current_rom:
            messagebox.showwarning("CATNES Search", "No ROM loaded to search, meow! Load one to find those hidden gems!")
            return

        search_hex_str = self.search_bytes_entry.get().strip()
        if not search_hex_str:
            messagebox.showwarning("CATNES Search", "Please enter bytes to search for, kitty! Like a secret code!")
            return

        try:
            # Convert hex string to bytes, super tricky!
            search_bytes = bytes.fromhex(search_hex_str)
            
            results = []
            
            # Search PRG ROM! So many possibilities!
            if hasattr(self.current_rom, "prg_rom") and self.current_rom.prg_rom:
                prg_data = self.current_rom.prg_rom
                for i in range(len(prg_data) - len(search_bytes) + 1):
                    if prg_data[i:i+len(search_bytes)] == search_bytes:
                        results.append(f"Found in PRG ROM at relative address ${i:04X} (Absolute: ${self.current_rom.prg_rom_offset + i:08X})")

            # Search CHR ROM! Discover hidden graphics or patterns!
            if hasattr(self.current_rom, "chr_rom") and self.current_rom.chr_rom:
                chr_data = self.current_rom.chr_rom
                for i in range(len(chr_data) - len(search_bytes) + 1):
                    if chr_data[i:i+len(search_bytes)] == search_bytes:
                        results.append(f"Found in CHR ROM at relative address ${i:04X} (Absolute: ${self.current_rom.chr_rom_offset + i:08X})")

            self.search_results_text.config(state="normal")
            self.search_results_text.delete(1.0, tk.END)
            if results:
                self.search_results_text.insert(tk.END, "Hooray! Found these locations:\n" + "\n".join(results) + "\n\nYou're a super detective, meow!")
            else:
                self.search_results_text.insert(tk.END, "Mrow! No matches found. Try a different pattern, purr-haps? Keep searching for secrets!")
            self.search_results_text.config(state="disabled")

        except ValueError:
            messagebox.showerror("CATNES Search Error", "Purr-fect! Invalid hex string for search bytes. Please use valid hex, like 'C903', meow! You'll get it!")
        except Exception as e:
            messagebox.showerror("CATNES Search Error", f"An unexpected search error occurred: {e}. We'll figure it out together!")

    def rip_rom_section(self, rom_type):
        if not self.current_rom:
            messagebox.showwarning("CATNES Ripper", "No ROM loaded to rip, meow! Load one to start extracting awesome stuff!")
            return

        data_to_rip = None
        section_name = ""
        if rom_type == "PRG":
            data_to_rip = self.current_rom.prg_rom
            section_name = "PRG_ROM"
        elif rom_type == "CHR":
            data_to_rip = self.current_rom.chr_rom
            section_name = "CHR_ROM"
        else:
            messagebox.showerror("CATNES Ripper", "Invalid ROM section to rip, meow! Choose PRG or CHR, please!")
            return

        if not data_to_rip:
            messagebox.showwarning("CATNES Ripper", f"No {rom_type} data available to rip! Load a ROM first, kitty! We need data to play with!")
            return

        # Suggest a filename based on the original ROM and section, so cute!
        original_filename = self.current_rom.filepath.split('/')[-1]
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
            initialfile=f"{base_name}_{section_name}.bin",
            title=f"Save your ripped {section_name} data! So much fun to extract!"
        )
        if save_path:
            try:
                with open(save_path, "wb") as f:
                    f.write(data_to_rip)
                messagebox.showinfo("CATNES Ripper", f"Hooray! {section_name} ripped and saved to {save_path}! You've just pulled off a super cool data heist, purrfectly! You're amazing!")
            except Exception as e:
                messagebox.showerror("CATNES Ripper Error", f"Oh no! Couldn't rip the {section_name} data:\n{e}. Keep trying, you'll get it!")


if __name__ == "__main__":
    # Super cute style for our app! Making it look purr-fectly adorable!
    style = ttk.Style()
    style.theme_create("cattheme", parent="alt", settings={
        "TNotebook": {"configure": {"tabmargins": [2, 5, 2, 0], "background": "#e9eafc"}},
        "TNotebook.Tab": {
            "configure": {"padding": [10, 5], "background": "#b0c4de", "foreground": "#333", "font": ("Segoe UI", 11, "bold")},
            "map": {"background": [("selected", "#d3e0f0")], "foreground": [("selected", "#000")]}
        },
        "TFrame": {"configure": {"background": "#e9eafc"}}
    })
    style.theme_use("cattheme")

    app = CatNESApp()
    app.mainloop()
 
