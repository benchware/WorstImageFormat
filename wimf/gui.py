import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
from .io import saveImage, loadImage
from PIL import Image, ImageTk
import threading
import time
import numpy as np
import subprocess

def modern_file_picker(title="Select File", mode="open", default_ext=".wimf"):
    # Try Zenity (Standard on GNOME/many Arch setups)
    try:
        cmd = ["zenity", "--file-selection", f"--title={title}"]
        if mode == "save":
            cmd.extend(["--save", "--confirm-overwrite", f"--filename=output{default_ext}"])
        res = subprocess.check_output(cmd).decode().strip()
        if res: return res
    except: pass

    # Try KDialog (Standard on Plasma)
    try:
        cmd = ["kdialog", "--title", title]
        if mode == "save":
            cmd.extend(["--getsavefilename", ".", f"*{default_ext}"])
        else:
            cmd.append("--getopenfilename")
        res = subprocess.check_output(cmd).decode().strip()
        if res: return res
    except: pass

    # Fallback to Tkinter (The "outdated" one)
    if mode == "save":
        return filedialog.asksaveasfilename(title=title, defaultextension=default_ext)
    return filedialog.askopenfilename(title=title)

class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x, y, _, _ = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify='left', background="#1e1e1e", foreground="#ffffff", relief='solid', borderwidth=1, font=("Segoe UI", 8), padx=5, pady=3)
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw: tw.destroy()

