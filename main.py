import numpy as np
from common import smoothstep
def loadImage(filename):
    with open(filename, 'rb') as f:
        header = f.read(4)
        if header == b"\x57\x49\x4d\x46":
            pass
        else: # "WIMF" in ASCII
            raise ValueError(f"Invalid file format. Expected 'WIMF' header, but got {header}.")
        
        width = int.from_bytes(f.read(4), 'little')
        height = int.from_bytes(f.read(4), 'little')
        pixels = list(f.read())    
        return width, height, pixels

def saveImage(filename, width, height, pixels, use_wimf=False):
    length = width * height * 3
    if len(pixels) != length:
        raise ValueError(f"Pixel data length requires {length} values, but got {len(pixels)} values from the code.")
    with open(filename, 'wb') as f:
        f.write(b"\x57\x49\x4d\x46")
        f.write(width.to_bytes(4, 'little'))
        f.write(height.to_bytes(4, 'little'))
        f.write(bytes(pixels))

def createProceduralImage(filename, width, height, start_col, end_col):
    _, x = np.indices((height, width))
    y, _ = np.indices((height, width))
    
    p = np.linspace(0, 1, width).reshape(1, width)
    r = start_col[0] * (1.0 - p) + end_col[0] * p
    g = start_col[1] * (1.0 - p) + end_col[1] * p
    b = start_col[2] * (1.0 - p) + end_col[2] * p
    
    rows = np.stack([r,g,b], axis=-1).astype(np.uint8)
    saveImage(filename, width, height, np.tile(rows, (height, 1, 1)).flatten().tolist())

if __name__ == "__main__":
    createProceduralImage('procedural.wif', 128, 128, [255, 0, 0], [0, 0, 255])

    w,h,pixels = loadImage('procedural.wif')
    print(f'W: {w}, H: {h}, Pixels: {pixels}')