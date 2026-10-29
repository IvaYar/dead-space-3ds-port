"""Opt-in hidden OpenGL libretro frontend; leaves the CPU baseline unchanged.

Install glfw 2.11.0 into porting/toolchain/python-glfw (local, ignored).
ABI: libretro-common/include/libretro.h, retro_hw_render_callback.
"""
import ctypes as C,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'toolchain/python-glfw'))
import glfw
Reset=C.CFUNCTYPE(None)
Framebuffer=C.CFUNCTYPE(C.c_size_t)
Proc=C.CFUNCTYPE(C.c_void_p,C.c_char_p)
class Render(C.Structure):
    _fields_=[('context_type',C.c_uint),('context_reset',Reset),('framebuffer',Framebuffer),('proc',Proc),
        ('depth',C.c_bool),('stencil',C.c_bool),('bottom_left',C.c_bool),('major',C.c_uint),('minor',C.c_uint),
        ('cache',C.c_bool),('context_destroy',Reset),('debug',C.c_bool)]

class Frontend:
    def __init__(self,f):
        self.f=f;self.render=None
        assert glfw.init(),'GLFW initialization failed'
        glfw.window_hint(glfw.VISIBLE,glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR,4);glfw.window_hint(glfw.CONTEXT_VERSION_MINOR,3)
        glfw.window_hint(glfw.OPENGL_PROFILE,glfw.OPENGL_CORE_PROFILE)
        self.window=glfw.create_window(400,480,'Azahar isolated test',None,None)
        assert self.window,'No OpenGL 4.3 context'
        glfw.make_context_current(self.window)
        self.framebuffer=Framebuffer(lambda:0)
        self.proc=Proc(lambda name:glfw.get_proc_address(name.decode()))
        original=f.environment
        @C.CFUNCTYPE(C.c_bool,C.c_uint,C.c_void_p)
        def environment(command,data):
            command &= ~0x10000
            if command==14:
                r=C.cast(data,C.POINTER(Render)).contents
                if r.context_type not in (1,3):return False
                r.framebuffer=self.framebuffer;r.proc=self.proc
                self.render=Render.from_buffer_copy(r);return True
            if command==56:C.cast(data,C.POINTER(C.c_uint))[0]=3;return True
            return original(command,data)
        self.environment=environment;f.environment=environment
        f.OPTIONS[b'citra_graphics_api']=b'OpenGL'
        f.OPTIONS[b'citra_use_hw_shader']=b'disabled'
        f.OPTIONS[b'citra_texture_sampling']=b'GameControlled'
        def proc(name,result,*args):return C.WINFUNCTYPE(result,*args)(glfw.get_proc_address(name))
        read=proc('glReadPixels',None,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p)
        get=proc('glGetIntegerv',None,C.c_uint,C.POINTER(C.c_int))
        store=proc('glPixelStorei',None,C.c_uint,C.c_int)
        bind_buffer=proc('glBindBuffer',None,C.c_uint,C.c_uint)
        bind_fb=proc('glBindFramebuffer',None,C.c_uint,C.c_uint)
        read_buffer=proc('glReadBuffer',None,C.c_uint)
        error=proc('glGetError',C.c_uint)
        get_string=proc('glGetString',C.c_char_p,C.c_uint)
        self.info={'version':get_string(0x1f02).decode(),'renderer':get_string(0x1f01).decode(),'captures':[]}
        def integer(key):
            value=C.c_int();get(key,C.byref(value));return value.value
        @C.CFUNCTYPE(None,C.c_void_p,C.c_uint,C.c_uint,C.c_size_t)
        def video(data,width,height,pitch):
            if data==C.c_void_p(-1).value:
                # A core may leave PACK_ROW_LENGTH, PBO and read FBO bindings.
                # Define a tightly packed BGRA8 capture, then restore GL state.
                pack={key:integer(key) for key in (0x0d05,0x0d02,0x0d03,0x0d04,0x0d00,0x0d01)}
                pbo=integer(0x88ed);fb=integer(0x8caa);buffer=integer(0x0c02)
                before=error();bind_buffer(0x88eb,0);bind_fb(0x8ca8,0)
                default_buffer=integer(0x0c02);read_buffer(0x0405)
                for key in pack:store(key,1 if key==0x0d05 else 0)
                pixels=C.create_string_buffer(width*height*4);read(0,0,width,height,0x80e1,0x1401,pixels)
                after=error();read_buffer(default_buffer);bind_fb(0x8ca8,fb);read_buffer(buffer);bind_buffer(0x88eb,pbo)
                for key,value in pack.items():store(key,value)
                if len(self.info['captures'])<64:self.info['captures'].append({'width':width,'height':height,'pitch':pitch,'pack':pack,'pbo':pbo,'read_fbo':fb,'read_buffer':buffer,'error_before':before,'error_after':after})
                rows=bytes(pixels);stride=width*4
                f.frame=(width,height,stride,b''.join(rows[y*stride:(y+1)*stride] for y in range(height-1,-1,-1)))
        self.video=video;f.video=video
    def reset(self):
        assert self.render and self.render.context_reset,'Core did not negotiate OpenGL'
        self.render.context_reset()
