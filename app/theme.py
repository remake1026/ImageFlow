"""Shared interaction colors for QSS templates and custom-painted controls."""
ACCENT = "#3B82F6"
ACCENT_HOVER = "#60A5FA"
ACCENT_PRESSED = "#2563EB"
SELECTION = "rgba(59, 130, 246, 0.16)"
HOVER_BACKGROUND = "rgba(96, 165, 250, 0.12)"


def render_theme(stylesheet: str) -> str:
    tokens = {
        "accent": ACCENT,
        "accent_hover": ACCENT_HOVER,
        "accent_pressed": ACCENT_PRESSED,
        "accent_rgb": "59, 130, 246",
        "hover_rgb": "96, 165, 250",
        "selection": SELECTION,
        "hover_background": HOVER_BACKGROUND,
    }
    for name, color in tokens.items():
        stylesheet = stylesheet.replace("@" + name + "@", color)
    return stylesheet


def theme_color(value: str):
    """Convert the shared rgba tokens for QPainter (QColor accepts hex directly)."""
    from app.qt.QtGui import QColor
    if value.startswith("rgba("):
        r, g, b, alpha = value[5:-1].split(",")
        return QColor(int(r), int(g), int(b), round(float(alpha) * 255))
    return QColor(value)