class CustomButton(tk.Canvas):
    def __init__(self, master, text, command=None, color="#bb86fc", **kwargs):
        super().__init__(master, height=45, bg="#0a0a0a", highlightthickness=0, cursor="hand2", **kwargs)
        self.text = text
        self.command = command
        self.base_color = color
        self.hover_color = "#d7b7fd"
        self.current_color = color
        self.is_disabled = False
        self.bind("<Enter>", self.on_enter); self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click); self.bind("<Configure>", lambda e: self.draw())

    def draw(self, color=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        c = color or self.current_color
        if self.is_disabled: c = "#333333"
        self.create_rectangle(0, 0, w, h, fill=c, outline="")
        text_c = "#000000" if not self.is_disabled else "#888888"
        self.create_text(w//2, h//2, text=self.text, fill=text_c, font=("Segoe UI Bold", 10))

    def on_enter(self, e): 
        if not self.is_disabled: self.current_color = self.hover_color; self.draw()
    def on_leave(self, e): 
        if not self.is_disabled: self.current_color = self.base_color; self.draw()
    def on_click(self, e):
        if not self.is_disabled and self.command: self.command()

    def config_state(self, state, text=None):
        self.is_disabled = (state == "disabled")
        if text: self.text = text
        self.draw()

class ModernSlider(tk.Canvas):
    def __init__(self, master, from_=1, to=10, initial=7, command=None, **kwargs):
        super().__init__(master, height=35, bg="#161616", highlightthickness=0, **kwargs)
        self.from_, self.to, self.val = from_, to, initial
        self.command = command
        self.padding = 25
        self.display_val = float(initial)
        self.bind("<Button-1>", self.click); self.bind("<B1-Motion>", self.click)
        self.bind("<Configure>", lambda e: self.draw())
        self.animate_slider()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        ty = h // 2
        self.create_line(self.padding, ty, w-self.padding, ty, fill="#2a2a2a", width=6, capstyle="round")
        ratio = (self.display_val - self.from_) / (self.to - self.from_)
        vx = self.padding + ratio * (w - 2 * self.padding)
        self.create_line(self.padding, ty, vx, ty, fill="#bb86fc", width=6, capstyle="round")
        self.create_oval(vx-8, ty-8, vx+8, ty+8, fill="#ffffff", outline="#bb86fc", width=2)

    def animate_slider(self):
        diff = self.val - self.display_val
        if abs(diff) > 0.05:
            self.display_val += diff * 0.3; self.draw()
        self.after(20, self.animate_slider)

    def click(self, event):
        w = self.winfo_width()
        ratio = max(0, min(1, (event.x - self.padding) / (w - 2 * self.padding)))
        self.val = int(self.from_ + ratio * (self.to - self.from_))
        if self.command: self.command(self.val)

class WorstImageFormatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WIMF Studio")
        self.root.geometry("950x600")
        self.root.resizable(True, True)
        self.root.configure(bg="#0a0a0a")
        
        self.colors = {"bg": "#0a0a0a", "surface": "#161616", "accent": "#bb86fc", "neon": "#03dac6", "text": "#ffffff", "sub": "#888888"}
        
        self.input_path, self.output_path = tk.StringVar(), tk.StringVar()
        self.compression_mode = tk.IntVar(value=2)
        self.preset = tk.StringVar(value="Balanced")
        self.opt_alpha, self.opt_hdr, self.opt_10bit, self.opt_anim, self.opt_depth = [tk.BooleanVar() for _ in range(5)]
        self.gpu_mode = tk.StringVar(value="auto")
        self.show_preview = tk.BooleanVar(value=True)
        
        self.setup_styles(); self.build_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure("TCombobox", fieldbackground="#1a1a1a", background="#1a1a1a", foreground="white", borderwidth=0, arrowcolor="#bb86fc")
        self.root.option_add("*TCombobox*Listbox*Background", "#1a1a1a")
        self.root.option_add("*TCombobox*Listbox*Foreground", "white")

    def build_ui(self):
        body = tk.Frame(self.root, bg=self.colors["bg"])
        body.pack(expand=True, fill="both", pady=10)
        
        lp = tk.Frame(body, bg=self.colors["bg"], padx=40); lp.pack(side="left", fill="both", expand=True)
        rp = tk.Frame(body, bg=self.colors["bg"], padx=30); rp.pack(side="right", fill="both", expand=False)

        tk.Label(lp, text="WIMF Studio", font=("Segoe UI Semilight", 28), bg=self.colors["bg"], fg=self.colors["text"]).pack(pady=(0, 20))
        
        self.create_io(lp, "SOURCE ASSET", self.input_path, self.browse_input)
        self.create_io(lp, "EXPORT DESTINATION", self.output_path, self.browse_output)

        card = tk.Frame(lp, bg=self.colors["surface"], padx=20, pady=15, highlightthickness=1, highlightbackground="#252525")
        card.pack(fill="x", pady=10)

        r1 = tk.Frame(card, bg=self.colors["surface"]); r1.pack(fill="x")
        m_f = tk.Frame(r1, bg=self.colors["surface"]); m_f.pack(side="left")
        tk.Label(m_f, text="ENCODING METHOD", font=("Segoe UI Bold", 7), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w")
        for t, v in [("RAW", 0), ("LOSSLESS", 1), ("LOSSY", 2)]:
            tk.Radiobutton(m_f, text=t, variable=self.compression_mode, value=v, bg=self.colors["surface"], fg="white", font=("Segoe UI Bold", 8), selectcolor="#333333", command=self.update_ui).pack(side="left", padx=(0, 15))

        p_f = tk.Frame(r1, bg=self.colors["surface"]); p_f.pack(side="right")
        tk.Label(p_f, text="PRESET / GPU", font=("Segoe UI Bold", 7), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w")
        cb_f = tk.Frame(p_f, bg=self.colors["surface"]); cb_f.pack()
        self.preset_cb = ttk.Combobox(cb_f, values=["Fast", "Balanced", "Extreme"], textvariable=self.preset, state="readonly", width=10, font=("Segoe UI", 8))
        self.preset_cb.pack(side="left", padx=2)
        self.gpu_cb = ttk.Combobox(cb_f, values=["off", "auto", "opengl", "vulkan"], textvariable=self.gpu_mode, state="readonly", width=8, font=("Segoe UI", 8))
        self.gpu_cb.pack(side="left", padx=2)

        sf = tk.Frame(card, bg=self.colors["surface"]); sf.pack(fill="x", pady=(15, 0))
        tk.Label(sf, text="COMPRESSION QUALITY", font=("Segoe UI Bold", 7), bg=self.colors["surface"], fg=self.colors["sub"]).pack(side="left")
        self.q_label = tk.Label(sf, text="7", font=("Segoe UI Bold", 12), bg=self.colors["surface"], fg=self.colors["accent"]); self.q_label.pack(side="right")
        self.slider = ModernSlider(card, from_=1, to=10, initial=7, command=self.update_q_label); self.slider.pack(fill="x", pady=5)

        tk.Label(rp, text="LIVE PREVIEW", font=("Segoe UI Bold", 11), bg=self.colors["bg"], fg=self.colors["sub"]).pack(pady=(5, 10))
        self.pc = tk.Frame(rp, bg="#111111", width=320, height=320, highlightthickness=1, highlightbackground="#333333")
        self.pc.pack_propagate(False); self.pc.pack(pady=5)
        self.pl = tk.Label(self.pc, bg="#111111"); self.pl.pack(expand=True, fill="both")
        
        self.rmse_l = tk.Label(rp, text="RMSE: 0.0000", font=("Consolas", 12), bg=self.colors["bg"], fg=self.colors["neon"]); self.rmse_l.pack(pady=10)
        tk.Checkbutton(rp, text="ENABLE PREVIEW", variable=self.show_preview, bg=self.colors["bg"], fg="white", font=("Segoe UI Bold", 8), selectcolor="#222222").pack(pady=5)

        tk.Label(lp, text="EXPERIMENTAL FEATURES", font=("Segoe UI Bold", 8), bg=self.colors["bg"], fg=self.colors["sub"]).pack(anchor="w", pady=(15, 0))
        hf = tk.Frame(lp, bg=self.colors["bg"], pady=10); hf.pack(fill="x")
        
        c_alpha = tk.Checkbutton(hf, text="ALPHA CHANNEL", variable=self.opt_alpha, bg=self.colors["bg"], fg="white", font=("Segoe UI Bold", 8), selectcolor="#222222")
        c_alpha.grid(row=0, column=0, sticky="w", padx=(0, 20))
        Tooltip(c_alpha, "Preserve transparency using a lossless Paeth-predicted sub-stream.")

        c_10bit = tk.Checkbutton(hf, text="10-BIT DEPTH", variable=self.opt_10bit, bg=self.colors["bg"], fg="white", font=("Segoe UI Bold", 8), selectcolor="#222222")
        c_10bit.grid(row=0, column=1, sticky="w", padx=(0, 20))
        Tooltip(c_10bit, "Increase color precision to 1024 levels per channel for HDR content.")

        c_anim = tk.Checkbutton(hf, text="ANIMATION", variable=self.opt_anim, bg=self.colors["bg"], fg="white", font=("Segoe UI Bold", 8), selectcolor="#222222")
        c_anim.grid(row=0, column=2, sticky="w")
        Tooltip(c_anim, "Encode multiple frames using temporal Wavelet delta compression (AWIF).")

        self.console = tk.Text(lp, height=3, bg="#000000", fg=self.colors["neon"], font=("Consolas", 9), padx=10, pady=10, bd=0)
        self.console.pack(fill="x", pady=10)
        self.btn_run = CustomButton(lp, text="START ENCODING SEQUENCE", command=self.run, color=self.colors["accent"]); self.btn_run.pack(fill="x", pady=10)

    def create_io(self, parent, label, var, cmd):
        f = tk.Frame(parent, bg=self.colors["bg"], pady=5); f.pack(fill="x")
        tk.Label(f, text=label, font=("Segoe UI Bold", 7), bg=self.colors["bg"], fg=self.colors["sub"]).pack(anchor="w")
        row = tk.Frame(f, bg=self.colors["bg"]); row.pack(fill="x", pady=2)
        tk.Entry(row, textvariable=var, bg="#111111", fg="white", bd=0, font=("Segoe UI", 10), insertbackground="white").pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 10))
        tk.Button(row, text="SEARCH", command=cmd, bg=self.colors["surface"], fg=self.colors["accent"], font=("Segoe UI Bold", 8), relief="flat", padx=15, cursor="hand2").pack(side="right", fill="y")

    def update_q_label(self, v): self.q_label.config(text=str(v))
    def update_ui(self):
        is_lossy = self.compression_mode.get() == 2
        self.q_label.config(fg=self.colors["accent"] if is_lossy else "#333333")
        self.preset_cb.config(state="readonly" if is_lossy else "disabled")

    def log(self, m):
        self.console.config(state="normal"); self.console.insert("end", f"> {m}\n"); self.console.see("end"); self.console.config(state="disabled")

    def browse_input(self):
        p = modern_file_picker(title="Select Source Image", mode="open")
        if p: self.input_path.set(p); self.log(f"Linked: {os.path.basename(p)}")

    def browse_output(self):
        p = modern_file_picker(title="Select Export Path", mode="save", default_ext=".wimf")
        if p: self.output_path.set(p)

    def run(self):
        if not self.input_path.get() or not self.output_path.get(): return
        self.btn_run.config_state("disabled", "PROCESSING..."); threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            meta = {"engine": "WIMF v19.0", "bit10": self.opt_10bit.get(), "alpha": self.opt_alpha.get(), "is_animated": self.opt_anim.get(), "gpu_mode": self.gpu_mode.get()}
            from .cli import convert
            convert(input_path=self.input_path.get(), output_path=self.output_path.get(), compression=self.compression_mode.get(), quality=self.slider.val, preset=self.preset.get(), meta=meta)
            self.root.after(0, lambda: self.log("Done."))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"Error: {e}"))
        finally:
            self.root.after(0, lambda: self.btn_run.config_state("normal", "START ENCODING SEQUENCE"))

def main():
    root = tk.Tk()
    app = WorstImageFormatApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
