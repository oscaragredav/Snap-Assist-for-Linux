import time
import sys
from pynput import keyboard

# Keep track of pressed modifiers
pressed_vks = set()

def on_press(key):
    try:
        vk = key.vk if hasattr(key, 'vk') else key.value.vk
    except AttributeError:
        vk = None

    if vk:
        pressed_vks.add(vk)
        
    print(f"Press: {key} (vk: {vk}) | Current pressed: {pressed_vks}")
    
    # Check for Super (vk 133 is usually Super_L) + Z (vk 122 or char 'z')
    # Or just check by key name
    
    # Simple check for Super + Z (z is vk 122 usually, Super is 133 or 134)
    # pynput handles character keys simply
    if hasattr(key, 'char') and key.char == 'z':
        if keyboard.Key.cmd in pressed_vks or 133 in pressed_vks or 134 in pressed_vks:
            print(">>> DETECTED SUPER + Z! <<<")
            sys.exit(0)
    
def on_release(key):
    try:
        vk = key.vk if hasattr(key, 'vk') else key.value.vk
        if vk in pressed_vks:
            pressed_vks.remove(vk)
    except AttributeError:
        pass
    print(f"Release: {key}")

    if key == keyboard.Key.esc:
        return False

print("Listening for events with pynput... Press Super+Z (or ESC to exit)")
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
