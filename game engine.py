"""
====================================================================================================
                            PURE PYTHON GAME ENGINE 2.0
                         MULTITRACK DAW & CROSS-PLATFORM RENDERER
====================================================================================================

[ TECHNICAL MANUAL 2.0 ]

1. AUDIO SYSTEM (DAW)
   - Synthesis: Pure sine-wave generation with normalization to prevent clipping.
   - Syntax: "Note_Note-Duration" -> e.g., "C4_E4_G4-1/4" (C Major chord, quarter note).
   - Triplets: Natively supported by using fractions like "1/12" or "1/6".
   - Accidentals: The engine only supports Sharps (#). Use D# instead of Eb.
   - Pauses: Use 'P' (e.g., "P-1/4").
   - Multitracking: Melody.compile_to_memory(bpm, track1, track2, ...) 
     Automatically pads shorter tracks with silence to ensure perfect looping sync.

2. INPUT SYSTEM
   - Keyboard: Supports concurrent OS-level key presses (WASD, Arrows, Space, Esc, 1, 2).
   - Mouse: Real-time client-space coordinate tracking and button state (LMB, RMB, MMB).

3. RENDERING & OPTIMIZATION
   - Windows: Uses 'gdi32.dll' with Brush Caching and Double-Buffering to eliminate memory churn.
   - FPS Lock: Hybrid Sleep/Spin-lock using perf_counter for microsecond precision on Windows.
   - Fullscreen: Supported natively via dynamic SystemMetrics resolution.

4. CONTROLS (RUNTIME)
   - Move: WASD or Arrow Keys.
   - Boost: Hold SPACE (while moving).
   - FPS Limit: Press '1' to decrease, '2' to increase.
   - Interaction: Left Mouse Button (LMB) to change player color.
   - Exit: Press ESCAPE to instantly quit Fullscreen mode.

====================================================================================================
"""

import os
import ctypes
import math
import struct
import random
import time
import subprocess
import atexit
import traceback
import threading
import array 

# =================================================================================
# STAGE 1: PLATFORM DETECTION & CLEANUP
# =================================================================================

# Detect operating system: 'nt' for Windows, 'posix' for Linux/macOS
OS_TYPE = os.name 
SYS = {}
ACTIVE_SOUNDS = [] # Registry to keep track of audio processes so we can close them cleanly
ARCH_64 = (ctypes.sizeof(ctypes.c_void_p) == 8) # True if running on a 64-bit Python interpreter

def _set_pdeathsig():
    # Linux specific function: ensures that if the main python process crashes, 
    # the child audio processes (aplay) receive a kill signal and don't become zombies.
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl(1, 15) 
    except: pass

@atexit.register
def kill_audio_processes():
    # This runs automatically when the Python script exits normally or via exception.
    for s in ACTIVE_SOUNDS:
        if getattr(s, 'proc', None):
            try: s.proc.kill() # Kill Linux audio subprocesses
            except: pass
    if OS_TYPE == 'nt':
        # Stop any audio playing via Windows multimedia
        ctypes.windll.winmm.PlaySoundA(None, None, 0)
        # Restore normal Windows system timer resolution to save battery
        SYS['mm'].timeEndPeriod(1) 

if OS_TYPE == 'nt':
    # --- WINDOWS SETUP ---
    from ctypes import wintypes
    
    # Load core Windows DLLs needed for window creation, drawing, and audio
    SYS['u32'] = ctypes.windll.user32
    SYS['g32'] = ctypes.windll.gdi32
    SYS['k32'] = ctypes.windll.kernel32
    SYS['mm']  = ctypes.windll.winmm
    
    # Windows API Constants for window styles and messages
    WS_OVERLAPPEDWINDOW, CW_USEDEFAULT = 0x00CF0000, 0x80000000
    WM_DESTROY, WM_PAINT = 2, 0x000F
    SW_SHOW, SRCCOPY = 5, 0x00CC0020
    PM_REMOVE = 1 
    
    # C-Structures to pass coordinate and rectangle data to Windows
    class POINT(ctypes.Structure): _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    class RECT(ctypes.Structure): _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    
    # Handle pointer memory sizes for 32-bit vs 64-bit Windows architectures
    if ARCH_64:
        LRESULT, WPARAM_T, LPARAM_T = ctypes.c_longlong, ctypes.c_ulonglong, ctypes.c_longlong
    else:
        LRESULT, WPARAM_T, LPARAM_T = ctypes.c_long, ctypes.c_uint, ctypes.c_long
        
    # Define argument and return types for safety (prevents memory segmentation faults)
    WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T)
    SYS['u32'].DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T]
    SYS['u32'].DefWindowProcW.restype = LRESULT
    SYS['mm'].PlaySoundA.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint]
    SYS['mm'].PlaySoundA.restype = ctypes.c_int
    
    # Setup types for cursor and mouse tracking
    SYS['u32'].GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    SYS['u32'].ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]
    SYS['mm'].timeBeginPeriod.argtypes = [ctypes.c_uint]
    SYS['mm'].timeEndPeriod.argtypes = [ctypes.c_uint]
    
    # Cursor Fix: Prevents the blue loading wheel from persisting
    SYS['u32'].LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    SYS['u32'].LoadCursorW.restype = ctypes.c_void_p

