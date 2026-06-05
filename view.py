from PIL import Image

# COPY FROM MAIN.py
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

def view_image(filename):
    try:
        w,h,pixels = loadImage(filename)

        pixel_bytes = bytes(pixels)
        image = Image.frombytes('RGB', (w, h), pixel_bytes)
        image.show()
    except Exception as e:
        print(f"Err opening image: {e}")

if __name__ == "__main__":
    view_image((input("Enter .wif/.wimf image path: ")))