import tkinter as tk
from PIL import Image, ImageTk
from common import loadImage
import sys
import os

class WIMFViewer:
    def __init__(self, root, filename):
        self.root = root
        self.root.title(f"WIMF Viewer - {os.path.basename(filename)}")
        self.root.configure(bg="#0a0a0a")
        
        try:
            # DPI Awareness for sharp pixels
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except: pass

            w, h, pixel_bytes, self.meta = loadImage(filename)
            self.orig_image = Image.frombytes('RGB', (w, h), pixel_bytes)
            
            # Setup Canvas
            self.canvas = tk.Canvas(root, bg="#0a0a0a", highlightthickness=0)
            self.canvas.pack(expand=True, fill="both")
            
            self.zoom_level = 1.0
            self.max_zoom = 30.0
            self.min_zoom = 0.01
            
            # Initial sizing
            sw = root.winfo_screenwidth() * 0.8
            sh = root.winfo_screenheight() * 0.8
            self.zoom_level = min(sw / w, sh / h, 1.0)
            
            # Bindings
            self.canvas.bind("<MouseWheel>", self.on_zoom)
            self.canvas.bind("<Button-4>", self.on_zoom)
            self.canvas.bind("<Button-5>", self.on_zoom)
            self.canvas.bind("<ButtonPress-1>", self.start_pan)
            self.canvas.bind("<B1-Motion>", self.do_pan)
            
            self.update_display()
            
            # MODERN STATUS BAR
            self.status_frame = tk.Frame(root, bg="#161616", height=30)
            self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
            
            self.status_left = tk.Label(self.status_frame, text="", bg="#161616", fg="#bb86fc", font=("Segoe UI Bold", 9), padx=15)
            self.status_left.pack(side=tk.LEFT)
            
            self.status_right = tk.Label(self.status_frame, text="SCROLL TO ZOOM • DRAG TO PAN", bg="#161616", fg="#888888", font=("Segoe UI Bold", 8), padx=15)
            self.status_right.pack(side=tk.RIGHT)
            
            self.update_status()
            
            # Initial geometry
            ww = min(int(w * self.zoom_level), int(sw))
            wh = min(int(h * self.zoom_level), int(sh))
            root.geometry(f"{ww}x{wh+30}")
            
        except Exception as e:
            tk.Label(root, text=f"LOAD ERROR\n{e}", fg="#ff4444", bg="#0a0a0a", font=("Segoe UI Bold", 12), pady=50).pack()

    def update_display(self):
        nw = int(self.orig_image.width * self.zoom_level)
        nh = int(self.orig_image.height * self.zoom_level)
        
        # resampling
        res = Image.Resampling.LANCZOS if self.zoom_level < 1.0 else Image.Resampling.NEAREST
        
        resized = self.orig_image.resize((nw, nh), res)
        self.tk_image = ImageTk.PhotoImage(resized)
        
        self.canvas.delete("all")
        self.canvas.create_image(nw//2, nh//2, image=self.tk_image)
        self.canvas.config(scrollregion=(0, 0, nw, nh))

    def on_zoom(self, event):
        if event.num == 4 or event.delta > 0: self.zoom_level *= 1.2
        else: self.zoom_level /= 1.2
        self.zoom_level = max(self.min_zoom, min(self.max_zoom, self.zoom_level))
        self.update_display()
        self.update_status()

    def start_pan(self, event): self.canvas.scan_mark(event.x, event.y)
    def do_pan(self, event): self.canvas.scan_dragto(event.x, event.y, gain=1)

    def update_status(self):
        auth = self.meta.get('author', 'Unknown')
        txt = f"{self.orig_image.width}x{self.orig_image.height}  •  {self.zoom_level:.2f}x  •  {auth}"
        self.status_left.config(text=txt.upper())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        p = sys.argv[1]
    else:
        p = input("Enter WIMF path: ")
    
    if os.path.exists(p):
        root = tk.Tk()
        viewer = WIMFViewer(root, p)
        root.mainloop()
    else:
        print(f"File not found: {p}")
