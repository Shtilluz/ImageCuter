"""Watchdog process: shows the «программа не отвечает» dialog for a frozen UI.

The main application pings a beat file from its event loop. When pings stop,
the UI thread is stuck; this process — running in its own interpreter — offers
to wait, restart, or close the application. Runs standalone or via
`gui_cutter.py --sm-watchdog` when frozen by PyInstaller.
"""
import json
import os
import signal
import subprocess
import sys
import time


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate(pid, grace=2.0):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except OSError:
            return
        deadline = time.time() + grace
        while time.time() < deadline:
            if not _alive(pid):
                return
            time.sleep(0.05)


def _beat_age(beat):
    try:
        return time.time() - os.path.getmtime(beat)
    except OSError:
        return float("inf")


def _parse(argv):
    options = {"pid": None, "beat": None, "timeout": 10.0,
               "restart": None, "cwd": None}
    it = iter(argv)
    for key in it:
        if key.startswith("--"):
            name = key[2:]
            if name not in options:
                continue
            value = next(it, None)
            if name in ("timeout", "pid"):
                options[name] = float(value) if name == "timeout" else int(value)
            elif name == "restart":
                options[name] = json.loads(value)
            else:
                options[name] = value
    return options


def _dialog(pid, age, timeout):
    """Modal Tk window; returns 'wait' | 'restart' | 'close' | 'died'."""
    import tkinter as tk

    choice = {"value": "wait"}
    root = tk.Tk()
    root.title("Sprite Manufacturer")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    frame = tk.Frame(root, padx=24, pady=18)
    frame.pack(fill=tk.BOTH, expand=True)
    tk.Label(frame, text="Программа не отвечает",
             font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
    tk.Label(frame, wraplength=380, justify=tk.LEFT, text=(
        f"Интерфейс не обновляется {int(age)} сек.\n"
        f"Возможно, идёт долгая операция или произошёл сбой.\n\n"
        f"«Подождать» — продолжить ожидание (ещё {int(timeout)} сек).\n"
        f"«Перезапустить» — закрыть и открыть программу заново.\n"
        f"«Закрыть» — завершить работу программы.")).pack(anchor=tk.W, pady=(10, 16))
    buttons = tk.Frame(frame)
    buttons.pack(fill=tk.X)

    def finish(value):
        choice["value"] = value
        root.destroy()

    def check():
        if not _alive(pid):
            choice["value"] = "died"
            root.destroy()
            return
        root.after(400, check)

    for text, value in (("Подождать", "wait"),
                        ("Перезапустить", "restart"),
                        ("Закрыть", "close")):
        tk.Button(buttons, text=text, width=12,
                  command=lambda v=value: finish(v)).pack(side=tk.LEFT, expand=True, padx=4)
    root.protocol("WM_DELETE_WINDOW", lambda: finish("wait"))
    root.after(400, check)
    root.mainloop()
    return choice["value"]


def main(argv=None):
    options = _parse(sys.argv[1:] if argv is None else argv)
    pid, beat, timeout = options["pid"], options["beat"], options["timeout"]
    if pid is None or beat is None:
        print("hang_watchdog: --pid and --beat are required", file=sys.stderr)
        return 2
    snooze = 0.0
    while True:
        if not _alive(pid):
            return 0
        if time.time() >= snooze and _beat_age(beat) > timeout:
            try:
                action = _dialog(pid, _beat_age(beat), timeout)
            except Exception as error:
                print(f"hang_watchdog: dialog failed: {error}", file=sys.stderr)
                return 1
            if action == "died":
                return 0
            if action == "wait":
                snooze = time.time() + timeout
            elif action in ("restart", "close"):
                _terminate(pid)
                if action == "restart" and options["restart"]:
                    subprocess.Popen(options["restart"],
                                     cwd=options["cwd"] or None,
                                     start_new_session=True)
                return 0
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