elif OS_TYPE == 'posix':
    # --- LINUX SETUP ---
    import ctypes.util
    x11_path = ctypes.util.find_library("X11")
    if x11_path:
        # Load the X11 library used for Linux display and inputs
        SYS['x11'] = ctypes.cdll.LoadLibrary(x11_path)
        
        # Define return types for window creation functions
        SYS['x11'].XOpenDisplay.restype = ctypes.c_void_p
        SYS['x11'].XCreateSimpleWindow.restype = ctypes.c_ulong
        SYS['x11'].XCreateGC.restype = ctypes.c_void_p
        SYS['x11'].XDefaultScreen.restype = ctypes.c_int
        SYS['x11'].XRootWindow.restype = ctypes.c_ulong
        
        # Define types for reading keyboard inputs and mouse positions on Linux
        SYS['x11'].XStringToKeysym.restype = ctypes.c_ulong
        SYS['x11'].XKeysymToKeycode.restype = ctypes.c_ubyte
        SYS['x11'].XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        SYS['x11'].XDrawString.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        SYS['x11'].XQueryPointer.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), 
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int), 
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int), 
            ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_uint)
        ]
        
        # Define types for handling Linux window events
        SYS['x11'].XPending.argtypes = [ctypes.c_void_p]
        SYS['x11'].XPending.restype = ctypes.c_int
        SYS['x11'].XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        
        # Define types for Linux graphics rendering (Double Buffering)
        SYS['x11'].XDefaultDepth.restype = ctypes.c_int
        SYS['x11'].XCreatePixmap.restype = ctypes.c_ulong
        SYS['x11'].XCopyArea.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int]
        SYS['x11'].XInternAtom.restype = ctypes.c_ulong
        SYS['x11'].XSetWMProtocols.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong), ctypes.c_int]
        
        # Window cleanup definitions
        SYS['x11'].XDestroyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        SYS['x11'].XCloseDisplay.argtypes = [ctypes.c_void_p]

# =================================================================================
# STAGE 2: AUDIO & PHYSICS
# =================================================================================

def RGB(r, g, b):
    # Converts 0-255 R, G, B values into a 32-bit color code based on the OS structure
    if OS_TYPE == 'nt': return r | (g << 8) | (b << 16) # Windows wants 0x00BBGGRR
    return (r << 16) | (g << 8) | b                       # Linux usually wants standard RGB

class MemorySound:
    """ Wrapper to play raw WAV byte data directly from RAM. """
    def __init__(self, wave_bytes):
        self.wave_bytes = bytes(wave_bytes) 
        self.is_looping = False
        self.proc = None
        ACTIVE_SOUNDS.append(self) # Register for auto-cleanup on exit

    def _pump(self, p, data):
        # Background thread to feed raw audio bytes to Linux's 'aplay' program
        try:
            p.stdin.write(data)
            p.stdin.close()
        except: pass

    def play(self, loop=False):
        self.is_looping = loop
        if OS_TYPE == 'nt':
            # Windows API: 0x0004=SND_MEMORY (play from RAM), 0x0001=SND_ASYNC, 0x0008=SND_LOOP
            flags = 0x0004 | 0x0001 
            if loop: flags |= 0x0008 
            SYS['mm'].PlaySoundA(self.wave_bytes, None, flags)
        else:
            # Linux API: Create a hidden aplay process and pipe the memory bytes to it
            if self.proc:
                try: self.proc.kill()
                except: pass
            self.proc = subprocess.Popen(['aplay', '-q'], stdin=subprocess.PIPE, preexec_fn=_set_pdeathsig, stderr=subprocess.DEVNULL)
            threading.Thread(target=self._pump, args=(self.proc, self.wave_bytes), daemon=True).start()

    def update(self, sw, sh):
        # Software looping mechanism for Linux (checks if process died and restarts it)
        if not self.is_looping: return
        if OS_TYPE == 'posix':
            if self.proc and self.proc.poll() is not None:
                self.proc = subprocess.Popen(['aplay', '-q'], stdin=subprocess.PIPE, preexec_fn=_set_pdeathsig, stderr=subprocess.DEVNULL)
                threading.Thread(target=self._pump, args=(self.proc, self.wave_bytes), daemon=True).start()
                
    def draw(self, *args, **kwargs): pass # Dummy draw so we can add this object to engine pipeline

class Synth:
    """ Pure software synthesizer generating sine waves mathematically. """
    SR = 44100 # Sample Rate (Standard CD Quality)
    NOTES = {}
    names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    base = 55.0 # Base frequency for note A1
    
    # Procedurally generate a dictionary of note frequencies for 7 octaves
    for o in range(1, 8):
        for i, n in enumerate(names): NOTES[f"{n}{o}"] = base * (2 ** (((o*12+i)-(21))/12.0))
    NOTES['P'] = 0.0 # Pause/Rest frequency

    @staticmethod
    def tone(freqs, ms, vol=0.5, type='sine'):
        # Generates PCM wave bytes for given frequencies over ms duration
        if not isinstance(freqs, list): freqs = [freqs]
        ns = int(Synth.SR * ms / 1000) # Total number of samples needed
        b = bytearray()
        active_f = [f for f in freqs if f > 0]
        num_f = len(active_f) or 1 
        
        for i in range(ns):
            # Audio Envelope: fades volume in and out to prevent clicking sounds
            env = 1.0
            if i < 200: env = i / 200 
            elif i > ns - 200: env = (ns - i) / 200
            
            val = 0.0
            # Mix multiple frequencies (for chords)
            for f in freqs:
                if f > 0:
                    if type == 'noise': val += random.uniform(-1, 1) # White noise generator
                    else: val += math.sin(2*math.pi*f*(i/Synth.SR))  # Pure Sine wave math
            
            # Normalize volume (divide by num of notes) and apply envelope
            val = (val / num_f) * vol * env
            # Clamp limits to 16-bit integer space (-32768 to 32767)
            sample = max(-32768, min(32767, int(val * 32767)))
            b.extend(struct.pack('<h', sample)) # Pack as 16-bit little-endian binary
        return b

    @staticmethod
    def to_memory(d):
        # Wraps the raw PCM data with a standard RIFF WAV file header so the OS recognizes it
        sz = len(d)
        h = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36+sz, b'WAVE', b'fmt ', 16, 1, 1, 44100, 88200, 2, 16, b'data', sz)
        return h + d

