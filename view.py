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
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except: pass

            self.w, self.h, pixel_data, self.meta = loadImage(filename)
            self.is_animated = self.meta.get('is_animated', False)
            self.is_live_photo = self.meta.get('is_live_photo', False)
            
            if self.is_animated:
                # pixel_data is a list of frame bytes
                self.frames = [Image.frombytes('RGB', (self.w, self.h), frame_bytes) for frame_bytes in pixel_data]
                self.current_frame = 0
                self.playing = True
            else:
                self.orig_image = Image.frombytes('RGB', (self.w, self.h), pixel_data)
            
            self.canvas = tk.Canvas(root, bg="#0a0a0a", highlightthickness=0)
            self.canvas.pack(expand=True, fill="both")
            
            self.zoom_level = 1.0
            self.max_zoom = 30.0
            self.min_zoom = 0.01
            
            sw = root.winfo_screenwidth() * 0.8
            sh = root.winfo_screenheight() * 0.8
            self.zoom_level = min(sw / self.w, sh / self.h, 1.0)
            
            self.canvas.bind("<MouseWheel>", self.on_zoom)
            self.canvas.bind("<Button-4>", self.on_zoom)
            self.canvas.bind("<Button-5>", self.on_zoom)
            self.canvas.bind("<ButtonPress-1>", self.start_pan)
            self.canvas.bind("<B1-Motion>", self.do_pan)
            
            if self.is_animated:
                self.canvas.bind("<space>", self.toggle_playback)
                self.root.bind("<space>", self.toggle_playback)
            
            self.status_frame = tk.Frame(root, bg="#161616", height=30)
            self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
            
            self.status_left = tk.Label(self.status_frame, text="", bg="#161616", fg="#bb86fc", font=("Segoe UI Bold", 9), padx=15)
            self.status_left.pack(side=tk.LEFT)
            
            hints = "SCROLL: ZOOM • DRAG: PAN"
            if self.is_animated: hints += " • SPACE: PLAY/PAUSE"
            self.status_right = tk.Label(self.status_frame, text=hints, bg="#161616", fg="#888888", font=("Segoe UI Bold", 8), padx=15)
            self.status_right.pack(side=tk.RIGHT)
            
            ww = min(int(self.w * self.zoom_level), int(sw))
            wh = min(int(self.h * self.zoom_level), int(sh))
            root.geometry(f"{ww}x{wh+30}")
            
            if self.is_animated:
                self.play_loop()
            else:
                self.update_display()
            self.update_status()
            
        except Exception as e:
            tk.Label(root, text=f"LOAD ERROR\n{e}", fg="#ff4444", bg="#0a0a0a", font=("Segoe UI Bold", 12), pady=50).pack()

    def get_current_image(self):
        if self.is_animated:
            return self.frames[self.current_frame]
        return self.orig_image

    def update_display(self):
        img = self.get_current_image()
        nw = int(self.w * self.zoom_level)
        nh = int(self.h * self.zoom_level)
        
        res = Image.Resampling.LANCZOS if self.zoom_level < 1.0 else Image.Resampling.NEAREST
        resized = img.resize((nw, nh), res)
        self.tk_image = ImageTk.PhotoImage(resized)
        
        self.canvas.delete("all")
        self.canvas.create_image(nw//2, nh//2, image=self.tk_image)
        self.canvas.config(scrollregion=(0, 0, nw, nh))
        
        # Add Live Photo Badge if applicable
        if self.is_live_photo:
            self.canvas.create_oval(20, 20, 40, 40, fill="#bb86fc", outline="")
            self.canvas.create_text(30, 30, text="LIVE", fill="black", font=("Segoe UI Bold", 7))

    def play_loop(self):
        if self.playing:
            self.current_frame = (self.current_frame + 1) % len(self.frames)
            self.update_display()
        self.root.after(33, self.play_loop) # ~30fps

    def toggle_playback(self, event=None):
        if self.is_animated:
            self.playing = not self.playing

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
        mode = "LIVE PHOTO" if self.is_live_photo else ("ANIMATED" if self.is_animated else "STILL")
        txt = f"[{mode}] {self.w}x{self.h}  •  {self.zoom_level:.2f}x  •  {auth}"
        self.status_left.config(text=txt.upper())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        p = sys.argv[1]
    else:
        p = input("Enter WIMF/AWIF/LWIF path: ")
    
    if os.path.exists(p):
        root = tk.Tk()
        viewer = WIMFViewer(root, p)
        root.mainloop()
    else:
        print(f"File not found: {p}")
