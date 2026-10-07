"""Behavioral checks for the custom workspace controls."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from ui_widgets import SoftButton, SoftCheck, SoftRadio, SoftSlider


class SoftControls(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("320x180")
        self.root.configure(bg="#fbfaf7")
        self.calls = []

    def tearDown(self):
        self.root.destroy()

    def test_button_release_outside_and_disabled_button_do_not_act(self):
        button = SoftButton(self.root, "Action", command=lambda: self.calls.append("action"))
        button.pack()
        self.root.update()
        button._press(SimpleNamespace(x=10, y=10))
        button._release(SimpleNamespace(x=-10, y=10))
        self.assertEqual(self.calls, [])
        button._press(SimpleNamespace(x=10, y=10))
        button._release(SimpleNamespace(x=10, y=10))
        self.assertEqual(self.calls, ["action"])
        button.config(state="disabled")
        button.invoke()
        self.assertEqual(self.calls, ["action"])
        self.assertEqual(int(button.cget("takefocus")), 0)

    def test_button_keyboard_activation(self):
        button = SoftButton(self.root, "Action", command=lambda: self.calls.append("action"))
        button.pack()
        self.root.update()
        button.focus_force()
        self.root.update()
        button.event_generate("<Return>")
        button.event_generate("<space>")
        self.assertEqual(self.calls, ["action", "action"])

    def test_choice_updates_variable_callback_and_disabled_state(self):
        variable = tk.BooleanVar(value=False)
        check = SoftCheck(self.root, text="Option", variable=variable,
                          command=lambda: self.calls.append(variable.get()))
        check.pack()
        check.invoke()
        self.assertTrue(variable.get())
        check.config(state="disabled")
        check.invoke()
        self.assertTrue(variable.get())
        self.assertEqual(self.calls, [True])

    def test_radio_arrow_navigation(self):
        variable = tk.StringVar(value="a")
        first = SoftRadio(self.root, text="A", variable=variable, value="a")
        second = SoftRadio(self.root, text="B", variable=variable, value="b")
        first.pack()
        second.pack()
        first._select_adjacent(1)
        self.assertEqual(variable.get(), "b")
        second._select_adjacent(1)
        self.assertEqual(variable.get(), "a")

    def test_slider_clamps_drag_and_keyboard_runs_callback(self):
        slider = SoftSlider(self.root, from_=200, to=255)
        slider.pack(fill="x")
        slider.bind("<ButtonRelease-1>", lambda _: self.calls.append(slider.get()))
        self.root.update()
        slider._move(SimpleNamespace(x=-100))
        self.assertEqual(slider.get(), 200)
        slider._move(SimpleNamespace(x=9999))
        self.assertEqual(slider.get(), 255)
        slider._step(-1)
        self.assertEqual(slider.get(), 254)
        self.assertEqual(self.calls, [254])


if __name__ == "__main__":
    unittest.main(verbosity=2)
