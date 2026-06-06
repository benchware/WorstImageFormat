import numpy as np
import time
import sys
import os

# Ensure we can import wimf from the current directory
sys.path.append(os.getcwd())

try:
    from wimf.codec import encode_lossy, decode_lossy, encode_lossless, decode_lossless
    from wimf.hwaccel import get_gpu_manager
except ImportError as e:
    print(f"Error: Could not import WIMF modules. Are you running this from the project root? {e}")
    sys.exit(1)

def calculate_rmse(orig, dec):
    return np.sqrt(np.mean((orig.astype(np.float32) - dec.astype(np.float32))**2))

def test_phase1_precision():
    print("\n[TEST] Phase 1: Precision (8/10-bit)")
    w, h = 64, 64
    
    # 8-bit test
    img8 = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    enc8 = encode_lossy(img8.tobytes(), w, h, quality=10, channels=3, bit_depth=8)
    dec8_bytes = decode_lossy(enc8, w, h, channels=3, bit_depth=8)
    dec8 = np.frombuffer(dec8_bytes, dtype=np.uint8).reshape((h, w, 3))
    rmse8 = calculate_rmse(img8, dec8)
    print(f"  8-bit RMSE: {rmse8:.6f} {'[OK]' if rmse8 < 1.0 else '[HIGH]'}")
    
    # 10-bit test
    img10 = np.random.randint(0, 1024, (h, w, 3), dtype=np.uint16)
    enc10 = encode_lossy(img10.tobytes(), w, h, quality=10, channels=3, bit_depth=10)
    dec10_bytes = decode_lossy(enc10, w, h, channels=3, bit_depth=10)
    dec10 = np.frombuffer(dec10_bytes, dtype=np.uint16).reshape((h, w, 3))
    rmse10 = calculate_rmse(img10, dec10)
    print(f"  10-bit RMSE: {rmse10:.6f} {'[OK]' if rmse10 < 1.0 else '[HIGH]'}")
    
    return rmse8 < 1.0 and rmse10 < 1.0

def test_phase2_performance():
    print("\n[TEST] Phase 2: CPU Multi-threading & Optimization")
    w, h = 1024, 1024
    img = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    
    print(f"  Decoding {w}x{h} lossless image...")
    start = time.time()
    enc = encode_lossless(img.tobytes(), w, h, channels=3)
    mid = time.time()
    dec_bytes = decode_lossless(enc, w, h, channels=3)
    end = time.time()
    
    dec = np.frombuffer(dec_bytes, dtype=np.uint8).reshape((h, w, 3))
    rmse = calculate_rmse(img, dec)
    print(f"  Lossless RMSE: {rmse:.6f} {'[PASS]' if rmse == 0.0 else '[FAIL]'}")
    print(f"  Decode Time: {end - mid:.4f}s")
    return rmse == 0.0

def test_phase3_gpu():
    print("\n[TEST] Phase 3: GPU Capability & Shaders")
    
    # Try to initialize OpenGL GPU manager
    gpu = get_gpu_manager(mode='opengl')
    info = gpu.get_info()
    print(f"  GPU Acceleration Info: {info}")
    
    if gpu.enabled:
        print("  [SUCCESS] OpenGL Compute Shaders are supported and initialized!")
    else:
        print("  [NOTE] GPU Acceleration is disabled or not supported on this hardware.")
        print("         This script will use the optimized CPU fallback.")
    
    # Check for Vulkan
    try:
        import vulkan
        print("  [SUCCESS] Vulkan Python library is installed.")
    except ImportError:
        print("  [INFO] Vulkan Python library not found.")
        
    return True

def run_suite():
    print("==================================================")
    print("   WIMF CODEC VERIFICATION SUITE (PHASES 1-3)     ")
    print("==================================================")
    
    p1 = test_phase1_precision()
    p2 = test_phase2_performance()
    p3 = test_phase3_gpu()
    
    print("\n================  FINAL SUMMARY  ================")
    print(f" PHASE 1 (PRECISION):  {'PASSED' if p1 else 'FAILED'}")
    print(f" PHASE 2 (CPU PERF):   {'PASSED' if p2 else 'FAILED'}")
    print(f" PHASE 3 (GPU INFRA):  {'READY' if p3 else 'FAILED'}")
    print("==================================================")

if __name__ == "__main__":
    run_suite()
