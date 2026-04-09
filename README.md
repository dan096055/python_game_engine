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
