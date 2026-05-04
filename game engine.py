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

# Detect the host operating system: 'nt' means Windows, 'posix' means Linux or macOS.
OS_TYPE = os.name

# Global dictionary for OS-specific library handles (DLLs on Windows, .so files on Linux).
SYS = {}

# Global list tracking all active audio process/sound objects for guaranteed cleanup on exit.
ACTIVE_SOUNDS = []

# True when the Python interpreter is running in 64-bit mode.
# Affects pointer sizes used in ctypes structures and function signatures.
ARCH_64 = (ctypes.sizeof(ctypes.c_void_p) == 8)


def _set_pdeathsig():
    """
    Linux only: Sets the child process's 'parent death signal' to SIGTERM (15).
    This ensures that any audio subprocess spawned by this engine is automatically
    killed if the parent Python process dies unexpectedly (e.g., crash or SIGKILL).
    Without this, orphan audio processes would keep playing after the game closes.
    """
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                                ctypes.c_ulong, ctypes.c_ulong]
        libc.prctl(1, 15, 0, 0, 0)
    except:
        pass


@atexit.register
def kill_audio_processes():
    """
    Registered with Python's atexit module, so it runs automatically when the
    interpreter exits — whether cleanly or due to an unhandled exception.

    On Linux: kills all tracked 'aplay' subprocesses.
    On Windows: stops any currently playing WAV via winmm, and restores the
    system multimedia timer resolution back to its default (saves battery/CPU).
    """
    for s in ACTIVE_SOUNDS:
        if getattr(s, 'proc', None):
            try:
                s.proc.kill()
            except:
                pass
    if OS_TYPE == 'nt':
        # Passing None stops any sound currently playing via PlaySoundA.
        ctypes.windll.winmm.PlaySoundA(None, None, 0)
        # Undo the 1ms timer resolution we set at startup to avoid wasting power.
        SYS['mm'].timeEndPeriod(1)


if OS_TYPE == 'nt':
    # -------------------------------------------------------------------------
    # WINDOWS SETUP: Load Win32 DLLs and define all required API signatures.
    # Specifying argtypes/restype prevents silent memory corruption from
    # mismatched argument sizes, especially on 64-bit systems.
    # -------------------------------------------------------------------------
    from ctypes import wintypes

    SYS['u32'] = ctypes.windll.user32   # Window management, input, message loop
    SYS['g32'] = ctypes.windll.gdi32    # 2D drawing primitives and device contexts
    SYS['k32'] = ctypes.windll.kernel32 # Process/module handles
    SYS['mm']  = ctypes.windll.winmm    # Multimedia: audio playback and timers

    # Standard Win32 constants used throughout the engine.
    WS_OVERLAPPEDWINDOW, CW_USEDEFAULT = 0x00CF0000, 0x80000000
    WM_DESTROY, WM_PAINT = 2, 0x000F
    SW_SHOW, SRCCOPY = 5, 0x00CC0020
    PM_REMOVE = 1

    # POINT: used by GetCursorPos to receive absolute screen coordinates.
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    # RECT: used by FillRect and BitBlt to define rectangular regions.
    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]

    # On 64-bit Windows, window procedure parameters are 64-bit wide.
    # Using the wrong width here causes stack corruption and random crashes.
    if ARCH_64:
        LRESULT, WPARAM_T, LPARAM_T = ctypes.c_longlong, ctypes.c_ulonglong, ctypes.c_longlong
    else:
        LRESULT, WPARAM_T, LPARAM_T = ctypes.c_long, ctypes.c_uint, ctypes.c_long

    # Function pointer type for the window procedure callback passed to RegisterClassW.
    WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T)

    SYS['u32'].DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM_T, LPARAM_T]
    SYS['u32'].DefWindowProcW.restype = LRESULT

    SYS['mm'].PlaySoundA.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_uint]
    SYS['mm'].PlaySoundA.restype = ctypes.c_int

    SYS['u32'].GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    SYS['u32'].ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(POINT)]

    SYS['mm'].timeBeginPeriod.argtypes = [ctypes.c_uint]
    SYS['mm'].timeEndPeriod.argtypes = [ctypes.c_uint]

    # LoadCursorW is needed to load the default arrow cursor and prevent
    # the blue spinning-wheel cursor from persisting during window creation.
    SYS['u32'].LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    SYS['u32'].LoadCursorW.restype = ctypes.c_void_p

elif OS_TYPE == 'posix':
    # -------------------------------------------------------------------------
    # LINUX/POSIX SETUP: Load libX11 and define all required function signatures.
    # Every argtypes/restype declaration here was determined by the X11 C headers.
    # Missing or wrong type declarations cause silent 64-bit pointer truncation,
    # which produces non-reproducible crashes (bus errors, BadDrawable X errors).
    # -------------------------------------------------------------------------
    import ctypes.util

    x11_path = ctypes.util.find_library("X11")
    if not x11_path:
        raise RuntimeError("CRITICAL: libX11.so not found. Is an X11 display server running?")

    SYS['x11'] = ctypes.cdll.LoadLibrary(x11_path)
    x11 = SYS['x11']

    # --- Return types (restype) ---
    # Omitting restype defaults to c_int, which silently truncates 64-bit pointers
    # and causes corrupted display handles on 64-bit Linux.
    x11.XOpenDisplay.restype = ctypes.c_void_p         # Returns Display* (pointer)
    x11.XCreateSimpleWindow.restype = ctypes.c_ulong   # Returns Window (XID, 32-bit on X11)
    x11.XCreateGC.restype = ctypes.c_void_p            # Returns GC (pointer)
    x11.XDefaultScreen.restype = ctypes.c_int
    x11.XRootWindow.restype = ctypes.c_ulong
    x11.XCreatePixmap.restype = ctypes.c_ulong
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XDefaultDepth.restype = ctypes.c_int
    x11.XDisplayWidth.restype = ctypes.c_int
    x11.XDisplayHeight.restype = ctypes.c_int
    # These two were the primary cause of previous crashes:
    # XStringToKeysym returns a 64-bit KeySym on 64-bit systems.
    # XKeysymToKeycode takes that 64-bit value; passing a truncated int corrupts the stack.
    x11.XStringToKeysym.restype = ctypes.c_ulong
    x11.XKeysymToKeycode.restype = ctypes.c_ubyte

    # --- Argument types (argtypes) ---
    # Display and screen queries
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XDefaultScreen.argtypes = [ctypes.c_void_p]
    x11.XRootWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
    x11.XDefaultDepth.argtypes = [ctypes.c_void_p, ctypes.c_int]

    # Window and graphics context creation
    x11.XCreateSimpleWindow.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_ulong
    ]
    x11.XCreateGC.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    x11.XCreatePixmap.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                   ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]

    # Window management
    x11.XMapWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XStoreName.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_char_p]
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XSetWMProtocols.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
                                     ctypes.POINTER(ctypes.c_ulong), ctypes.c_int]
    x11.XFlush.argtypes = [ctypes.c_void_p]

    # Drawing primitives
    x11.XSetForeground.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    x11.XFillRectangle.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    x11.XFillArc.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                               ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                               ctypes.c_int, ctypes.c_int]
    x11.XDrawString.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                                  ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    x11.XCopyArea.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                               ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                               ctypes.c_uint, ctypes.c_uint, ctypes.c_int, ctypes.c_int]

    # Input: keyboard and mouse query functions.
    # XKeysymToKeycode's second argument must be c_ulong to receive the full 64-bit KeySym.
    # Passing c_int here was the root cause of the previous process-killing crash.
    x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
    x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XQueryKeymap.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    x11.XQueryPointer.argtypes = [
        ctypes.c_void_p, ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_uint)
    ]
    x11.XPending.argtypes = [ctypes.c_void_p]
    x11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

    # Cleanup
    x11.XDestroyWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]


