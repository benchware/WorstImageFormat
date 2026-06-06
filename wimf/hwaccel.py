import numpy as np
import logging
import os
import subprocess

try:
    import glfw
    from OpenGL.GL import *
    from OpenGL.GL.shaders import compileProgram, compileShader
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

class GPUManager:
    def __init__(self, mode='auto', device_index=0):
        self.mode = mode
        self.device_index = device_index
        self.enabled = False
        self.context = None
        self.devices = ["CPU Fallback"]
        
        if mode == 'off': return
        self._init_backend()
            
    def _init_backend(self):
        if self.mode in ['auto', 'opengl']:
            self._init_opengl()
        elif self.mode == 'vulkan':
            self._init_vulkan()

    def _init_opengl(self):
        if not OPENGL_AVAILABLE: return
        if not glfw.init(): return

        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 4)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, glfw.TRUE)
        
        self.context = glfw.create_window(1, 1, "WIMF Compute", None, None)
        if not self.context:
            glfw.terminate()
            return

        glfw.make_context_current(self.context)
        renderer = glGetString(GL_RENDERER).decode()
        self.devices = [renderer]
        
        major = glGetIntegerv(GL_MAJOR_VERSION)
        minor = glGetIntegerv(GL_MINOR_VERSION)
        
        if major < 4 or (major == 4 and minor < 3):
            self.cleanup()
            return

        self.enabled = True
        self._load_shaders()
        
        # DETACH CONTEXT from main thread so worker threads can use it
        glfw.make_context_current(None)

    def _init_vulkan(self):
        # Placeholder for Vulkan - currently defaults to OpenGL for compute
        self._init_opengl()

    def _load_shaders(self):
        ycocg_fwd_src = """
        #version 430
        layout(local_size_x = 16, local_size_y = 16) in;
        layout(rgba32f, binding = 0) uniform image2D img_in;
        layout(rgba32f, binding = 1) uniform image2D img_out;
        void main() {
            ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
            vec4 pixel = imageLoad(img_in, pos);
            float r = pixel.r, g = pixel.g, b = pixel.b;
            float co = r - b;
            float tmp = b + floor(co / 2.0);
            float cg = g - tmp;
            float y = tmp + floor(cg / 2.0);
            imageStore(img_out, pos, vec4(y, co, cg, pixel.a));
        }
        """
        ycocg_inv_src = """
        #version 430
        layout(local_size_x = 16, local_size_y = 16) in;
        layout(rgba32f, binding = 0) uniform image2D img_in;
        layout(rgba32f, binding = 1) uniform image2D img_out;
        void main() {
            ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
            vec4 pixel = imageLoad(img_in, pos);
            float y = pixel.r, co = pixel.g, cg = pixel.b;
            float tmp = y - floor(cg / 2.0);
            float g = cg + tmp;
            float b = tmp - floor(co / 2.0);
            float r = b + co;
            imageStore(img_out, pos, vec4(r, g, b, pixel.a));
        }
        """
        try:
            self.shader_ycocg_fwd = compileProgram(compileShader(ycocg_fwd_src, GL_COMPUTE_SHADER))
            self.shader_ycocg_inv = compileProgram(compileShader(ycocg_inv_src, GL_COMPUTE_SHADER))
        except: self.enabled = False

    def dispatch_ycocg_fwd(self, data_np, w, h):
        if not self.enabled: return None
        glfw.make_context_current(self.context)
        try:
            tex_in = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_in)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, w, h, 0, GL_RGB, GL_FLOAT, data_np.astype(np.float32))
            glBindImageTexture(0, tex_in, 0, GL_FALSE, 0, GL_READ_ONLY, GL_RGBA32F)
            tex_out = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_out)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, w, h, 0, GL_RGBA, GL_FLOAT, None)
            glBindImageTexture(1, tex_out, 0, GL_FALSE, 0, GL_WRITE_ONLY, GL_RGBA32F)
            glUseProgram(self.shader_ycocg_fwd)
            glDispatchCompute((w + 15) // 16, (h + 15) // 16, 1)
            glMemoryBarrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)
            res = np.empty((h, w, 4), dtype=np.float32)
            glGetTexImage(GL_TEXTURE_2D, 0, GL_RGBA, GL_FLOAT, res)
            glDeleteTextures(2, [tex_in, tex_out])
            return res
        finally:
            glfw.make_context_current(None)

    def dispatch_ycocg_inv(self, data_np, w, h):
        if not self.enabled: return None
        glfw.make_context_current(self.context)
        try:
            tex_in = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_in)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, w, h, 0, GL_RGBA, GL_FLOAT, data_np.astype(np.float32))
            glBindImageTexture(0, tex_in, 0, GL_FALSE, 0, GL_READ_ONLY, GL_RGBA32F)
            tex_out = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, tex_out)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, w, h, 0, GL_RGBA, GL_FLOAT, None)
            glBindImageTexture(1, tex_out, 0, GL_FALSE, 0, GL_WRITE_ONLY, GL_RGBA32F)
            glUseProgram(self.shader_ycocg_inv)
            glDispatchCompute((w + 15) // 16, (h + 15) // 16, 1)
            glMemoryBarrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)
            res = np.empty((h, w, 4), dtype=np.float32)
            glGetTexImage(GL_TEXTURE_2D, 0, GL_RGBA, GL_FLOAT, res)
            glDeleteTextures(2, [tex_in, tex_out])
            return res
        finally:
            glfw.make_context_current(None)

    def get_info(self):
        if not self.enabled: return "Disabled (CPU Only)"
        dev = self.devices[self.device_index] if self.device_index < len(self.devices) else "Unknown"
        return f"{dev} (Active)"

    def list_devices(self):
        return self.devices

    def cleanup(self):
        if self.context:
            glfw.make_context_current(self.context)
            glfw.destroy_window(self.context)
            glfw.terminate()
            self.context = None
        self.enabled = False

_gpu_manager = None

def get_gpu_manager(mode='auto', device_index=0):
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager(mode, device_index)
    elif mode != 'auto' and (_gpu_manager.mode != mode or _gpu_manager.device_index != device_index):
        _gpu_manager.cleanup()
        _gpu_manager = GPUManager(mode, device_index)
    return _gpu_manager
