import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from common import saveImage, loadImage
from PIL import Image, ImageTk
import threading
import time
import numpy as np

# --- ULTIMATE MODERN WIDGETS ---

class CustomButton(tk.Canvas):
    def __init__(self, master, text, command=None, color="#bb86fc", **kwargs):
        super().__init__(master, height=50, bg="#0a0a0a", highlightthickness=0, cursor="hand2", **kwargs)
        self.text = text
        self.command = command
        self.base_color = color
        self.hover_color = "#d7b7fd"
        self.current_color = color
        self.is_disabled = False
        self.glow_strength = 0
        
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Configure>", lambda e: self.draw())
        self.pulse()

    def draw(self, color=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        c = color or self.current_color
        if self.is_disabled: c = "#333333"
        
        self.create_rectangle(0, 0, w, h, fill=c, outline="")
        text_c = "#000000" if not self.is_disabled else "#888888"
        self.create_text(w//2, h//2, text=self.text, fill=text_c, font=("Segoe UI Bold", 11))

    def pulse(self):
        if not self.is_disabled:
            self.glow_strength = (np.sin(time.time() * 3) + 1) / 2
            self.draw()
        self.after(50, self.pulse)

    def on_enter(self, e): 
        if not self.is_disabled: self.current_color = self.hover_color
    def on_leave(self, e): 
        if not self.is_disabled: self.current_color = self.base_color
    def on_click(self, e):
        if not self.is_disabled and self.command: self.command()

    def config_state(self, state, text=None):
        self.is_disabled = (state == "disabled")
        if text: self.text = text
        self.draw()

class ModernSlider(tk.Canvas):
    def __init__(self, master, from_=1, to=10, initial=7, command=None, **kwargs):
        super().__init__(master, height=40, bg="#161616", highlightthickness=0, **kwargs)
        self.from_, self.to, self.val = from_, to, initial
        self.command = command
        self.padding = 30
        self.display_val = float(initial)
        
        self.bind("<Button-1>", self.click)
        self.bind("<B1-Motion>", self.click)
        self.bind("<Configure>", lambda e: self.draw())
        self.animate_slider()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        ty = h // 2
        self.create_line(self.padding, ty, w-self.padding, ty, fill="#2a2a2a", width=8, capstyle="round")
        ratio = (self.display_val - self.from_) / (self.to - self.from_)
        vx = self.padding + ratio * (w - 2 * self.padding)
        self.create_line(self.padding, ty, vx, ty, fill="#bb86fc", width=8, capstyle="round")
        self.create_oval(vx-12, ty-12, vx+12, ty+12, fill="#ffffff", outline="#bb86fc", width=3)

    def animate_slider(self):
        diff = self.val - self.display_val
        if abs(diff) > 0.05:
            self.display_val += diff * 0.3
            self.draw()
        self.after(20, self.animate_slider)

    def click(self, event):
        w = self.winfo_width()
        ratio = max(0, min(1, (event.x - self.padding) / (w - 2 * self.padding)))
        self.val = int(self.from_ + ratio * (self.to - self.from_))
        if self.command: self.command(self.val)

# --- THE ERGONOMIC APP ---

class WorstImageFormatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Worst IMage Format (WIMF)")
        self.root.geometry("800x950") # Expanded for Hyper-Tech Modules
        self.root.configure(bg="#0a0a0a")
        
        self.colors = {"bg": "#0a0a0a", "surface": "#161616", "accent": "#bb86fc", "neon": "#03dac6", "text": "#ffffff", "sub": "#888888"}
        
        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar(value="")
        self.motion_path = tk.StringVar(value="")
        
        self.compression_mode = tk.IntVar(value=2)
        self.preset = tk.StringVar(value="Extreme")
        
        # Hyper-Tech Variables
        self.opt_alpha = tk.BooleanVar()
        self.opt_hdr = tk.BooleanVar()
        self.opt_anim = tk.BooleanVar()
        self.opt_depth = tk.BooleanVar()
        self.opt_live = tk.BooleanVar()
        
        self.setup_styles()
        self.build_ui()
        self.fade_in_elements()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure("TCombobox", fieldbackground="#1a1a1a", background="#1a1a1a", foreground="white", borderwidth=0, arrowcolor="#bb86fc")
        self.root.option_add("*TCombobox*Listbox*Background", "#1a1a1a")
        self.root.option_add("*TCombobox*Listbox*Foreground", "white")

    def build_ui(self):
        self.main_container = tk.Frame(self.root, bg=self.colors["bg"])
        self.main_container.pack(expand=True, fill="both")

        # HERO
        hero = tk.Frame(self.main_container, bg=self.colors["bg"], pady=30)
        hero.pack(fill="x")
        tk.Label(hero, text="Worst IMage Format", font=("Segoe UI Semilight", 40), bg=self.colors["bg"], fg=self.colors["text"]).pack()
        tk.Label(hero, text="CREATED BY BENCHWARE", font=("Segoe UI Bold", 9), bg=self.colors["bg"], fg=self.colors["accent"]).pack()

        content = tk.Frame(self.main_container, bg=self.colors["bg"], padx=60)
        content.pack(expand=True, fill="both")

        self.create_modern_io(content, "SOURCE ASSET (IMAGE/WIMF)", self.input_path, self.browse_input)
        self.create_modern_io(content, "EXPORT DESTINATION", self.output_path, self.browse_output)

        # SETTINGS CARD
        self.card = tk.Frame(content, bg=self.colors["surface"], padx=35, pady=20, highlightthickness=1, highlightbackground="#252525")
        self.card.pack(fill="x", pady=15)

        r1 = tk.Frame(self.card, bg=self.colors["surface"])
        r1.pack(fill="x")

        # Modes
        m_f = tk.Frame(r1, bg=self.colors["surface"])
        m_f.pack(side="left")
        tk.Label(m_f, text="ENCODING METHOD", font=("Segoe UI Bold", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w")
        for t, v in [("RAW", 0), ("LOSSLESS", 1), ("LOSSY", 2)]:
            tk.Radiobutton(m_f, text=t, variable=self.compression_mode, value=v, bg=self.colors["surface"], fg="white", 
                           font=("Segoe UI Bold", 9), selectcolor="#333333", activebackground=self.colors["surface"],
                           activeforeground=self.colors["accent"], command=self.update_ui_states).pack(side="left", padx=(0, 15))

        # Preset
        p_f = tk.Frame(r1, bg=self.colors["surface"])
        p_f.pack(side="right")
        tk.Label(p_f, text="PRESET", font=("Segoe UI Bold", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w")
        self.preset_cb = ttk.Combobox(p_f, values=["Fast", "Balanced", "Extreme"], textvariable=self.preset, state="readonly", width=12)
        self.preset_cb.pack(pady=5)

        # Slider
        tk.Label(self.card, text="QUALITY", font=("Segoe UI Bold", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w", pady=(15, 0))
        tk.Label(self.card, text="Note: 1 is smallest size, 10 is max fidelity.", font=("Segoe UI Italic", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w", pady=(0, 5))
        
        self.slider = ModernSlider(self.card, from_=1, to=10, initial=7, command=self.update_q_label)
        self.slider.pack(fill="x", pady=5)
        
        self.q_label = tk.Label(self.card, text="LEVEL: 7", font=("Segoe UI Bold", 16), bg=self.colors["surface"], fg=self.colors["accent"])
        self.q_label.pack()

        # EXPERIMENTAL FEATURES
        ht_frame = tk.LabelFrame(self.card, text=" EXPERIMENTAL FEATURES ", font=("Segoe UI Bold", 8), 
                                 bg=self.colors["surface"], fg=self.colors["sub"], padx=15, pady=10, bd=1, highlightthickness=1)
        ht_frame.config(highlightbackground="#222222")
        ht_frame.pack(fill="x", pady=(15, 0))

        cb_style = {"bg": self.colors["surface"], "fg": "white", "font": ("Segoe UI Bold", 8), 
                    "selectcolor": "#222222", "activebackground": self.colors["surface"], 
                    "activeforeground": self.colors["accent"]}

        # Row 1 Checkboxes
        tk.Checkbutton(ht_frame, text="ALPHA (RGBA)", variable=self.opt_alpha, **cb_style).grid(row=0, column=0, sticky="w", padx=5)
        tk.Checkbutton(ht_frame, text="HDR (10-BIT)", variable=self.opt_hdr, **cb_style).grid(row=0, column=1, sticky="w", padx=5)
        tk.Checkbutton(ht_frame, text="ANIMATED", variable=self.opt_anim, **cb_style).grid(row=0, column=2, sticky="w", padx=5)
        
        # Row 2 Checkboxes
        tk.Checkbutton(ht_frame, text="DEPTH MAP", variable=self.opt_depth, **cb_style).grid(row=2, column=0, sticky="w", padx=5, pady=(5,0))
        tk.Checkbutton(ht_frame, text="LIVE PHOTO", variable=self.opt_live, command=self.toggle_live, **cb_style).grid(row=2, column=1, sticky="w", padx=5, pady=(5,0))

        # Descriptions (Row 1 & 3)
        lbl_style = {"bg": self.colors["surface"], "fg": "#666666", "font": ("Segoe UI", 7)}
        tk.Label(ht_frame, text="Lossless transparency", **lbl_style).grid(row=1, column=0, sticky="w", padx=25)
        tk.Label(ht_frame, text="High precision color", **lbl_style).grid(row=1, column=1, sticky="w", padx=25)
        tk.Label(ht_frame, text="Motion delta P-frames", **lbl_style).grid(row=1, column=2, sticky="w", padx=25)
        tk.Label(ht_frame, text="5-Channel 3D data", **lbl_style).grid(row=3, column=0, sticky="w", padx=25)
        tk.Label(ht_frame, text="Attach MP4/MOV to Image", **lbl_style).grid(row=3, column=1, sticky="w", padx=25)

        # Motion Path (Hidden by default)
        self.motion_frame = tk.Frame(ht_frame, bg=self.colors["surface"])
        tk.Label(self.motion_frame, text="MOTION VIDEO:", font=("Segoe UI Bold", 7), bg=self.colors["surface"], fg=self.colors["accent"]).pack(side="left")
        tk.Entry(self.motion_frame, textvariable=self.motion_path, bg="#111111", fg="white", bd=0, font=("Segoe UI", 8), width=12).pack(side="left", padx=5, ipady=3)
        tk.Button(self.motion_frame, text="...", command=self.browse_motion, bg="#222222", fg=self.colors["accent"], font=("Segoe UI Bold", 7), relief="flat").pack(side="left")

        # METADATA
        meta_f = tk.Frame(content, bg=self.colors["bg"])
        meta_f.pack(fill="x", pady=(0, 10))
        tk.Label(meta_f, text="AUTHOR TAG", font=("Segoe UI Bold", 8), bg=self.colors["bg"], fg=self.colors["sub"]).pack(anchor="w")
        self.author_entry = tk.Entry(meta_f, bg="#111111", fg="white", bd=0, font=("Segoe UI", 12), insertbackground="white")
        self.author_entry.pack(fill="x", ipady=8, pady=5)
        self.author_entry.insert(0, "BenchWare User")

        # CONSOLE
        self.console = tk.Text(content, height=4, bg="#000000", fg=self.colors["neon"], font=("Consolas", 10), padx=20, pady=15, bd=0)
        self.console.pack(fill="x", pady=10)

        # START BUTTON
        self.btn_run = CustomButton(content, text="START ENCODING SEQUENCE", command=self.run, color=self.colors["accent"])
        self.btn_run.pack(fill="x", pady=5)

    def fade_in_elements(self):
        self.main_container.place(relx=0.5, rely=0.55, anchor="center")
        def slide_up(curr_y):
            if curr_y > 0.5:
                self.main_container.place(relx=0.5, rely=curr_y, anchor="center")
                self.root.after(10, lambda: slide_up(curr_y - 0.005))
        slide_up(0.6)

    def create_modern_io(self, parent, label, var, cmd):
        f = tk.Frame(parent, bg=self.colors["bg"], pady=10)
        f.pack(fill="x")
        tk.Label(f, text=label, font=("Segoe UI Bold", 8), bg=self.colors["bg"], fg=self.colors["sub"]).pack(anchor="w")
        row = tk.Frame(f, bg=self.colors["bg"])
        row.pack(fill="x", pady=5)
        e = tk.Entry(row, textvariable=var, bg="#111111", fg="white", bd=0, font=("Segoe UI", 11), insertbackground="white")
        e.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 15))
        tk.Button(row, text="SEARCH", command=cmd, bg=self.colors["surface"], fg=self.colors["accent"], font=("Segoe UI Bold", 8), 
                  relief="flat", padx=20, cursor="hand2", activebackground="#222222").pack(side="right", fill="y")

    def update_q_label(self, v): self.q_label.config(text=f"LEVEL: {v}")

    def update_ui_states(self):
        is_l = self.compression_mode.get() == 2
        self.q_label.config(fg=self.colors["accent"] if is_l else "#333333")
        self.preset_cb.config(state="readonly" if is_l else "disabled")

    def toggle_live(self):
        if self.opt_live.get():
            self.motion_frame.grid(row=2, column=2, sticky="w", padx=5, pady=(5,0))
            self.opt_anim.set(False) # Live photo implies animated
        else:
            self.motion_frame.grid_forget()

    def log(self, m):
        self.console.config(state="normal")
        self.console.insert("end", f"> {m}\n")
        self.console.see("end")
        self.console.config(state="disabled")

    def browse_input(self):
        file_types = [
            ("All Supported", "*.wimf *.wif *.awif *.lwif *.png *.jpg *.jpeg *.bmp *.webp *.ppm *.mp4 *.mov"),
            ("Worst IMage Format", "*.wimf *.wif *.awif *.lwif"),
            ("Standard Images", "*.png *.jpg *.jpeg *.bmp *.webp *.ppm"),
            ("Video Files (For Live Photo)", "*.mp4 *.mov")
        ]
        p = filedialog.askopenfilename(filetypes=file_types)
        if p:
            self.input_path.set(p)
            ext = os.path.splitext(p)[1].lower()
            base = os.path.splitext(p)[0]
            if ext in ['.wimf', '.wif', '.awif', '.lwif']:
                self.output_path.set(base + ".png")
            elif ext in ['.mp4', '.mov']:
                self.output_path.set(base + ".lwif")
                self.opt_live.set(True) # Auto-check Live Photo
            else:
                self.output_path.set(base + ".wimf")
            self.log(f"Linked: {os.path.basename(p)}")

    def browse_output(self):
        file_types = [
            ("Worst IMage Format (.wimf)", "*.wimf"),
            ("Worst Animated Format (.awif)", "*.awif"),
            ("Worst Live Photo (.lwif)", "*.lwif"),
            ("PNG Image", "*.png"),
            ("JPEG Image", "*.jpg")
        ]
        p = filedialog.asksaveasfilename(filetypes=file_types, defaultextension=".wimf")
        if p: self.output_path.set(p)

    def browse_motion(self):
        file_types = [("Video Files", "*.mp4 *.mov *.avi *.mkv")]
        p = filedialog.askopenfilename(filetypes=file_types)
        if p:
            self.motion_path.set(p)
            self.log(f"Motion Linked: {os.path.basename(p)}")
        
    # Audio browser removed as FFMPEG handles it now

    def run(self):
        if not self.input_path.get() or not self.output_path.get(): return
        self.btn_run.config_state("disabled", "PROCESSING...")
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            in_p, out_p = self.input_path.get(), self.output_path.get()
            in_ext = os.path.splitext(in_p)[1].lower()
            
            if in_ext in ['.wimf', '.wif', '.awif', '.lwif']:
                # Extraction mode
                from common import loadImage
                w, h, pix, meta = loadImage(in_p)
                if isinstance(pix, list):
                    pix = pix[0]
                    self.root.after(0, lambda: self.log("Extracted Keyframe from sequence."))
                
                mode = 'RGBA' if meta.get('alpha') else 'RGB'
                Image.frombytes(mode, (w, h), pix).save(out_p)
                self.root.after(0, lambda: self.done(f"Extraction finalized."))
                
            else:
                # Encoding mode
                if in_ext in ['.mp4', '.mov']:
                    raise ValueError("Please select a STILL IMAGE as the Source Asset. To create a Live Photo, check the 'LIVE PHOTO' box and attach a Motion Video.")
                
                img = Image.open(in_p)
                if self.opt_alpha.get():
                    img = img.convert('RGBA')
                else:
                    img = img.convert('RGB')
                    
                w, h = img.size
                pixels = img.tobytes()
                
                meta = {"author": self.author_entry.get(), "engine": "WIMF Open Suite v18.5"}
                if self.opt_hdr.get(): meta['hdr'] = True
                if self.opt_depth.get(): meta['depth'] = True
                
                audio_bytes = None
                
                if self.opt_live.get():
                    meta['is_live_photo'] = True
                    m_path = self.motion_path.get()
                    if m_path and os.path.exists(m_path):
                        self.root.after(0, lambda: self.log("Extracting motion frames & Opus audio via FFMPEG..."))
                        from common import extract_video_data
                        vw, vh, vframes, audio_bytes = extract_video_data(m_path)
                        
                        # True Apple Live Photo: Still Image (I-Frame) + Resized Video Frames (P-Frames)
                        pixels = [pixels]
                        self.root.after(0, lambda: self.log(f"Aligning {len(vframes)} motion frames to keyframe..."))
                        for vf in vframes:
                            v_img = Image.frombytes('RGB', (vw, vh), vf).resize((w, h), Image.Resampling.LANCZOS)
                            if self.opt_alpha.get(): v_img = v_img.convert('RGBA')
                            pixels.append(v_img.tobytes())
                    else:
                        raise ValueError("Live Photo requires a valid Motion Video (MP4/MOV) path.")
                
                elif self.opt_anim.get():
                    meta['is_animated'] = True
                    pixels = [pixels, pixels] # Mock 2-frame loop for testing still images as animation
                
                self.root.after(0, lambda: self.log("Compressing data stream..."))
                from common import saveImage
                saveImage(out_p, w, h, pixels, 
                          compression=self.compression_mode.get(), quality=self.slider.val,
                          metadata=meta, preset=self.preset.get(), audio_bytes=audio_bytes)
                          
                self.root.after(0, lambda: self.done("Encoding sequence successful."))
                
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: self.log(f"FAIL: {msg}"))
            self.root.after(0, lambda: self.btn_run.config_state("normal", "START ENCODING SEQUENCE"))

    def done(self, m):
        self.log(m)
        self.log(f"Final Size: {os.path.getsize(self.output_path.get()):,} Bytes")
        self.btn_run.config_state("normal", "START ENCODING SEQUENCE")
        messagebox.showinfo("WIMF", "Task finished.")

if __name__ == "__main__":
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = WorstImageFormatApp(root)
    root.mainloop()