# =================================================================================
# STAGE 2: AUDIO & PHYSICS
# =================================================================================

def RGB(r, g, b):
    """
    Packs three 0-255 channel values into a single 32-bit integer color code.

    Windows GDI expects the byte order 0x00BBGGRR (blue in the low byte).
    X11 expects standard 0x00RRGGBB (red in the high byte).
    This function handles the difference transparently so callers can always
    write RGB(red, green, blue) regardless of platform.
    """
    if OS_TYPE == 'nt':
        return r | (g << 8) | (b << 16)  # Windows: 0x00BBGGRR
    return (r << 16) | (g << 8) | b       # Linux:   0x00RRGGBB


class MemorySound:
    """
    Plays a raw WAV byte sequence stored entirely in RAM.

    On Windows, PlaySoundA with SND_MEMORY plays directly from a pointer to the
    byte buffer — no temporary file is ever written to disk.
    On Linux, the bytes are piped to stdin of a spawned 'aplay' subprocess
    from a background thread so the main game loop never blocks.
    """

    def __init__(self, wave_bytes):
        # Store as immutable bytes so the buffer pointer stays valid throughout playback.
        self.wave_bytes = bytes(wave_bytes)
        self.is_looping = False
        self.proc = None                  # Handle to the Linux aplay subprocess, if any.
        ACTIVE_SOUNDS.append(self)        # Register so kill_audio_processes() can clean up.

    def _pump(self, p, data):
        """
        Background thread target: writes all WAV bytes to aplay's stdin, then closes it.
        Running this in a thread prevents the main loop from blocking on a large write.
        Exceptions are silently swallowed because the process may be killed externally
        before the write completes (e.g., rapid repeated calls to play()).
        """
        try:
            p.stdin.write(data)
            p.stdin.close()
        except:
            pass

    def play(self, loop=False):
        """
        Starts audio playback.

        loop=True keeps the sound repeating indefinitely.
        On Windows this is handled natively by the SND_LOOP flag.
        On Linux it is emulated by the update() method, which restarts
        the aplay process each time it exits.
        """
        self.is_looping = loop
        if OS_TYPE == 'nt':
            # Flags: SND_MEMORY (0x04) = data is a pointer, not a filename.
            #        SND_ASYNC  (0x01) = return immediately; don't block.
            #        SND_LOOP   (0x08) = repeat until PlaySoundA(None) is called.
            flags = 0x0004 | 0x0001
            if loop:
                flags |= 0x0008
            SYS['mm'].PlaySoundA(self.wave_bytes, None, flags)
        else:
            # Kill any previous aplay instance to avoid overlapping audio.
            if self.proc:
                try:
                    self.proc.kill()
                except:
                    pass
            # Launch aplay in quiet mode; preexec_fn ties its lifetime to ours.
            self.proc = subprocess.Popen(
                ['aplay', '-q'],
                stdin=subprocess.PIPE,
                preexec_fn=_set_pdeathsig,
                stderr=subprocess.DEVNULL
            )
            threading.Thread(target=self._pump, args=(self.proc, self.wave_bytes),
                             daemon=True).start()

    def update(self, sw, sh):
        """
        Called every game tick. On Linux, implements software looping by checking
        whether the aplay process has terminated (poll() returns a non-None exit code)
        and immediately spawning a fresh one. Has no effect on Windows.
        """
        if not self.is_looping:
            return
        if OS_TYPE == 'posix':
            if self.proc and self.proc.poll() is not None:
                # Process exited — restart it to continue the loop.
                self.proc = subprocess.Popen(
                    ['aplay', '-q'],
                    stdin=subprocess.PIPE,
                    preexec_fn=_set_pdeathsig,
                    stderr=subprocess.DEVNULL
                )
                threading.Thread(target=self._pump, args=(self.proc, self.wave_bytes),
                                 daemon=True).start()

    def draw(self, *args, **kwargs):
        """
        No-op draw method. Allows MemorySound to be added to the engine's object
        pipeline (engine.add(sound)) so its update() is called each frame without
        special-casing it in the main loop.
        """
        pass


class Synth:
    """
    Pure-software synthesizer. Generates PCM audio samples mathematically
    using sine waves — no external audio library required.
    """

    SR = 44100  # Sample rate in Hz (CD quality: 44,100 samples per second).

    # Build the complete note-frequency table for octaves 1–7.
    # A4 = 440 Hz is the international tuning standard. The formula
    # freq = 55 * 2^((midi_note - 21) / 12) derives every other note from A1 = 55 Hz.
    NOTES = {}
    names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    base = 55.0  # Frequency of A1
    for o in range(1, 8):
        for i, n in enumerate(names):
            NOTES[f"{n}{o}"] = base * (2 ** (((o * 12 + i) - 21) / 12.0))
    NOTES['P'] = 0.0  # 'P' represents a rest (silence).

    @staticmethod
    def tone(freqs, ms, vol=0.5, type='sine'):
        """
        Generates 16-bit mono PCM audio data for a given set of frequencies.

        freqs : list of Hz values to mix together (use a list for chords).
        ms    : duration of the tone in milliseconds.
        vol   : master volume scalar (0.0 – 1.0).
        type  : 'sine' for a pure tone, 'noise' for white noise.

        Returns a bytearray of little-endian signed 16-bit samples.

        The 200-sample linear ramp at the start and end (the "envelope") prevents
        the abrupt amplitude jumps that cause audible clicks at note boundaries.
        """
        if not isinstance(freqs, list):
            freqs = [freqs]
        ns = int(Synth.SR * ms / 1000)  # Total samples needed for this duration.
        b = bytearray()
        active_f = [f for f in freqs if f > 0]
        num_f = len(active_f) or 1  # Avoid division by zero for pure rests.

        for i in range(ns):
            # Amplitude envelope: linear fade-in over the first 200 samples,
            # linear fade-out over the last 200, full amplitude in between.
            env = 1.0
            if i < 200:
                env = i / 200
            elif i > ns - 200:
                env = (ns - i) / 200

            val = 0.0
            for f in freqs:
                if f > 0:
                    if type == 'noise':
                        val += random.uniform(-1, 1)           # Uniform white noise
                    else:
                        val += math.sin(2 * math.pi * f * (i / Synth.SR))  # Sine wave

            # Average the voices to prevent inter-channel clipping, then scale.
            val = (val / num_f) * vol * env

            # Clamp to the 16-bit signed integer range before packing.
            sample = max(-32768, min(32767, int(val * 32767)))
            b.extend(struct.pack('<h', sample))  # '<h' = little-endian int16
        return b

    @staticmethod
    def to_memory(d):
        """
        Wraps raw PCM bytes in a minimal RIFF/WAV header so the OS recognizes
        the data as a valid WAV stream when passed to PlaySoundA or aplay.

        Header layout (44 bytes total):
          RIFF chunk descriptor → fmt sub-chunk (PCM, mono, 44100 Hz, 16-bit) → data sub-chunk
        """
        sz = len(d)
        h = struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF', 36 + sz, b'WAVE',
            b'fmt ', 16,          # fmt chunk size = 16 for PCM
            1,                    # Audio format = 1 (PCM, uncompressed)
            1,                    # Number of channels = 1 (mono)
            44100,                # Sample rate
            88200,                # Byte rate = SampleRate * NumChannels * BitsPerSample/8
            2,                    # Block align = NumChannels * BitsPerSample/8
            16,                   # Bits per sample
            b'data', sz
        )
        return h + d


