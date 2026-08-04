"""Pillow registration for WIMF images.

Importing :mod:`wimf` registers this plugin; it does not monkey-patch Pillow.
"""

from PIL import Image, ImageFile

from .api import WIMFDecoder, WIMFEncoder


def _accept(prefix):
    return prefix[:4] in (b"WIM2", b"WIMF", b"AWIF", b"ROT!")


class WIMFImageFile(ImageFile.ImageFile):
    format = "WIMF"
    format_description = "Worst Image Format (WIM2)"

    def _open(self):
        payload = self.fp.read()
        decoded = WIMFDecoder(payload).decode()
        self._decoded = decoded.pil
        self._size = self._decoded.size
        self._mode = self._decoded.mode
        self.info.update(decoded.metadata)
        self.tile = []

    def load(self):
        if getattr(self, "_decoded", None) is not None:
            self.im = self._decoded.im
            self._decoded.readonly = True
        return Image.Image.load(self)


def _save(image, fp, filename):
    options = dict(getattr(image, "encoderinfo", {}))
    supported = {"quality", "lossless", "preset", "codec", "threads", "metadata", "anti_rot"}
    options = {key: value for key, value in options.items() if key in supported}
    encoder = WIMFEncoder(image)
    metadata = options.pop("metadata", None)
    if metadata:
        encoder.set_metadata(**metadata)
    if options.pop("anti_rot", False):
        encoder.set_anti_rot(True)
    fp.write(encoder.encode(**options))


def register():
    Image.register_open(WIMFImageFile.format, WIMFImageFile, _accept)
    Image.register_save(WIMFImageFile.format, _save)
    Image.register_extensions(WIMFImageFile.format, [".wimf"])
    Image.register_mime(WIMFImageFile.format, "image/x-wimf")
