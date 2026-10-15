"""Soft, keyboard-accessible controls for the Tk workspace."""
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageDraw, ImageTk, ImageColor
from ui_themes import palette


class ToolTip:
    """Small keyboard/mouse hints; no interaction is required to dismiss them."""
    def __init__(self, widget, text, colors):
        self.widget, self.text, self.colors = widget, text, colors
        self.pending = self.window = None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<FocusIn>", self.schedule, add="+")
        for event in ("<Leave>", "<FocusOut>", "<ButtonPress>", "<Destroy>"):
            widget.bind(event, self.hide, add="+")

    def schedule(self, _=None):
        self.hide()
        self.pending = self.widget.after(550, self.show)

    def show(self):
        self.pending = None
        if not self.widget.winfo_exists() or not self.widget.winfo_ismapped():
            return
        p = self.colors()
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.attributes("-topmost", True)
        label = tk.Label(self.window, text=self.text, bg=p.INPUT, fg=p.FG, justify="left",
                         font=("Segoe UI", 9), wraplength=300, padx=10, pady=8,
                         highlightthickness=1, highlightbackground=p.BORDER)
        label.pack()
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - self.window.winfo_reqwidth() - 8)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        if y + self.window.winfo_reqheight() > self.widget.winfo_screenheight():
            y = self.widget.winfo_rooty() - self.window.winfo_reqheight() - 6
        self.window.geometry(f"+{max(0, x)}+{max(0, y)}")

    def hide(self, _=None):
        if self.pending is not None:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


def blend(first, second, amount):
    a, b = ImageColor.getrgb(first), ImageColor.getrgb(second)
    return "#" + "".join(f"{round(x * (1 - amount) + y * amount):02x}" for x, y in zip(a, b))


class SoftButton(tk.Canvas):
    def __init__(self, parent, text, command=None, bg="#eeede7", fg="#303b34",
                 font=("Segoe UI", 10), height=34, width=None, **kwargs):
        self.text, self.command = text, command
        self.fill, self.foreground = bg, fg
        self.palette = palette("light")
        self.font = tkfont.Font(font=font)
        self.control_state = kwargs.pop("state", "normal")
        self.hover = self.pressed = False
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0,
                         width=width or self.font.measure(text) + 26, height=height,
                         takefocus=0 if self.control_state == "disabled" else 1,
                         cursor="arrow" if self.control_state == "disabled" else "hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", lambda _: self._hover(True))
        self.bind("<Leave>", lambda _: self._hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Return>", lambda _: self.invoke())
        self.bind("<space>", lambda _: self.invoke())
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)

    def _hover(self, value):
        self.hover = value
        self._draw()

    def _press(self, event):
        if self.control_state != "disabled":
            self.focus_set()
            self.pressed = True
            self._draw()

    def _release(self, event):
        pressed = self.pressed
        self.pressed = False
        self._draw()
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.control_state != "disabled" and self.command:
            return self.command()

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        for key, attribute in (("text", "text"), ("bg", "fill"), ("fg", "foreground"),
                               ("state", "control_state"), ("command", "command")):
            if key in kwargs:
                setattr(self, attribute, kwargs.pop(key))
        if kwargs:
            super().configure(**kwargs)
        super().configure(takefocus=0 if self.control_state == "disabled" else 1,
                          cursor="arrow" if self.control_state == "disabled" else "hand2")
        self._draw()

    config = configure

    def apply_theme(self, colors):
        self.palette = colors
        super().configure(bg=self.master.cget("bg"))
        self._draw()

    def cget(self, key):
        values = {"state": self.control_state, "text": self.text, "bg": self.fill, "fg": self.foreground}
        return values[key] if key in values else super().cget(key)

    def _draw(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 2 or height < 2:
            return
        background = self.master.cget("bg")
        fill, foreground = self.fill, self.foreground
        if self.control_state == "disabled":
            fill = blend(fill, background, .8)
            foreground = self.palette.FG2
        elif self.pressed:
            fill = blend(fill, "#303b34", .10)
        elif self.hover:
            fill = blend(fill, "#ffffff", .16)
        image = Image.new("RGB", (width * 2, height * 2), background)
        draw = ImageDraw.Draw(image)
        outline = self.palette.FOCUS if self.focus_get() == self and self.control_state != "disabled" else fill
        draw.rounded_rectangle((2, 2, width * 2 - 3, height * 2 - 3), radius=18,
                               fill=fill, outline=outline, width=2)
        self._photo = ImageTk.PhotoImage(image.resize((width, height), Image.Resampling.LANCZOS))
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=self._photo)
        self.create_text(width / 2, height / 2, text=self.text, fill=foreground, font=self.font)


