"""Paleta e stylesheet da interface."""

BG_DARK = "#12121C"
BG_SIDEBAR = "#1A1A28"
BG_CARD = "#1E1E30"
BG_CARD_HOVER = "#222233"
BG_CARD_SELECTED = "#2A2A40"
BG_PLAYER = "#0D0D14"
BORDER = "#2A2A3E"
TEXT_PRIMARY = "#F0F0F5"
TEXT_SECONDARY = "#A0A0B8"
TEXT_MUTED = "#8888A0"
ACCENT = "#E94560"
ACCENT_HOVER = "#c73a52"
ACCENT_SECONDARY = "#533483"
SUCCESS_BG = "#1B4332"
SUCCESS_TEXT = "#95D5B2"

SIDEBAR_WIDTH = 260
PLAYER_MIN_WIDTH = 420
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800

STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {BG_SIDEBAR};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: #444460;
    border-radius: 4px;
    min-height: 24px;
}}
QPushButton {{
    background-color: #333348;
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{
    background-color: #444460;
}}
QPushButton#accent {{
    background-color: {ACCENT};
    color: white;
}}
QPushButton#accent:hover {{
    background-color: {ACCENT_HOVER};
}}
QComboBox {{
    background-color: #333348;
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 6px 10px;
}}
QComboBox::drop-down {{
    border: none;
}}
QComboBox QAbstractItemView {{
    background-color: #333348;
    color: {TEXT_PRIMARY};
    selection-background-color: {ACCENT};
}}
QTableWidget {{
    background-color: {BG_CARD};
    alternate-background-color: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
    gridline-color: {BORDER};
    border: none;
    border-radius: 12px;
}}
QTableWidget::item {{
    padding: 8px;
}}
QTableWidget::item:selected {{
    background-color: {BG_CARD_SELECTED};
}}
QHeaderView::section {{
    background-color: {BG_SIDEBAR};
    color: {TEXT_SECONDARY};
    padding: 8px;
    border: none;
}}
QProgressBar {{
    background-color: #333348;
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 4px;
}}
QSlider::groove:horizontal {{
    background: #333348;
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT_SECONDARY};
    border-radius: 3px;
}}
QLabel#muted {{
    color: {TEXT_MUTED};
}}
QLabel#title {{
    font-size: 20px;
    font-weight: bold;
}}
QFrame#sidebar {{
    background-color: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
}}
QFrame#player {{
    background-color: {BG_PLAYER};
    border-left: 1px solid {BORDER};
}}
QFrame#courseCard {{
    background-color: {BG_CARD_HOVER};
    border-radius: 10px;
}}
QFrame#courseCard[selected="true"] {{
    background-color: {BG_CARD_SELECTED};
}}
QFrame#paneFrame {{
    background-color: {BG_DARK};
}}
QFrame#paneHeader {{
    background-color: {BG_SIDEBAR};
    border-bottom: 1px solid {BORDER};
}}
QLabel#paneTitle {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: bold;
}}
QFrame#collapsedRail {{
    background-color: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
}}
QSplitter#mainSplitter::handle {{
    background-color: {BORDER};
    width: 6px;
}}
QSplitter#mainSplitter::handle:hover {{
    background-color: {ACCENT};
}}
"""
