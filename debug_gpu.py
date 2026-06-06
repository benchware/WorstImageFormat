import glfw
from OpenGL.GL import *
import sys

def debug_gpu():
    print("--- GPU Detection Debug ---")
    
    print(f"Python Version: {sys.version}")
    
    # 1. Check GLFW
    print("\n1. Initializing GLFW...")
    if not glfw.init():
        print("   [FAIL] glfw.init() returned False. Do you have an X server or Wayland running?")
        return
    print("   [OK] GLFW initialized.")

    # 2. Check Window Creation
    print("\n2. Creating Hidden Window...")
    glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
    # Force a core profile to get higher versions on some drivers
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
    glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
    
    window = glfw.create_window(1, 1, "Debug", None, None)
    if not window:
        print("   [FAIL] Could not create GLFW window. Checking error...")
        err = glfw.get_error()
        print(f"   GLFW Error: {err}")
        glfw.terminate()
        return
    print("   [OK] Window created.")

    # 3. Check OpenGL Version
    glfw.make_context_current(window)
    version = glGetString(GL_VERSION).decode()
    vendor = glGetString(GL_VENDOR).decode()
    renderer = glGetString(GL_RENDERER).decode()
    
    print(f"\n3. OpenGL Info:")
    print(f"   Version:  {version}")
    print(f"   Vendor:   {vendor}")
    print(f"   Renderer: {renderer}")
    
    major = glGetIntegerv(GL_MAJOR_VERSION)
    minor = glGetIntegerv(GL_MINOR_VERSION)
    print(f"   Numeric:  {major}.{minor}")

    # 4. Check Compute Shader Support
    print("\n4. Feature Check:")
    if major > 4 or (major == 4 and minor >= 3):
        print("   [SUCCESS] Compute Shaders (4.3+) are supported!")
    else:
        print(f"   [FAIL] Version {major}.{minor} is too low for Compute Shaders.")

    glfw.destroy_window(window)
    glfw.terminate()

if __name__ == "__main__":
    debug_gpu()
