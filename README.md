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
5. **Run:** Call `game.run()` to start the hybrid-sleep event loop.Вот полная, финальная версия файла **`README.md`**. Я объединил историю обновлений (от 1.2 до 2.0) и написал максимально подробное, пошаговое руководство («для чайников»), чтобы любой новичок мог скопировать код и сразу начать делать свою игру.

Скопируй этот текст и сохрани его как `README.md`.

***

```markdown
# 🎮 PURE PYTHON GAME ENGINE 2.0
**Cross-Platform • Zero Dependencies • Built-in Multitrack DAW**

Welcome to the Pure Python Game Engine! This is a lightweight, incredibly fast game framework built entirely in Python. It requires **ZERO external libraries** (no `pygame`, no `numpy`). It talks directly to your operating system (Windows `gdi32.dll` / Linux `X11`) to draw graphics and play audio.

---

## 🚀 WHAT'S NEW IN VERSION 2.0 (Since v1.2)
Version 2.0 is a massive architectural rewrite focused on speed, stability, and professional features:

1. **Microsecond Precision Timing (The Hybrid Sleep System)**
   * *Fixed:* In v1.2, setting the FPS limit to 900 resulted in only ~400 FPS due to sloppy OS timers.
   * *New:* We replaced `time.time()` with the hardware counter `time.perf_counter()`. The engine now uses a "Spin-lock" for the final 2 milliseconds of every frame, giving you mathematically perfect, rock-solid FPS.
2. **Memory Churn Elimination (GDI Brush Caching)**
   * *Fixed:* v1.2 allocated and deleted memory for colors thousands of times per second, bottlenecking Windows.
   * *New:* Colors and brushes are now cached globally. Zero memory allocation during the active game loop. FPS is practically uncapped.
3. **True Borderless Fullscreen**
   * *New:* Pass `fullscreen=True` when creating the engine. It automatically polls the OS (`GetSystemMetrics`) for your exact monitor resolution and removes window borders.
4. **The "Blue Wheel of Death" Fix**
   * *Fixed:* On Windows, the mouse cursor used to be permanently stuck in the "Loading" animation. 
   * *New:* Bound `LoadCursorW` to enforce the standard arrow cursor.
5. **Advanced Audio: Math-based Rhythm & Triplets**
   * *New:* The `Melody` parser now calculates lengths mathematically as fractions. You can write perfect triplets just by typing `1/12` (8th-note triplet) or `1/6` (quarter-note triplet).
6. **MusicXML Support**
   * *New:* You no longer have to code music by hand. You can compose in MuseScore or FL Studio, export as `.musicxml`, and feed it directly into the engine using the new `XMLParser`.

---

## 📖 THE ULTIMATE BEGINNER'S MANUAL
*How to use this engine even if you've never made a game before.*

### Step 1: Installation
**There is no installation.** You don't need `pip install anything`. Just ensure you have Python 3 installed on your computer. Create a file named `game.py`, paste the engine code into it, and you're ready to go.

### Step 2: The Boilerplate (Opening a Window)
Every game needs a starting point. Put this at the very bottom of your script:

```python
if __name__ == "__main__":
    # 1. Create the engine: "Title", Width, Height, Background Color (RGB)
    # Hint: Change fullscreen=False to True for a massive screen!
    game = WindowEngine("My Awesome Game", 800, 600, RGB(20, 20, 20), fullscreen=False)
    
    # 2. Lock the speed to 60 Frames Per Second
    game.set_fps_limit(60)
    
    # 3. Start the game!
    game.run()
```

### Step 3: Creating Things (Entities)
To put something on the screen, you need to create an "Entity". 
**Every entity MUST have two functions:**
1. `update(sw, sh)`: This is where you do math (moving, physics, reading the keyboard).
2. `draw(gfx)`: This is where you actually paint the object on the screen.

Let's make a simple red box that moves to the right:

```python
class MovingBox:
    def __init__(self, start_x, start_y):
        self.x = start_x
        self.y = start_y
        
    def update(self, screen_width, screen_height):
        # Move the box right by 5 pixels every frame
        self.x += 5 
        
        # If it goes off the screen, teleport it back to the left!
        if self.x > screen_width:
            self.x = 0

    def draw(self, gfx):
        # Draw a Red rectangle: X, Y, Width, Height, Color
        gfx.draw_rect(self.x, self.y, 50, 50, RGB(255, 0, 0))
```

**How to add it to your game:**
Right before `game.run()`, add this line:
```python
game.add(MovingBox(100, 100))
```

### Step 4: Controls (Keyboard and Mouse)
You don't need complicated event loops. The engine reads your keyboard and mouse directly from the hardware.

**Keyboard Check:**
Inside your object's `update` function, you can check if a key is pressed like this:
```python
if game.input.is_pressed('W'):
    self.y -= 5  # Move UP
if game.input.is_pressed('S'):
    self.y += 5  # Move DOWN
if game.input.is_pressed('SPACE'):
    print("PEW PEW! Lasers fired!")
```
*(Supported keys: A-Z, 0-9, UP, DOWN, LEFT, RIGHT, SPACE, BACKSPACE, ESCAPE)*

**Mouse Check:**
```python
# Get the exact X, Y coordinates of the mouse
mouse_x, mouse_y = game.mouse.get_pos()

# Check for Left Click (LMB), Right Click (RMB), or Middle Click (MMB)
if game.mouse.is_pressed('LMB'):
    print(f"You clicked at {mouse_x}, {mouse_y}!")
```

### Step 5: Adding Music & Sound Effects (The DAW)
This engine synthesizes music directly into your RAM. You write music using text: `"Note-Duration"`.

* `C4-1/4` = C note, 4th octave, Quarter note.
* `P-1/2` = Pause (Silence) for a Half note.
* `C4_E4_G4-1/4` = Play three notes at the same time (A Chord!).

**How to play a simple track:**
```python
# 1. Write the music (Melody and Bass)
melody = "E4-1/4, E4-1/4, F4-1/4, G4-1/4"
bass = "C3-1/2, G2-1/2"

# 2. Compile it at 120 Beats Per Minute
audio_data = Melody.compile_to_memory(120, melody, bass)
my_song = MemorySound(audio_data)

# 3. Play it! (loop=True makes it repeat forever)
my_song.play(loop=True)

# Add the audio to the engine so it keeps the loop alive
game.add(my_song)
```
