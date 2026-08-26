"""Pillow registration for WIMF images.

Importing :mod:`wimf` registers this plugin; it does not monkey-patch Pillow.
"""

from PIL import Image, ImageFile

from .api import WIMFDecoder, WIMFEncoder


def _accept(prefix):
    return prefix[:4] in (b"WIM2", b"WIM3", b"WIMF", b"AWIF", b"ROT!")


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
        if decoded.metadata.get("exif"):
            # Raw EXIF bytes in info let Pillow re-attach the tags when the
            # image is saved to formats that carry them (JPEG, TIFF, WebP).
            self.info["exif"] = decoded.exif.tobytes()
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
    metadata = dict(options.pop("metadata", None) or {})
    if "exif" not in metadata and image.info.get("exif"):
        # Round-trip EXIF from a previously opened WIMF (or any source that
        # stashed raw tags in info) into the container metadata.
        try:
            exif = Image.Exif()
            exif.load(image.info["exif"])
            metadata["exif"] = {str(tag): value for tag, value in exif.items()}
        except Exception:
            pass
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
