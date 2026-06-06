import numpy as np
import logging

try:
    import glfw
    from OpenGL.GL import *
    from OpenGL.GL.shaders import compileProgram, compileShader
    OPENGL_AVAILABLE = True
except ImportError:
    OPENGL_AVAILABLE = False

class GPUManager:
    def __init__(self, mode='auto'):
        self.mode = mode
        self.enabled = False
        self.context = None
        self.shader_program = None
        
        if mode == 'off':
            return
            
        if mode in ['auto', 'opengl']:
            self._init_opengl()
            
    def _init_opengl(self):
        if not OPENGL_AVAILABLE:
            logging.warning("[WIMF] PyOpenGL or glfw not found. GPU acceleration disabled.")
            return

        if not glfw.init():
            logging.warning("[WIMF] Failed to initialize GLFW. GPU acceleration disabled.")
            return

        # Hidden window for offscreen compute
        glfw.window_hint(glfw.VISIBLE, glfw.FALSE)
        self.context = glfw.create_window(1, 1, "WIMF Compute Context", None, None)
        if not self.context:
            logging.warning("[WIMF] Failed to create OpenGL context.")
            glfw.terminate()
            return

        glfw.make_context_current(self.context)
        
        # Check for Compute Shader support (OpenGL 4.3+)
        major = glGetIntegerv(GL_MAJOR_VERSION)
        minor = glGetIntegerv(GL_MINOR_VERSION)
        
        if major < 4 or (major == 4 and minor < 3):
            logging.warning(f"[WIMF] OpenGL {major}.{minor} detected. Compute shaders require 4.3+. Falling back to CPU.")
            self.cleanup()
            return

        self.enabled = True
        logging.info(f"[WIMF] GPU Acceleration Enabled (OpenGL {major}.{minor})")
        
        self._load_shaders()

    def _load_shaders(self):
        # Forward YCoCg-R Compute Shader
        ycocg_fwd_src = """
        #version 430
        layout(local_size_x = 16, local_size_y = 16) in;
        layout(rgba32f, binding = 0) uniform image2D img_in;
        layout(rgba32f, binding = 1) uniform image2D img_out;

        void main() {
            ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
            vec4 pixel = imageLoad(img_in, pos);
            
            // Reversible YCoCg-R
            float r = pixel.r;
            float g = pixel.g;
            float b = pixel.b;
            
            float co = r - b;
            float tmp = b + floor(co / 2.0);
            float cg = g - tmp;
            float y = tmp + floor(cg / 2.0);
            
            imageStore(img_out, pos, vec4(y, co, cg, pixel.a));
        }
        """
        
        # Inverse YCoCg-R Compute Shader
        ycocg_inv_src = """
        #version 430
        layout(local_size_x = 16, local_size_y = 16) in;
        layout(rgba32f, binding = 0) uniform image2D img_in;
        layout(rgba32f, binding = 1) uniform image2D img_out;

        void main() {
            ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
            vec4 pixel = imageLoad(img_in, pos);
            
            float y = pixel.r;
            float co = pixel.g;
            float cg = pixel.b;
            
            float tmp = y - floor(cg / 2.0);
            float g = cg + tmp;
            float b = tmp - floor(co / 2.0);
            float r = b + co;
            
            imageStore(img_out, pos, vec4(r, g, b, pixel.a));
        }
        """

        # Forward Haar Level Shader (Simplified for 16x16 blocks)
        haar_fwd_src = """
        #version 430
        layout(local_size_x = 8, local_size_y = 8) in;
        layout(rgba32f, binding = 0) uniform image2D img_in;
        layout(rgba32f, binding = 1) uniform image2D LL;
        layout(rgba32f, binding = 2) uniform image2D HL;
        layout(rgba32f, binding = 3) uniform image2D LH;
        layout(rgba32f, binding = 4) uniform image2D HH;

        void main() {
            ivec2 pos = ivec2(gl_GlobalInvocationID.xy) * 2;
            
            vec4 a = imageLoad(img_in, pos + ivec2(0, 0));
            vec4 b = imageLoad(img_in, pos + ivec2(1, 0));
            vec4 c = imageLoad(img_in, pos + ivec2(0, 1));
            vec4 d = imageLoad(img_in, pos + ivec2(1, 1));
            
            // Integer Lifting Scheme
            // H: d = odd - even, s = even + (d >> 1)
            vec4 dh0 = b - a;
            vec4 sh0 = a + floor(dh0 / 2.0);
            vec4 dh1 = d - c;
            vec4 sh1 = c + floor(dh1 / 2.0);
            
            // V: HL = s1 - s0, LL = s0 + (HL >> 1)
            vec4 vHL = sh1 - sh0;
            vec4 vLL = sh0 + floor(vHL / 2.0);
            
            vec4 vHH = dh1 - dh0;
            vec4 vLH = dh0 + floor(vHH / 2.0);
            
            ivec2 out_pos = ivec2(gl_GlobalInvocationID.xy);
            imageStore(LL, out_pos, vLL);
            imageStore(HL, out_pos, vHL);
            imageStore(LH, out_pos, vLH);
            imageStore(HH, out_pos, vHH);
        }
        """

        # Inverse Haar Level Shader
        haar_inv_src = """
        #version 430
        layout(local_size_x = 8, local_size_y = 8) in;
        layout(rgba32f, binding = 0) uniform image2D LL;
        layout(rgba32f, binding = 1) uniform image2D HL;
        layout(rgba32f, binding = 2) uniform image2D LH;
        layout(rgba32f, binding = 3) uniform image2D HH;
        layout(rgba32f, binding = 4) uniform image2D img_out;

        void main() {
            ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
            
            vec4 vLL = imageLoad(LL, pos);
            vec4 vHL = imageLoad(HL, pos);
            vec4 vLH = imageLoad(LH, pos);
            vec4 vHH = imageLoad(HH, pos);
            
            // Inverse Vertical
            vec4 sh0 = vLL - floor(vHL / 2.0);
            vec4 sh1 = sh0 + vHL;
            
            // Inverse Horizontal
            vec4 dh0 = vLH - floor(vHH / 2.0);
            vec4 dh1 = dh0 + vHH;
            
            vec4 a = sh0 - floor(dh0 / 2.0);
            vec4 b = a + dh0;
            vec4 c = sh1 - floor(dh1 / 2.0);
            vec4 d = c + dh1;
            
            ivec2 out_pos = pos * 2;
            imageStore(img_out, out_pos + ivec2(0, 0), a);
            imageStore(img_out, out_pos + ivec2(1, 0), b);
            imageStore(img_out, out_pos + ivec2(0, 1), c);
            imageStore(img_out, out_pos + ivec2(1, 1), d);
        }
        """

        try:
            self.shader_ycocg_fwd = compileProgram(compileShader(ycocg_fwd_src, GL_COMPUTE_SHADER))
            self.shader_ycocg_inv = compileProgram(compileShader(ycocg_inv_src, GL_COMPUTE_SHADER))
            self.shader_haar_fwd = compileProgram(compileShader(haar_fwd_src, GL_COMPUTE_SHADER))
            self.shader_haar_inv = compileProgram(compileShader(haar_inv_src, GL_COMPUTE_SHADER))
        except Exception as e:
            logging.error(f"[WIMF] Failed to compile shaders: {e}")
            self.enabled = False

    def dispatch_ycocg_fwd(self, data_np, w, h):
        """
        Executes Forward YCoCg-R transform on the GPU.
        """
        if not self.enabled: return None
        
        glfw.make_context_current(self.context)
        
        # Create Textures
        tex_in = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_in)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, w, h, 0, GL_RGB, GL_FLOAT, data_np.astype(np.float32))
        glBindImageTexture(0, tex_in, 0, GL_FALSE, 0, GL_READ_ONLY, GL_RGBA32F)
        
        tex_out = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_out)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, w, h, 0, GL_RGBA, GL_FLOAT, None)
        glBindImageTexture(1, tex_out, 0, GL_FALSE, 0, GL_WRITE_ONLY, GL_RGBA32F)
        
        # Dispatch
        glUseProgram(self.shader_ycocg_fwd)
        glDispatchCompute((w + 15) // 16, (h + 15) // 16, 1)
        glMemoryBarrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT)
        
        # Read Back
        res = np.empty((h, w, 4), dtype=np.float32)
        glGetTexImage(GL_TEXTURE_2D, 0, GL_RGBA, GL_FLOAT, res)
        
        # Cleanup Textures
        glDeleteTextures(2, [tex_in, tex_out])
        
        return res

    def dispatch_ycocg_inv(self, data_np, w, h):
        if not self.enabled: return None
        glfw.make_context_current(self.context)
        
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

    def dispatch_haar_fwd(self, img_in, w, h):
        if not self.enabled: return None
        glfw.make_context_current(self.context)
        
        # In is 16x16 blocks, out is 8x8 blocks for each LL,HL,LH,HH
        # But for WIMF it's gh, gw, 16, 16
        # Let's simplify and assume flat 2D for now as a POC
        pass

    def cleanup(self):
        if self.context:
            glfw.destroy_window(self.context)
            glfw.terminate()
        self.enabled = False

    def get_info(self):
        if not self.enabled:
            return "Disabled (CPU Only)"
        return f"Enabled (OpenGL {glGetIntegerv(GL_MAJOR_VERSION)}.{glGetIntegerv(GL_MINOR_VERSION)})"

# Global instance
_gpu_manager = None

def get_gpu_manager(mode='auto'):
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager(mode)
    return _gpu_manager
