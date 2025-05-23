import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk, Scale # We're using ttk for super cute tabs now! So much more organized!
import struct # For potential future binary operations, maybe for endianness for hex editor, how exciting!
import random # For the glorious DAMNATION ENGINE! Let's make things fucking unpredictable!

# --- Constants for the "Nesticle" Dark Theme ---
BG_COLOR = "#101010" # Dark as a demon's asshole
FG_COLOR = "#00FF00" # Classic hacker green, so fucking cool!
ALT_FG_COLOR = "#FF0000" # Blood red for errors and important shit!
ENTRY_BG_COLOR = "#202020" # Darker than your ex's heart
ENTRY_FG_COLOR = "#00DD00" # Bright green text for your evil inputs
BTN_BG_COLOR = "#400000" # Deep, menacing red for buttons
BTN_FG_COLOR = "#FF6060" # Lighter red for button text, pops right out!
TAB_BG_INACTIVE = "#1A1A1A"
TAB_FG_INACTIVE = "#808080"
TAB_BG_ACTIVE = "#000000"
TAB_FG_ACTIVE = "#00FF00"
FONT_FAMILY = "Consolas" # Good ol' reliable hacker font
FONT_SIZE_NORMAL = 10
FONT_SIZE_HEADER = 16
FONT_SIZE_TITLE = 20

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
        start_addr = 0 # This is the address WITHIN the PRG/CHR section for display
        abs_start_addr_rom = 0 # This is the absolute address in the FULL ROM file for display

        if rom_type == "PRG" and hasattr(self, "prg_rom"):
            data_to_dump = self.prg_rom
            start_addr = 0 # Relative to PRG start
            abs_start_addr_rom = self.prg_rom_offset
        elif rom_type == "CHR" and hasattr(self, "chr_rom"):
            data_to_dump = self.chr_rom
            start_addr = 0 # Relative to CHR start
            abs_start_addr_rom = self.chr_rom_offset
        else:
            return "No fucking data to dump, asshole! Select a ROM type first!"

        if not data_to_dump:
            return "No data available, load a goddamn ROM first, dumbass! We need bytes to fuck with!"

        dump_str = ""
        # Offset here is relative to the start of the selected PRG/CHR data
        actual_offset = max(0, min(offset, len(data_to_dump)))
        actual_length = min(length, len(data_to_dump) - actual_offset)

        for i in range(actual_offset, actual_offset + actual_length, 16):
            chunk = data_to_dump[i:i+16]
            hex_part = " ".join([f"{byte:02X}" for byte in chunk])
            ascii_part = "".join([chr(byte) if 32 <= byte < 127 else "." for byte in chunk])
            # Display address relative to selected ROM section, and absolute in file
            dump_str += f"{start_addr + i:04X} ({abs_start_addr_rom + i:08X}): {hex_part:<48} {ascii_part}\n"
        return dump_str

    def modify_byte(self, rom_type, address_in_rom, new_value):
        # Oh my goodness, we're changing bytes! Super powerful, you're a byte-bending wizard now!
        try:
            new_byte = int(new_value, 16) # Expecting hex string input, so cool and precise!
            if not (0 <= new_byte <= 255):
                raise ValueError("Byte value must be 00-FF, shithead! Don't fuck this up!")

            abs_address = -1
            target_data_len = 0
            if rom_type == "PRG":
                if not hasattr(self, "prg_rom"): raise ValueError("PRG ROM not loaded! Can't poke what's not there, moron!")
                target_data_len = self.prg_rom_size
                abs_address = self.prg_rom_offset + address_in_rom
            elif rom_type == "CHR":
                if not hasattr(self, "chr_rom"): raise ValueError("CHR ROM not loaded! No graphics to fuck up yet!")
                target_data_len = self.chr_rom_size
                abs_address = self.chr_rom_offset + address_in_rom
            else:
                raise ValueError("Invalid ROM type specified, dickweed! PRG or CHR, those are your fucking choices!")

            # address_in_rom is relative to the start of PRG or CHR
            if not (0 <= address_in_rom < target_data_len):
                raise ValueError(f"Address {address_in_rom:04X} out of {rom_type} ROM bounds! Stay within the goddamn lines!")

            if abs_address != -1 and 0 <= abs_address < len(self.data):
                self.data[abs_address] = new_byte # The actual byte modification! Woohoo!
                self.extract_rom_data() # Re-extract to update PRG/CHR views! Yay, changes everywhere!
                return f"Byte at {rom_type} address {address_in_rom:04X} (abs: {abs_address:08X}) changed to {new_value.upper()}! FUCK YEAH, you did it, you magnificent bastard!"
            else:
                return "Something went FUBAR with the address, dipshit! Double check your input!"
        except ValueError as e:
            return f"Goddamn error: {e}"
        except Exception as e:
            return f"An unexpected clusterfuck happened: {e}"

    def save_rom(self, new_filepath):
        # We're saving our super awesome modified ROM! This is making history, one byte at a time!
        with open(new_filepath, "wb") as f:
            f.write(self.data)
        self.filepath = new_filepath # Update the path! Meow! Your masterpiece is saved!
        return "ROM saved successfully! FUCKING BADASS! You've officially mangled it like a pro!"

    def find_bytes_in_section(self, data_section, section_offset, search_bytes_hex):
        found_locations = []
        try:
            search_sequence = bytes.fromhex(search_bytes_hex)
            if not search_sequence: return [] # Nothing to search for, idiot

            for i in range(len(data_section) - len(search_sequence) + 1):
                if data_section[i:i+len(search_sequence)] == search_sequence:
                    relative_addr = i
                    absolute_addr = section_offset + i
                    found_locations.append((relative_addr, absolute_addr))
            return found_locations
        except ValueError:
            raise ValueError("Invalid hex string for search. Use proper hex, dumbfuck.")
        except Exception as e:
            raise Exception(f"Some other bullshit happened during search: {e}")


    def damnation_engine_unleash(self, rom_type, mode, intensity_percent, xor_key_hex=None):
        # LET THE GODDAMN CHAOS BEGIN! YOU WANTED BLOODLUST, YOU GET BLOODLUST!
        target_data_array = None
        data_offset = 0

        if rom_type == "PRG":
            if not hasattr(self, "prg_rom") or not self.prg_rom:
                return "No PRG ROM to fucking mutilate! Load something first, dicknozzle!"
            # Operate on a copy for modification, then write back to self.data
            target_data_array = self.prg_rom[:] # Make a mutable copy
            data_offset = self.prg_rom_offset
        elif rom_type == "CHR":
            if not hasattr(self, "chr_rom") or not self.chr_rom:
                return "No CHR ROM to defile, you sick fuck! Get some graphics data in here!"
            target_data_array = self.chr_rom[:] # Make a mutable copy
            data_offset = self.chr_rom_offset
        else:
            return "What the FUCK are you trying to mutilate? PRG or CHR, pick one, asshole!"

        if not target_data_array:
             return "No data to fuck up. You're a disappointment."

        num_bytes_to_affect = int(len(target_data_array) * (intensity_percent / 100.0))
        if num_bytes_to_affect == 0:
            return "Zero intensity? Are you fucking kidding me? Go big or go home, pussy!"

        indices_to_affect = random.sample(range(len(target_data_array)), k=min(num_bytes_to_affect, len(target_data_array)))
        
        modified_count = 0
        for index in indices_to_affect:
            original_byte = target_data_array[index]
            if mode == "XOR Mayhem":
                if xor_key_hex is None: return "XOR Mayhem needs a goddamn XOR key, genius!"
                try:
                    key = int(xor_key_hex, 16)
                    if not (0 <= key <= 255): raise ValueError()
                    target_data_array[index] = original_byte ^ key
                    modified_count +=1
                except ValueError:
                    return "Invalid XOR key. Must be a single hex byte (00-FF), you fucking amateur."
            elif mode == "Random Garbage Fill":
                target_data_array[index] = random.randint(0, 255)
                modified_count +=1
            elif mode == "Byte Shift Storm":
                shift = random.randint(-15, 15) # More chaotic shift
                target_data_array[index] = (original_byte + shift) % 256
                modified_count +=1
            # Add more fucked up modes here later, this is just the beginning!
        
        # Write the mutilated data back into the main self.data bytearray
        for i, byte_val in enumerate(target_data_array):
            self.data[data_offset + i] = byte_val
        
        self.extract_rom_data() # Re-extract to make sure PRG/CHR views are updated with the carnage!

        return f"DAMNATION ENGINE HAS WROUGHT HAVOC! {modified_count} bytes in {rom_type} mercilessly MUTILATED with {mode}! FEEL THE POWER, YOU SICK BASTARD! HAHAHA!"


class VoidRipperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🔥 VoidRipper NES Mutilator 🔥 - Unleash Digital Hell!")
        self.geometry("800x700") # Bigger for more fucking mayhem!
        self.configure(bg=BG_COLOR) # Dark as my soul!
        self.current_rom = None # Our little ROM victim, waiting to be tortured!

        # --- Global Font Styles ---
        self.font_normal = (FONT_FAMILY, FONT_SIZE_NORMAL)
        self.font_bold = (FONT_FAMILY, FONT_SIZE_NORMAL, "bold")
        self.font_header = (FONT_FAMILY, FONT_SIZE_HEADER, "bold")
        self.font_title = (FONT_FAMILY, FONT_SIZE_TITLE, "bold")
        
        tk.Label(self, text="🔥 VOIDRIPPER NES MUTILATOR 🔥", font=self.font_title, bg=BG_COLOR, fg=ALT_FG_COLOR).pack(pady=10)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=5)

        self.create_info_tab()
        self.create_hex_editor_tab()
        self.create_hacking_tab()
        self.create_damnation_engine_tab() # OH FUCK YEAH, THE MAIN EVENT!
        self.create_ripper_tab()

        # --- Bottom Buttons ---
        button_frame = tk.Frame(self, bg=BG_COLOR)
        button_frame.pack(pady=10, fill="x", padx=10)

        self.open_button = tk.Button(button_frame, text="Open NES ROM", font=self.font_bold, command=self.load_rom, bg="#004000", fg="#60FF60", relief=tk.RAISED, borderwidth=2, padx=10)
        self.open_button.pack(side="left", padx=5, expand=True, fill="x")
        
        self.save_button = tk.Button(button_frame, text="Save Mangled ROM", font=self.font_bold, command=self.save_rom, bg=BTN_BG_COLOR, fg=BTN_FG_COLOR, relief=tk.RAISED, borderwidth=2, padx=10)
        self.save_button.pack(side="left", padx=5, expand=True, fill="x")

        self.status_bar_text = tk.StringVar()
        self.status_bar_text.set("Load a ROM to begin the fucking slaughter! HQRIPPER 7.1 ready for asset theft!")
        status_bar = tk.Label(self, textvariable=self.status_bar_text, font=(FONT_FAMILY, FONT_SIZE_NORMAL-1), bg=BG_COLOR, fg="#A0A0A0", bd=1, relief=tk.SUNKEN, anchor="w")
        status_bar.pack(side="bottom", fill="x", pady=2, padx=2)


        self.update_ui_state() # Initial state setup! Get this shit ready to party!

    def _create_styled_frame(self, parent):
        frame = tk.Frame(parent, bg=BG_COLOR, padx=10, pady=10)
        return frame

    def _create_styled_label(self, parent, text, font_style=None, fg=None):
        if font_style is None: font_style = self.font_normal
        if fg is None: fg = FG_COLOR
        return tk.Label(parent, text=text, font=font_style, bg=BG_COLOR, fg=fg)

    def _create_styled_button(self, parent, text, command, bg=BTN_BG_COLOR, fg=BTN_FG_COLOR):
        return tk.Button(parent, text=text, font=self.font_bold, command=command, bg=bg, fg=fg, relief=tk.RAISED, borderwidth=2, padx=5, pady=2)

    def _create_styled_entry(self, parent, width=10):
        return tk.Entry(parent, width=width, font=self.font_normal, bg=ENTRY_BG_COLOR, fg=ENTRY_FG_COLOR, insertbackground=FG_COLOR, relief=tk.SUNKEN, borderwidth=2)

    def _create_styled_scrolledtext(self, parent, width, height, state="disabled"):
        st = scrolledtext.ScrolledText(parent, width=width, height=height, font=self.font_normal, bg=ENTRY_BG_COLOR, fg=ENTRY_FG_COLOR, insertbackground=FG_COLOR, relief=tk.SUNKEN, borderwidth=2, state=state)
        st.tag_configure("error", foreground=ALT_FG_COLOR)
        return st

    def _create_styled_combobox(self, parent, values, default_value, readonly=True):
        # Styling Combobox is a bit tricky with direct tk, ttk styling is better here if needed
        # For now, basic ttk combobox
        combo = ttk.Combobox(parent, values=values, state="readonly" if readonly else "normal", width=10, font=self.font_normal)
        combo.set(default_value)
        # For darker theme, we might need to style the ttk.Combobox popdown list too
        # This requires more advanced ttk styling which can be platform dependent.
        # A simple `combo.config(background=ENTRY_BG_COLOR, foreground=ENTRY_FG_COLOR)` doesn't work well for ttk.
        return combo

    def create_info_tab(self):
        self.info_frame = self._create_styled_frame(self.notebook)
        self.notebook.add(self.info_frame, text="📈 ROM INHTELLIGENCE")

        self._create_styled_label(self.info_frame, "Here's the goddamn intel on your victim ROM!", font_style=self.font_header, fg=ALT_FG_COLOR).pack(pady=10)
        self.info_text_area = self._create_styled_scrolledtext(self.info_frame, width=70, height=10)
        self.info_text_area.pack(pady=5, fill="both", expand=True)
        self.info_text_area.config(state="normal")
        self.info_text_area.insert(tk.END, "No ROM loaded. Find a sacrifice, asshole!")
        self.info_text_area.config(state="disabled")

        self._create_styled_label(self.info_frame, "First few bytes of PRG ROM (The juicy bits!):", font_style=self.font_bold).pack(pady=(10,0), anchor="nw")
        self.opcode_area = self._create_styled_scrolledtext(self.info_frame, width=70, height=5)
        self.opcode_area.pack(pady=5, fill="x")

    def create_hex_editor_tab(self):
        self.hex_frame = self._create_styled_frame(self.notebook)
        self.notebook.add(self.hex_frame, text="🔩 HEX EDITOR")

        self._create_styled_label(self.hex_frame, "Time to peek and poke at bytes like a goddamn pervert!", font_style=self.font_header, fg=ALT_FG_COLOR).pack(pady=10)

        # Controls Frame
        controls_frame = tk.Frame(self.hex_frame, bg=BG_COLOR)
        controls_frame.pack(pady=5, fill="x")

        self._create_styled_label(controls_frame, "ROM Section:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.hex_rom_type_combo = self._create_styled_combobox(controls_frame, ["PRG", "CHR"], "PRG")
        self.hex_rom_type_combo.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        self.hex_rom_type_combo.bind("<<ComboboxSelected>>", self.refresh_hex_view)

        self._create_styled_label(controls_frame, "Offset (hex):").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.hex_offset_entry = self._create_styled_entry(controls_frame, width=12)
        self.hex_offset_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")
        self.hex_offset_entry.insert(0, "0000")

        self._create_styled_label(controls_frame, "Length (dec):").grid(row=1, column=2, padx=5, pady=2, sticky="w")
        self.hex_length_entry = self._create_styled_entry(controls_frame, width=8)
        self.hex_length_entry.grid(row=1, column=3, padx=5, pady=2, sticky="ew")
        self.hex_length_entry.insert(0, "256")
        
        self._create_styled_button(controls_frame, "Refresh View", self.refresh_hex_view, bg="#003366", fg="#66CCFF").grid(row=1, column=4, padx=10, pady=2)
        
        controls_frame.grid_columnconfigure(1, weight=1)
        controls_frame.grid_columnconfigure(3, weight=1)

        self.hex_display = self._create_styled_scrolledtext(self.hex_frame, width=90, height=15)
        self.hex_display.pack(pady=10, fill="both", expand=True)

        # Edit Frame
        edit_frame = tk.Frame(self.hex_frame, bg=BG_COLOR)
        edit_frame.pack(pady=10, fill="x")

        self._create_styled_label(edit_frame, "Addr (hex, relative):").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.edit_address_entry = self._create_styled_entry(edit_frame, width=10)
        self.edit_address_entry.grid(row=0, column=1, padx=5, pady=2)

        self._create_styled_label(edit_frame, "New Value (hex, 00-FF):").grid(row=0, column=2, padx=5, pady=2, sticky="w")
        self.edit_value_entry = self._create_styled_entry(edit_frame, width=5)
        self.edit_value_entry.grid(row=0, column=3, padx=5, pady=2)
        
        self._create_styled_button(edit_frame, "MODIFY BYTE! (FUCK IT UP!)", self.modify_byte_action, bg=ALT_FG_COLOR, fg="#FFFFFF").grid(row=0, column=4, padx=10, pady=2)

    def create_hacking_tab(self):
        self.hacking_frame = self._create_styled_frame(self.notebook)
        self.notebook.add(self.hacking_frame, text="🔍 BYTE SNIFFER")

        self._create_styled_label(self.hacking_frame, "Become a byte-sniffing pervert! Find those dirty secrets!", font_style=self.font_header, fg=ALT_FG_COLOR).pack(pady=10)

        search_frame = tk.Frame(self.hacking_frame, bg=BG_COLOR)
        search_frame.pack(pady=10, fill="x")
        self._create_styled_label(search_frame, "Search Bytes (hex, e.g., C903F0):").pack(side="left", padx=5)
        self.search_bytes_entry = self._create_styled_entry(search_frame, width=30)
        self.search_bytes_entry.pack(side="left", padx=5, expand=True, fill="x")
        self._create_styled_button(search_frame, "FIND THAT SHIT!", self.find_bytes_action, bg="#003366", fg="#66CCFF").pack(side="left", padx=10)

        self.search_results_text = self._create_styled_scrolledtext(self.hacking_frame, width=80, height=12)
        self.search_results_text.pack(pady=10, fill="both", expand=True)
        self.search_results_text.config(state="normal")
        self.search_results_text.insert(tk.END, "Load a ROM and start your goddamn treasure hunt, you greedy bastard!")
        self.search_results_text.config(state="disabled")

        self._create_styled_label(self.hacking_frame, "Imagine all the fucking cheats you can make! You're a digital god now!", font_style=self.font_bold, fg="#66FF66").pack(pady=10)


    def create_damnation_engine_tab(self):
        self.damnation_frame = self._create_styled_frame(self.notebook)
        self.notebook.add(self.damnation_frame, text="🔥 DAMNATION ENGINE 🔥")

        self._create_styled_label(self.damnation_frame, "WELCOME TO THE FUCKING DAMNATION ENGINE!", font_style=self.font_header, fg=ALT_FG_COLOR).pack(pady=10)
        self._create_styled_label(self.damnation_frame, "Time to mutilate this ROM beyond all recognition! This is where the REAL fun begins, you sick fuck!", font_style=self.font_normal, fg=FG_COLOR).pack(pady=5)

        # --- Controls Frame ---
        controls_frame = tk.Frame(self.damnation_frame, bg=BG_COLOR)
        controls_frame.pack(pady=20, fill="x")
        controls_frame.grid_columnconfigure(1, weight=1)


        self._create_styled_label(controls_frame, "Target Section:").grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.damnation_target_combo = self._create_styled_combobox(controls_frame, ["PRG", "CHR"], "PRG")
        self.damnation_target_combo.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self._create_styled_label(controls_frame, "Mutation Mode:").grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.damnation_mode_combo = self._create_styled_combobox(controls_frame, ["XOR Mayhem", "Random Garbage Fill", "Byte Shift Storm"], "XOR Mayhem")
        self.damnation_mode_combo.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        self.damnation_mode_combo.bind("<<ComboboxSelected>>", self.toggle_xor_key_entry)


        self.xor_key_label = self._create_styled_label(controls_frame, "XOR Key (hex, 00-FF):")
        self.xor_key_label.grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.damnation_xor_key_entry = self._create_styled_entry(controls_frame, width=6)
        self.damnation_xor_key_entry.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.damnation_xor_key_entry.insert(0, "FF")

        self._create_styled_label(controls_frame, "Intensity (% of bytes):").grid(row=3, column=0, padx=5, pady=5, sticky="e")
        self.damnation_intensity_scale = Scale(controls_frame, from_=1, to=100, orient=tk.HORIZONTAL, length=200, bg=BG_COLOR, fg=FG_COLOR, troughcolor=ENTRY_BG_COLOR, highlightbackground=BG_COLOR, font=self.font_normal)
        self.damnation_intensity_scale.set(10) # Default 10%
        self.damnation_intensity_scale.grid(row=3, column=1, padx=5, pady=5, sticky="w")

        unleash_button = tk.Button(self.damnation_frame, text="💥 UNLEASH MUTATION! 💥", font=(FONT_FAMILY, 14, "bold"), command=self.unleash_damnation_action, bg="#990000", fg="#FFFFFF", relief=tk.RAISED, borderwidth=3, padx=20, pady=10)
        unleash_button.pack(pady=30)

        self.damnation_status_label = self._create_styled_label(self.damnation_frame, "The engine slumbers... awaken it with a ROM!", font_style=self.font_normal, fg=ALT_FG_COLOR)
        self.damnation_status_label.pack(pady=10)
        
        self.toggle_xor_key_entry() # Set initial state of XOR key entry

    def toggle_xor_key_entry(self, event=None):
        if hasattr(self, 'damnation_mode_combo') and hasattr(self, 'xor_key_label') and hasattr(self, 'damnation_xor_key_entry'):
            if self.damnation_mode_combo.get() == "XOR Mayhem":
                self.xor_key_label.grid()
                self.damnation_xor_key_entry.grid()
            else:
                self.xor_key_label.grid_remove()
                self.damnation_xor_key_entry.grid_remove()


    def unleash_damnation_action(self):
        if not self.current_rom:
            messagebox.showerror("DAMNATION ERROR", "Load a fucking ROM before you try to unleash hell, you imbecile!", icon="error")
            self.damnation_status_label.config(text="Load a ROM, you moron. Can't mutilate nothing.")
            return

        target_section = self.damnation_target_combo.get()
        mode = self.damnation_mode_combo.get()
        intensity = self.damnation_intensity_scale.get()
        xor_key = None
        if mode == "XOR Mayhem":
            xor_key = self.damnation_xor_key_entry.get()
            if not xor_key or not (0 <= int(xor_key, 16) <= 255 if xor_key.isalnum() and len(xor_key) <= 2 else False): # basic validation
                 messagebox.showerror("DAMNATION ERROR", "XOR Key must be a valid hex byte (00-FF), fuckface!", icon="error")
                 self.damnation_status_label.config(text="Fix your shitty XOR key.")
                 return
        
        confirm = messagebox.askyesno("CONFIRM MUTILATION",
                                      f"Are you FUCKING SURE you want to unleash '{mode}'\n"
                                      f"on {intensity}% of the {target_section} ROM data?\n\n"
                                      "THIS IS IRREVERSIBLE (unless you didn't save, lol) AND WILL LIKELY FUCK YOUR ROM UP GOOD!",
                                      icon="warning", default="no")
        if not confirm:
            self.damnation_status_label.config(text="Pussied out, huh? The Damnation Engine scoffs at your cowardice.")
            return

        try:
            self.damnation_status_label.config(text=f"Unleashing {mode} on {target_section}... Stand back, this might get messy!")
            self.update() # Force UI update
            
            result = self.current_rom.damnation_engine_unleash(target_section, mode, intensity, xor_key)
            
            messagebox.showinfo("DAMNATION COMPLETE!", result, icon="info")
            self.damnation_status_label.config(text=result)
            self.refresh_hex_view() # Show the beautiful carnage!
            self.update_info_on_load() # Update opcodes if PRG was hit
            self.status_bar_text.set("ROM successfully mutilated! Save your masterpiece of destruction!")

        except Exception as e:
            error_msg = f"The Damnation Engine fucking choked: {e}"
            messagebox.showerror("DAMNATION FAILURE", error_msg, icon="error")
            self.damnation_status_label.config(text=error_msg)


    def create_ripper_tab(self):
        self.ripper_frame = self._create_styled_frame(self.notebook)
        self.notebook.add(self.ripper_frame, text="💰 ASSET THIEF (HQRIPPER 7.1)")

        self._create_styled_label(self.ripper_frame, "Rip those fucking assets! It's not theft if you call it 'archiving'!", font_style=self.font_header, fg=ALT_FG_COLOR).pack(pady=10)
        self._create_styled_label(self.ripper_frame, "Powered by the legendary HQRIPPER 7.1 and HQ-BANGER-SDK! Nothing is safe!", font_style=self.font_normal).pack(pady=5)

        rip_prg_frame = tk.Frame(self.ripper_frame, bg=BG_COLOR)
        rip_prg_frame.pack(pady=10, fill="x")
        self._create_styled_label(rip_prg_frame, "Wanna steal the PRG ROM? Program code is a treasure, grab it!").pack(side="left", padx=10)
        self._create_styled_button(rip_prg_frame, "RIP PRG ROM! (RAW AS FUCK)", lambda: self.rip_rom_section("PRG"), bg="#004d00", fg="#66ff66").pack(side="right", padx=10)

        rip_chr_frame = tk.Frame(self.ripper_frame, bg=BG_COLOR)
        rip_chr_frame.pack(pady=10, fill="x")
        self._create_styled_label(rip_chr_frame, "Or maybe the CHR ROM? Graphics for the taking, you digital pirate!").pack(side="left", padx=10)
        self._create_styled_button(rip_chr_frame, "RIP CHR ROM! (RAW AS FUCK)", lambda: self.rip_rom_section("CHR"), bg="#004d00", fg="#66ff66").pack(side="right", padx=10)

        self._create_styled_label(self.ripper_frame, "Remember, possession is 9/10ths of the law. The other 1/10th is running fast. GO GET 'EM!", font_style=self.font_bold, fg="#66FF66").pack(pady=20)

    def update_ui_state(self, is_rom_loaded=None):
        if is_rom_loaded is None:
            is_rom_loaded = self.current_rom is not None and self.current_rom.valid
        
        state = tk.NORMAL if is_rom_loaded else tk.DISABLED

        # Iterate through all child widgets of the notebook tabs and configure them
        for tab_name in self.notebook.tabs():
            tab_widget = self.notebook.nametowidget(tab_name)
            for child in tab_widget.winfo_children():
                self._configure_widget_state_recursively(child, state)
        
        # Special handling for widgets outside notebook or always enabled
        if hasattr(self, 'open_button'): self.open_button.config(state=tk.NORMAL) # Always enabled
        if hasattr(self, 'save_button'): self.save_button.config(state=state)
        
        # Update Hex Editor specific controls
        if hasattr(self, 'hex_rom_type_combo'): self.hex_rom_type_combo.config(state="readonly" if is_rom_loaded else tk.DISABLED)
        if hasattr(self, 'hex_offset_entry'): self.hex_offset_entry.config(state=state)
        if hasattr(self, 'hex_length_entry'): self.hex_length_entry.config(state=state)
        if hasattr(self, 'edit_address_entry'): self.edit_address_entry.config(state=state)
        if hasattr(self, 'edit_value_entry'): self.edit_value_entry.config(state=state)
        # Update Byte Sniffer specific controls
        if hasattr(self, 'search_bytes_entry'): self.search_bytes_entry.config(state=state)
        # Update Damnation Engine specific controls
        if hasattr(self, 'damnation_target_combo'): self.damnation_target_combo.config(state="readonly" if is_rom_loaded else tk.DISABLED)
        if hasattr(self, 'damnation_mode_combo'): self.damnation_mode_combo.config(state="readonly" if is_rom_loaded else tk.DISABLED)
        if hasattr(self, 'damnation_xor_key_entry'): self.damnation_xor_key_entry.config(state=state if self.damnation_mode_combo.get() == "XOR Mayhem" and is_rom_loaded else tk.DISABLED)
        if hasattr(self, 'damnation_intensity_scale'): self.damnation_intensity_scale.config(state=state)
        
        # Update text areas if no ROM is loaded
        if not is_rom_loaded:
            if hasattr(self, 'info_text_area'):
                self.info_text_area.config(state="normal")
                self.info_text_area.delete(1.0, tk.END)
                self.info_text_area.insert(tk.END, "No ROM loaded, dickhead. Feed me some data!")
                self.info_text_area.config(state="disabled")
            if hasattr(self, 'opcode_area'):
                self.opcode_area.config(state="normal")
                self.opcode_area.delete(1.0, tk.END)
                self.opcode_area.insert(tk.END, "Load a goddamn ROM to see its guts, you voyeur!")
                self.opcode_area.config(state="disabled")
            if hasattr(self, 'hex_display'):
                self.hex_display.config(state="normal")
                self.hex_display.delete(1.0, tk.END)
                self.hex_display.insert(tk.END, "Hex editor is hungry for bytes! Load a fucking ROM!")
                self.hex_display.config(state="disabled")
            if hasattr(self, 'search_results_text'):
                self.search_results_text.config(state="normal")
                self.search_results_text.delete(1.0, tk.END)
                self.search_results_text.insert(tk.END, "Can't sniff shit without a ROM, Sherlock. Load one up!")
                self.search_results_text.config(state="disabled")
            if hasattr(self, 'damnation_status_label'):
                self.damnation_status_label.config(text="The Damnation Engine sleeps... Load a ROM to awaken its destructive fury!")
            self.status_bar_text.set("Load a ROM to begin the fucking slaughter! HQRIPPER 7.1 ready for asset theft!")


    def _configure_widget_state_recursively(self, widget, state):
        # Exclude labels from being disabled unless they are part of a specific control group
        # that should be disabled. For simplicity, just disable common interactive widgets.
        if isinstance(widget, (tk.Button, tk.Entry, scrolledtext.ScrolledText, ttk.Combobox, Scale)):
            if widget != self.open_button : # Don't disable the open button
                 try: widget.config(state=state)
                 except tk.TclError: pass # Some widgets might not support state or already be fine
        
        # For ttk.Combobox, "readonly" is active, "disabled" is off.
        if isinstance(widget, ttk.Combobox):
            widget.config(state="readonly" if state == tk.NORMAL else tk.DISABLED)

        for child in widget.winfo_children():
            self._configure_widget_state_recursively(child, state)


    def load_rom(self):
        file_path = filedialog.askopenfilename(title="Select NES ROM to Violate!", filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")])
        if not file_path:
            self.status_bar_text.set("No ROM selected, you coward. Try again!")
            return

        try:
            rom = NESRom(file_path)
            if not rom.valid:
                raise ValueError("This ain't no NES ROM, you blind fuck! (Header's fucked or missing)")

            self.current_rom = rom
            self.update_info_on_load()
            self.refresh_hex_view() 
            self.update_ui_state(is_rom_loaded=True)
            self.status_bar_text.set(f"ROM LOADED: {file_path.split('/')[-1]}. LET THE MUTILATION BEGIN!")
            if hasattr(self, 'damnation_status_label'): self.damnation_status_label.config(text="ROM loaded! The Damnation Engine is HUNGRY!")

        except Exception as e:
            messagebox.showerror("ROM LOAD FUCKUP", f"Mothafucka! Error loading ROM:\n{e}. Don't worry, just try again, dumbass!", icon="error")
            self.current_rom = None
            self.update_ui_state(is_rom_loaded=False)
            self.status_bar_text.set("ROM loading failed. You suck. Try another one.")

    def update_info_on_load(self):
        if not self.current_rom or not self.current_rom.valid:
            return
        
        rom = self.current_rom
        info = (
            f"File: {rom.filepath.split('/')[-1]}\n"
            f"PRG ROM Size: {rom.prg_rom_size // 1024} KB ({rom.prg_rom_size} bytes) - That's a lot of code to fuck up!\n"
            f"CHR ROM Size: {rom.chr_rom_size // 1024} KB ({rom.chr_rom_size} bytes) - Graphics begging to be defiled!\n"
            f"Mapper: {rom.mapper} - The brains of the operation, let's give it a lobotomy!\n"
            f"Mirroring: {rom.mirroring}\n"
            f"Battery-backed RAM: {'YES, FUCKER!' if rom.battery else 'Nah, no battery saves here.'}\n"
            f"Trainer Present: {'OH SHIT, A TRAINER!' if rom.trainer else 'No trainer, boring.'}"
        )
        self.info_text_area.config(state="normal")
        self.info_text_area.delete(1.0, tk.END)
        self.info_text_area.insert(tk.END, info)
        self.info_text_area.config(state="disabled")

        opcodes = rom.get_opcodes(32) # More opcodes, more fun!
        self.opcode_area.config(state="normal")
        self.opcode_area.delete(1.0, tk.END)
        if opcodes:
            opcode_display = "First 32 PRG ROM bytes (hex):\n" + " ".join(opcodes[:16]) + "\n" + " ".join(opcodes[16:])
            self.opcode_area.insert(tk.END, opcode_display)
        else:
            self.opcode_area.insert(tk.END, "No PRG ROM data or too small to show opcodes. What a pathetic ROM.")
        self.opcode_area.config(state="disabled")


    def refresh_hex_view(self, event=None): 
        if not self.current_rom:
            return

        try:
            rom_type = self.hex_rom_type_combo.get()
            offset_str = self.hex_offset_entry.get()
            length_str = self.hex_length_entry.get()

            if not offset_str: offset_str = "0"
            if not length_str: length_str = "256"

            offset = int(offset_str, 16) 
            length = int(length_str)

            dump = self.current_rom.get_hex_dump(offset, length, rom_type)
            self.hex_display.config(state="normal")
            self.hex_display.delete(1.0, tk.END)
            self.hex_display.insert(tk.END, dump)
            self.hex_display.config(state="disabled")
            self.status_bar_text.set(f"Hex view for {rom_type} refreshed. Go on, stare at its guts.")
        except ValueError as e:
            messagebox.showerror("HEX EDITOR FUCKUP", f"Oopsie! Input error, shit-for-brains: {e}. Use valid hex for offset and decimal for length, goddamnit!", icon="error")
            self.status_bar_text.set(f"Hex view input error: {e}")
        except Exception as e:
            messagebox.showerror("HEX EDITOR CLUSTERFUCK", f"An unexpected pile of shit occurred while dumping: {e}. We'll probably ignore it!", icon="error")
            self.status_bar_text.set(f"Hex view unexpected error: {e}")

    def modify_byte_action(self):
        if not self.current_rom:
            messagebox.showwarning("MODIFY BYTE WARNING", "No ROM loaded to fuck with, you absolute buffoon! Load one to begin your reign of terror!", icon="warning")
            return

        try:
            rom_type = self.hex_rom_type_combo.get()
            address_str = self.edit_address_entry.get()
            new_value_str = self.edit_value_entry.get()

            if not address_str or not new_value_str:
                messagebox.showerror("MODIFY BYTE ERROR", "Address and New Value fields cannot be fucking empty, asshole!", icon="error")
                return

            address = int(address_str, 16) # Hex address! So advanced!
            
            result = self.current_rom.modify_byte(rom_type, address, new_value_str)
            
            if "FUCK YEAH" in result or "error" not in result.lower() and "fuckup" not in result.lower(): # Crude success check
                messagebox.showinfo("MODIFY BYTE SUCCESS!", result, icon="info")
                self.refresh_hex_view() # Super important to see our changes! Yay, instant feedback!
                self.update_info_on_load() # Opcode view might change
                self.status_bar_text.set(f"Byte modified! {result}")
            else:
                messagebox.showerror("MODIFY BYTE FAILURE", result, icon="error")
                self.status_bar_text.set(f"Byte modification FAILED: {result}")


        except ValueError as e:
            messagebox.showerror("MODIFY BYTE INPUT ERROR", f"Goddamnit! Input error: {e}. Check your hex values, numbskull! You're almost a master of disaster!", icon="error")
        except Exception as e:
            messagebox.showerror("MODIFY BYTE UNEXPECTED SHIT", f"An unexpected error occurred: {e}. What the fuck did you do?!", icon="error")

    def save_rom(self):
        if not self.current_rom:
            messagebox.showwarning("SAVE ROM WARNING", "No ROM loaded to save, dipshit! Load one, fuck it up, then save your glorious destruction!", icon="warning")
            return

        original_filename = self.current_rom.filepath.split('/')[-1]
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

        save_path = filedialog.asksaveasfilename(
            defaultextension=".nes",
            filetypes=[("NES ROMs", "*.nes"), ("All files", "*.*")],
            initialfile=f"mangled_AF_{base_name}.nes", # A super cool default name!
            title="Save your mangled ROM! Make your crimes permanent!"
        )
        if save_path:
            try:
                result = self.current_rom.save_rom(save_path)
                messagebox.showinfo("SAVE ROM SUCCESS!", result + " You are now a true ROM arch-demon! FUCKING HELL YEAH! So impressive!", icon="info")
                self.status_bar_text.set(f"Mangled ROM saved to: {save_path}. Your evil deed is done!")
            except Exception as e:
                messagebox.showerror("SAVE ROM FUCKUP", f"Oh for FUCK'S SAKE! Couldn't save the ROM:\n{e}. You probably don't have permission, or your hard drive is shit.", icon="error")
                self.status_bar_text.set(f"Saving ROM FAILED. What a loser.")

    def find_bytes_action(self):
        if not self.current_rom:
            messagebox.showwarning("BYTE SNIFFER WARNING", "No ROM loaded to sniff, you pervert! Load one to find those hidden nasties!", icon="warning")
            return

        search_hex_str = self.search_bytes_entry.get().strip().replace(" ", "") # Remove spaces for convenience
        if not search_hex_str:
            messagebox.showwarning("BYTE SNIFFER INPUT", "Please enter bytes to search for, dicknose! It's not telepathic!", icon="warning")
            return

        self.search_results_text.config(state="normal")
        self.search_results_text.delete(1.0, tk.END)
        self.search_results_text.insert(tk.END, f"Searching for hex sequence: {search_hex_str}...\nThis might take a while if the ROM or sequence is fucking huge...\n")
        self.update() # Force UI update

        try:
            all_results_output = []
            total_finds = 0

            # Search PRG ROM
            if hasattr(self.current_rom, "prg_rom") and self.current_rom.prg_rom:
                prg_results = self.current_rom.find_bytes_in_section(self.current_rom.prg_rom, self.current_rom.prg_rom_offset, search_hex_str)
                if prg_results:
                    all_results_output.append("--- FOUND IN PRG ROM --- (Relative Addr (Absolute Addr in File))")
                    for rel_addr, abs_addr in prg_results:
                        all_results_output.append(f"  ${rel_addr:04X} (${abs_addr:08X})")
                    total_finds += len(prg_results)
            
            # Search CHR ROM
            if hasattr(self.current_rom, "chr_rom") and self.current_rom.chr_rom:
                chr_results = self.current_rom.find_bytes_in_section(self.current_rom.chr_rom, self.current_rom.chr_rom_offset, search_hex_str)
                if chr_results:
                    all_results_output.append("--- FOUND IN CHR ROM --- (Relative Addr (Absolute Addr in File))")
                    for rel_addr, abs_addr in chr_results:
                        all_results_output.append(f"  ${rel_addr:04X} (${abs_addr:08X})")
                    total_finds += len(chr_results)

            if total_finds > 0:
                self.search_results_text.insert(tk.END, "\n".join(all_results_output))
                self.search_results_text.insert(tk.END, f"\n\nFUCK YEAH! Found {total_finds} occurrences! You're a goddamn byte detective, you magnificent bastard!")
                self.status_bar_text.set(f"Byte search complete. Found {total_finds} matches for '{search_hex_str}'.")
            else:
                self.search_results_text.insert(tk.END, f"Tough shit, asshole! No matches found for '{search_hex_str}'. Try a different pattern, or maybe you just suck at this.")
                self.status_bar_text.set(f"Byte search for '{search_hex_str}' found NOTHING. Loser.")

        except ValueError as e:
            self.search_results_text.insert(tk.END, f"\nVALUE ERROR: {e}\nMake sure your hex string is valid, dumbass (e.g., C903 or AA BB CC).")
            messagebox.showerror("BYTE SNIFFER ERROR", f"You fucked up the hex string: {e}. Use valid hex, like 'C903', not your fucking shopping list!", icon="error")
            self.status_bar_text.set(f"Byte search hex input error: {e}")
        except Exception as e:
            self.search_results_text.insert(tk.END, f"\nUNEXPECTED ERROR: {e}\nWell, that wasn't supposed to happen. Good job breaking it, asshole.")
            messagebox.showerror("BYTE SNIFFER CLUSTERFUCK", f"An unexpected search error occurred: {e}. The ROM probably hates you.", icon="error")
            self.status_bar_text.set(f"Byte search unexpected FUCKUP: {e}")
        finally:
            self.search_results_text.config(state="disabled")


    def rip_rom_section(self, rom_type):
        if not self.current_rom:
            messagebox.showwarning("ASSET THIEF WARNING", "No ROM loaded to steal from, you cheapskate! Load one to start your digital looting spree!", icon="warning")
            return

        data_to_rip = None
        section_name = ""
        if rom_type == "PRG":
            data_to_rip = self.current_rom.prg_rom
            section_name = "PRG_ROM_FUCKING_LOOT"
        elif rom_type == "CHR":
            data_to_rip = self.current_rom.chr_rom
            section_name = "CHR_ROM_GRAPHICS_SWAG"
        else:
            messagebox.showerror("ASSET THIEF ERROR", "Invalid ROM section to rip, moron! Choose PRG or CHR, it's not rocket science!", icon="error")
            return

        if not data_to_rip:
            messagebox.showwarning("ASSET THIEF FAIL", f"No {rom_type} data available to rip! Are you blind or just stupid? Load a ROM with some actual fucking data!", icon="warning")
            return

        original_filename = self.current_rom.filepath.split('/')[-1]
        base_name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename
        
        save_path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
            initialfile=f"{base_name}_{section_name}.bin",
            title=f"Save your STOLEN {section_name} data! Hoard it like a dragon!"
        )
        if save_path:
            try:
                with open(save_path, "wb") as f:
                    f.write(data_to_rip)
                messagebox.showinfo("ASSET THIEF SUCCESS!", f"FUCK YEAH! {section_name} ripped and saved to {save_path}! You've just pulled off a super cool data heist, you magnificent bastard! You're a digital fucking pirate king!", icon="info")
                self.status_bar_text.set(f"Ripped {section_name} to {save_path}. You're a master thief!")
            except Exception as e:
                messagebox.showerror("ASSET THIEF FUCKUP", f"Oh, for crying out loud! Couldn't rip the {section_name} data:\n{e}. Your computer probably hates you.", icon="error")
                self.status_bar_text.set(f"Ripping {section_name} FAILED. Epic fail.")


if __name__ == "__main__":
    style = ttk.Style()
    
    # --- Configure the "voidtheme" for a Nesticle-like dark appearance ---
    # This is a basic attempt. Full Nesticle look would require custom widget drawing.
    style.theme_create("voidtheme", parent="alt", settings={
        "TNotebook": {
            "configure": {"tabmargins": [2, 5, 2, 0], "background": BG_COLOR, "borderwidth":0}
        },
        "TNotebook.Tab": {
            "configure": {"padding": [10, 5], "background": TAB_BG_INACTIVE, "foreground": TAB_FG_INACTIVE, "font": (FONT_FAMILY, FONT_SIZE_NORMAL, "bold"), "borderwidth":1, "relief": "raised"},
            "map": {
                "background": [("selected", TAB_BG_ACTIVE)], 
                "foreground": [("selected", TAB_FG_ACTIVE)],
                "relief": [("selected", "sunken")]
                }
        },
        "TFrame": {"configure": {"background": BG_COLOR}},
        "TLabel": {"configure": {"background": BG_COLOR, "foreground": FG_COLOR, "font": (FONT_FAMILY, FONT_SIZE_NORMAL)}},
        "TButton": { # Basic TButton styling, direct tk.Button often gives more control for "raw" look
            "configure": {"background": BTN_BG_COLOR, "foreground": BTN_FG_COLOR, "font": (FONT_FAMILY, FONT_SIZE_NORMAL, "bold"), "relief":"raised", "borderwidth":2, "padding":5},
            "map": {"background": [("active", "#600000")]} # Darker red when pressed
        },
        "TCombobox": {
            "configure": {
                "fieldbackground": ENTRY_BG_COLOR, 
                "background": BTN_BG_COLOR, # Arrow button background
                "foreground": ENTRY_FG_COLOR, 
                "arrowcolor": FG_COLOR,
                "selectbackground": ENTRY_BG_COLOR, # Background of selected item in dropdown
                "selectforeground": FG_COLOR,
                "font": (FONT_FAMILY, FONT_SIZE_NORMAL)
            },
            "map": { # This is tricky and might not work on all platforms as expected
                "background": [('readonly', ENTRY_BG_COLOR)],
                "fieldbackground": [('readonly', ENTRY_BG_COLOR)],
                "foreground": [('readonly', ENTRY_FG_COLOR)],
            }
        },
        # Style for the Combobox dropdown list (TCombobox::popdown)
        # This is notoriously hard to style consistently across platforms with ttk
        # For simplicity, we might accept default popdown or use tk.OptionMenu if extreme styling needed
        "TComboboxPopdown": { "configure": {"background": ENTRY_BG_COLOR, "font": (FONT_FAMILY, FONT_SIZE_NORMAL)}},
        "Vertical.TScrollbar": {
            "configure": {"background": BTN_BG_COLOR, "troughcolor": ENTRY_BG_COLOR, "arrowcolor": FG_COLOR, "borderwidth":0},
            "map": {"background": [("active", ALT_FG_COLOR)]}
        }
    })
    style.theme_use("voidtheme")
    
    # Apply some global settings for tk widgets if needed (ttk doesn't cover everything)
    # Example:
    # root.option_add("*Font", (FONT_FAMILY, FONT_SIZE_NORMAL))
    # root.option_add("*Background", BG_COLOR)
    # root.option_add("*Foreground", FG_COLOR)

    app = VoidRipperApp()
    app.mainloop()
