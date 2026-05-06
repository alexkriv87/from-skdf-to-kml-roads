import tkinter as tk
from tkinter import ttk


def paste(event=None):
    try:
        text = root.clipboard_get()
        widget = root.focus_get()
        if isinstance(widget, tk.Entry):
            widget.insert(tk.INSERT, text)
    except:
        pass


def show_context_menu(event):
    menu.post(event.x_root, event.y_root)


root = tk.Tk()
root.title("Тест")
root.geometry("300x150")

menu = tk.Menu(root, tearoff=0)
menu.add_command(label="Вставить", command=paste)

label = ttk.Label(root, text="Введите текст:")
label.pack(pady=10)

entry = ttk.Entry(root, width=40)
entry.pack(pady=5)
entry.bind('<Button-3>', show_context_menu)

root.mainloop()
