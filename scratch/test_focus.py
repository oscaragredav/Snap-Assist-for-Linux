import tkinter as tk
root = tk.Tk()
root.geometry("400x200")
root.attributes("-type", "splash")
root.attributes("-topmost", True)
lbl = tk.Label(root, text="Press a key")
lbl.pack(expand=True)
def on_key(e):
    lbl.config(text=f"Key: {e.keysym}")
    if e.keysym == "Escape":
        root.quit()
root.bind("<Key>", on_key)
root.focus_force()
root.mainloop()
