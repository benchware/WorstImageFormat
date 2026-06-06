import tkinter as tk
from PIL import Image, ImageTk
from .io import loadImage, stream_load
import sys
import os

class WIMFViewer:
    def __init__(self, root, filename):
        self.root = root
        self.root.title(f"WIMF Viewer - {os.path.basename(filename)}")
        self.root.configure(bg="#0a0a0a")
        
        self.canvas_img_id = None
        self.tk_frames = []
        self.last_zoom = -1.0
        self.current_frame = 0
        self.filename = filename

        try:
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except: pass

            # Quick initial load to get metadata and dimensions
            self.w, self.h, _, self.meta = loadImage(filename, target_layer=0)
            self.is_animated = self.meta.get('is_animated', False)
            
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
                # For animations, we just load all frames normally (no progressive support yet)
                _, _, pixel_data, _ = loadImage(filename)
                channels = self.meta.get('channels', 3)
                img_mode = 'RGBA' if channels >= 4 else 'RGB'
                self.frames = [Image.frombytes(img_mode, (self.w, self.h), frame_bytes) for frame_bytes in pixel_data]
                self.playing = True
                self.play_loop()
            else:
                # For still images, use progressive loader
                self.stream = stream_load(filename)
                self.load_next_layer()
                
            self.update_status()
            
        except Exception as e:
            tk.Label(root, text=f"LOAD ERROR\n{e}", fg="#ff4444", bg="#0a0a0a", font=("Segoe UI Bold", 12), pady=50).pack()

    def load_next_layer(self):
        try:
            self.w, self.h, pix, self.meta, is_final = next(self.stream)
            channels = self.meta.get('channels', 3)
            img_mode = 'RGBA' if channels >= 4 else 'RGB'
            self.orig_image = Image.frombytes(img_mode, (self.w, self.h), pix)
            self.update_display()
            if not is_final:
                self.root.after(100, self.load_next_layer)
        except StopIteration:
            pass
        except Exception as e:
            print(f"Streaming error: {e}")

    def get_current_image(self):
        if self.is_animated:
            return self.frames[self.current_frame]
        return self.orig_image

    def update_display(self):
        nw = int(self.w * self.zoom_level)
        nh = int(self.h * self.zoom_level)
        
        # If zoom changed, we need to regenerate TK frames
        if self.zoom_level != self.last_zoom:
            self.last_zoom = self.zoom_level
            res = Image.Resampling.LANCZOS if self.zoom_level < 1.0 else Image.Resampling.NEAREST
            if self.is_animated:
                self.tk_frames = [ImageTk.PhotoImage(f.resize((nw, nh), res)) for f in self.frames]
            else:
                self.tk_image = ImageTk.PhotoImage(self.orig_image.resize((nw, nh), res))
            
            self.canvas.config(scrollregion=(0, 0, nw, nh))
            self.canvas.delete("all")
            self.canvas_img_id = None

        # Determine which image to show
        display_img = self.tk_frames[self.current_frame] if self.is_animated else self.tk_image
        
        if self.canvas_img_id is None:
            self.canvas_img_id = self.canvas.create_image(nw//2, nh//2, image=display_img)
        else:
            self.canvas.itemconfig(self.canvas_img_id, image=display_img)
        


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
        mode = "ANIMATED" if self.is_animated else "STILL"
        txt = f"[{mode}] {self.w}x{self.h}  •  {self.zoom_level:.2f}x  •  {auth}"
        self.status_left.config(text=txt.upper())

def main():
    if len(sys.argv) > 1:
        p = sys.argv[1]
    else:
        p = input("Enter WIMF/AWIF path: ")
    
    if os.path.exists(p):
        root = tk.Tk()
        viewer = WIMFViewer(root, p)
        root.mainloop()
    else:
        print(f"File not found: {p}")

if __name__ == "__main__":
    main()
