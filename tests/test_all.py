import os
import time
import json
import numpy as np
from PIL import Image
import unittest
import wimf
import io
import base64
from unittest.mock import patch

class TestWIMF(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate assets
        cls.img_data = np.random.randint(0, 255, (256, 256, 4), dtype=np.uint8)
        cls.img_pil = Image.fromarray(cls.img_data, 'RGBA')
        cls.img_pil.save('test_input.png')
        
    def test_high_level_api(self):
        wimf.save("test.wimf", self.img_pil, quality=7)
        loaded = wimf.open("test.wimf")
        self.assertEqual(loaded.size, (256, 256))
        self.assertEqual(loaded.metadata['author'], 'WIMF_User')

    def test_vectorized_lossless(self):
        wimf.save("lossless.wimf", self.img_pil, lossless=True)
        loaded = wimf.open("lossless.wimf")
        # Compare PIL images directly or via numpy
        self.assertTrue(np.array_equal(np.array(self.img_pil), loaded.to_numpy()))

    def test_anti_rot(self):
        encoder = wimf.WIMFEncoder(self.img_pil)
        encoder.set_anti_rot(True)
        data = encoder.encode()
        
        # Corrupt 1 byte
        mutable = bytearray(data)
        # Offset 1000 is likely in the metadata or start of data, safe for test
        mutable[1000] = (mutable[1000] + 1) % 256
        
        # Decoder should auto-repair
        decoder = wimf.WIMFDecoder(bytes(mutable))
        repaired = decoder.decode()
        self.assertEqual(repaired.size, (256, 256))

    def test_roi_and_mip(self):
        wimf.save("roi_mip.wimf", self.img_pil, quality=5)
        decoder = wimf.WIMFDecoder("roi_mip.wimf")
        
        # Mip Level 2 (Quarter)
        mip2 = decoder.decode(mip_level=2)
        self.assertEqual(mip2.size, (64, 64))
        
        # ROI 100x100
        roi = decoder.decode(roi=(50, 50, 100, 100))
        self.assertEqual(roi.size, (100, 100))

    def test_chrono_layers(self):
        state1 = Image.new('RGB', (100, 100), (255, 0, 0))
        state2 = Image.new('RGB', (100, 100), (0, 255, 0))
        
        enc = wimf.WIMFEncoder(state1)
        enc.add_chrono_state(state2)
        data = enc.encode()
        
        dec = wimf.WIMFDecoder(data)
        ext = dec.decode_chrono_state(index=1)
        self.assertTrue(np.all(np.array(ext.pil) == [0, 255, 0]))

    def test_depth_map(self):
        depth_data = np.random.randint(0, 255, (256, 256), dtype=np.uint8)
        depth_pil = Image.fromarray(depth_data, 'L')
        
        # Use Encoder directly to set depth
        enc = wimf.WIMFEncoder(self.img_pil)
        # Depth Map is typically handled by CLI/API but we can simulate by adding a 5th channel
        # WIMF natively supports 5 channels if passed
        pixels_5ch = np.dstack((np.array(self.img_pil), depth_data))
        
        # Save manually with depth flag (using Lossless for pixel-perfect check)
        wimf.save("depth.wimf", pixels_5ch, lossless=True, depth=True)
        
        dec = wimf.WIMFDecoder("depth.wimf")
        img = dec.decode()
        self.assertTrue(dec.metadata.get('depth'))
        self.assertEqual(dec.channels, 5)
        # img.depth_map is a property of WIMFImage
        self.assertTrue(np.array_equal(img.depth_map, depth_data))

    def test_steganography(self):
        secret = "WIMF-SECRET-KEY"
        enc = wimf.WIMFEncoder(self.img_pil)
        enc.set_metadata(watermark_payload=secret)
        data = enc.encode(quality=7)
        
        # Capture stdout to verify extraction message
        f = io.StringIO()
        with patch('sys.stdout', f):
            dec = wimf.WIMFDecoder(data)
            dec.decode()
        
        self.assertIn(secret, f.getvalue())

    def test_base64_integration(self):
        enc = wimf.WIMFEncoder(self.img_pil)
        b64 = enc.to_base64()
        
        dec = wimf.WIMFDecoder.from_base64(b64)
        self.assertEqual(dec.width, 256)
        self.assertEqual(dec.height, 256)

    def test_metadata_surgery(self):
        wimf.save("surgery.wimf", self.img_pil)
        with wimf.edit_meta("surgery.wimf") as meta:
            meta['new_tag'] = "SurgicalValue"
            
        info = wimf.info("surgery.wimf")
        self.assertEqual(info['new_tag'], "SurgicalValue")

    def test_10bit_pipeline(self):
        # Save as 10-bit
        wimf.save("hdr.wimf", self.img_pil, bit10=True)
        info = wimf.info("hdr.wimf")
        self.assertTrue(info.get('bit10'))
        
        dec = wimf.WIMFDecoder("hdr.wimf")
        self.assertEqual(dec.bit_depth, 10)
        img = dec.decode()
        self.assertEqual(img.size, (256, 256))

    @classmethod
    def tearDownClass(cls):
        for f in ['test_input.png', 'test.wimf', 'lossless.wimf', 'roi_mip.wimf', 
                  'depth.wimf', 'surgery.wimf', 'hdr.wimf']:
            if os.path.exists(f): os.remove(f)

if __name__ == '__main__':
    unittest.main()
