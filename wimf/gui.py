import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import subprocess
import threading
import time
import numpy as np
from PIL import Image, ImageTk, ImageSequence

def modern_file_picker(title="Select File", mode="open", default_ext=".wimf"):
    if os.name == 'nt':
        if mode == "save": return filedialog.asksaveasfilename(title=title, defaultextension=default_ext)
        return filedialog.askopenfilename(title=title)

    # Check for Zenity
    if os.path.exists("/usr/bin/zenity"):
        try:
            cmd = ["zenity", "--file-selection", f"--title={title}"]
            if mode == "save": cmd.extend(["--save", "--confirm-overwrite", f"--filename=output{default_ext}"])
            res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            return res if res else None
        except subprocess.CalledProcessError as e:
            if e.returncode == 1: return None # User cancelled
        except: pass

    # Check for KDialog
    if os.path.exists("/usr/bin/kdialog"):
        try:
            cmd = ["kdialog", "--title", title]
            if mode == "save": cmd.extend(["--getsavefilename", ".", f"*{default_ext}"])
            else: cmd.append("--getopenfilename")
            res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            return res if res else None
        except subprocess.CalledProcessError as e:
            if e.returncode == 1: return None # User cancelled
        except: pass

    # Fallback to Tkinter only if native tools fail/missing
    if mode == "save": return filedialog.asksaveasfilename(title=title, defaultextension=default_ext)
    return filedialog.askopenfilename(title=title)

class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip_window = widget, text, None
        widget.bind("<Enter>", self.show_tip); widget.bind("<Leave>", self.hide_tip)
    def show_tip(self, event=None):
        if self.tip_window or not self.text: return
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25; y += self.widget.winfo_rooty() + 20
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True); tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify='left', background="#111", foreground="#fff", relief='solid', borderwidth=1, font=("Segoe UI", 8), padx=5, pady=3).pack()
    def hide_tip(self, event=None):
        tw = self.tip_window; self.tip_window = None
        if tw: tw.destroy()

class ModernCheckbox(tk.Canvas):
    def __init__(self, master, text, variable, command=None, **kwargs):
        super().__init__(master, width=160, height=30, bg="#050505", highlightthickness=0, cursor="hand2", **kwargs)
        self.text, self.variable, self.command = text, variable, command
        self.bind("<Button-1>", self.toggle); self.draw()
    def toggle(self, event=None):
        self.variable.set(not self.variable.get())
        if self.command: self.command()
        self.draw()
    def draw(self):
        self.delete("all")
        v = self.variable.get()
        accent = "#bb86fc" if v else "#222"
        self.create_rectangle(5, 5, 25, 25, fill="#111", outline=accent, width=2)
        if v: self.create_text(15, 15, text="✦", fill="#bb86fc", font=("Segoe UI Bold", 12))
        self.create_text(35, 15, text=self.text, fill="#eee" if v else "#777", font=("Segoe UI Bold", 9), anchor="w")

