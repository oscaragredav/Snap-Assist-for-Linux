import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from snapassist.wm.x11_backend import X11Backend

def main():
    backend = X11Backend()
    monitors = backend._get_monitors()
    print(f"Monitors detected: {len(monitors)}")
    for i, m in enumerate(monitors):
        print(f"Monitor {i}: x={m.x}, y={m.y}, w={m.w}, h={m.h}")
        
    prop = backend.root.get_full_property(backend.atoms["_NET_WORKAREA"], 0)
    if prop and prop.value:
        print(f"_NET_WORKAREA raw: {list(prop.value)}")
        
if __name__ == "__main__":
    main()
