#  WinMultimedia-Py Engine

A lightweight, **zero-dependency** multimedia engine for Windows, built entirely with Python and the native Windows API (`ctypes`).

##  The Mission
Most Python games rely on heavy libraries like `Pygame` or `Pyglet`. This engine takes a different path: it interfaces **directly** with the Windows OS kernels (`user32`, `gdi32`, `winmm`). It is designed for high performance, low overhead, and a deep understanding of how Windows handles graphics and sound.

---

##  Key Features

###  Graphics & UI
* **GDI Rendering:** Uses the Windows Graphics Device Interface for fast, flicker-free drawing.
* **Double Buffering:** Implements a memory Device Context (HDC) to eliminate screen tearing and flickering.
* **Dynamic Text:** Custom wrapper for `CreateFontW` and `TextOutW` for sharp, hardware-accelerated text.

###  Audio Engineering
* **Mathematical Synthesis:** Built-in oscillators for **Sine, Square, Triangle, and Sawtooth** waveforms.
* **Pitch-Shifting Sampler:** A custom resampling algorithm that allows you to load a single `.wav` file (e.g., a piano C3) and automatically maps it across the entire keyboard by mathematically adjusting playback speed.
* **Melody Interpreter:** Composers can write music using a simple string syntax: `"(Note_Octave_Duration)"`.

###  Input System
* **Real-time Input:** Uses `GetAsyncKeyState` for frame-perfect keyboard response, bypassing the standard (and slower) Python `input()` or event queues.

---

##  Musical Arrangement Example
The engine currently features a custom arrangement of **"Dark is the Night" (Тёмная ночь)**, demonstrating complex rhythmic structures like triplets and staccato "gates."

# The engine parses this into raw PCM frequencies and timings


## Python Windows API Game Engine (v1.1)

A high-performance, zero-dependency 2D game engine built from scratch using Python and the native Windows API (ctypes). This project bypasses high-level libraries like PyGame to interface directly with the Windows Kernel, Graphics Device Interface (GDI), and Multimedia Control Interface (MCI).

## What's New in Version 1.1?

The v1.1 update focuses on Stability and Lifecycle Management, fixing critical bugs related to audio drivers and system cleanup.

    Stable Software Audio Looping: Fixed the common "Driver cannot recognize parameter" error by replacing unreliable hardware SND_LOOP flags with a custom Software Monitor that polls audio states 60 times/sec.

    Automatic Process Cleanup: Implemented an Audio Registry that intercepts the WM_DESTROY signal to force-kill all MCI threads, preventing "ghost music" from playing after the window is closed.

    Collision Physics (MTD): Upgraded physics from simple overlap checks to a proper Elastic Impulse model with Minimum Translation Distance (MTD) resolution to prevent objects from getting stuck.

    Dynamic Session Handling: Generates Unique Session IDs for temporary audio assets to prevent PermissionError when restarting the engine rapidly.

    Robust Melody Parsing: Added a built-in string sanitizer to handle complex music strings (stripping parentheses and spaces) without crashing the float converter.

## System Architecture
Module	Technology	Responsibility
Graphics	gdi32.dll	Double-buffered rasterization & BitBlt pixel flipping.
Input	user32.dll	Asynchronous key state detection via GetAsyncKeyState.
Audio	winmm.dll	44.1kHz PCM synthesis and MCI command interfacing.
Physics	Native Math	Vector projection and unit normal impulse calculation.

## Music String Format

The engine includes a built-in synthesizer and melody compiler. You can write music as simple strings:
Python

# Format: (NoteName_DurationNumerator/DurationDenominator)
melody_string = "(C4_1/4, E4_1/4, G4_1/2, C5_1/1)"
Melody.compile("bgm.wav", 120, melody_string)

## Quick Start

    Clone the repository to your Windows machine.

    Run the engine script directly (requires Python 3.x):
    Bash

    python engine_v1.1.py

## Documentation

The source code contains a Detailed Reference Manual at the top of the file. It covers:

    Memory management for GDI Device Contexts.

    Bitwise coloring logic (0x00BBGGRR).

    The math behind Elastic Collision and Vector Projection.
