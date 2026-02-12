# trigrid_gl.py
import os
import numpy as np
from PIL import Image
import glfw
from OpenGL.GL import *
import ctypes
import warnings

# ---------- 默认参数 ----------
DEFAULT_PARAMS = {
    "tex_size": (0.2, 0.25),
    "base_color": (0.018, 0.018, 0.018, 0.4),
    "face_color": (0.702, 0.9449554, 1.0, 1.0),
    "face_brightness": 0.1,
    "grid_color": (1.0, 1.0, 1.0, 1.0),
    "grid_brightness": 0.4,
    "glow_color": (0.383, 0.8843222, 1.0, 1.0),
    "glow_brightness": 0.71,
    "always_on": False,
    "glow_ooroff": False,
}

VERTEX_SHADER_120 = """
#version 120
attribute vec2 aPos;
attribute vec2 aUV;
varying vec2 uv;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
    uv = aUV;
}
"""

class TriGridRenderer:
    """单例 OpenGL 渲染器，复用全局资源"""
    _instance = None
    _initialized = False
    _window = None
    _program = None
    _vbo = None
    _base_tex = None
    _width = 1920
    _height = 1080

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self, base_tex_path, width=1920, height=1080, frag_shader_path="./resources/trigrid.glsl"):
        """初始化 GLFW 上下文、编译着色器、加载纹理（仅一次）"""
        if self._initialized:
            return

        self._width = width
        self._height = height

        # ----- 1. 初始化 GLFW（强制 OpenGL 2.1）-----
        if not glfw.init():
            raise RuntimeError("Failed to initialize GLFW")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)
        glfw.window_hint(glfw.VISIBLE, False)
        glfw.window_hint(glfw.RESIZABLE, False)

        self._window = glfw.create_window(width, height, "Offscreen", None, None)
        if not self._window:
            glfw.terminate()
            raise RuntimeError("Failed to create offscreen window")
        glfw.make_context_current(self._window)

        # ----- 2. 编译着色器 -----
        self._program = self._compile_shader(frag_shader_path)

        # ----- 3. 加载基础纹理 -----
        self._base_tex = self._load_texture(base_tex_path, width, height)

        # ----- 4. 创建 VBO -----
        self._vbo = self._create_vbo()

        # ----- 5. 设置视口 -----
        glViewport(0, 0, width, height)

        self._initialized = True
        print("[TriGrid] OpenGL 渲染器已初始化")

    def _compile_shader(self, frag_path):
        """编译 GLSL 120 着色器程序"""
        # 顶点着色器
        vert = glCreateShader(GL_VERTEX_SHADER)
        glShaderSource(vert, VERTEX_SHADER_120)
        glCompileShader(vert)
        if not glGetShaderiv(vert, GL_COMPILE_STATUS):
            log = glGetShaderInfoLog(vert).decode()
            raise RuntimeError(f"Vertex shader compile error:\n{log}")

        # 读取并转换片段着色器
        with open(frag_path, 'r') as f:
            src = f.read()
        lines = [line for line in src.split('\n') if not line.startswith('#version')]
        src = '#version 120\n' + '\n'.join(lines)
        src = src.replace("precision highp float;", "")
        src = src.replace("precision lowp float;", "")
        src = src.replace("precision mediump float;", "")
        src = src.replace("lowp ", "")
        src = src.replace("highp ", "")
        src = src.replace("mediump ", "")

        frag = glCreateShader(GL_FRAGMENT_SHADER)
        glShaderSource(frag, src)
        glCompileShader(frag)
        if not glGetShaderiv(frag, GL_COMPILE_STATUS):
            log = glGetShaderInfoLog(frag).decode()
            raise RuntimeError(f"Fragment shader compile error:\n{log}")

        program = glCreateProgram()
        glAttachShader(program, vert)
        glAttachShader(program, frag)
        glBindAttribLocation(program, 0, "aPos")
        glBindAttribLocation(program, 1, "aUV")
        glLinkProgram(program)
        if not glGetProgramiv(program, GL_LINK_STATUS):
            log = glGetProgramInfoLog(program).decode()
            raise RuntimeError(f"Program link error:\n{log}")

        return program

    def _load_texture(self, path, w, h):
        img = Image.open(path).convert("RGBA").resize((w, h), Image.LANCZOS)
        data = np.array(img, dtype=np.uint8)
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
        return tex

    def _create_vbo(self):
        vertices = np.array([
            -1.0, -1.0,  0.0, 0.0,
             1.0, -1.0,  1.0, 0.0,
            -1.0,  1.0,  0.0, 1.0,
             1.0,  1.0,  1.0, 1.0,
        ], dtype=np.float32)
        vbo = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        return vbo

    def render(self, params=None, t=0.0, output_size=None):
        """渲染一帧，返回 PIL Image (RGBA)"""
        if not self._initialized:
            raise RuntimeError("Renderer not initialized. Call initialize() first.")

        # 使用默认参数
        if params is None:
            params = DEFAULT_PARAMS

        # 若指定输出尺寸，动态调整视口（不修改全局尺寸）
        w, h = output_size if output_size else (self._width, self._height)
        if output_size:
            glViewport(0, 0, w, h)

        glUseProgram(self._program)

        # 传递 uniform
        glUniform2f(glGetUniformLocation(self._program, "tex_size"), *params["tex_size"])
        glUniform4f(glGetUniformLocation(self._program, "base_color"), *params["base_color"])
        glUniform4f(glGetUniformLocation(self._program, "face_color"), *params["face_color"])
        glUniform1f(glGetUniformLocation(self._program, "face_brightness"), params["face_brightness"])
        glUniform4f(glGetUniformLocation(self._program, "grid_color"), *params["grid_color"])
        glUniform1f(glGetUniformLocation(self._program, "grid_brightness"), params["grid_brightness"])
        glUniform4f(glGetUniformLocation(self._program, "glow_color"), *params["glow_color"])
        glUniform1f(glGetUniformLocation(self._program, "glow_brightness"), params["glow_brightness"])
        glUniform1i(glGetUniformLocation(self._program, "always_on"), params["always_on"])
        glUniform1i(glGetUniformLocation(self._program, "glow_ooroff"), params["glow_ooroff"])
        glUniform1f(glGetUniformLocation(self._program, "t"), t)

        # 绑定纹理
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self._base_tex)
        glUniform1i(glGetUniformLocation(self._program, "screenTexture"), 0)

        # 绘制
        glBindBuffer(GL_ARRAY_BUFFER, self._vbo)
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(0))
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 4 * 4, ctypes.c_void_p(2 * 4))
        glEnableVertexAttribArray(1)

        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

        glDisableVertexAttribArray(0)
        glDisableVertexAttribArray(1)
        glBindBuffer(GL_ARRAY_BUFFER, 0)

        # 读取像素
        pixels = glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE)
        img = np.frombuffer(pixels, dtype=np.uint8).reshape(h, w, 4)
        img = np.flipud(img)  # 转为左上角原点

        # 恢复视口（如果之前修改过）
        if output_size:
            glViewport(0, 0, self._width, self._height)

        return Image.fromarray(img, 'RGBA')

    def cleanup(self):
        """释放 OpenGL 资源并终止 GLFW"""
        if self._window:
            glfw.destroy_window(self._window)
        glfw.terminate()
        self._initialized = False
        self._window = None
        self._program = None
        self._vbo = None
        self._base_tex = None
        print("[TriGrid] 渲染器已清理")

# ---------- 便捷函数（供外部调用）----------
_renderer = TriGridRenderer()

def is_available():
    """检查 OpenGL/GLFW 是否可用"""
    try:
        if not glfw.init():
            return False
        glfw.window_hint(glfw.VISIBLE, False)
        win = glfw.create_window(64, 64, "Test", None, None)
        if not win:
            glfw.terminate()
            return False
        glfw.destroy_window(win)
        glfw.terminate()
        return True
    except Exception:
        return False

def render_trigrid_gl(base_tex_path, params=None, t=0.0, output_size=(1920,1080)):
    """单次渲染接口（自动初始化/清理）——适合只渲染一帧的场景"""
    if not os.path.exists(base_tex_path):
        raise FileNotFoundError(f"纹理文件不存在: {base_tex_path}")
    renderer = TriGridRenderer()
    try:
        renderer.initialize(base_tex_path, width=output_size[0], height=output_size[1])
        img = renderer.render(params, t, output_size)
        return img
    finally:
        renderer.cleanup()

def get_cached_renderer():
    """获取单例渲染器实例（需手动调用 initialize 和 cleanup）"""
    return _renderer