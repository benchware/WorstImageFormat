from .io import loadImage, saveImage, stream_load

__version__ = "1.2.0"
__all__ = ["loadImage", "saveImage", "stream_load"]

# Alias for library standard feel
load = loadImage
save = saveImage