class SoftChoice(tk.Canvas):
    def __init__(self, parent, text, variable, value=None, command=None, radio=False,
                 bg="#fbfaf7", fg="#303b34", font=("Segoe UI", 10), **kwargs):
        self.variable, self.value, self.command, self.radio = variable, value, command, radio
        self.text, self.foreground = text, fg
        self.palette = palette("light")
        self.control_state = kwargs.pop("state", "normal")
        self.font = tkfont.Font(font=font)
        super().__init__(parent, bg=bg, highlightthickness=0, takefocus=1,
                         width=self.font.measure(text) + 29, height=30, cursor="hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<Button-1>", lambda _: self.invoke())
        self.bind("<space>", lambda _: self.invoke())
        self.bind("<Return>", lambda _: self.invoke())
        if self.radio:
            self.bind("<Left>", lambda _: self._select_adjacent(-1))
            self.bind("<Right>", lambda _: self._select_adjacent(1))
            self.bind("<Up>", lambda _: self._select_adjacent(-1))
            self.bind("<Down>", lambda _: self._select_adjacent(1))
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)
        self._trace = variable.trace_add("write", self._draw)
        self.bind("<Destroy>", self._destroy_trace)

    def _destroy_trace(self, event):
        if event.widget == self:
            self.variable.trace_remove("write", self._trace)

    def invoke(self):
        if self.control_state == "disabled":
            return
        self.focus_set()
        self.variable.set(self.value if self.radio else not self.variable.get())
        if self.command:
            self.command()

    def _select_adjacent(self, direction):
        choices = [widget for widget in self.master.winfo_children()
                   if isinstance(widget, SoftChoice) and widget.radio and
                   str(widget.variable) == str(self.variable) and widget.control_state != "disabled"]
        if self in choices:
            choices[(choices.index(self) + direction) % len(choices)].invoke()
        return "break"

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        self.control_state = kwargs.pop("state", self.control_state)
        self.foreground = kwargs.pop("fg", kwargs.pop("foreground", self.foreground))
        self.text = kwargs.pop("text", self.text)
        if kwargs:
            super().configure(**kwargs)
        super().configure(takefocus=0 if self.control_state == "disabled" else 1,
                          cursor="arrow" if self.control_state == "disabled" else "hand2")
        self._draw()

    config = configure

    def apply_theme(self, colors):
        self.palette = colors
        self._draw()

    def cget(self, key):
        values = {"state": self.control_state, "fg": self.foreground, "foreground": self.foreground, "text": self.text}
        return values[key] if key in values else super().cget(key)

    def _draw(self, *args):
        if not self.winfo_exists():
            return
        selected = self.variable.get() == self.value if self.radio else bool(self.variable.get())
        disabled = self.control_state == "disabled"
        color = self.palette.FG2 if disabled else self.palette.ACC
        self.delete("all")
        if self.radio:
            self.create_oval(3, 8, 17, 22, fill=self.palette.INPUT, outline=color if selected else self.palette.BORDER, width=1.5)
            if selected:
                self.create_oval(7, 12, 13, 18, fill=color, outline=color)
        else:
            self.create_polygon(6, 8, 15, 8, 18, 11, 18, 20, 15, 23, 6, 23, 3, 20, 3, 11,
                                smooth=True, fill=color if selected else self.palette.INPUT,
                                outline=color if selected else self.palette.BORDER)
            if selected:
                self.create_line(6, 15, 10, 19, 15, 12, fill=self.palette.WHITE, width=2, capstyle="round", joinstyle="round")
        self.create_text(26, 15, anchor="w", text=self.text,
                         fill=self.palette.FG2 if disabled else self.foreground, font=self.font)
        if self.focus_get() == self:
            self.create_line(26, 27, min(self.winfo_width(), self.font.measure(self.text)+26), 27,
                             fill=self.palette.FOCUS, width=1)


class SoftRadio(SoftChoice):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, radio=True, **kwargs)


class SoftCheck(SoftChoice):
    pass


class SoftSlider(tk.Canvas):
    def __init__(self, parent, from_=0, to=100, bg="#fbfaf7", fg="#303b34", **kwargs):
        self.low, self.high, self.value = from_, to, from_
        self.palette = palette("light")
        super().__init__(parent, bg=bg, highlightthickness=0, takefocus=1, height=44, cursor="hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<ButtonPress-1>", self._move)
        self.bind("<B1-Motion>", self._move)
        self.bind("<Left>", lambda _: self._step(-1))
        self.bind("<Right>", lambda _: self._step(1))
        self.bind("<FocusIn>", self._draw)
        self.bind("<FocusOut>", self._draw)

    def get(self):
        return self.value

    def apply_theme(self, colors):
        self.palette = colors
        self._draw()

    def set(self, value):
        self.value = max(self.low, min(self.high, round(float(value))))
        self._draw()

    def _step(self, amount):
        self.set(self.value + amount)
        self.event_generate("<ButtonRelease-1>")

    def _move(self, event):
        self.focus_set()
        ratio = (event.x - 10) / max(1, self.winfo_width() - 20)
        self.set(self.low + ratio * (self.high - self.low))

    def _draw(self, *args):
        width = self.winfo_width()
        self.delete("all")
        if width < 20:
            return
        x = 10 + (width - 20) * (self.value - self.low) / max(1, self.high - self.low)
        self.create_text(width-10, 9, anchor="e", text=str(self.value), font=("Segoe UI", 9), fill=self.palette.FG2)
        self.create_line(10, 29, width-10, 29, fill=self.palette.BORDER, width=4, capstyle="round")
        self.create_line(10, 29, x, 29, fill=self.palette.ACC, width=4, capstyle="round")
        self.create_oval(x-7, 22, x+7, 36, fill=self.palette.INPUT, outline=self.palette.ACC, width=2)
        if self.focus_get() == self:
            self.create_oval(x-10, 19, x+10, 39, outline=self.palette.FOCUS)