class CustomButton(tk.Canvas):
    def __init__(self, master, text, command=None, color="#bb86fc", **kwargs):
        super().__init__(master, height=50, bg="#050505", highlightthickness=0, cursor="hand2", **kwargs)
        self.text, self.command, self.base_color = text, command, color
        self.hover_color, self.current_color, self.is_disabled = "#d7b7fd", color, False
        self.bind("<Enter>", self.on_enter); self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click); self.bind("<Configure>", lambda e: self.draw())
    def draw(self, color=None):
        self.delete("all"); w, h = self.winfo_width(), self.winfo_height()
        c = color or self.current_color
        if self.is_disabled: c = "#222"
        self.create_rectangle(0, 0, w, h, fill=c, outline="")
        self.create_text(w//2, h//2, text=self.text, fill="#000" if not self.is_disabled else "#555", font=("Segoe UI Bold", 11))
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
        super().__init__(master, height=45, bg="#0f0f0f", highlightthickness=0, **kwargs)
        self.from_, self.to, self.val = from_, to, initial
        self.command, self.padding, self.display_val = command, 30, float(initial)
        self.bind("<Button-1>", self.click); self.bind("<B1-Motion>", self.click)
        self.bind("<Configure>", lambda e: self.draw()); self.animate()
    def draw(self):
        self.delete("all"); w, h = self.winfo_width(), self.winfo_height(); ty = h // 2
        self.create_line(self.padding, ty, w-self.padding, ty, fill="#222", width=10, capstyle="round")
        ratio = (self.display_val - self.from_) / (self.to - self.from_)
        vx = self.padding + ratio * (w - 2 * self.padding)
        self.create_line(self.padding, ty, vx, ty, fill="#bb86fc", width=10, capstyle="round")
        self.create_oval(vx-12, ty-12, vx+12, ty+12, fill="#fff", outline="#bb86fc", width=3)
    def animate(self):
        diff = self.val - self.display_val
        if abs(diff) > 0.05: self.display_val += diff * 0.3; self.draw()
        self.after(20, self.animate)
    def click(self, event):
        w = self.winfo_width(); ratio = max(0, min(1, (event.x - self.padding) / (w - 2 * self.padding)))
        self.val = int(self.from_ + ratio * (self.to - self.from_))
        if self.command: self.command(self.val)

class WorstImageFormatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WIMF STUDIO PRO")
        self.root.geometry("1000x680")
        self.root.configure(bg="#050505")
        
        self.colors = {"bg": "#050505", "surface": "#0f0f0f", "accent": "#bb86fc", "neon": "#03dac6", "text": "#ffffff", "sub": "#555"}
        
        self.input_path, self.output_path = tk.StringVar(), tk.StringVar()
        self.compression_mode = tk.IntVar(value=2)
        self.preset = tk.StringVar(value="Balanced")
        self.opt_alpha = tk.BooleanVar(value=True)
        self.opt_hdr, self.opt_10bit, self.opt_anim = [tk.BooleanVar() for _ in range(3)]
        self.gpu_mode, self.show_preview = tk.StringVar(value="auto"), tk.BooleanVar(value=True)
        
        self.setup_styles(); self.build_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground="#111", background="#111", foreground="#fff", borderwidth=0, arrowcolor="#bb86fc")
        style.map("TCombobox", fieldbackground=[('readonly', "#111")], background=[('readonly', "#111")])
        self.root.option_add("*TCombobox*Listbox*Background", "#111")
        self.root.option_add("*TCombobox*Listbox*Foreground", "white")

    def build_ui(self):
        header = tk.Frame(self.root, bg="#000", height=60); header.pack(fill="x")
        tk.Label(header, text="WIMF", font=("Impact", 24), bg="#000", fg="#fff", padx=20).pack(side="left")
        tk.Label(header, text="STUDIO PRO v19.0", font=("Segoe UI Bold", 10), bg="#000", fg=self.colors["accent"]).pack(side="left", pady=(10,0))
        
        main = tk.Frame(self.root, bg="#050505", padx=30, pady=20); main.pack(expand=True, fill="both")
        lp = tk.Frame(main, bg="#050505"); lp.pack(side="left", fill="both", expand=True)
        rp = tk.Frame(main, bg="#050505", padx=20); rp.pack(side="right", fill="both")

        # IO Section
        self.create_io(lp, "SOURCE ASSET", self.input_path, self.browse_input)
        self.create_io(lp, "EXPORT PATH", self.output_path, self.browse_output)

        # Core Config Card
        card = tk.Frame(lp, bg=self.colors["surface"], padx=25, pady=20, highlightthickness=1, highlightbackground="#1a1a1a")
        card.pack(fill="x", pady=20)
        
        r1 = tk.Frame(card, bg=self.colors["surface"]); r1.pack(fill="x")
        m_f = tk.Frame(r1, bg=self.colors["surface"]); m_f.pack(side="left")
        tk.Label(m_f, text="ENGINE MODE", font=("Segoe UI Bold", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w", pady=(0,5))
        for t, v in [("RAW", 0), ("LOSSLESS", 1), ("LOSSY", 2)]:
            tk.Radiobutton(m_f, text=t, variable=self.compression_mode, value=v, bg=self.colors["surface"], fg="#fff", font=("Segoe UI Bold", 9), selectcolor="#000", command=self.update_ui, activebackground=self.colors["surface"]).pack(side="left", padx=(0, 20))

        p_f = tk.Frame(r1, bg=self.colors["surface"]); p_f.pack(side="right")
        tk.Label(p_f, text="PRESET / ACCELERATION", font=("Segoe UI Bold", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(anchor="w", pady=(0,5))
        cb_f = tk.Frame(p_f, bg=self.colors["surface"]); cb_f.pack()
        self.preset_cb = ttk.Combobox(cb_f, values=["Fast", "Balanced", "Extreme"], textvariable=self.preset, state="readonly", width=12)
        self.preset_cb.pack(side="left", padx=5)
        self.gpu_cb = ttk.Combobox(cb_f, values=["off", "auto", "opengl", "vulkan"], textvariable=self.gpu_mode, state="readonly", width=8)
        self.gpu_cb.pack(side="left")

        # Quality
        sf = tk.Frame(card, bg=self.colors["surface"]); sf.pack(fill="x", pady=(20, 0))
        tk.Label(sf, text="COMPRESSION INTENSITY", font=("Segoe UI Bold", 8), bg=self.colors["surface"], fg=self.colors["sub"]).pack(side="left")
        self.q_label = tk.Label(sf, text="7", font=("Impact", 18), bg=self.colors["surface"], fg=self.colors["accent"]); self.q_label.pack(side="right")
        self.slider = ModernSlider(card, from_=1, to=10, initial=7, command=self.update_q_label); self.slider.pack(fill="x", pady=10)

        # Experimental
        tk.Label(lp, text="FEATURE DASHBOARD", font=("Segoe UI Bold", 8), bg="#050505", fg=self.colors["sub"]).pack(anchor="w", pady=(10, 5))
        hf = tk.Frame(lp, bg="#050505"); hf.pack(fill="x")
        self.check_alpha = ModernCheckbox(hf, "TRANSPARENCY", self.opt_alpha); self.check_alpha.grid(row=0, column=0)
        self.check_hdr = ModernCheckbox(hf, "HDR METADATA", self.opt_hdr, command=self.toggle_hdr); self.check_hdr.grid(row=0, column=1)
        self.check_10bit = ModernCheckbox(hf, "10-BIT HDR", self.opt_10bit, command=self.toggle_10bit); self.check_10bit.grid(row=1, column=0)
        self.check_anim = ModernCheckbox(hf, "ANIMATION (AWIF)", self.opt_anim); self.check_anim.grid(row=1, column=1)
        
        for c, t in [(self.check_alpha, "Lossless alpha layer."), (self.check_hdr, "Standard HDR hints."), (self.check_10bit, "1024-step color."), (self.check_anim, "Wavelet motion.")]: Tooltip(c, t)

        # Right Panel - Dashboard
        tk.Label(rp, text="VISUAL PIPELINE", font=("Segoe UI Bold", 10), bg="#050505", fg=self.colors["sub"]).pack(pady=(0, 10))
        self.pc = tk.Frame(rp, bg="#000", width=360, height=360, highlightthickness=2, highlightbackground="#111")
        self.pc.pack_propagate(False); self.pc.pack()
        self.pl = tk.Label(self.pc, bg="#000"); self.pl.pack(expand=True, fill="both")
        
        stats = tk.Frame(rp, bg="#000", pady=15, highlightthickness=1, highlightbackground="#1a1a1a")
        stats.pack(fill="x", pady=20)
        self.rmse_l = tk.Label(stats, text="RMSE: 0.0000", font=("Consolas Bold", 14), bg="#000", fg=self.colors["neon"]); self.rmse_l.pack()
        ModernCheckbox(rp, "REAL-TIME PREVIEW", self.show_preview).pack(pady=5)

        # Footer Console
        self.console = tk.Text(lp, height=4, bg="#000", fg=self.colors["neon"], font=("Consolas", 10), padx=15, pady=10, bd=0)
        self.console.pack(fill="x", pady=20)
        self.btn_run = CustomButton(lp, text="INVOKE ENCODER", command=self.run, color=self.colors["accent"]); self.btn_run.pack(fill="x")

    def create_io(self, parent, label, var, cmd):
        f = tk.Frame(parent, bg="#050505", pady=10); f.pack(fill="x")
        tk.Label(f, text=label, font=("Segoe UI Bold", 8), bg="#050505", fg=self.colors["sub"]).pack(anchor="w")
        row = tk.Frame(f, bg="#050505"); row.pack(fill="x", pady=5)
        tk.Entry(row, textvariable=var, bg="#111", fg="#fff", bd=0, font=("Segoe UI", 11), insertbackground="#fff").pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 15))
        tk.Button(row, text="SEARCH", command=cmd, bg="#111", fg=self.colors["accent"], font=("Segoe UI Bold", 9), relief="flat", padx=25, cursor="hand2").pack(side="right", fill="y")

    def toggle_hdr(self):
        if self.opt_hdr.get(): self.opt_10bit.set(False); self.check_10bit.draw()
    def toggle_10bit(self):
        if self.opt_10bit.get(): self.opt_hdr.set(False); self.check_hdr.draw()
    def update_q_label(self, v): self.q_label.config(text=str(v))
    def update_ui(self):
        is_l = self.compression_mode.get() == 2
        self.q_label.config(fg=self.colors["accent"] if is_l else "#222")
        self.preset_cb.config(state="readonly" if is_l else "disabled")

    def log(self, m):
        self.console.config(state="normal"); self.console.insert("end", f"▶ {m}\n"); self.console.see("end"); self.console.config(state="disabled")

    def browse_input(self):
        p = modern_file_picker(title="Select Asset", mode="open")
        if p: 
            self.input_path.set(p); self.log(f"Asset Linked: {os.path.basename(p)}")
            try:
                with Image.open(p) as img:
                    if img.mode in ('I;16', 'RGB;16', 'RGBA;16') or 'hdr' in p.lower():
                        self.opt_hdr.set(True); self.opt_10bit.set(False)
                        self.check_hdr.draw(); self.check_10bit.draw(); self.log("HDR Profile Auto-Detected.")
            except: pass

    def browse_output(self):
        p = modern_file_picker(title="Export Asset", mode="save", default_ext=".wimf")
        if p: self.output_path.set(p)

    def run(self):
        if not self.input_path.get() or not self.output_path.get(): return
        self.btn_run.config_state("disabled", "PROCESSING PIPELINE..."); threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            meta = {"engine": "WIMF v19.0", "hdr": self.opt_hdr.get(), "bit10": self.opt_10bit.get(), "alpha": self.opt_alpha.get(), "is_animated": self.opt_anim.get(), "gpu_mode": self.gpu_mode.get()}
            from .cli import convert
            convert(input_path=self.input_path.get(), output_path=self.output_path.get(), compression=self.compression_mode.get(), quality=self.slider.val, preset=self.preset.get(), meta=meta)
            self.root.after(0, lambda: self.log("Sequence Finalized."))
        except Exception as e: self.root.after(0, lambda: self.log(f"ERROR: {e}"))
        finally: self.root.after(0, lambda: self.btn_run.config_state("normal", "INVOKE ENCODER"))

def main():
    root = tk.Tk()
    app = WorstImageFormatApp(root)
    root.mainloop()

if __name__ == "__main__": main()
