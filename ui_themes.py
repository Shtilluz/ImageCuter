"""Application palettes and colour-role mapping for live Tk theme changes."""

from types import SimpleNamespace


THEMES = {
    "light": {
        "BG": "#fbfaf7", "BG2": "#f1f0eb", "BTN": "#eeede7", "FG": "#303b34",
        "FG2": "#626d60", "ACC": "#53664f", "GRN": "#e1eade", "RED": "#f3e4df",
        "GOLD": "#53664f", "TOOL_BG": "#f5f4ef", "INPUT": "#ffffff", "WHITE": "#ffffff",
        "BORDER": "#deded6", "CANVAS": "#e9e7df", "FOCUS": "#829a77", "RED_FG": "#94594e",
        "CHECKER_A": "#efede7", "CHECKER_B": "#d4d1c7",
    },
    "dark": {
        "BG": "#1d252c", "BG2": "#151c22", "BTN": "#303c46", "FG": "#edf2f5",
        "FG2": "#b1bec8", "ACC": "#a0c69a", "GRN": "#314b3b", "RED": "#543330",
        "GOLD": "#a0c69a", "TOOL_BG": "#192128", "INPUT": "#11191f", "WHITE": "#142311",
        "BORDER": "#4a5a65", "CANVAS": "#0e151a", "FOCUS": "#b5d7aa", "RED_FG": "#ffd2c4",
        "CHECKER_A": "#26313a", "CHECKER_B": "#35434d",
    },
    "contrast": {
        "BG": "#111111", "BG2": "#000000", "BTN": "#292929", "FG": "#ffffff",
        "FG2": "#dfdfdf", "ACC": "#ffdb70", "GRN": "#443b20", "RED": "#58252b",
        "GOLD": "#ffdb70", "TOOL_BG": "#191919", "INPUT": "#070707", "WHITE": "#141414",
        "BORDER": "#939393", "CANVAS": "#050505", "FOCUS": "#fff0b3", "RED_FG": "#ffc3cc",
        "CHECKER_A": "#303030", "CHECKER_B": "#555555",
    },
}
THEME_NAMES = {"light": "Светлая", "dark": "Тёмная", "contrast": "Контрастная"}


def palette(name):
    return SimpleNamespace(**THEMES.get(name, THEMES["light"]))


def translate_color(value, option, previous, current):
    """Map semantic UI colours, retaining deliberate annotation/asset colours."""
    value = str(value).lower()
    if option in ("foreground", "activeforeground", "selectforeground"):
        preferred = ("WHITE", "FG", "FG2", "RED_FG", "ACC")
    else:
        preferred = ("INPUT", "BG", "BG2", "BTN", "TOOL_BG", "CANVAS", "GRN", "RED", "BORDER", "FOCUS")
    for role in (*preferred, *vars(previous)):
        if value == getattr(previous, role).lower():
            return getattr(current, role)
    # Older controls use these explicit neutral colours for focus/disabled text.
    aliases = {"#a7b7a0": "FOCUS", "#83877d": "FG2", "#969d91": "FG2"}
    return getattr(current, aliases[value]) if value in aliases else value
