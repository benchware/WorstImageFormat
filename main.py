import numpy as np
from common import saveImage, loadImage

def createProceduralImage(filename, width, height, start_col, end_col):
    # Numpy broadcast to optimize
    p = np.linspace(0, 1, width)
    
    # Linear interpolation between colors
    r = np.interp(p, [0, 1], [start_col[0], end_col[0]])
    g = np.interp(p, [0, 1], [start_col[1], end_col[1]])
    b = np.interp(p, [0, 1], [start_col[2], end_col[2]])
    
    # Stack to create a single row
    row = np.stack([r, g, b], axis=-1).astype(np.uint8)
    
    # Repeat the row for all heights
    image_data = np.tile(row, (height, 1, 1))
    
    saveImage(filename, width, height, image_data)

if __name__ == "__main__":
    createProceduralImage('procedural.wif', 128, 128, [255, 0, 0], [0, 0, 255])

    w, h, pixels = loadImage('procedural.wif')
    print(f'W: {w}, H: {h}, Data size: {len(pixels)} bytes (compressed on disk)')
    # NO PRINT MANY PIXELS
    print(f'First 10 bytes: {pixels[:10]}')
