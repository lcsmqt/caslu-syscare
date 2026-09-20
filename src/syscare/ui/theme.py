"""Service-bench theme: cool charcoal work surface, oscilloscope cyan, gold mark."""

ACCENT = "#3DB8C5"
GOLD = "#D4B06A"
OK, WARN, BAD = "#5DCCA0", "#E6B84F", "#E06C75"
MUTED = "#8A9BAA"
TEXT = "#E8F0F4"
BG = "#0A1016"
SURFACE = "#131B24"
RAISED = "#1A2430"
LINE = "#2A3644"

QSS = f"""
* {{ font-family: 'Segoe UI Variable', 'Segoe UI', 'Noto Sans', sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget#page {{ background: {BG}; }}
QWidget#sidebar {{ background: {SURFACE}; border-right: 1px solid {LINE}; }}
QLabel#brand {{ font-size: 18px; font-weight: 700; color: #fff; letter-spacing: 0.2px; }}
QLabel#brandtag {{ font-size: 11px; color: {GOLD}; }}
QLabel#title {{ font-size: 22px; font-weight: 700; color: #fff; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#tooltitle {{ font-size: 12px; font-weight: 600; color: {TEXT}; }}
QWidget#navsearchbox {{
    background: {BG}; border: 1px solid {LINE}; border-radius: 10px;
    margin: 0 12px 8px 12px; min-height: 36px;
}}
QWidget#navsearchbox[active="true"] {{ border: 1px solid {ACCENT}; }}
QLineEdit#navsearch {{
    background: transparent; border: none; padding: 8px 0;
    margin: 0;
}}
QListWidget#nav, QTreeWidget#nav {{ background: transparent; border: none; outline: none; }}
QTreeWidget#nav::item {{
    padding: 7px 10px; margin: 1px 8px; border-radius: 9px; color: {MUTED};
}}
QTreeWidget#nav::item:hover {{ background: {RAISED}; color: #fff; }}
QTreeWidget#nav::item:selected {{ background: {ACCENT}; color: #0A1016; }}
QTreeWidget#nav::branch {{ background: transparent; }}
QFrame#card {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px;
}}
QFrame#tool {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 14px;
}}
QFrame#tool:hover {{ background: {RAISED}; border: 1px solid {ACCENT}; }}
QLabel#cardvalue {{ font-size: 26px; font-weight: 700; color: #fff; }}
QPushButton {{
    background: {ACCENT}; color: #062026; border: none; border-radius: 9px;
    padding: 9px 16px; font-weight: 650;
}}
QPushButton:hover {{ background: #5CCFDB; }}
QPushButton:pressed {{ background: #2A9AA6; }}
QPushButton:disabled {{ background: {LINE}; color: {MUTED}; }}
QPushButton#danger {{ background: #B4454D; color: #fff; }}
QPushButton#danger:hover {{ background: {BAD}; }}
QPushButton#ghost {{ background: {RAISED}; color: {TEXT}; }}
QPushButton#ghost:hover {{ background: #243040; }}
QLineEdit, QPlainTextEdit, QSpinBox {{
    background: {BG}; border: 1px solid {LINE}; border-radius: 9px; padding: 8px;
    selection-background-color: {ACCENT}; selection-color: #062026;
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QTableWidget {{
    background: {BG}; border: 1px solid {LINE}; border-radius: 12px;
    gridline-color: {LINE}; alternate-background-color: #0E161D;
}}
QTableWidget::item {{ padding: 4px 6px; }}
QTableWidget::item:selected {{ background: #1C3A42; color: #fff; }}
QHeaderView::section {{
    background: {SURFACE}; color: {MUTED}; border: none; padding: 10px 8px; font-weight: 600;
}}
QProgressBar {{
    background: {RAISED}; border: none; border-radius: 6px; height: 10px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; padding: 9px 16px; color: {MUTED};
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: #fff; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: {LINE}; border-radius: 5px; min-width: 28px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid {LINE}; background: {BG};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QToolTip {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE};
    padding: 6px 8px; border-radius: 6px;
}}
QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; padding: 6px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {RAISED}; }}
QMessageBox {{ background: {SURFACE}; }}
QSplitter::handle {{ background: {LINE}; }}
"""
