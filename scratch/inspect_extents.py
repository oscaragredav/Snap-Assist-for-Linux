import Xlib.display
import Xlib.X
import sys

def main():
    display = Xlib.display.Display()
    root = display.screen().root
    atom_extents = display.get_atom('_GTK_FRAME_EXTENTS')
    atom_name = display.get_atom('_NET_WM_NAME')
    
    # Get all windows
    tree = root.query_tree()
    for wid in tree.children:
        try:
            name_prop = wid.get_full_property(atom_name, Xlib.X.AnyPropertyType)
            name = name_prop.value.decode('utf-8', 'replace') if name_prop else "Unknown"
            
            extents_prop = wid.get_full_property(atom_extents, Xlib.X.AnyPropertyType)
            if extents_prop and extents_prop.value:
                print(f"Window: {name} (0x{wid.id:x}) Extents: {list(extents_prop.value)}")
        except Exception:
            pass

if __name__ == "__main__":
    main()