class Melody:
    """ Compiler to turn string notation ("C4-1/4") into audio bytearrays. """
    @staticmethod
    def _compile_raw(bpm, notes):
        d = bytearray(); ms = 60000/bpm # Calculate ms per beat based on BPM
        clean_notes = notes.replace('(','').replace(')','').replace(' ','').upper()
        
        for i in clean_notes.split(','):
            if not i: continue
            # Parse chords connected by underscores (e.g. C4_E4-1/4)
            if '-' in i:
                n_str, l = i.split('-')
                notes_list = n_str.split('_')
            elif '_' in i:
                parts = i.rsplit('_', 1)
                if len(parts) == 2:
                    n_str, l = parts[0], parts[1]
                    notes_list = n_str.split('_')
                else: continue
            else: continue
            
            # Calculate duration fraction (supports triplets natively via float division)
            nu, de = map(float, l.split('/'))
            dur = (nu/de)*ms*4
            
            # Retrieve frequency values from dictionary
            freqs = [Synth.NOTES.get(n, 0) for n in notes_list]
            d.extend(Synth.tone(freqs, dur*0.9)) # Note duration (90%)
            d.extend(Synth.tone([0], dur*0.1))   # Silence between notes (10%) to distinguish repeats
        return d

    @staticmethod
    def compile_to_memory(bpm, *tracks):
        # Mixes multiple string tracks into a single unified byte stream
        if not tracks: return Synth.to_memory(bytearray())
        if len(tracks) == 1: return Synth.to_memory(Melody._compile_raw(bpm, tracks[0]))
        
        raw_tracks = [Melody._compile_raw(bpm, t) for t in tracks]
        max_len = max(len(t) for t in raw_tracks) # Find longest track
        arrays = []
        
        # Pad all shorter tracks with zeros (silence) so they sync perfectly when looping
        for t in raw_tracks:
            padded = t + bytearray(max_len - len(t))
            arrays.append(array.array('h', padded))
            
        num_tracks = len(arrays)
        mixed_array = array.array('h')
        
        # Audio Mixing: Add samples together and divide to avoid clipping
        if num_tracks == 2:
            mixed_array.extend(int((x + y) / 2) for x, y in zip(arrays[0], arrays[1]))
        else:
            for i in range(max_len // 2):
                s = sum(arr[i] for arr in arrays)
                mixed_array.append(int(s / num_tracks))
        return Synth.to_memory(mixed_array.tobytes())

class Physics:
    """ Basic physics resolution for collisions. """
    @staticmethod
    def resolve(b1, b2):
        # Calculate overlap using distance formula
        dx = (b1.x+b1.r) - (b2.x+b2.r); dy = (b1.y+b1.r) - (b2.y+b2.r); dist = math.sqrt(dx*dx + dy*dy)
        if dist == 0 or dist > (b1.r + b2.r): return # Not colliding
        
        # Minimum Translation Distance: Separate objects so they aren't stuck inside each other
        overlap = 0.5 * (dist - (b1.r + b2.r))
        b1.x -= overlap * (dx/dist); b1.y -= overlap * (dy/dist)
        b2.x += overlap * (dx/dist); b2.y += overlap * (dy/dist)
        
        # Momentum transfer logic (Elastic collision swapping velocities along normals)
        nx, ny = dx/dist, dy/dist; tx, ty = -ny, nx
        dpT1, dpT2 = b1.vx*tx + b1.vy*ty, b2.vx*tx + b2.vy*ty
        dpN1, dpN2 = b1.vx*nx + b1.vy*ny, b2.vx*nx + b2.vy*ny
        b1.vx, b1.vy = tx*dpT1 + nx*dpN2, ty*dpT1 + ny*dpN2
        b2.vx, b2.vy = tx*dpT2 + nx*dpN1, ty*dpT2 + ny*dpN1

# =================================================================================
# STAGE 3: INPUT & CONTROLS 
# =================================================================================

# Translates generic keys into Windows Virtual-Key Codes and Linux Keysyms
KEY_MAP = {
    'A': {'nt': 0x41, 'posix': b'a'}, 'B': {'nt': 0x42, 'posix': b'b'}, 'C': {'nt': 0x43, 'posix': b'c'},
    'D': {'nt': 0x44, 'posix': b'd'}, 'E': {'nt': 0x45, 'posix': b'e'}, 'F': {'nt': 0x46, 'posix': b'f'},
    'G': {'nt': 0x47, 'posix': b'g'}, 'H': {'nt': 0x48, 'posix': b'h'}, 'I': {'nt': 0x49, 'posix': b'i'},
    'J': {'nt': 0x4A, 'posix': b'j'}, 'K': {'nt': 0x4B, 'posix': b'k'}, 'L': {'nt': 0x4C, 'posix': b'l'},
    'M': {'nt': 0x4D, 'posix': b'm'}, 'N': {'nt': 0x4E, 'posix': b'n'}, 'O': {'nt': 0x4F, 'posix': b'o'},
    'P': {'nt': 0x50, 'posix': b'p'}, 'Q': {'nt': 0x51, 'posix': b'q'}, 'R': {'nt': 0x52, 'posix': b'r'},
    'S': {'nt': 0x53, 'posix': b's'}, 'T': {'nt': 0x54, 'posix': b't'}, 'U': {'nt': 0x55, 'posix': b'u'},
    'V': {'nt': 0x56, 'posix': b'v'}, 'W': {'nt': 0x57, 'posix': b'w'}, 'X': {'nt': 0x58, 'posix': b'x'},
    'Y': {'nt': 0x59, 'posix': b'y'}, 'Z': {'nt': 0x5A, 'posix': b'z'},
    '0': {'nt': 0x30, 'posix': b'0'}, '1': {'nt': 0x31, 'posix': b'1'}, '2': {'nt': 0x32, 'posix': b'2'},
    '3': {'nt': 0x33, 'posix': b'3'}, '4': {'nt': 0x34, 'posix': b'4'}, '5': {'nt': 0x35, 'posix': b'5'},
    '6': {'nt': 0x36, 'posix': b'6'}, '7': {'nt': 0x37, 'posix': b'7'}, '8': {'nt': 0x38, 'posix': b'8'},
    '9': {'nt': 0x39, 'posix': b'9'},
    'ESCAPE': {'nt': 0x1B, 'posix': b'Escape'},
    'UP': {'nt': 0x26, 'posix': b'Up'}, 'DOWN': {'nt': 0x28, 'posix': b'Down'},
    'LEFT': {'nt': 0x25, 'posix': b'Left'}, 'RIGHT': {'nt': 0x27, 'posix': b'Right'},
    'SPACE': {'nt': 0x20, 'posix': b'space'}, 'BACKSPACE': {'nt': 0x08, 'posix': b'BackSpace'}
}

class Keyboard:
    """ Reads hardware key state directly to allow for concurrent keypresses (e.g. W + D). """
    def __init__(self, disp=None): 
        self.disp = disp
        self.keys_ret = ctypes.create_string_buffer(32)
        
    def update(self):
        # Update X11 keymap buffer for Linux
        if OS_TYPE == 'posix' and self.disp:
            SYS['x11'].XQueryKeymap(self.disp, self.keys_ret)

    def is_pressed(self, key):
        k = KEY_MAP.get(key.upper())
        if not k: return False
        if OS_TYPE == 'nt': 
            # GetAsyncKeyState checks highest bit (& 0x8000) to see if key is CURRENTLY held down
            return (SYS['u32'].GetAsyncKeyState(k['nt']) & 0x8000) != 0
        else:
            if not self.disp: return False
            keysym = SYS['x11'].XStringToKeysym(k['posix'])
            keycode = SYS['x11'].XKeysymToKeycode(self.disp, keysym)
            # Check bitwise mask for Linux keys
            return (self.keys_ret.raw[keycode // 8] & (1 << (keycode % 8))) != 0

class Mouse:
    """ Tracks cursor location mapped to the internal engine window coordinates. """
    def __init__(self, engine): 
        self.engine = engine
        self.x, self.y, self.m_mask = 0, 0, 0
        
    def update(self):
        # Linux Mouse Update
        if OS_TYPE == 'posix' and getattr(self.engine, 'disp', None):
            r, c = ctypes.c_ulong(), ctypes.c_ulong()
            rx, ry, wx, wy, m = ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_int(), ctypes.c_uint()
            SYS['x11'].XQueryPointer(self.engine.disp, self.engine.win, ctypes.byref(r), ctypes.byref(c), ctypes.byref(rx), ctypes.byref(ry), ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(m))
            self.x, self.y, self.m_mask = wx.value, wy.value, m.value

    def is_pressed(self, btn):
        if OS_TYPE == 'nt':
            if btn == 'LMB': return (SYS['u32'].GetAsyncKeyState(0x01) & 0x8000) != 0
            if btn == 'RMB': return (SYS['u32'].GetAsyncKeyState(0x02) & 0x8000) != 0
            if btn == 'MMB': return (SYS['u32'].GetAsyncKeyState(0x04) & 0x8000) != 0
        else:
            # Linux masks: 0x0100 for LMB, 0x0400 for RMB, etc.
            if btn == 'LMB': return (self.m_mask & 0x0100) != 0
            if btn == 'MMB': return (self.m_mask & 0x0200) != 0
            if btn == 'RMB': return (self.m_mask & 0x0400) != 0
        return False
        
    def get_pos(self):
        if OS_TYPE == 'nt':
            if not hasattr(self.engine, 'hw'): return 0, 0
            pt = POINT()
            SYS['u32'].GetCursorPos(ctypes.byref(pt)) # Gets absolute screen coordinates
            SYS['u32'].ScreenToClient(self.engine.hw, ctypes.byref(pt)) # Maps it to the game window
            return pt.x, pt.y
        else:
            return self.x, self.y

# =================================================================================
# STAGE 4: MODULAR RENDERERS (ENGINE 2.0 - PRECISION TIMING)
# =================================================================================

class Win32Engine:
    """ The core Windows Rendering and Event Loop system. """
    def __init__(self, title, w, h, bg, fps=60, fullscreen=False):
        self.objs = []
        self.target_fps = fps
        self.real_fps = 0 
        self.frame_delay = 1.0 / fps # Target time per frame
        self.fixed_dt = 1.0 / 60.0   # Fixed timestep to decouple logic from framerate
        self.bg = bg
        
        # Configure Window Dimensions
        if fullscreen:
            SYS['u32'].GetSystemMetrics.argtypes = [ctypes.c_int]
            self.w = SYS['u32'].GetSystemMetrics(0) # Get Desktop Width
            self.h = SYS['u32'].GetSystemMetrics(1) # Get Desktop Height
            win_style = 0x80000000 | 0x10000000     # No Borders (WS_POPUP | WS_VISIBLE)
            start_x, start_y = 0, 0
        else:
            self.w, self.h = w, h
            win_style = WS_OVERLAPPEDWINDOW         # Standard Window With Borders
            start_x, start_y = 100, 100

        # Create Brush Cache to eliminate Memory Churn issues
        self.brush_cache = {}
        self.bg_brush = SYS['g32'].CreateSolidBrush(self.bg)
        
        # Improve windows internal timer to 1ms resolution
        SYS['mm'].timeBeginPeriod(1)
        self.wp = WNDPROCTYPE(self._proc_win)
        h_inst = SYS['k32'].GetModuleHandleW(None)
        
        # Create Window Class template
        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', ctypes.c_uint), ('lpfnWndProc', WNDPROCTYPE), 
                        ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int), 
                        ('hInstance', ctypes.c_void_p), ('hIcon', ctypes.c_void_p), 
                        ('hCursor', ctypes.c_void_p), ('hbrBackground', ctypes.c_void_p), 
                        ('lpszMenuName', ctypes.c_wchar_p), ('lpszClassName', ctypes.c_wchar_p)]
        
        wc = WNDCLASS()
        wc.lpfnWndProc = self.wp
        wc.hInstance = h_inst
        
        # Cursor Fix: Load default arrow to remove blue loading ring
        IDC_ARROW = ctypes.c_void_p(32512)
        wc.hCursor = SYS['u32'].LoadCursorW(None, IDC_ARROW)
        
        class_name = "GE_" + str(random.randint(0,999))
        wc.lpszClassName = class_name
        
        SYS['u32'].RegisterClassW(ctypes.byref(wc))
        
        SYS['u32'].CreateWindowExW.argtypes = [
            ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        SYS['u32'].CreateWindowExW.restype = ctypes.c_void_p
        
        # Actually create the window via Windows OS
        self.hw = SYS['u32'].CreateWindowExW(
            0, class_name, title, win_style, 
            start_x, start_y, self.w, self.h, None, None, h_inst, None
        )
        
        if not self.hw: raise RuntimeError("CRITICAL: Failed to create Win32 Window!")
            
        self.input = Keyboard(None)
        self.mouse = Mouse(self)
        self.active_dc = None

    def _proc_win(self, h, m, w, l):
        # Callback function listening to OS Window Messages (Close, Resize)
        if m == 2: # WM_DESTROY
            SYS['u32'].PostQuitMessage(0)
            return 0
        elif m == 5: # WM_SIZE
            self.w = l & 0xFFFF
            self.h = (l >> 16) & 0xFFFF
            return 0
        return SYS['u32'].DefWindowProcW(h, m, w, l)

    def add(self, o): self.objs.append(o) # Register object to engine
    
    def set_fps_limit(self, fps):
        self.target_fps = fps
        self.frame_delay = 1.0 / fps

    def _get_brush(self, c):
        # Uses Brush Cache to prevent constant memory allocation
        if c not in self.brush_cache:
            self.brush_cache[c] = SYS['g32'].CreateSolidBrush(c)
        return self.brush_cache[c]

    def draw_rect(self, x, y, w, h, c):
        b = self._get_brush(c)
        r = RECT(int(x), int(y), int(x+w), int(y+h))
        SYS['u32'].FillRect(self.active_dc, ctypes.byref(r), b)

    def draw_ellipse(self, x, y, w, h, c):
        b = self._get_brush(c)
        ob = SYS['g32'].SelectObject(self.active_dc, b)
        SYS['g32'].Ellipse(self.active_dc, int(x), int(y), int(x+w), int(y+h))
        SYS['g32'].SelectObject(self.active_dc, ob)

    def draw_text(self, x, y, text, c):
        SYS['g32'].SetTextColor(self.active_dc, c)
        SYS['g32'].SetBkMode(self.active_dc, 1) # Transparent Background
        SYS['g32'].TextOutA(self.active_dc, int(x), int(y), str(text).encode('ascii'), len(str(text)))

    def run(self):
        try:
            # 2.0 Feature: Microsecond Hardware Clock for perfect timing
            last_time = time.perf_counter()
            accumulator = 0.0
            fps_timer = time.perf_counter()
            fps_count = 0
            from ctypes import wintypes
            
            SYS['u32'].ShowWindow(self.hw, SW_SHOW)
            msg = wintypes.MSG()
            
            # --- DOUBLE BUFFERING SETUP ---
            # Creates a virtual screen (mem_dc) in RAM. Drawing happens here first to prevent flickering.
            hdc = SYS['u32'].GetDC(self.hw)
            mem_dc = SYS['g32'].CreateCompatibleDC(hdc)
            mem_bm = SYS['g32'].CreateCompatibleBitmap(hdc, self.w, self.h)
            SYS['g32'].SelectObject(mem_dc, mem_bm)
            prev_sw, prev_sh = self.w, self.h
            self.active_dc = mem_dc 

            # Infinite Game Loop
            while True:
                # 1. Pump OS Messages
                while SYS['u32'].PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == 0x0012: # WM_QUIT
                        SYS['u32'].ReleaseDC(self.hw, hdc)
                        return
                    if self.input.is_pressed('ESCAPE'):
                        SYS['u32'].PostQuitMessage(0)
                    SYS['u32'].TranslateMessage(ctypes.byref(msg))
                    SYS['u32'].DispatchMessageW(ctypes.byref(msg))
                
                # 2. Update Input States
                self.input.update()
                self.mouse.update()

                now = time.perf_counter()
                accumulator += (now - last_time)
                last_time = now
                
                sw, sh = self.w, self.h

                if sw > 0 and sh > 0:
                    # 3. Fixed Time-Step Updates (Logic runs independently of Frame Rate)
                    while accumulator >= self.fixed_dt:
                        for o in self.objs: o.update(sw, sh)
                        accumulator -= self.fixed_dt
                    
                    # Ensure buffer size matches window size
                    if sw != prev_sw or sh != prev_sh:
                        SYS['g32'].DeleteObject(mem_bm) 
                        mem_bm = SYS['g32'].CreateCompatibleBitmap(hdc, sw, sh) 
                        SYS['g32'].SelectObject(mem_dc, mem_bm)
                        prev_sw, prev_sh = sw, sh

                    # 4. Clear screen (Draw Background)
                    SYS['u32'].FillRect(mem_dc, ctypes.byref(RECT(0, 0, sw, sh)), self.bg_brush)

                    # 5. Draw Game Objects to Memory Buffer
                    for o in self.objs: o.draw(self)
                    
                    # 6. Blit Buffer to Screen (Instantaneous Copy)
                    SYS['g32'].BitBlt(hdc, 0, 0, sw, sh, mem_dc, 0, 0, SRCCOPY) 
                    
                    # Count frames
                    fps_count += 1
                    if time.perf_counter() - fps_timer >= 1.0:
                        self.real_fps = fps_count
                        fps_count = 0
                        fps_timer = time.perf_counter()
                
                # 7. Engine 2.0 Precision Control: Hybrid Sleep/Spin-lock
                work_time = time.perf_counter() - now
                sleep_time = self.frame_delay - work_time
                
                if sleep_time > 0:
                    # If we have more than 2ms to spare, sleep using the OS to lower CPU usage
                    if sleep_time > 0.002:
                        time.sleep(sleep_time - 0.002)
                    
                    # Spin-lock (empty while loop) for the final <2ms for mathematically perfect timing
                    while (time.perf_counter() - now) < self.frame_delay:
                        pass
        finally:
            # Memory Cleanup
            for b in self.brush_cache.values():
                SYS['g32'].DeleteObject(b)
            SYS['g32'].DeleteObject(self.bg_brush)
            kill_audio_processes()
            
class X11Engine:
    """ The core Linux Rendering and Event Loop system via X11. """
    def __init__(self, title, w, h, bg, fps=60, fullscreen=False):
        self.objs = []
        self.target_fps = fps
        self.real_fps = 0 
        self.frame_delay = 1.0 / fps
        self.fixed_dt = 1.0 / 60.0  
        self.bg = bg
        
        x11 = SYS['x11']
        self.disp = x11.XOpenDisplay(None)
        self.scr = x11.XDefaultScreen(self.disp)
        
        if fullscreen:
            x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
            x11.XDisplayWidth.restype = ctypes.c_int
            x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
            x11.XDisplayHeight.restype = ctypes.c_int
            self.w = x11.XDisplayWidth(self.disp, self.scr)
            self.h = x11.XDisplayHeight(self.disp, self.scr)
        else:
            self.w, self.h = w, h
            
        self.win = x11.XCreateSimpleWindow(self.disp, x11.XRootWindow(self.disp, self.scr), 0, 0, self.w, self.h, 1, 0, self.bg)
        self.gc = x11.XCreateGC(self.disp, self.win, 0, None)
        
        # Double buffering setup for Linux
        depth = x11.XDefaultDepth(self.disp, self.scr)
        self.pixmap = x11.XCreatePixmap(self.disp, self.win, self.w, self.h, depth)
        
        # Protocol to catch window close button
        self.wm_delete = x11.XInternAtom(self.disp, b"WM_DELETE_WINDOW", 0)
        x11.XSetWMProtocols(self.disp, self.win, ctypes.byref(ctypes.c_ulong(self.wm_delete)), 1)
        
        x11.XStoreName(self.disp, self.win, title.encode('utf-8'))
        x11.XMapWindow(self.disp, self.win)
        x11.XFlush(self.disp)
        
        self.input = Keyboard(self.disp)
        self.mouse = Mouse(self)

    def add(self, o): self.objs.append(o)
    def set_fps_limit(self, fps):
        self.target_fps = fps
        self.frame_delay = 1.0 / fps

    def draw_rect(self, x, y, w, h, c):
        SYS['x11'].XSetForeground(self.disp, self.gc, c)
        SYS['x11'].XFillRectangle(self.disp, self.pixmap, self.gc, int(x), int(y), int(w), int(h))

    def draw_ellipse(self, x, y, w, h, c):
        SYS['x11'].XSetForeground(self.disp, self.gc, c)
        SYS['x11'].XFillArc(self.disp, self.pixmap, self.gc, int(x), int(y), int(w), int(h), 0, 23040)

    def draw_text(self, x, y, text, c):
        SYS['x11'].XSetForeground(self.disp, self.gc, c)
        enc = str(text).encode('ascii')
        SYS['x11'].XDrawString(self.disp, self.pixmap, self.gc, int(x), int(y+10), enc, len(enc))

    def run(self):
        try:
            last_time = time.perf_counter()
            accumulator = 0.0
            fps_timer = time.perf_counter()
            fps_count = 0
            xevent = ctypes.create_string_buffer(192) 

            while True:
                # Handle X11 Window events
                while SYS['x11'].XPending(self.disp):
                    SYS['x11'].XNextEvent(self.disp, xevent)
                    event_type = struct.unpack("i", xevent.raw[:4])[0]
                    if event_type == 33: # Window Closed
                        SYS['x11'].XDestroyWindow(self.disp, self.win)
                        SYS['x11'].XCloseDisplay(self.disp)
                        return 
                        
                self.input.update()
                self.mouse.update()
                
                if self.input.is_pressed('ESCAPE'):
                    SYS['x11'].XDestroyWindow(self.disp, self.win)
                    SYS['x11'].XCloseDisplay(self.disp)
                    return 

                now = time.perf_counter()
                accumulator += (now - last_time)
                last_time = now
                
                while accumulator >= self.fixed_dt:
                    for o in self.objs: o.update(self.w, self.h)
                    accumulator -= self.fixed_dt
                
                # Clear Background
                SYS['x11'].XSetForeground(self.disp, self.gc, self.bg)
                SYS['x11'].XFillRectangle(self.disp, self.pixmap, self.gc, 0, 0, self.w, self.h)
                
                for o in self.objs: o.draw(self)
                
                # Blit Pixmap to Window
                SYS['x11'].XCopyArea(self.disp, self.pixmap, self.win, self.gc, 0, 0, self.w, self.h, 0, 0)
                SYS['x11'].XFlush(self.disp) 
                
                fps_count += 1
                if time.perf_counter() - fps_timer >= 1.0:
                    self.real_fps = fps_count
                    fps_count = 0
                    fps_timer = time.perf_counter()
                
                # Engine 2.0 Precision Control (Hybrid Sleep)
                work_time = time.perf_counter() - now
                sleep_time = self.frame_delay - work_time
                if sleep_time > 0:
                    if sleep_time > 0.002:
                        time.sleep(sleep_time - 0.002)
                    while (time.perf_counter() - now) < self.frame_delay:
                        pass
                        
        finally:
            kill_audio_processes()

# Auto-assign the correct Engine class depending on OS
WindowEngine = Win32Engine if OS_TYPE == 'nt' else X11Engine

# =================================================================================
# STAGE 5: BASIC SHAPES (Graphic Primitive Base Classes)
# =================================================================================

class Box:
    def __init__(self, x, y, w, h, c): 
        self.x, self.y, self.w, self.h, self.c = x, y, w, h, c
    def update(self, sw, sh): pass
    def draw(self, gfx): 
        gfx.draw_rect(self.x, self.y, self.w, self.h, self.c)

class Circle(Box):
    def __init__(self, x, y, r, c): 
        super().__init__(x, y, r*2, r*2, c); self.r = r
    def draw(self, gfx): 
        gfx.draw_ellipse(self.x, self.y, self.w, self.h, self.c)

class TextLine:
    def __init__(self, x, y, text, c):
        self.x, self.y, self.text, self.c = x, y, text, c
    def update(self, sw, sh): pass
    def draw(self, gfx):
        gfx.draw_text(self.x, self.y, self.text, self.c)

class FPSCounter:
    def __init__(self, x, y, game, c):
        self.x, self.y, self.game, self.c = x, y, game, c
    def update(self, sw, sh): pass
    def draw(self, gfx):
        txt = f"FPS: {self.game.real_fps} / Limit: {self.game.target_fps}"
        gfx.draw_text(self.x, self.y, txt, self.c)

# =================================================================================
# STAGE 6: RUNTIME ENTITIES (Custom Game Logic)
# =================================================================================

class HerzController:
    """ Control Engine Clock Speed via keys '1' and '2' """
    def __init__(self, game):
        self.game = game
        self.last_press = 0

    def update(self, sw, sh):
        now = time.time()
        # Debounce the keypress so it doesn't change 60 times a second
        if now - self.last_press > 0.1:
            if self.game.input.is_pressed('1'):
                new_fps = max(10, self.game.target_fps - 10)
                self.game.set_fps_limit(new_fps)
                self.last_press = now
            elif self.game.input.is_pressed('2'):
                new_fps = min(2000, self.game.target_fps + 10)
                self.game.set_fps_limit(new_fps)
                self.last_press = now

    def draw(self, gfx):
        gfx.draw_text(20, 40, "Press '1' / '2' to change FPS limit. ESC to Exit.", RGB(150, 150, 150))

class Ball(Circle):
    """ Interactive Physics Sphere """
    def __init__(self, x, y, r, c, vx, vy, sfx, p):
        super().__init__(x, y, r, c); self.vx, self.vy, self.sfx, self.p = vx, vy, sfx, p
        self.target = None
        
    def update(self, sw, sh):
        # Optional Player Controls for the Ball
        if getattr(self, 'id', 0) == 1 and hasattr(self.p, 'input'):
            if self.p.input.is_pressed('W') or self.p.input.is_pressed('UP'): self.vy -= 0.5
            if self.p.input.is_pressed('S') or self.p.input.is_pressed('DOWN'): self.vy += 0.5
            if self.p.input.is_pressed('A') or self.p.input.is_pressed('LEFT'): self.vx -= 0.5
            if self.p.input.is_pressed('D') or self.p.input.is_pressed('RIGHT'): self.vx += 0.5
            if self.p.input.is_pressed('SPACE'):
                self.vx *= 1.05; self.vy *= 1.05

        self.x += self.vx; self.y += self.vy
        hit = False
        
        # Screen bounds reflection (Bouncing off walls)
        if self.x <= 0: self.x = 0; self.vx *= -1; hit = True
        elif self.x + self.w >= sw: self.x = sw - self.w; self.vx *= -1; hit = True
        if self.y <= 0: self.y = 0; self.vy *= -1; hit = True
        elif self.y + self.h >= sh: self.y = sh - self.h; self.vy *= -1; hit = True
            
        if hit and self.sfx: self.sfx.play()
        # Resolve physics with target
        if self.target and Physics.resolve(self, self.target): self.sfx.play()

class Human:
    """ Main Player character with WASD movement """
    def __init__(self, x, y, c, p):
        self.x, self.y, self.c, self.p = x, y, c, p
        self.vx = self.vy = 0; self.speed = 8
        self.last_click = 0

    def update(self, sw, sh):
        self.vx = self.vy = 0
        # Keyboard controls mapping
        if hasattr(self.p, 'input'):
            if self.p.input.is_pressed('W') or self.p.input.is_pressed('UP'): self.vy = -self.speed
            if self.p.input.is_pressed('S') or self.p.input.is_pressed('DOWN'): self.vy = self.speed
            if self.p.input.is_pressed('A') or self.p.input.is_pressed('LEFT'): self.vx = -self.speed
            if self.p.input.is_pressed('D') or self.p.input.is_pressed('RIGHT'): self.vx = self.speed

        # Mouse click interaction to randomize color
        if hasattr(self.p, 'mouse') and self.p.mouse.is_pressed('LMB'):
            now = time.time()
            if now - self.last_click > 0.2:
                self.c = RGB(random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
                self.last_click = now

        self.x += self.vx; self.y += self.vy
        
        # Clamp coordinates to screen width/height
        self.x = max(0, min(self.x, sw - 40))
        self.y = max(0, min(self.y, sh - 60))

    def draw(self, gfx):
        # Composite object rendering (A circle head on top of a box body)
        hx, hy = int(self.x + 10), int(self.y)
        bx, by = int(self.x), int(self.y + 20)
        gfx.draw_ellipse(hx, hy, 20, 20, self.c)
        gfx.draw_rect(bx, by, 40, 40, self.c)

# =================================================================================
# MAIN EXECUTION
# =================================================================================

if __name__ == "__main__":
    try:
        print("Synthesizing Multitrack Audio into RAM...")
        
        # Track 1 Data
        melody_track = (
            "E4-1/4, E4-1/4, F4-1/4, G4-1/4, "
            "G4-1/4, F4-1/4, E4-1/4, D4-1/4, "
            "C4-1/4, C4-1/4, D4-1/4, E4-1/4, "
            "E4-3/8, D4-1/8, D4-1/2,         "
            "E4-1/4, E4-1/4, F4-1/4, G4-1/4, "
            "G4-1/4, F4-1/4, E4-1/4, D4-1/4, "
            "C4-1/4, C4-1/4, D4-1/4, E4-1/4, "
            "D4-3/8, C4-1/8, C4-1/2"
        )

        # Track 2 Data
        bass_track = (
            "C3-1/2, C3-1/2, "
            "G2-1/2, G2-1/2, "
            "C3-1/2, G2-1/2, "
            "C3-1/2, G2-1/2, "
            "C3-1/2, C3-1/2, "
            "G2-1/2, G2-1/2, "
            "C3-1/2, G2-1/2, "
            "C3-1/2, G2-1/2"
        )
        
        # Compile tracks dynamically
        m_bytes = Melody.compile_to_memory(120, melody_track, bass_track)
        bgm = MemorySound(m_bytes)

        # Initialize Window & Framerate
        game = WindowEngine("Game Engine 2.0 - Precision Runtime", 800, 600, RGB(20,20,20), fullscreen=True)
        game.set_fps_limit(60)
        bgm.play(loop=True) # Play background music
        
        # Initialize Scene Entities
        player = Human(game.w // 2, game.h // 2, RGB(0, 255, 255), game)
        herz_control = HerzController(game)
        fps_display = FPSCounter(20, 20, game, RGB(255, 255, 0))
        
        # Register Entities to Engine Pipeline
        game.add(player)
        game.add(herz_control)
        game.add(fps_display)
        game.add(bgm) 

        print("[*] Engine 2.0 Running. Fullscreen Mode Enabled.")
        
        # Start Master Game Loop
        game.run()

    # Catch any fatal errors and prevent immediate crash so dev can read traceback
    except Exception as e:
        print("\n" + "="*50)
        print("CRITICAL ENGINE FAILURE:")
        print("="*50)
        traceback.print_exc()
        print("="*50)
        input("Press Enter to exit...")
