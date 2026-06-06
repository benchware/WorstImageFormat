import os
import time
import json
import numpy as np
from PIL import Image
import unittest
import wimf
import io

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

    @classmethod
    def tearDownClass(cls):
        for f in ['test_input.png', 'test.wimf', 'lossless.wimf', 'roi_mip.wimf']:
            if os.path.exists(f): os.remove(f)

if __name__ == '__main__':
    unittest.main()
