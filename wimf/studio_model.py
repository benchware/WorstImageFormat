"""Headless state and job services shared by WIMF Studio tests and Tk widgets."""

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

import wimf


@dataclass
class EncodeSettings:
    quality: int = 7
    lossless: bool = False
    preset: str = "Balanced"
    codec: str = "auto"
    threads: int | None = None
    anti_rot: bool = False


@dataclass
class StudioDocument:
    path: Path | None = None
    source: np.ndarray | None = None
    encoded: bytes | None = None
    decoded: np.ndarray | None = None
    metadata: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    dirty: bool = False
    diagnostic_only: bool = False

    @classmethod
    def open(cls, path):
        path = Path(path)
        if wimf.is_wimf(path):
            encoded = path.read_bytes()
            image = wimf.decode(encoded)
            array = image.to_numpy().copy()
            return cls(path=path, source=array, encoded=encoded, decoded=array.copy(), metadata=dict(image.metadata), details=wimf.inspect(encoded))
        with Image.open(path) as image:
            image.load()
            if image.mode not in ("L", "LA", "RGB", "RGBA"):
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            array = np.array(image)
            if array.ndim == 2:
                array = array[..., None]
            return cls(path=path, source=array, metadata={})

    def encode(self, settings, cancelled=None, operation_token=None):
        if self.source is None:
            raise ValueError("open an image before encoding")
        if cancelled is not None and cancelled.is_set():
            raise CancelledError("operation cancelled")
        start = time.perf_counter()
        encoded = wimf.encode(
            self.source,
            quality=settings.quality,
            lossless=settings.lossless,
            preset=settings.preset,
            codec=settings.codec,
            threads=settings.threads,
            anti_rot=settings.anti_rot,
            metadata=self.metadata,
            operation_token=operation_token,
        )
        encode_seconds = time.perf_counter() - start
        if cancelled is not None and cancelled.is_set():
            raise CancelledError("operation cancelled")
        start = time.perf_counter()
        decoded = wimf.decode(encoded, operation_token=operation_token).to_numpy().copy()
        decode_seconds = time.perf_counter() - start
        metrics = wimf.compare(self.source, decoded)
        metrics.update(
            {
                "encode_seconds": encode_seconds,
                "decode_seconds": decode_seconds,
                "encoded_bytes": len(encoded),
                "ratio": len(encoded) / max(1, self.source.nbytes),
            }
        )
        return encoded, decoded, metrics, wimf.inspect(encoded)

    def apply_encode_result(self, result):
        self.encoded, self.decoded, self.metrics, self.details = result
        self.dirty = True
        self.diagnostic_only = False


class CancelledError(RuntimeError):
    pass


class JobController:
    """Single-worker controller; UI code polls events and never receives worker callbacks."""

    def __init__(self):
        self.events = queue.Queue()
        self.cancelled = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wimf-studio")
        self.future = None
        self.token = None

    @property
    def running(self):
        return self.future is not None and not self.future.done()

    def submit(self, name, function, *args, **kwargs):
        if self.running:
            raise RuntimeError("another Studio operation is already running")
        self.cancelled.clear()
        self.token = wimf.operation_token()
        self.events.put(("started", name, None))

        def run():
            try:
                result = function(*args, cancelled=self.cancelled, operation_token=self.token, **kwargs)
                if self.cancelled.is_set():
                    raise CancelledError("operation cancelled")
                self.events.put(("completed", name, result))
            except CancelledError as error:
                self.events.put(("cancelled", name, str(error)))
            except Exception as error:
                self.events.put(("failed", name, str(error)))

        self.future = self.executor.submit(run)

    def cancel(self):
        if self.running:
            self.cancelled.set()
            if self.token is not None:
                self.token.cancel()

    def close(self):
        self.cancel()
        self.executor.shutdown(wait=False, cancel_futures=True)
