🚀 CHANGELOG: Engine v1.2 ➔ v2.0

### Version 2.0 represents a massive shift from a simple Windows-only script to a professional, cross-platform framework. Here is exactly what changed:
## 1. Timing & FPS (The Hybrid-Sleep System)

    v1.2: Relied on a basic Windows timer (WM_TIMER at 16ms), which is notoriously inaccurate and capped real-world performance.

    v2.0: Uses Microsecond Precision Timing. It leverages Python's time.perf_counter() with a hybrid Sleep/Spin-lock algorithm. It sleeps to save CPU during long gaps, but "spins" for the final 2 milliseconds of a frame, resulting in rock-solid, mathematically perfect FPS locking.

## 2. Graphics Memory & Rendering

    v1.2: Suffered from Memory Churn. Every time a box or circle was drawn, the engine requested a new brush from Windows (CreateSolidBrush) and deleted it (DeleteObject).

    v2.0: Implements GDI Brush Caching. The engine creates a brush for a color once, saves it in a brush_cache dictionary, and reuses it indefinitely. This eliminates tens of thousands of memory allocation calls per second.

## 3. Cross-Platform Support

    v1.2: Strictly tied to Windows (ctypes.windll, USER32, GDI32).

    v2.0: Fully Cross-Platform. It automatically detects the host OS and dynamically switches between the Windows API and a custom-built Linux X11 backend for rendering and input.

## 4. Audio Architecture (In-Memory DAW)

    v1.2: Generated .wav files and saved them to the hard drive, then used Windows MCI (winmm.mciSendString) to play them. This caused file-lock errors and required messy session IDs.

    v2.0: Features a RAM-based Audio Pipeline. Audio is synthesized as raw PCM bytes directly into memory (MemorySound). On Windows, it plays from RAM via PlaySoundA. On Linux, it pipes bytes directly into aplay. No files are ever written to the hard drive.

## 5. Advanced Music Synthesis & Chords

    v1.2: Only supported single notes played one after another.

    v2.0: Supports Multitracking and Chords.

        You can play chords by linking notes (C4_E4_G4-1/4).

        You can compile multiple tracks simultaneously, and the engine automatically pads them with silence to ensure perfect looping sync.

        Supports native triplets and advanced fractions (1/12, 1/6).

        Features a MusicXML Parser to import sheet music directly from professional DAWs like MuseScore.

## 6. Input System

    v1.2: Relied on the standard Windows message pump, which makes handling multiple simultaneous key presses (like pressing 'W' and 'D' to move diagonally) very difficult.

    v2.0: Uses Direct Hardware Polling. The Keyboard and Mouse classes directly query the OS state (GetAsyncKeyState on Windows, XQueryKeymap on Linux) allowing for flawless real-time movement and interaction.

## 7. Display Modes

    v1.2: Hardcoded to a fixed window size (e.g., 800x600).

    v2.0: Supports Dynamic Borderless Fullscreen. By passing fullscreen=True, the engine queries GetSystemMetrics to match your monitor's native resolution and strips the window borders for a seamless gaming experience.
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