class Melody:
    """
    Compiles a human-readable note string into WAV bytes.

    Note string format:  "Note1_Note2-Duration, ..."
      Notes   : standard names like C4, D#3, P (rest).
      Duration: a fraction of a whole note, e.g. 1/4 = quarter, 1/12 = triplet eighth.
      Chord   : multiple notes joined by underscores before the dash, e.g. C4_E4_G4-1/4.

    Multiple tracks can be compiled and mixed together in compile_to_memory().
    """

    @staticmethod
    def _compile_raw(bpm, notes):
        """
        Parses a note string and synthesizes the corresponding PCM bytes.
        Returns a bytearray (no WAV header — that is added by compile_to_memory).

        Each note is rendered at 90% of its calculated duration, with 10% silence
        appended after it. This small gap keeps repeated identical notes audibly distinct.
        """
        d = bytearray()
        ms = 60000 / bpm  # Duration of one beat in milliseconds at this BPM.

        # Strip chord grouping parentheses and whitespace, then normalize to uppercase.
        clean_notes = notes.replace('(', '').replace(')', '').replace(' ', '').upper()

        for i in clean_notes.split(','):
            if not i:
                continue

            # Parse "NOTES-DURATION" — the dash separates pitch from length.
            if '-' in i:
                n_str, l = i.split('-')
                notes_list = n_str.split('_')  # Chord: C4_E4_G4
            elif '_' in i:
                # Fallback parser for edge-case formatting without an explicit dash.
                parts = i.rsplit('_', 1)
                if len(parts) == 2:
                    n_str, l = parts[0], parts[1]
                    notes_list = n_str.split('_')
                else:
                    continue
            else:
                continue

            # Convert fraction string "1/4" to a float, then scale to milliseconds.
            # Using float division makes triplets (1/12, 1/6) work without integer rounding.
            nu, de = map(float, l.split('/'))
            dur = (nu / de) * ms * 4  # × 4 because 1/1 = one whole note = 4 beats.

            freqs = [Synth.NOTES.get(n, 0) for n in notes_list]
            d.extend(Synth.tone(freqs, dur * 0.9))  # Audible portion: 90%
            d.extend(Synth.tone([0], dur * 0.1))    # Silent gap:      10%
        return d

    @staticmethod
    def compile_to_memory(bpm, *tracks):
        """
        Compiles one or more note-string tracks into a single mixed WAV bytestream.

        Shorter tracks are zero-padded (silence) to match the length of the longest
        track before mixing. This guarantees that all tracks loop in perfect sync.

        Mixing is done by sample-wise averaging: (a + b) / 2 for two tracks, or
        sum / n for more, which keeps the output within the 16-bit amplitude range.
        """
        if not tracks:
            return Synth.to_memory(bytearray())
        if len(tracks) == 1:
            return Synth.to_memory(Melody._compile_raw(bpm, tracks[0]))

        raw_tracks = [Melody._compile_raw(bpm, t) for t in tracks]
        max_len = max(len(t) for t in raw_tracks)  # Length of the longest track in bytes.

        # Pad every track to the same byte length with silence (0x00 = zero amplitude).
        arrays = []
        for t in raw_tracks:
            padded = t + bytearray(max_len - len(t))
            arrays.append(array.array('h', padded))  # Interpret bytes as int16 samples.

        num_tracks = len(arrays)
        mixed_array = array.array('h')

        # Mix: average samples across all tracks to prevent clipping.
        if num_tracks == 2:
            mixed_array.extend(int((x + y) / 2) for x, y in zip(arrays[0], arrays[1]))
        else:
            for i in range(max_len // 2):  # // 2 because each sample is 2 bytes (int16).
                s = sum(arr[i] for arr in arrays)
                mixed_array.append(int(s / num_tracks))

        return Synth.to_memory(mixed_array.tobytes())


class Physics:
    """
    Minimal 2D elastic collision resolution between two circular bodies.
    """

    @staticmethod
    def resolve(b1, b2):
        """
        Checks whether two circles overlap and, if they do, separates them
        and exchanges their velocity components along the collision normal.

        Uses the center-to-center distance formula:
          dist < r1 + r2  →  circles are intersecting.

        Separation is split equally (50/50) between the two bodies.
        Velocity exchange uses the 1D elastic collision solution projected
        onto the collision normal and tangent axes.
        """
        # Offset by radius to get center coordinates from top-left corner position.
        dx = (b1.x + b1.r) - (b2.x + b2.r)
        dy = (b1.y + b1.r) - (b2.y + b2.r)
        dist = math.sqrt(dx * dx + dy * dy)

        if dist == 0 or dist > (b1.r + b2.r):
            return  # No intersection; nothing to resolve.

        # Minimum Translation Distance: how much each circle must move to stop overlapping.
        overlap = 0.5 * (dist - (b1.r + b2.r))
        b1.x -= overlap * (dx / dist)
        b1.y -= overlap * (dy / dist)
        b2.x += overlap * (dx / dist)
        b2.y += overlap * (dy / dist)

        # Decompose velocities into normal (along collision axis) and tangent (perpendicular) components.
        nx, ny = dx / dist, dy / dist   # Unit normal vector
        tx, ty = -ny, nx                # Unit tangent vector (perpendicular to normal)

        # Dot products give the scalar speed in each direction for each body.
        dpT1 = b1.vx * tx + b1.vy * ty
        dpT2 = b2.vx * tx + b2.vy * ty
        dpN1 = b1.vx * nx + b1.vy * ny
        dpN2 = b2.vx * nx + b2.vy * ny

        # For equal-mass elastic collisions, normal components are simply swapped.
        b1.vx, b1.vy = tx * dpT1 + nx * dpN2, ty * dpT1 + ny * dpN2
        b2.vx, b2.vy = tx * dpT2 + nx * dpN1, ty * dpT2 + ny * dpN1


# =================================================================================
# STAGE 3: INPUT & CONTROLS
# =================================================================================

# Maps logical key names to platform-specific codes.
# Windows uses Virtual-Key codes (integers); Linux uses X11 keysym name strings (bytes).
KEY_MAP = {
    'A': {'nt': 0x41, 'posix': b'a'}, 'B': {'nt': 0x42, 'posix': b'b'},
    'C': {'nt': 0x43, 'posix': b'c'}, 'D': {'nt': 0x44, 'posix': b'd'},
    'E': {'nt': 0x45, 'posix': b'e'}, 'F': {'nt': 0x46, 'posix': b'f'},
    'G': {'nt': 0x47, 'posix': b'g'}, 'H': {'nt': 0x48, 'posix': b'h'},
    'I': {'nt': 0x49, 'posix': b'i'}, 'J': {'nt': 0x4A, 'posix': b'j'},
    'K': {'nt': 0x4B, 'posix': b'k'}, 'L': {'nt': 0x4C, 'posix': b'l'},
    'M': {'nt': 0x4D, 'posix': b'm'}, 'N': {'nt': 0x4E, 'posix': b'n'},
    'O': {'nt': 0x4F, 'posix': b'o'}, 'P': {'nt': 0x50, 'posix': b'p'},
    'Q': {'nt': 0x51, 'posix': b'q'}, 'R': {'nt': 0x52, 'posix': b'r'},
    'S': {'nt': 0x53, 'posix': b's'}, 'T': {'nt': 0x54, 'posix': b't'},
    'U': {'nt': 0x55, 'posix': b'u'}, 'V': {'nt': 0x56, 'posix': b'v'},
    'W': {'nt': 0x57, 'posix': b'w'}, 'X': {'nt': 0x58, 'posix': b'x'},
    'Y': {'nt': 0x59, 'posix': b'y'}, 'Z': {'nt': 0x5A, 'posix': b'z'},
    '0': {'nt': 0x30, 'posix': b'0'}, '1': {'nt': 0x31, 'posix': b'1'},
    '2': {'nt': 0x32, 'posix': b'2'}, '3': {'nt': 0x33, 'posix': b'3'},
    '4': {'nt': 0x34, 'posix': b'4'}, '5': {'nt': 0x35, 'posix': b'5'},
    '6': {'nt': 0x36, 'posix': b'6'}, '7': {'nt': 0x37, 'posix': b'7'},
    '8': {'nt': 0x38, 'posix': b'8'}, '9': {'nt': 0x39, 'posix': b'9'},
    'ESCAPE':    {'nt': 0x1B, 'posix': b'Escape'},
    'UP':        {'nt': 0x26, 'posix': b'Up'},
    'DOWN':      {'nt': 0x28, 'posix': b'Down'},
    'LEFT':      {'nt': 0x25, 'posix': b'Left'},
    'RIGHT':     {'nt': 0x27, 'posix': b'Right'},
    'SPACE':     {'nt': 0x20, 'posix': b'space'},
    'BACKSPACE': {'nt': 0x08, 'posix': b'BackSpace'},
}


class Keyboard:
    """
    Queries the hardware key state directly, bypassing the OS event queue.
    This enables detecting multiple simultaneous key presses (e.g., W + D + SPACE)
    which is impossible with a standard event-driven input model.
    """

    def __init__(self, disp=None):
        self.disp = disp
        # 256-bit (32-byte) buffer used by XQueryKeymap to store the state of all keycodes.
        self.keys_ret = ctypes.create_string_buffer(32)

    def update(self):
        """
        Refreshes the Linux keymap snapshot. Must be called once per frame
        before any is_pressed() calls. Has no effect on Windows (GetAsyncKeyState
        queries hardware state directly each call).
        """
        if OS_TYPE == 'posix' and self.disp:
            SYS['x11'].XQueryKeymap(self.disp, self.keys_ret)

    def is_pressed(self, key):
        """
        Returns True if the named key is physically held down right now.

        Windows: GetAsyncKeyState bit 15 is set while the key is held.
        Linux:   The 256-bit XQueryKeymap buffer encodes each key as a single bit.
                 keycode // 8 selects the correct byte; (1 << keycode % 8) is the bit mask.
        """
        k = KEY_MAP.get(key.upper())
        if not k:
            return False
        if OS_TYPE == 'nt':
            # Bit 15 (0x8000) is the "currently pressed" flag. Bit 0 is the toggle state.
            return (SYS['u32'].GetAsyncKeyState(k['nt']) & 0x8000) != 0
        else:
            if not self.disp:
                return False
            keysym  = SYS['x11'].XStringToKeysym(k['posix'])
            keycode = SYS['x11'].XKeysymToKeycode(self.disp, keysym)
            return (self.keys_ret.raw[keycode // 8] & (1 << (keycode % 8))) != 0


class Mouse:
    """
    Tracks the cursor position in window-local coordinates and the state
    of all three mouse buttons (LMB, MMB, RMB).
    """

    def __init__(self, engine):
        self.engine = engine
        self.x = 0         # Cursor X in window space
        self.y = 0         # Cursor Y in window space
        self.m_mask = 0    # Linux button bitmask returned by XQueryPointer

    def update(self):
        """
        Updates cursor position and button state for Linux each frame.
        On Windows, get_pos() and is_pressed() query the OS directly on demand,
        so no per-frame update is needed.
        """
        if OS_TYPE == 'posix' and getattr(self.engine, 'disp', None):
            r, c = ctypes.c_ulong(), ctypes.c_ulong()
            rx, ry = ctypes.c_int(), ctypes.c_int()  # Root-relative coordinates (unused)
            wx, wy = ctypes.c_int(), ctypes.c_int()  # Window-relative coordinates (used)
            m = ctypes.c_uint()                       # Button/modifier mask
            SYS['x11'].XQueryPointer(
                self.engine.disp, self.engine.win,
                ctypes.byref(r), ctypes.byref(c),
                ctypes.byref(rx), ctypes.byref(ry),
                ctypes.byref(wx), ctypes.byref(wy),
                ctypes.byref(m)
            )
            self.x, self.y, self.m_mask = wx.value, wy.value, m.value

    def is_pressed(self, btn):
        """
        Returns True if the specified mouse button is currently held.

        Windows: Uses GetAsyncKeyState with the virtual button codes (0x01, 0x02, 0x04).
        Linux:   Reads the button bits from the XQueryPointer modifier mask.
                 Bit 8 (0x0100) = Button 1 (LMB)
                 Bit 9 (0x0200) = Button 2 (MMB)
                 Bit 10 (0x0400) = Button 3 (RMB)
        """
        if OS_TYPE == 'nt':
            if btn == 'LMB': return (SYS['u32'].GetAsyncKeyState(0x01) & 0x8000) != 0
            if btn == 'RMB': return (SYS['u32'].GetAsyncKeyState(0x02) & 0x8000) != 0
            if btn == 'MMB': return (SYS['u32'].GetAsyncKeyState(0x04) & 0x8000) != 0
        else:
            if btn == 'LMB': return (self.m_mask & 0x0100) != 0
            if btn == 'MMB': return (self.m_mask & 0x0200) != 0
            if btn == 'RMB': return (self.m_mask & 0x0400) != 0
        return False

    def get_pos(self):
        """
        Returns the current cursor position as (x, y) in window-local space.

        On Windows: GetCursorPos gives absolute screen coordinates; ScreenToClient
        converts them to the coordinate space of our game window.
        On Linux: the values from the last update() call are used directly.
        """
        if OS_TYPE == 'nt':
            if not hasattr(self.engine, 'hw'):
                return 0, 0
            pt = POINT()
            SYS['u32'].GetCursorPos(ctypes.byref(pt))          # Absolute screen coords
            SYS['u32'].ScreenToClient(self.engine.hw, ctypes.byref(pt))  # → window coords
            return pt.x, pt.y
        else:
            return self.x, self.y


# =================================================================================
# STAGE 4: MODULAR RENDERERS (ENGINE 2.0 - PRECISION TIMING)
# =================================================================================

class Win32Engine:
    """
    Windows rendering backend built on the Win32 GDI API.

    Key design decisions:
    - Double-buffering: all drawing goes to an off-screen memory DC first;
      the finished frame is copied to the real window in a single BitBlt call,
      eliminating visible tearing and flickering.
    - Brush cache: GDI HBRUSH objects are expensive to create. We cache one per
      color value so each unique color is only allocated once per session.
    - Fixed timestep: game logic updates run at a constant 1/60 s regardless of
      the rendering frame rate, keeping physics deterministic.
    - Hybrid sleep: coarse OS sleep brings us close to the frame deadline, then a
      busy-spin covers the last <2 ms for microsecond-accurate frame pacing.
    """

    def __init__(self, title, w, h, bg, fps=60, fullscreen=False):
        self.objs = []
        self.target_fps = fps
        self.real_fps = 0
        self.frame_delay = 1.0 / fps   # Target seconds per frame
        self.fixed_dt = 1.0 / 60.0    # Fixed logic timestep (always 60 Hz)
        self.bg = bg

        if fullscreen:
            SYS['u32'].GetSystemMetrics.argtypes = [ctypes.c_int]
            self.w = SYS['u32'].GetSystemMetrics(0)  # SM_CXSCREEN: desktop width in pixels
            self.h = SYS['u32'].GetSystemMetrics(1)  # SM_CYSCREEN: desktop height in pixels
            win_style = 0x80000000 | 0x10000000      # WS_POPUP | WS_VISIBLE: borderless fullscreen
            start_x, start_y = 0, 0
        else:
            self.w, self.h = w, h
            win_style = WS_OVERLAPPEDWINDOW           # Standard window with title bar and borders
            start_x, start_y = 100, 100

        # Pre-create a solid brush for the background fill used every frame.
        self.brush_cache = {}
        self.bg_brush = SYS['g32'].CreateSolidBrush(self.bg)

        # Raise the Windows multimedia timer resolution to 1 ms.
        # The default is ~15 ms, which makes time.sleep() too coarse for smooth frame pacing.
        SYS['mm'].timeBeginPeriod(1)

        # Keep a reference to the window procedure so the garbage collector
        # doesn't free the ctypes function pointer while the window is alive.
        self.wp = WNDPROCTYPE(self._proc_win)
        h_inst = SYS['k32'].GetModuleHandleW(None)

        # Define the WNDCLASSW structure inline to avoid module-level clutter.
        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ('style',         ctypes.c_uint),
                ('lpfnWndProc',   WNDPROCTYPE),
                ('cbClsExtra',    ctypes.c_int),
                ('cbWndExtra',    ctypes.c_int),
                ('hInstance',     ctypes.c_void_p),
                ('hIcon',         ctypes.c_void_p),
                ('hCursor',       ctypes.c_void_p),
                ('hbrBackground', ctypes.c_void_p),
                ('lpszMenuName',  ctypes.c_wchar_p),
                ('lpszClassName', ctypes.c_wchar_p),
            ]

        wc = WNDCLASS()
        wc.lpfnWndProc = self.wp
        wc.hInstance = h_inst

        # Explicitly load the arrow cursor. Without this, Windows shows the blue
        # "application loading" spinner for the lifetime of the window.
        IDC_ARROW = ctypes.c_void_p(32512)
        wc.hCursor = SYS['u32'].LoadCursorW(None, IDC_ARROW)

        # Use a randomised class name to allow multiple engine instances in one process.
        class_name = "GE_" + str(random.randint(0, 999))
        wc.lpszClassName = class_name
        SYS['u32'].RegisterClassW(ctypes.byref(wc))

        SYS['u32'].CreateWindowExW.argtypes = [
            ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        ]
        SYS['u32'].CreateWindowExW.restype = ctypes.c_void_p

        self.hw = SYS['u32'].CreateWindowExW(
            0, class_name, title, win_style,
            start_x, start_y, self.w, self.h,
            None, None, h_inst, None
        )

        if not self.hw:
            raise RuntimeError("CRITICAL: Failed to create Win32 window!")

        self.input = Keyboard(None)
        self.mouse = Mouse(self)
        self.active_dc = None  # Set to the memory DC at the start of run()

    def _proc_win(self, h, m, w, l):
        """
        Window procedure: receives OS messages and handles the ones we care about.
        All unhandled messages are forwarded to DefWindowProcW (the OS default handler).

        WM_DESTROY (2): posted when the user clicks the X button. We respond with
                         PostQuitMessage(0) to inject a WM_QUIT into the message queue,
                         which causes PeekMessageW to return msg.message == 0x0012.
        WM_SIZE (5):     sent when the window is resized. We update self.w/h so the
                         double-buffer bitmap can be recreated at the new dimensions.
        """
        if m == 2:   # WM_DESTROY
            SYS['u32'].PostQuitMessage(0)
            return 0
        elif m == 5:  # WM_SIZE — low word = new width, high word = new height
            self.w = l & 0xFFFF
            self.h = (l >> 16) & 0xFFFF
            return 0
        return SYS['u32'].DefWindowProcW(h, m, w, l)

    def add(self, o):
        """Register a game object. update() and draw() will be called on it each frame."""
        self.objs.append(o)

    def set_fps_limit(self, fps):
        """Change the target frame rate at runtime. Called by HerzController."""
        self.target_fps = fps
        self.frame_delay = 1.0 / fps

    def _get_brush(self, c):
        """
        Returns a cached HBRUSH for color c, creating it on first use.
        GDI brush creation involves a kernel call; caching avoids doing it every frame.
        """
        if c not in self.brush_cache:
            self.brush_cache[c] = SYS['g32'].CreateSolidBrush(c)
        return self.brush_cache[c]

    def draw_rect(self, x, y, w, h, c):
        b = self._get_brush(c)
        r = RECT(int(x), int(y), int(x + w), int(y + h))
        SYS['u32'].FillRect(self.active_dc, ctypes.byref(r), b)

    def draw_ellipse(self, x, y, w, h, c):
        """
        GDI Ellipse() requires the brush to be selected into the DC first.
        We restore the previous object immediately after to avoid state leakage.
        """
        b = self._get_brush(c)
        ob = SYS['g32'].SelectObject(self.active_dc, b)
        SYS['g32'].Ellipse(self.active_dc, int(x), int(y), int(x + w), int(y + h))
        SYS['g32'].SelectObject(self.active_dc, ob)  # Restore previous brush

    def draw_text(self, x, y, text, c):
        """
        Draws ASCII text at pixel position (x, y).
        SetBkMode(TRANSPARENT) prevents the text from overwriting the background with a white box.
        """
        SYS['g32'].SetTextColor(self.active_dc, c)
        SYS['g32'].SetBkMode(self.active_dc, 1)  # 1 = TRANSPARENT
        encoded = str(text).encode('ascii')
        SYS['g32'].TextOutA(self.active_dc, int(x), int(y), encoded, len(encoded))

    def run(self):
        """
        Main loop. Handles the message pump, fixed-timestep logic updates,
        double-buffered rendering, and precision frame pacing.
        """
        try:
            last_time  = time.perf_counter()
            accumulator = 0.0   # Accumulated time waiting for the next fixed logic tick
            fps_timer  = time.perf_counter()
            fps_count  = 0

            from ctypes import wintypes
            SYS['u32'].ShowWindow(self.hw, SW_SHOW)
            msg = wintypes.MSG()

            # --- Double-buffer setup ---
            # hdc: the real window device context (the screen).
            # mem_dc: an in-memory context where we draw each frame silently.
            # mem_bm: the bitmap backing mem_dc — sized to the current window dimensions.
            hdc    = SYS['u32'].GetDC(self.hw)
            mem_dc = SYS['g32'].CreateCompatibleDC(hdc)
            mem_bm = SYS['g32'].CreateCompatibleBitmap(hdc, self.w, self.h)
            SYS['g32'].SelectObject(mem_dc, mem_bm)
            prev_sw, prev_sh = self.w, self.h
            self.active_dc = mem_dc   # Expose the buffer so draw_* methods can target it.

            while True:
                # --- 1. Message pump ---
                # PeekMessageW with PM_REMOVE drains the OS message queue without blocking.
                while SYS['u32'].PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == 0x0012:  # WM_QUIT: exit the loop cleanly.
                        SYS['u32'].ReleaseDC(self.hw, hdc)
                        return
                    if self.input.is_pressed('ESCAPE'):
                        SYS['u32'].PostQuitMessage(0)
                    SYS['u32'].TranslateMessage(ctypes.byref(msg))
                    SYS['u32'].DispatchMessageW(ctypes.byref(msg))

                # --- 2. Input snapshot ---
                self.input.update()
                self.mouse.update()

                now = time.perf_counter()
                accumulator += (now - last_time)
                last_time = now
                sw, sh = self.w, self.h

                if sw > 0 and sh > 0:
                    # --- 3. Fixed-timestep logic ---
                    # Consume accumulated time in fixed_dt chunks. If the machine is slow
                    # and accumulator grows large, multiple logic ticks run per frame to
                    # keep simulation speed consistent ("catch-up" behaviour).
                    while accumulator >= self.fixed_dt:
                        for o in self.objs:
                            o.update(sw, sh)
                        accumulator -= self.fixed_dt

                    # If the window was resized, the old bitmap is no longer the right
                    # size. Delete it and create a fresh one matching the new dimensions.
                    if sw != prev_sw or sh != prev_sh:
                        SYS['g32'].DeleteObject(mem_bm)
                        mem_bm = SYS['g32'].CreateCompatibleBitmap(hdc, sw, sh)
                        SYS['g32'].SelectObject(mem_dc, mem_bm)
                        prev_sw, prev_sh = sw, sh

                    # --- 4. Clear the back-buffer ---
                    SYS['u32'].FillRect(mem_dc, ctypes.byref(RECT(0, 0, sw, sh)), self.bg_brush)

                    # --- 5. Draw all objects into the back-buffer ---
                    for o in self.objs:
                        o.draw(self)

                    # --- 6. Blit: atomically copy the completed frame to the screen ---
                    # SRCCOPY copies every pixel as-is. Because it's one operation,
                    # the user never sees a partially rendered frame.
                    SYS['g32'].BitBlt(hdc, 0, 0, sw, sh, mem_dc, 0, 0, SRCCOPY)

                    fps_count += 1
                    if time.perf_counter() - fps_timer >= 1.0:
                        self.real_fps = fps_count
                        fps_count = 0
                        fps_timer = time.perf_counter()

                # --- 7. Hybrid sleep: precision frame pacing ---
                # Measure how long the logic+rendering work took this frame.
                work_time  = time.perf_counter() - now
                sleep_time = self.frame_delay - work_time

                if sleep_time > 0:
                    # Sleep for most of the remaining time, waking up 2 ms early.
                    # time.sleep() is accurate to ~1–15 ms depending on the OS timer;
                    # we cannot trust it for the final sub-2 ms window.
                    if sleep_time > 0.002:
                        time.sleep(sleep_time - 0.002)

                    # Spin-loop for the final <2 ms to hit the deadline precisely.
                    # This burns one CPU core but guarantees microsecond accuracy.
                    while (time.perf_counter() - now) < self.frame_delay:
                        pass

        finally:
            # Always release GDI resources, even if an exception ended the loop.
            for b in self.brush_cache.values():
                SYS['g32'].DeleteObject(b)
            SYS['g32'].DeleteObject(self.bg_brush)
            kill_audio_processes()


class X11Engine:
    """
    Linux rendering backend built directly on the Xlib C API via ctypes.

    Uses a Pixmap as the off-screen back-buffer (equivalent to Win32's memory DC).
    All drawing goes to the Pixmap; XCopyArea commits it to the window in one call.
    Frame pacing uses the same hybrid sleep/spin strategy as Win32Engine.
    """

    def __init__(self, title, w, h, bg, fps=60, fullscreen=False):
        self.objs = []
        self.target_fps = fps
        self.real_fps = 0
        self.frame_delay = 1.0 / fps
        self.fixed_dt    = 1.0 / 60.0
        self.bg = bg

        x11 = SYS['x11']
        self.disp = x11.XOpenDisplay(None)  # Connect to the default X display ($DISPLAY)

        if not self.disp:
            raise RuntimeError(
                "CRITICAL: XOpenDisplay returned NULL. "
                "Is an X11 display server running? Is $DISPLAY set?"
            )

        self.scr = x11.XDefaultScreen(self.disp)

        if fullscreen:
            self.w = x11.XDisplayWidth(self.disp, self.scr)
            self.h = x11.XDisplayHeight(self.disp, self.scr)
        else:
            self.w, self.h = w, h

        root = x11.XRootWindow(self.disp, self.scr)

        # XCreateSimpleWindow: border_width=1, border_color=0 (black), background=bg.
        self.win = x11.XCreateSimpleWindow(
            self.disp, root, 0, 0, self.w, self.h, 1, 0, self.bg
        )
        self.gc = x11.XCreateGC(self.disp, self.win, 0, None)  # Graphics context

        # Create the off-screen Pixmap at the same depth as the window.
        depth = x11.XDefaultDepth(self.disp, self.scr)
        self.pixmap = x11.XCreatePixmap(self.disp, self.win, self.w, self.h, depth)

        # Register the WM_DELETE_WINDOW protocol so clicking the X button sends
        # a ClientMessage event (type 33) instead of silently killing the process.
        self.wm_delete = x11.XInternAtom(self.disp, b"WM_DELETE_WINDOW", 0)
        x11.XSetWMProtocols(
            self.disp, self.win,
            ctypes.byref(ctypes.c_ulong(self.wm_delete)), 1
        )

        x11.XStoreName(self.disp, self.win, title.encode('utf-8'))
        x11.XMapWindow(self.disp, self.win)   # Make the window visible
        x11.XFlush(self.disp)                  # Send all pending requests to the server

        self.input = Keyboard(self.disp)
        self.mouse = Mouse(self)

    def add(self, o):
        self.objs.append(o)

    def set_fps_limit(self, fps):
        self.target_fps = fps
        self.frame_delay = 1.0 / fps

    def draw_rect(self, x, y, w, h, c):
        SYS['x11'].XSetForeground(self.disp, self.gc, c)
        SYS['x11'].XFillRectangle(self.disp, self.pixmap, self.gc,
                                   int(x), int(y), int(w), int(h))

    def draw_ellipse(self, x, y, w, h, c):
        """
        XFillArc draws a filled arc. Angle1=0, Angle2=23040 covers a full 360°
        (X11 angles are in 64ths of a degree: 360 * 64 = 23040).
        """
        SYS['x11'].XSetForeground(self.disp, self.gc, c)
        SYS['x11'].XFillArc(self.disp, self.pixmap, self.gc,
                              int(x), int(y), int(w), int(h), 0, 23040)

    def draw_text(self, x, y, text, c):
        """
        XDrawString renders ASCII text using the server's default fixed-width font.
        The y coordinate is the text baseline, so we add 10 px to place it below
        the requested top-left position.
        """
        SYS['x11'].XSetForeground(self.disp, self.gc, c)
        enc = str(text).encode('ascii')
        SYS['x11'].XDrawString(self.disp, self.pixmap, self.gc,
                                int(x), int(y + 10), enc, len(enc))

    def run(self):
        try:
            last_time   = time.perf_counter()
            accumulator = 0.0
            fps_timer   = time.perf_counter()
            fps_count   = 0

            # XEvent buffer: 192 bytes is large enough for any X11 event structure.
            xevent = ctypes.create_string_buffer(192)

            while True:
                # --- Event processing ---
                # XPending returns the number of queued events without blocking.
                while SYS['x11'].XPending(self.disp):
                    SYS['x11'].XNextEvent(self.disp, xevent)
                    # The event type is a 32-bit int at the start of the event struct.
                    event_type = struct.unpack("i", xevent.raw[:4])[0]
                    if event_type == 33:  # ClientMessage — WM_DELETE_WINDOW
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

                # Fixed-timestep logic updates
                while accumulator >= self.fixed_dt:
                    for o in self.objs:
                        o.update(self.w, self.h)
                    accumulator -= self.fixed_dt

                # Clear the off-screen Pixmap to the background color
                SYS['x11'].XSetForeground(self.disp, self.gc, self.bg)
                SYS['x11'].XFillRectangle(self.disp, self.pixmap, self.gc,
                                           0, 0, self.w, self.h)

                # Draw all objects into the Pixmap
                for o in self.objs:
                    o.draw(self)

                # Blit the Pixmap to the visible window in a single operation
                SYS['x11'].XCopyArea(self.disp, self.pixmap, self.win, self.gc,
                                      0, 0, self.w, self.h, 0, 0)
                SYS['x11'].XFlush(self.disp)

                fps_count += 1
                if time.perf_counter() - fps_timer >= 1.0:
                    self.real_fps = fps_count
                    fps_count = 0
                    fps_timer = time.perf_counter()

                # Hybrid sleep/spin frame pacing (same strategy as Win32Engine)
                work_time  = time.perf_counter() - now
                sleep_time = self.frame_delay - work_time
                if sleep_time > 0:
                    if sleep_time > 0.002:
                        time.sleep(sleep_time - 0.002)
                    while (time.perf_counter() - now) < self.frame_delay:
                        pass

        finally:
            kill_audio_processes()


# Select the correct engine class for the current platform at import time.
WindowEngine = Win32Engine if OS_TYPE == 'nt' else X11Engine


# =================================================================================
# STAGE 5: BASIC SHAPES (Graphic Primitive Base Classes)
# =================================================================================

class Box:
    """Axis-aligned filled rectangle. The simplest drawable entity."""
    def __init__(self, x, y, w, h, c):
        self.x, self.y, self.w, self.h, self.c = x, y, w, h, c

    def update(self, sw, sh):
        pass  # Static; no per-frame logic needed.

    def draw(self, gfx):
        gfx.draw_rect(self.x, self.y, self.w, self.h, self.c)


class Circle(Box):
    """Filled ellipse that fits within the bounding box defined by its radius."""
    def __init__(self, x, y, r, c):
        super().__init__(x, y, r * 2, r * 2, c)
        self.r = r  # Radius, also used by Physics.resolve() for collision detection.

    def draw(self, gfx):
        gfx.draw_ellipse(self.x, self.y, self.w, self.h, self.c)


class TextLine:
    """Static text label at a fixed screen position."""
    def __init__(self, x, y, text, c):
        self.x, self.y, self.text, self.c = x, y, text, c

    def update(self, sw, sh):
        pass

    def draw(self, gfx):
        gfx.draw_text(self.x, self.y, self.text, self.c)


class FPSCounter:
    """
    Displays the current measured frame rate and the active FPS limit.
    Reads real_fps and target_fps directly from the engine each frame.
    """
    def __init__(self, x, y, game, c):
        self.x, self.y, self.game, self.c = x, y, game, c

    def update(self, sw, sh):
        pass

    def draw(self, gfx):
        txt = f"FPS: {self.game.real_fps} / Limit: {self.game.target_fps}"
        gfx.draw_text(self.x, self.y, txt, self.c)


# =================================================================================
# STAGE 6: RUNTIME ENTITIES (Custom Game Logic)
# =================================================================================

class HerzController:
    """
    Adjusts the engine's FPS cap at runtime via the '1' and '2' keys.

    A 100 ms debounce timer prevents a single keypress from firing dozens of
    times before the user lifts their finger.
    """
    def __init__(self, game):
        self.game = game
        self.last_press = 0  # Timestamp of the most recent accepted key event

    def update(self, sw, sh):
        now = time.time()
        if now - self.last_press > 0.1:  # 100 ms debounce window
            if self.game.input.is_pressed('1'):
                new_fps = max(10, self.game.target_fps - 10)
                self.game.set_fps_limit(new_fps)
                self.last_press = now
            elif self.game.input.is_pressed('2'):
                new_fps = min(2000, self.game.target_fps + 10)
                self.game.set_fps_limit(new_fps)
                self.last_press = now

    def draw(self, gfx):
        gfx.draw_text(20, 40, "Press '1' / '2' to change FPS limit. ESC to Exit.",
                      RGB(150, 150, 150))


class Ball(Circle):
    """
    A physics-enabled sphere that bounces off screen edges.

    When assigned id=1 it also responds to WASD/arrow key input for direct control.
    SPACE applies a velocity multiplier each frame it is held, acting as a boost.
    A reference to a MemorySound (sfx) is played on every wall or body collision.
    """
    def __init__(self, x, y, r, c, vx, vy, sfx, p):
        super().__init__(x, y, r, c)
        self.vx, self.vy = vx, vy
        self.sfx = sfx    # Sound effect triggered on collision
        self.p   = p      # Reference to the engine (for input access)
        self.target = None  # Optional second Ball for physics interaction

    def update(self, sw, sh):
        # Player-controlled ball: direct velocity influence from keyboard.
        if getattr(self, 'id', 0) == 1 and hasattr(self.p, 'input'):
            if self.p.input.is_pressed('W') or self.p.input.is_pressed('UP'):    self.vy -= 0.5
            if self.p.input.is_pressed('S') or self.p.input.is_pressed('DOWN'):  self.vy += 0.5
            if self.p.input.is_pressed('A') or self.p.input.is_pressed('LEFT'):  self.vx -= 0.5
            if self.p.input.is_pressed('D') or self.p.input.is_pressed('RIGHT'): self.vx += 0.5
            if self.p.input.is_pressed('SPACE'):
                # Boost: amplify existing velocity by 5% per frame held.
                self.vx *= 1.05
                self.vy *= 1.05

        self.x += self.vx
        self.y += self.vy
        hit = False

        # Reflect velocity off the screen boundary and clamp position to stay inside.
        if self.x <= 0:
            self.x = 0;          self.vx *= -1; hit = True
        elif self.x + self.w >= sw:
            self.x = sw - self.w; self.vx *= -1; hit = True
        if self.y <= 0:
            self.y = 0;          self.vy *= -1; hit = True
        elif self.y + self.h >= sh:
            self.y = sh - self.h; self.vy *= -1; hit = True

        if hit and self.sfx:
            self.sfx.play()

        # Run elastic collision resolution against the paired target, if set.
        if self.target and Physics.resolve(self, self.target):
            self.sfx.play()


class Human:
    """
    The main player character: a humanoid figure made of an ellipse (head) + rectangle (body).

    Movement is 8-directional via WASD / arrow keys at a fixed pixel speed per frame.
    Left-clicking randomises the player's color (debounced to once per 200 ms).
    """
    def __init__(self, x, y, c, p):
        self.x, self.y, self.c, self.p = x, y, c, p
        self.vx = self.vy = 0
        self.speed = 8          # Pixels moved per logic tick
        self.last_click = 0     # Timestamp of the last accepted LMB event

    def update(self, sw, sh):
        self.vx = self.vy = 0

        if hasattr(self.p, 'input'):
            if self.p.input.is_pressed('W') or self.p.input.is_pressed('UP'):    self.vy = -self.speed
            if self.p.input.is_pressed('S') or self.p.input.is_pressed('DOWN'):  self.vy =  self.speed
            if self.p.input.is_pressed('A') or self.p.input.is_pressed('LEFT'):  self.vx = -self.speed
            if self.p.input.is_pressed('D') or self.p.input.is_pressed('RIGHT'): self.vx =  self.speed

        # Randomise color on left-click, debounced to 200 ms to prevent rapid flickering.
        if hasattr(self.p, 'mouse') and self.p.mouse.is_pressed('LMB'):
            now = time.time()
            if now - self.last_click > 0.2:
                self.c = RGB(
                    random.randint(50, 255),
                    random.randint(50, 255),
                    random.randint(50, 255)
                )
                self.last_click = now

        self.x += self.vx
        self.y += self.vy

        # Clamp to screen bounds. The sprite is 40 px wide × 60 px tall (20+40 head+body).
        self.x = max(0, min(self.x, sw - 40))
        self.y = max(0, min(self.y, sh - 60))

    def draw(self, gfx):
        """
        Draws a minimal two-piece humanoid:
          - Ellipse 20×20 px offset 10 px inward for the head (centred above the body).
          - Rectangle 40×40 px for the torso, starting 20 px below the head top.
        """
        hx, hy = int(self.x + 10), int(self.y)       # Head top-left corner
        bx, by = int(self.x),      int(self.y + 20)  # Body top-left corner
        gfx.draw_ellipse(hx, hy, 20, 20, self.c)
        gfx.draw_rect(bx, by, 40, 40, self.c)


# =================================================================================
# MAIN EXECUTION
# =================================================================================

if __name__ == "__main__":
    try:
        print("Synthesizing Multitrack Audio into RAM...")

        # --- Track definitions ---
        # "Ode to Joy" melody (Beethoven's 9th, 4th movement theme).
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

        # Simple C–G bass line providing harmonic support under the melody.
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

        # Synthesize both tracks into one in-memory WAV (no disk I/O).
        m_bytes = Melody.compile_to_memory(120, melody_track, bass_track)
        bgm = MemorySound(m_bytes)

        # Create the engine window (fullscreen, dark background, 60 FPS cap).
        game = WindowEngine(
            "Game Engine 2.0 - Precision Runtime",
            800, 600, RGB(20, 20, 20),
            fullscreen=True
        )
        game.set_fps_limit(60)

        # Start music before adding objects so the audio thread is warm by first frame.
        bgm.play(loop=True)

        # --- Scene setup ---
        player       = Human(game.w // 2, game.h // 2, RGB(0, 255, 255), game)
        herz_control = HerzController(game)
        fps_display  = FPSCounter(20, 20, game, RGB(255, 255, 0))

        # Register all scene objects. Order matters: earlier objects draw beneath later ones.
        game.add(player)
        game.add(herz_control)
        game.add(fps_display)
        game.add(bgm)   # MemorySound.update() handles Linux audio loop restart each tick.

        print("[*] Engine 2.0 Running. Fullscreen Mode Enabled.")
        game.run()

    except Exception as e:
        # Catch and display any fatal error without immediately closing the terminal,
        # giving the developer time to read the traceback.
        print("\n" + "=" * 50)
        print("CRITICAL ENGINE FAILURE:")
        print("=" * 50)
        traceback.print_exc()
        print("=" * 50)
        input("Press Enter to exit...")
