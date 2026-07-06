import sys
from Xlib import X, XK, display

def main():
    d = display.Display()
    root = d.screen().root

    # Super+Z = Mod4Mask + 'z'
    keycode = d.keysym_to_keycode(XK.string_to_keysym("z"))
    if not keycode:
        print("Error: Could not find keycode for 'z'")
        sys.exit(1)
        
    mask = X.Mod4Mask
    print(f"Grabbing keycode {keycode} with mask {hex(mask)}")
    
    try:
        root.grab_key(keycode, mask, True, X.GrabModeAsync, X.GrabModeAsync)
        d.sync()
        print("Grabbed successfully. Please press Super+Z...")
    except Exception as e:
        print(f"Grab failed: {e}")
        sys.exit(1)

    while True:
        try:
            event = d.next_event()
            if event.type == X.KeyPress:
                print(f"KeyPress: keycode={event.detail}, state={hex(event.state)}")
                break
        except KeyboardInterrupt:
            break
            
if __name__ == "__main__":
    main()
