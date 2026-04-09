# PURE PYTHON GAME ENGINE 2.0 - OFFICIAL MANUAL
**Cross-Platform • Zero Dependencies • Built-in Multitrack DAW**

---

## OVERVIEW
The Pure Python Game Engine 2.0 is a lightweight, dependency-free framework that interfaces directly with the host OS (Windows via `ctypes.windll` or Linux via `X11`/`aplay`). It features a custom software synthesizer, an entity-component style rendering loop, double-buffering, and microsecond-precision frame timing.

---

## AUDIO SYSTEM (DAW)
The engine includes a built-in software synthesizer that generates sine-wave PCM audio data directly into RAM. 

### Syntax & Transcription
Tracks are written as comma-separated string sequences using the format: `[Notes]-[Duration]`.

* **Single Notes:** `"C4-1/4"` *(C note, 4th octave, quarter note)*.
* **Chords:** Link notes with underscores. `"C4_E4_G4-1/2"` *(C Major chord, half note)*.
* **Pauses/Rests:** Use the letter P. `"P-1/8"` *(Eighth-note rest)*.
* **Accidentals:** The engine strictly uses sharps (`#`). Flat notes must be written as their sharp equivalent *(e.g., use `D#` instead of `Eb`)*.
* **Triplets & Advanced Rhythms:** Because the parser calculates fractions mathematically, triplets are supported natively:
  * 8th-note triplet: `"C4-1/12"`
  * Quarter-note triplet: `"C4-1/6"`

### Multitracking
The `Melody.compile_to_memory` function allows you to mix multiple string tracks into a single, synchronized audio object. It automatically pads shorter tracks with silence to ensure perfect looping.

```python
m_bytes = Melody.compile_to_memory(120, melody_track, bass_track)
bgm = MemorySound(m_bytes)
bgm.play(loop=True)
```

---

## RENDERING & OPTIMIZATION
The engine utilizes different backends depending on the OS, unified under the `WindowEngine` class.

### Graphics Features
* **Double Buffering:** Draws objects to a memory bitmap (`mem_dc`) before blitting to the screen (`BitBlt`), eliminating screen tearing and flickering.
* **Brush Caching (Windows):** Heavily optimizes GDI rendering by storing dynamically created `CreateSolidBrush` objects in a dictionary (`brush_cache`), effectively eliminating memory allocation churn during the main game loop.
* **Dynamic Fullscreen:** Initializing `WindowEngine(..., fullscreen=True)` dynamically fetches the host's monitor resolution (`GetSystemMetrics`) and removes window borders.

### Drawing Shapes
Custom objects can draw to the screen by accepting the `gfx` (engine) parameter in their `draw` method:
* `gfx.draw_rect(x, y, w, h, color)`
* `gfx.draw_ellipse(x, y, w, h, color)`
* `gfx.draw_text(x, y, text, color)`

*(Colors are defined using the cross-platform `RGB(r, g, b)` function).*

---

## TIMING & FPS CONTROL
Version 2.0 introduces a **Hybrid Sleep / Spin-lock** architecture for microsecond precision on Windows.

Because standard OS sleep commands (like `time.sleep`) are highly inaccurate and bound to system scheduler limits (often ~15ms on Windows), the engine uses `time.perf_counter()`:

1. **Macro-Sleep:** Yields the CPU back to the OS if there is more than 2ms of idle time left in the frame.
2. **Spin-Lock:** For the final 2ms of the frame, the engine enters an empty `while` loop, catching the exact microsecond the next frame should begin.

**Result:** Rock-solid FPS capping without CPU overheating.

---

## INPUT SYSTEM
Inputs bypass standard Python input handlers and poll the OS hardware state directly.

### Keyboard
Supports concurrent key presses. Supported Keys: `A-Z`, `0-9`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `SPACE`, `BACKSPACE`, `ESCAPE`.

```python
if game.input.is_pressed('W'):
    # Move up
if game.input.is_pressed('ESCAPE'):
    # Used to instantly exit fullscreen
```

### Mouse
Tracks cursor position mapped to the client window and supports three buttons (`LMB`, `RMB`, `MMB`).

```python
x, y = game.mouse.get_pos()
if game.mouse.is_pressed('LMB'):  
    # Shoot / Interact
```

---

## ENTITY CREATION (RUNTIME)
To add interactive objects to the game, create a class with two mandatory methods: `update(sw, sh)` and `draw(gfx)`.

```python
class MyPlayer:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def update(self, screen_width, screen_height):
        # Physics, movement, and input logic goes here
        self.x += 1 

    def draw(self, gfx):
        # Rendering logic goes here
        gfx.draw_rect(self.x, self.y, 50, 50, RGB(255, 0, 0))
```
*Add the object to the engine pipeline using `game.add(MyPlayer(0, 0))`.*

---

## EXECUTION LIFECYCLE
A standard game file should follow this setup phase:

1. **Synthesize Audio:** Compile tracks to `MemorySound`.
2. **Initialize Engine:** Create the `WindowEngine` instance and set the FPS limit.
3. **Instantiate Entities:** Create your players, UI, and logic controllers.
4. **Register Objects:** Add entities and audio to the engine via `game.add()`.
5. **Run:** Call `game.run()` to start the hybrid-sleep event loop.
```
