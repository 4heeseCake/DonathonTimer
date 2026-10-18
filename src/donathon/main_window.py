from __future__ import annotations

import datetime as dt
import gc
import math
import os
import re
import threading
import time
import webbrowser
from pathlib import Path
from collections import Counter, defaultdict

from PySide6.QtCore import Qt, QTimer, QDateTime, QRectF, QPointF, QEasingCurve, QPropertyAnimation, Property, Signal, QEvent
from PySide6.QtGui import QGuiApplication, QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QRadialGradient, QConicalGradient, QPixmap, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .config import APP_VERSION, DB_PATH, DONATIONALERTS_REDIRECT_URI, OVERLAY_URL, RECORDINGS_DIR
from .donationalerts import DonationAlertsService
from .state import AppState
from .storage import Storage
from .twitch import TwitchService
from .speech import SpeechService
from .entertainment import EntertainmentService


THEMES = [
    ("Классический", "classic", "Чистый и универсальный"),
    ("Неон", "neon", "Яркое cyan / violet свечение"),
    ("Pixel Arcade", "minimal", "Пиксельный аркадный стиль"),
    ("Ретро", "retro", "Тёплый терминальный стиль"),
    ("Holographic", "glass", "Переливающийся holographic gradient"),
    ("Cyber / Tech", "cyber", "Резкий футуристичный HUD"),
    ("Streamer", "streamer", "Современный мягкий стрим-пак"),
    ("Gaming Bold", "gaming", "Массивный игровой broadcast"),
    ("Vaporwave", "elegant", "Розово-синий synthwave вайб"),
    ("Comic Pop", "scoreboard", "Яркий комиксный pop-art"),
]
THEME_NAMES = {key: name for name, key, _ in THEMES}


def _build_style(mode: str = "gradient") -> str:
    """Return a complete application skin.

    gradient — фирменный цветной режим, light — светлый, night — строгий тёмный.
    Accent-карточки сохраняют свои смысловые цвета во всех режимах.
    """
    mode = mode if mode in {"gradient", "light", "night"} else "gradient"
    if mode == "light":
        p = {
            "main":"#edf5ff", "text":"#172033", "muted":"#637089", "dialog":"#f7fbff",
            "sidebar1":"#fff8fb", "sidebar2":"#eef7ff", "sidebar_border":"#c9d8ea",
            "input":"#ffffff", "input_border":"#b7c7da", "button":"#ffffff", "button_hover":"#edf3fb",
            "table":"#ffffff", "table_alt":"#f4f8fd", "header":"#e9f1fb", "grid":"#d4dfec",
            "neutral_bg":"#f9fbfe", "neutral_border":"#c7d4e4", "good":"#118a57", "warn":"#b47713", "bad":"#cf3f58",
            "central":"qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #fff7fb, stop:0.25 #eef8ff, stop:0.52 #f4efff, stop:0.76 #eafcf5, stop:1 #fff4df)",
            "sidebar":"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #fff9fc, stop:0.45 #f0f7ff, stop:1 #eefaf6)",
        }
        accents = {
            "green":("#e8fff4","#20c67b"), "purple":("#f2ebff","#8b62ef"), "orange":("#fff1e4","#f08a35"),
            "blue":("#e9f4ff","#3f8fe0"), "cyan":("#e5fbff","#21b8d2"), "gold":("#fff8d9","#d7ad20"),
            "teal":("#e5fbf6","#2ab29c"), "magenta":("#fff0fb","#e054c6"), "neutral":("#f8fbff","#b8c8dc"),
        }
    elif mode == "night":
        p = {
            "main":"#03060b", "text":"#f5f8ff", "muted":"#8d9ab0", "dialog":"#060a10",
            "sidebar1":"#05080d", "sidebar2":"#080c13", "sidebar_border":"#253247",
            "input":"#050a11", "input_border":"#324055", "button":"#0b111b", "button_hover":"#111a28",
            "table":"#050a11", "table_alt":"#08101a", "header":"#0b121d", "grid":"#273246",
            "neutral_bg":"#080d15", "neutral_border":"#3c4b62", "good":"#4dffa3", "warn":"#ffd36a", "bad":"#ff7890",
            "central":"qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #020409, stop:0.55 #050911, stop:1 #090712)",
            "sidebar":"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #03060a, stop:1 #070b12)",
        }
        accents = {
            "green":("#06150f","#27ec8d"), "purple":("#130b20","#a26dff"), "orange":("#180d05","#ff8e32"),
            "blue":("#071423","#42a0ff"), "cyan":("#06161d","#29d7f6"), "gold":("#181405","#ffd43b"),
            "teal":("#061915","#33dcc0"), "magenta":("#19091a","#ff5ee0"), "neutral":("#080d15","#53647f"),
        }
    else:
        p = {
            "main":"#07111d", "text":"#f4f6fb", "muted":"#9aa8bd", "dialog":"#0d1420",
            "sidebar1":"#111827", "sidebar2":"#0a1320", "sidebar_border":"#2c3b54",
            "input":"#0d1522", "input_border":"#36445a", "button":"#202a39", "button_hover":"#2a364a",
            "table":"#0d1623", "table_alt":"#111d2c", "header":"#172337", "grid":"#2b3a50",
            "neutral_bg":"#111b2a", "neutral_border":"#3a4b64", "good":"#65dda0", "warn":"#f2bf62", "bad":"#ff8fa1",
            "central":"qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #062b3a, stop:0.18 #0a2145, stop:0.38 #25134d, stop:0.57 #4b1741, stop:0.76 #123d46, stop:1 #0b2140)",
            "sidebar":"qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #171d3a, stop:0.38 #1a1232, stop:0.72 #0b2630, stop:1 #0a1320)",
        }
        accents = {
            "green":("#0a2b20","#21c97d"), "purple":("#291747","#8c63ff"), "orange":("#351b0b","#f28a32"),
            "blue":("#102b49","#3d94ef"), "cyan":("#0b3040","#28c5e4"), "gold":("#352c0b","#e6c13a"),
            "teal":("#0b322d","#31bda7"), "magenta":("#35143d","#ef5fd5"), "neutral":("#142033","#435675"),
        }

    accent_rules = []
    for name, (bg, border) in accents.items():
        accent_rules.append(f'QFrame#Card[accent="{name}"] {{ background:{bg}; border:2px solid {border}; }}')
    # The calendar popup button is part of QDateTimeEdit itself.  Give it an
    # explicit icon so the control is obvious to a first-time user.  Resolve
    # the asset from this module rather than the current working directory so
    # it keeps working after the application is packaged.
    calendar_icon = (Path(__file__).resolve().parent / "assets" / "calendar_white.png").as_posix()
    return f"""
QMainWindow {{ background:{p['main']}; color:{p['text']}; }}
QWidget {{ background:transparent; color:{p['text']}; font-family:'Segoe UI'; font-size:14px; }}
QWidget#CentralRoot {{ background:{p['central']}; }}
QDialog {{ background:{p['dialog']}; color:{p['text']}; }}
QStatusBar {{ background:{p['sidebar1']}; color:{p['muted']}; border-top:1px solid {p['sidebar_border']}; }}
QStatusBar::item {{ border:none; }}
QStackedWidget {{ background:transparent; }}
QLabel {{ background:transparent; }}
QScrollArea {{ background:transparent; border:none; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ background:rgba(0,0,0,65); width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:#53627a; border-radius:5px; min-height:35px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0px; }}
QFrame#Sidebar {{ background:{p['sidebar']}; border-right:1px solid {p['sidebar_border']}; }}
QLabel#Brand {{ font-size:19px; font-weight:800; letter-spacing:.5px; color:{p['text']}; }}
QLabel#BrandSub {{ color:{p['muted']}; font-size:12px; }}
QPushButton#NavButton {{ text-align:left; border:1px solid {p['input_border']}; border-left-width:4px; border-radius:10px; padding:11px 12px; color:{p['text']}; font-weight:700; background:{p['button']}; }}
QPushButton#NavButton:hover {{ background:{p['button_hover']}; }}
QPushButton#NavButton[navAccent="green"] {{ border-color:#1b8b5c; }} QPushButton#NavButton[navAccent="green"]:checked {{ color:#ffffff; background:#17432f; border-color:#35d68b; }}
QPushButton#NavButton[navAccent="orange"] {{ border-color:#a95b24; }} QPushButton#NavButton[navAccent="orange"]:checked {{ color:#ffffff; background:#4a2b13; border-color:#ff9b45; }}
QPushButton#NavButton[navAccent="cyan"] {{ border-color:#27859c; }} QPushButton#NavButton[navAccent="cyan"]:checked {{ color:#ffffff; background:#124354; border-color:#42d2ee; }}
QPushButton#NavButton[navAccent="gold"] {{ border-color:#9d8125; }} QPushButton#NavButton[navAccent="gold"]:checked {{ color:#ffffff; background:#493b14; border-color:#f5cf4a; }}
QPushButton#NavButton[navAccent="magenta"] {{ border-color:#9a3e89; }} QPushButton#NavButton[navAccent="magenta"]:checked {{ color:#ffffff; background:#47203f; border-color:#ff67df; }}
QPushButton#NavButton[navAccent="blue"] {{ border-color:#3472ad; }} QPushButton#NavButton[navAccent="blue"]:checked {{ color:#ffffff; background:#173d67; border-color:#59a8ff; }}
QPushButton#NavButton[navAccent="purple"] {{ border-color:#754a9c; }} QPushButton#NavButton[navAccent="purple"]:checked {{ color:#ffffff; background:#3c2356; border-color:#b578ff; }}
QPushButton#NavButton[navAccent="teal"] {{ border-color:#318e84; }} QPushButton#NavButton[navAccent="teal"]:checked {{ color:#ffffff; background:#16443f; border-color:#51d9ca; }}
QPushButton#NavButton[navAccent="neutral"] {{ border-color:#52617a; }} QPushButton#NavButton[navAccent="neutral"]:checked {{ color:#ffffff; background:#273142; border-color:#9fb2ce; }}
QPushButton#ModeButton {{ min-width:28px; max-width:34px; min-height:28px; padding:4px; border-radius:9px; background:{p['button']}; border:1px solid {p['input_border']}; }}
QPushButton#ModeButton:checked {{ background:#6557e8; border:1px solid #b8adff; color:#ffffff; }}
QLabel#PageTitle {{ font-size:25px; font-weight:750; }} QLabel#PageSubtitle {{ color:{p['muted']}; }} QLabel#SectionTitle {{ font-size:18px; font-weight:750; }}
QLabel#Muted {{ color:{p['muted']}; }} QLabel#Good {{ color:{p['good']}; font-weight:650; }} QLabel#Warn {{ color:{p['warn']}; font-weight:650; }} QLabel#Bad {{ color:{p['bad']}; font-weight:650; }}
QFrame#Card {{ background:{p['neutral_bg']}; border:1px solid {p['neutral_border']}; border-radius:15px; }}
{''.join(accent_rules)}
QFrame#RecentDonation {{ border-radius:10px; padding:0px; }}
QFrame#RecentDonation[rank="0"] {{ background:#0c2831; border:1px solid #22c7df; }} QFrame#RecentDonation[rank="1"] {{ background:#251b39; border:1px solid #a479f2; }} QFrame#RecentDonation[rank="2"] {{ background:#32230f; border:1px solid #e5a338; }}
QLabel#RecentDonationMain {{ font-weight:700; color:{p['text']}; }} QLabel#RecentDonationSub {{ color:{p['muted']}; font-size:12px; }}
QFrame#MetricCard {{ background:{p['button']}; border:1px solid {p['neutral_border']}; border-radius:12px; }} QLabel#MetricBig {{ font-size:22px; font-weight:850; color:{p['text']}; }} QLabel#MetricSmall {{ color:{p['muted']}; font-size:12px; }}
QPushButton {{ background:{p['button']}; border:1px solid {p['input_border']}; border-radius:12px; padding:10px 15px; font-weight:700; min-height:18px; }} QPushButton:hover {{ background:{p['button_hover']}; }} QPushButton:pressed {{ background:{p['button_hover']}; padding-top:11px; padding-bottom:9px; }} QPushButton:disabled {{ color:#697386; background:rgba(80,90,105,40); border-color:rgba(100,110,130,45); }}
QPushButton#OBSActionTimer {{ background:#116a76; color:#ffffff; border:2px solid #35dbee; font-size:14px; font-weight:800; min-height:30px; padding:8px 12px; }}
QPushButton#OBSActionTimer:hover {{ background:#158697; }}
QPushButton#OBSActionInteractive {{ background:#5b3cb7; color:#ffffff; border:2px solid #ba8cff; font-size:14px; font-weight:800; min-height:30px; padding:8px 12px; }}
QPushButton#OBSActionInteractive:hover {{ background:#7950d9; }}
QPushButton#SupportLink {{ background:transparent; color:{p['muted']}; font-size:12px; border:1px solid {p['sidebar_border']}; padding:6px; min-height:15px; }}
QPushButton#SupportLink:hover {{ color:{p['text']}; border-color:#46cbeb; background:{p['button_hover']}; }}
QProgressBar {{ background:{p['input']}; border:1px solid {p['input_border']}; border-radius:8px; text-align:center; min-height:18px; }}
QProgressBar::chunk {{ background:#6557e8; border-radius:7px; }}
QPushButton#Primary {{ background:#6557e8; border:1px solid #8e82ff; color:#ffffff; }} QPushButton#Primary:hover {{ background:#7568ef; }}
QPushButton#OrangePrimary {{ background:#d9792b; border:1px solid #f4a768; color:#ffffff; }} QPushButton#OrangePrimary:hover {{ background:#e2873a; }}
QPushButton#Danger {{ background:#2a2025; border:1px solid #743847; color:#ff9caa; }} QPushButton#Danger:hover {{ background:#35262d; }}
QPushButton#Chip {{ padding:8px 14px; border-radius:18px; border:1px solid {p['input_border']}; background:rgba(255,255,255,0.04); }} QPushButton#Chip:checked {{ background:#31275b; border-color:#9f8cff; color:#ffffff; }}
QPushButton#ThemeCard {{ text-align:left; background:{p['button']}; border:1px solid {p['input_border']}; border-radius:13px; padding:13px 15px; min-height:68px; color:{p['text']}; }}
QPushButton#ThemeCard:hover {{ background:{p['button_hover']}; }} QPushButton#ThemeCard:checked {{ background:#282038; border:2px solid #9a7bff; color:#ffffff; }}
QFrame#ThemeItem {{ background:transparent; border:none; }} QPushButton#ThemeApply {{ background:#d9792b; border:none; color:#ffffff; min-width:108px; }}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QDateTimeEdit {{ background:{p['input']}; color:{p['text']}; border:1px solid {p['input_border']}; border-radius:9px; padding:7px 10px; min-height:26px; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus {{ border:1px solid #8d7cff; }}
QCheckBox {{ spacing:8px; color:{p['text']}; background:transparent; }}
QComboBox::drop-down {{ border:none; width:24px; }}
/* QDateTimeEdit paints its calendar button as a separate sub-control.  Keep it
   inside the rounded outer frame instead of letting the native square button
   cover the right-hand corners. */
QDateTimeEdit {{ padding-right:42px; }}
QDateTimeEdit::drop-down {{
    subcontrol-origin:border;
    subcontrol-position:top right;
    width:36px;
    margin:1px 1px 1px 0px;
    background:#26364f;
    border:none;
    border-left:1px solid {p['input_border']};
    border-top-right-radius:8px;
    border-bottom-right-radius:8px;
}}
QDateTimeEdit::drop-down:hover {{ background:#334967; }}
QDateTimeEdit::down-arrow {{
    image:url("{calendar_icon}");
    width:18px;
    height:18px;
}}
/* Calendar popup: Qt creates a special compact year editor inside the
   navigation bar. The generic QSpinBox rule above is intentionally roomy for
   normal forms, but it makes qt_calendar_yearedit overflow the calendar header.
   Override the internal calendar controls so month and year use one compact,
   theme-consistent layout. */
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background:{p['header']};
    border:none;
    border-bottom:1px solid {p['grid']};
    min-height:36px;
}}
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth {{
    background:transparent;
    color:{p['text']};
    border:none;
    border-radius:7px;
    padding:4px 7px;
    margin:3px 2px;
    min-width:24px;
    min-height:24px;
}}
QCalendarWidget QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget QToolButton#qt_calendar_nextmonth:hover {{ background:{p['button_hover']}; }}
QCalendarWidget QToolButton#qt_calendar_monthbutton,
QCalendarWidget QToolButton#qt_calendar_yearbutton {{
    background:transparent;
    color:{p['text']};
    border:none;
    border-radius:7px;
    padding:4px 8px;
    margin:3px 1px;
    min-height:24px;
    font-weight:700;
}}
QCalendarWidget QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget QToolButton#qt_calendar_yearbutton:hover {{ background:{p['button_hover']}; }}
QCalendarWidget QSpinBox#qt_calendar_yearedit {{
    background:{p['input']};
    color:{p['text']};
    border:1px solid {p['input_border']};
    border-radius:7px;
    padding:2px 28px 2px 8px;
    margin:4px 2px;
    min-height:22px;
    max-height:22px;
    min-width:72px;
    max-width:88px;
    selection-background-color:#6557e8;
}}
QCalendarWidget QSpinBox#qt_calendar_yearedit::up-button,
QCalendarWidget QSpinBox#qt_calendar_yearedit::down-button {{
    subcontrol-origin:border;
    width:22px;
    background:{p['button']};
    border-left:1px solid {p['input_border']};
}}
QCalendarWidget QSpinBox#qt_calendar_yearedit::up-button {{
    subcontrol-position:top right;
    border-top-right-radius:6px;
    border-bottom:none;
}}
QCalendarWidget QSpinBox#qt_calendar_yearedit::down-button {{
    subcontrol-position:bottom right;
    border-bottom-right-radius:6px;
    border-top:1px solid {p['input_border']};
}}
QCalendarWidget QSpinBox#qt_calendar_yearedit::up-button:hover,
QCalendarWidget QSpinBox#qt_calendar_yearedit::down-button:hover {{ background:{p['button_hover']}; }}
QCalendarWidget QAbstractItemView {{
    background:{p['table']};
    color:{p['text']};
    selection-background-color:#6557e8;
    selection-color:#ffffff;
    border:none;
    outline:none;
}}
QTableWidget {{ background:{p['table']}; alternate-background-color:{p['table_alt']}; color:{p['text']}; border:1px solid {p['neutral_border']}; border-radius:11px; padding:1px; gridline-color:{p['grid']}; selection-background-color:#344267; }}
QHeaderView::section {{ background:{p['header']}; color:{p['text']}; border:none; border-bottom:1px solid {p['grid']}; padding:8px; font-weight:650; }}
QHeaderView::section:first {{ border-top-left-radius:9px; }}
QHeaderView::section:last {{ border-top-right-radius:9px; }}
QTableCornerButton::section {{ background:{p['header']}; border:none; border-top-left-radius:9px; }}
"""


def _format_duration(seconds: int | float, signed: bool = False) -> str:
    value = int(round(seconds))
    sign = ""
    if signed:
        sign = "+" if value > 0 else "−" if value < 0 else ""
    value = abs(value)
    days, value = divmod(value, 86400)
    hours, value = divmod(value, 3600)
    minutes, secs = divmod(value, 60)
    text = f"{hours:02}:{minutes:02}:{secs:02}"
    if days:
        text = f"{days}д {text}"
    return sign + text


def _format_money(value: float | None, currency: str | None = None) -> str:
    if value is None:
        return ""
    number = str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")
    symbol = "₽" if (currency or "").upper() in {"RUB", "RUR"} else (currency or "")
    return f"{number} {symbol}".strip()


class SortTableItem(QTableWidgetItem):
    """Table item with an explicit sort key instead of formatted display text."""
    def __init__(self, text: str, sort_value=None):
        super().__init__(text)
        self.sort_value = text.casefold() if sort_value is None and isinstance(text, str) else sort_value

    def __lt__(self, other):
        if isinstance(other, SortTableItem):
            a = self.sort_value
            b = other.sort_value
            try:
                return a < b
            except TypeError:
                return str(a) < str(b)
        return super().__lt__(other)


class ExactTimeDialog(QDialog):
    def __init__(self, current_seconds: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Установить время")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        label = QLabel("Задай точное оставшееся время")
        label.setObjectName("SectionTitle")
        layout.addWidget(label)
        row = QHBoxLayout()
        self.hours = QSpinBox(); self.hours.setRange(0, 9999); self.hours.setSuffix(" ч")
        self.minutes = QSpinBox(); self.minutes.setRange(0, 59); self.minutes.setSuffix(" мин")
        self.seconds = QSpinBox(); self.seconds.setRange(0, 59); self.seconds.setSuffix(" сек")
        self.hours.setValue(current_seconds // 3600)
        self.minutes.setValue((current_seconds % 3600) // 60)
        self.seconds.setValue(current_seconds % 60)
        row.addWidget(self.hours); row.addWidget(self.minutes); row.addWidget(self.seconds)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def total_seconds(self) -> int:
        return self.hours.value() * 3600 + self.minutes.value() * 60 + self.seconds.value()


class NewSessionDialog(QDialog):
    def __init__(self, current_seconds: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая сессия донатофона")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        title = QLabel("Новая сессия"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        hint = QLabel("Сессия объединяет донаты и действия одного стрима в отдельную историю. Начальное время можно оставить таким, как сейчас.")
        hint.setObjectName("Muted"); hint.setWordWrap(True); layout.addWidget(hint)
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("Например: Донатофон 17 октября")
        self.name_edit.setText(f"Донатофон {dt.datetime.now():%d.%m.%Y}")
        layout.addWidget(QLabel("Название")); layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Начальное время"))
        row = QHBoxLayout()
        self.hours = QSpinBox(); self.hours.setRange(0, 9999); self.hours.setSuffix(" ч")
        self.minutes = QSpinBox(); self.minutes.setRange(0, 59); self.minutes.setSuffix(" мин")
        self.seconds = QSpinBox(); self.seconds.setRange(0, 59); self.seconds.setSuffix(" сек")
        self.hours.setValue(current_seconds // 3600)
        self.minutes.setValue((current_seconds % 3600) // 60)
        self.seconds.setValue(current_seconds % 60)
        row.addWidget(self.hours); row.addWidget(self.minutes); row.addWidget(self.seconds); layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Начать сессию")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def session_name(self) -> str:
        return self.name_edit.text().strip() or "Донатофон"

    def total_seconds(self) -> int:
        return self.hours.value() * 3600 + self.minutes.value() * 60 + self.seconds.value()


class UndoEventDialog(QDialog):
    def __init__(self, events, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отменить начисление")
        self.setMinimumSize(720, 430)

        layout = QVBoxLayout(self)
        title = QLabel("Выбери начисление")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Начисления расположены от новых к старым. Выбранное изменение будет отменено, "
            "но останется в истории с пометкой «ОТМЕНЕНО». Донат повторно не начислится."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Время", "Тип", "Событие", "Изменение"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        for event in events:
            row = self.table.rowCount()
            self.table.insertRow(row)
            when = dt.datetime.fromtimestamp(event.created_at).strftime("%d.%m %H:%M:%S")
            kind = "Донат" if event.kind == "donation" else "Ручное"
            detail = event.title
            if event.amount is not None:
                detail += f" · {_format_money(event.amount, event.currency)}"
            values = [when, kind, detail, _format_duration(event.seconds_delta, signed=True)]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, event.id)
                self.table.setItem(row, col, item)

        layout.addWidget(self.table)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Отменить выбранное")
        self.buttons.button(QDialogButtonBox.Cancel).setText("Закрыть")
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.table.itemSelectionChanged.connect(
            lambda: self.buttons.button(QDialogButtonBox.Ok).setEnabled(bool(self.table.selectedItems()))
        )
        self.table.doubleClicked.connect(lambda _index: self.accept())
        layout.addWidget(self.buttons)

    def selected_event_id(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return int(item.data(Qt.UserRole)) if item else None


class GradientRoot(QWidget):
    """Animated branded background with a deliberately low refresh rate.

    The old build repainted the whole window ~14 times per second even while it
    was idle.  That created needless temporary Qt buffers.  The visual motion is
    intentionally slow, so 2–3 FPS is enough and keeps the working set stable.
    """
    def __init__(self, mode: str = "gradient", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.phase = 0.0
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._tick)
        self._sync_timer()

    def _sync_timer(self) -> None:
        if self.mode == "gradient":
            if not self.anim.isActive():
                self.anim.start(420)
        else:
            self.anim.stop()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._sync_timer()
        self.update()

    def _tick(self) -> None:
        if not self.isVisible() or self.window().isMinimized():
            return
        self.phase = (self.phase + 0.055) % (math.pi * 2)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w=max(1,self.width()); h=max(1,self.height())
        shift=0.12*math.sin(self.phase)
        grad=QLinearGradient(QPointF(0,0), QPointF(w,h))
        if self.mode == "light":
            colors=["#fff7fb","#e8f7ff","#f2ebff","#e6fff5","#fff1da"]
        elif self.mode == "night":
            colors=["#020409","#06101c","#10091c","#07151a","#03060b"]
        else:
            colors=["#032e47","#0b1f63","#37106c","#7a1a58","#0a5865","#0a2354"]
        n=len(colors)
        for i,color in enumerate(colors):
            pos=i/(n-1)
            if 0 < i < n-1:
                pos=max(0.0,min(1.0,pos+shift*(0.52 if i%2 else -0.42)))
            grad.setColorAt(pos,QColor(color))
        painter.fillRect(self.rect(),grad)


class DonorDetailsDialog(QDialog):
    def __init__(self, donor: str, summary: dict, records: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Донатер — {donor}")
        self.setMinimumSize(780, 520)
        layout = QVBoxLayout(self)
        title = QLabel(donor or "Аноним"); title.setObjectName("PageTitle"); layout.addWidget(title)
        stats = QLabel(
            f"Всего донатов: {summary['count']}   ·   Общая сумма: {_format_money(summary['total'], 'RUB')}   ·   "
            f"Средний донат: {_format_money(summary['average'], 'RUB')}   ·   Добавлено времени: {_format_duration(summary['seconds'])}"
        )
        stats.setObjectName("Muted"); stats.setWordWrap(True); layout.addWidget(stats)
        hint = QLabel("Все донаты этого пользователя в текущем DonationAlerts-профиле, от новых к старым.")
        hint.setObjectName("Muted"); layout.addWidget(hint)
        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Время", "Сумма", "Сессия", "Добавлено времени", "Статус"])
        table.verticalHeader().setVisible(False); table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setAlternatingRowColors(True); table.setSortingEnabled(False)
        h = table.horizontalHeader(); h.setSectionResizeMode(0, QHeaderView.ResizeToContents); h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch); h.setSectionResizeMode(3, QHeaderView.ResizeToContents); h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        table.setRowCount(len(records))
        for row, record in enumerate(records):
            event = record["event"]
            when = dt.datetime.fromtimestamp(event.created_at).strftime("%d.%m.%Y %H:%M:%S")
            credited = event.credited_amount if event.credited_amount is not None else float(event.amount or 0)
            amount = _format_money(event.amount, event.currency)
            if event.currency and event.currency.upper() not in {"RUB", "RUR"}:
                amount = f"{amount} → {_format_money(credited, 'RUB')}"
            values = (
                SortTableItem(when, event.created_at),
                SortTableItem(amount, credited),
                SortTableItem(record.get("session_name") or "—", (record.get("session_name") or "—").casefold()),
                SortTableItem(_format_duration(event.seconds_delta, signed=True), event.seconds_delta),
                SortTableItem("Отменено" if event.undone else "Учтён", 1 if event.undone else 0),
            )
            for col, item in enumerate(values): table.setItem(row, col, item)
        table.setSortingEnabled(True); table.sortItems(0, Qt.DescendingOrder)
        layout.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(self.reject); buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).setText("Закрыть"); layout.addWidget(buttons)


class CleanupDialog(QDialog):
    """Safe storage cleanup: heavy analytics are selectable, donations stay intact."""
    def __init__(self, default_days: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Очистка данных")
        self.setMinimumWidth(540)
        layout=QVBoxLayout(self)
        title=QLabel("Что удалить?"); title.setObjectName("SectionTitle"); layout.addWidget(title)
        hint=QLabel("Выбери тяжёлые данные и срок. Донаты и сами сессии этим окном не удаляются — финансовая история останется в приложении.")
        hint.setObjectName("Muted"); hint.setWordWrap(True); layout.addWidget(hint)
        days_row=QHBoxLayout(); days_row.addWidget(QLabel("Удалить данные старше:")); self.days=QSpinBox(); self.days.setRange(1,3650); self.days.setValue(max(1,int(default_days))); self.days.setSuffix(" дн."); days_row.addWidget(self.days); days_row.addStretch(); layout.addLayout(days_row)
        self.chat=QCheckBox("Сообщения Twitch-чата"); self.chat.setChecked(True)
        self.viewers=QCheckBox("Замеры онлайна зрителей"); self.viewers.setChecked(True)
        self.speech_segments=QCheckBox("Расшифровки речи стримера"); self.speech_segments.setChecked(True)
        self.speech_audio=QCheckBox("Временные аудиозаписи микрофона"); self.speech_audio.setChecked(True)
        self.events=QCheckBox("Служебная история действий (кроме донатов)"); self.events.setChecked(False)
        for box in (self.chat,self.viewers,self.speech_segments,self.speech_audio,self.events): layout.addWidget(box)
        warning=QLabel("Совет: для обычного использования достаточно первых четырёх пунктов. Донаты и статистика сессий занимают мало места и сохраняются отдельно.")
        warning.setObjectName("Muted"); warning.setWordWrap(True); layout.addWidget(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Очистить выбранное"); buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def options(self) -> dict:
        return {
            "days": self.days.value(),
            "delete_chat": self.chat.isChecked(),
            "delete_viewers": self.viewers.isChecked(),
            "delete_speech_segments": self.speech_segments.isChecked(),
            "delete_speech_recordings": self.speech_audio.isChecked(),
            "delete_non_donation_events": self.events.isChecked(),
        }


class DonationTimeline(QWidget):
    """Наглядная шкала донатов с подсказками при наведении."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: list[dict] = []
        self.start_ts = 0.0
        self.end_ts = 1.0
        self.mode = "gradient"
        self._hover_targets: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def set_data(self, records: list[dict], start_ts: float | None, end_ts: float | None) -> None:
        self.records = sorted(records, key=lambda r: r["event"].created_at)
        timestamps = [r["event"].created_at for r in self.records]
        now = time.time()
        self.start_ts = float(start_ts if start_ts is not None else (min(timestamps) if timestamps else now - 3600))
        self.end_ts = float(end_ts if end_ts is not None else (max(timestamps) if timestamps else now))
        if self.end_ts <= self.start_ts:
            self.end_ts = self.start_ts + 60
        if start_ts is None and end_ts is None and self.end_ts - self.start_ts < 600:
            center = (self.start_ts + self.end_ts) / 2
            self.start_ts, self.end_ts = center - 300, center + 300
        self.update()

    def _x(self, ts: float, left: float, right: float) -> float:
        span=max(1.0,self.end_ts-self.start_ts)
        return left+(right-left)*max(0.0,min(1.0,(float(ts)-self.start_ts)/span))

    def mouseMoveEvent(self, event) -> None:
        pos=event.position()
        for rect,tip in reversed(self._hover_targets):
            if rect.contains(pos):
                QToolTip.showText(event.globalPosition().toPoint(),tip,self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText(); super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing,True)
        self._hover_targets=[]
        if self.mode=="light":
            text,muted,axis,panel=QColor("#172033"),QColor("#637089"),QColor("#8092aa"),QColor(255,255,255,185)
        elif self.mode=="night":
            text,muted,axis,panel=QColor("#f5f8ff"),QColor("#8290a7"),QColor("#51617a"),QColor(5,9,15,218)
        else:
            text,muted,axis,panel=QColor("#f4f6fb"),QColor("#9aa8bd"),QColor("#7186a4"),QColor(9,18,31,190)
        rect=QRectF(self.rect()).adjusted(8,8,-8,-8)
        painter.setPen(QPen(axis,1)); painter.setBrush(QBrush(panel)); painter.drawRoundedRect(rect,14,14)
        left,right=rect.left()+38,rect.right()-24; axis_y=rect.bottom()-48
        painter.setPen(QPen(axis,2)); painter.drawLine(QPointF(left,axis_y),QPointF(right,axis_y))
        span=max(1.0,self.end_ts-self.start_ts)
        for i in range(6):
            frac=i/5; x=left+(right-left)*frac; ts=self.start_ts+span*frac
            painter.setPen(QPen(axis,1)); painter.drawLine(QPointF(x,axis_y-4),QPointF(x,axis_y+4)); painter.setPen(muted)
            label=dt.datetime.fromtimestamp(ts).strftime("%d.%m\n%H:%M") if span>86400 else dt.datetime.fromtimestamp(ts).strftime("%H:%M")
            painter.drawText(QRectF(x-38,axis_y+7,76,30),Qt.AlignHCenter|Qt.AlignTop,label)
        if not self.records:
            painter.setPen(muted); painter.setFont(QFont("Segoe UI",11)); painter.drawText(rect,Qt.AlignCenter,"В этом промежутке донатов нет")
            return
        lanes=4
        for idx,record in enumerate(self.records):
            e=record["event"]; x=self._x(e.created_at,left,right); lane=idx%lanes; y=axis_y-32-lane*36
            credited=float(e.credited_amount if e.credited_amount is not None else (e.amount or 0))
            radius=5+min(7,math.log10(max(1.0,credited)+1)*1.8)
            hue=(int(e.id)*47)%360; marker=QColor.fromHsv(hue,185,245)
            painter.setPen(QPen(marker,1,Qt.DashLine)); painter.drawLine(QPointF(x,axis_y),QPointF(x,y))
            painter.setBrush(marker); painter.setPen(QPen(QColor("#ffffff"),1)); painter.drawEllipse(QPointF(x,y),radius,radius)
            donor=e.title or "Аноним"; tm=dt.datetime.fromtimestamp(e.created_at).strftime("%d.%m.%Y %H:%M:%S")
            session=record.get("session_name") or "Вне сессии"
            tip=f"{tm}\n{donor} · {_format_money(e.amount,e.currency)}\nДобавлено: {_format_duration(e.seconds_delta,signed=True)}\n{session}"
            self._hover_targets.append((QRectF(x-radius-7,y-radius-7,(radius+7)*2,(radius+7)*2),tip))
        painter.setPen(muted); painter.setFont(QFont("Segoe UI",9)); painter.drawText(QRectF(rect.left()+12,rect.top()+10,rect.width()-24,22),Qt.AlignLeft,"Наведи курсор на точку, чтобы увидеть детали")


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{2,}", re.UNICODE)
_STOPWORDS = {
    "это","как","что","вот","для","или","там","тут","так","его","еще","ещё","уже","она","они","оно","мы","вы","ты","я","он",
    "на","по","из","за","до","от","при","про","без","над","под","между","и","а","но","да","нет","не","же","ли","бы","быть",
    "с","со","к","ко","в","во","у","о","об","обо","то","этот","эта","эти","этого","этом","мой","моя","твой","тебя","меня",
    "the","and","for","you","that","this","with","have","are","was","but","not","from","just","your","our","they","them","its",
}


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD_RE.findall(text or "") if w.casefold() not in _STOPWORDS and not w.isdigit()]


def _word_counter(rows: list[dict], text_key: str, user_key: str | None = None) -> tuple[Counter, dict[str, set[str]]]:
    counts: Counter = Counter(); users: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        seen=set()
        for word in _words(str(row.get(text_key) or "")):
            counts[word]+=1
            if user_key and word not in seen:
                users[word].add(str(row.get(user_key) or "").casefold()); seen.add(word)
    return counts,users


class WordCloudWidget(QWidget):
    """Облако слов без пересечений: самые частые слова рисуются крупнее."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.mode="gradient"; self.items=[]; self._hover_targets=[]
        self.empty_message="Пока нет сообщений чата для выбранного периода"
        self.setMouseTracking(True); self.setMinimumHeight(300); self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)

    def set_mode(self,mode: str) -> None:
        self.mode=mode; self.update()

    def set_words(self,counts: Counter) -> None:
        self.items=counts.most_common(48); self.update()

    def set_empty_message(self, message: str) -> None:
        self.empty_message=message
        self.update()

    def mouseMoveEvent(self,event) -> None:
        pos=event.position()
        for rect,tip in reversed(self._hover_targets):
            if rect.contains(pos):
                QToolTip.showText(event.globalPosition().toPoint(),tip,self); return
        QToolTip.hideText(); super().mouseMoveEvent(event)

    def leaveEvent(self,event) -> None:
        QToolTip.hideText(); super().leaveEvent(event)

    def paintEvent(self,event) -> None:
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing,True); self._hover_targets=[]
        if self.mode=="light": panel=QColor(255,255,255,180); border=QColor("#c7d4e4"); base=QColor("#172033")
        elif self.mode=="night": panel=QColor(5,9,15,215); border=QColor("#3c4b62"); base=QColor("#f5f8ff")
        else: panel=QColor(9,18,31,188); border=QColor("#435675"); base=QColor("#f4f6fb")
        rect=QRectF(self.rect()).adjusted(8,8,-8,-8); painter.setBrush(panel); painter.setPen(QPen(border,1)); painter.drawRoundedRect(rect,14,14)
        if not self.items:
            painter.setPen(base); painter.setFont(QFont("Segoe UI",11)); painter.drawText(rect.adjusted(20,0,-20,0),Qt.AlignCenter|Qt.TextWordWrap,self.empty_message)
            return
        max_count=max(1,self.items[0][1]); palette=["#67e8f9","#c084fc","#fbbf24","#60a5fa","#fb7185","#34d399","#f472b6"]
        usable=rect.adjusted(18,18,-18,-18); rows=[]; current=[]; current_w=0.0; row_h=0.0
        for idx,(word,count) in enumerate(self.items):
            size=int(12+28*((count/max_count)**0.55)); font=QFont("Segoe UI",size,QFont.Bold); fm=painter.fontMetrics() if False else None
            painter.setFont(font); fm=painter.fontMetrics(); w=float(fm.horizontalAdvance(word)+16); h=float(fm.height()+9)
            if current and current_w+w>usable.width():
                rows.append((current,current_w,row_h)); current=[]; current_w=0.0; row_h=0.0
            current.append((word,count,font,w,h,idx)); current_w+=w; row_h=max(row_h,h)
        if current: rows.append((current,current_w,row_h))
        total_h=sum(r[2] for r in rows); y=usable.top()+max(0.0,(usable.height()-total_h)/2)
        for words,row_w,rh in rows:
            if y+rh>usable.bottom()+1: break
            x=usable.left()+max(0.0,(usable.width()-row_w)/2)
            for word,count,font,w,h,idx in words:
                box=QRectF(x,y,w,h); painter.setFont(font); painter.setPen(QColor(palette[idx%len(palette)])); painter.drawText(box,Qt.AlignCenter,word)
                self._hover_targets.append((box,f"{word}: {count} упоминаний")); x+=w
            y+=rh


class StreamAnalyticsTimeline(QWidget):
    """Interactive timeline for one analytics source.

    Ctrl + mouse wheel zooms around the cursor, while a plain wheel event is
    deliberately forwarded to the surrounding scroll area.  This keeps the
    long Analysis page easy to navigate without giving up precise chart zoom.
    Dragging pans an already zoomed chart.  Each chart owns only the dataset it
    actually paints; older builds kept four full copies of chat/viewer/speech
    data per chart, which caused large RAM spikes.
    """
    def __init__(self,parent=None):
        super().__init__(parent)
        self.mode="gradient"
        self.source="viewers"
        self.donations=[]; self.viewers=[]; self.chat=[]; self.speech=[]
        now=time.time()
        self.full_start_ts=now-3600; self.full_end_ts=now
        self.view_start_ts=self.full_start_ts; self.view_end_ts=self.full_end_ts
        self._hover_targets=[]
        self._dragging=False; self._drag_x=0.0; self._drag_start=0.0; self._drag_end=0.0
        self._zoom_callback=None
        self.setMouseTracking(True)
        self.setMinimumHeight(245)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)

    def set_mode(self,mode: str) -> None:
        self.mode=mode; self.update()

    def set_zoom_callback(self, callback) -> None:
        self._zoom_callback=callback
        self._notify_zoom()

    def zoom_factor(self) -> float:
        full=max(1.0,self.full_end_ts-self.full_start_ts)
        view=max(0.001,self.view_end_ts-self.view_start_ts)
        return max(1.0,full/view)

    def zoom_percent(self) -> int:
        return max(100,int(round(self.zoom_factor()*100)))

    def zoom_label(self) -> str:
        factor=self.zoom_factor()
        if factor<=5:
            return f"{factor*100:.0f}%"
        if factor<1000:
            return f"×{factor:.0f}"
        if factor<1_000_000:
            return f"×{factor/1000:.1f}k"
        return f"×{factor/1_000_000:.1f}M"

    def _notify_zoom(self) -> None:
        if self._zoom_callback:
            try: self._zoom_callback(self.zoom_label())
            except Exception: pass

    def set_data(self,*,source: str,donations: list[dict],viewers: list[dict],chat: list[dict],speech: list[dict],start_ts: float|None,end_ts: float|None,query: str="",reset_view: bool=False) -> None:
        old_source=self.source
        old_full_span=max(1.0,self.full_end_ts-self.full_start_ts)
        old_view_span=max(1.0,self.view_end_ts-self.view_start_ts)
        was_full=old_view_span >= old_full_span*0.985
        self.source=source
        # Hold only the data needed by this chart. This is the main RAM fix for
        # the Analysis page: no more 4× sorted copies of 50k chat messages.
        self.donations=sorted(donations,key=lambda r:r["event"].created_at) if source=="donations" else []
        self.viewers=sorted(viewers,key=lambda r:float(r["created_at"])) if source=="viewers" else []
        self.chat=sorted(chat,key=lambda r:float(r["created_at"])) if source=="chat" else []
        self.speech=sorted(speech,key=lambda r:float(r["started_at"])) if source=="speech" else []
        timestamps=[]
        if source=="donations": timestamps=[r["event"].created_at for r in self.donations]
        elif source=="viewers": timestamps=[float(r["created_at"]) for r in self.viewers]
        elif source=="chat": timestamps=[float(r["created_at"]) for r in self.chat]
        elif source=="speech": timestamps=[float(r["started_at"]) for r in self.speech]
        now=time.time()
        self.full_start_ts=float(start_ts if start_ts is not None else (min(timestamps) if timestamps else now-3600))
        self.full_end_ts=float(end_ts if end_ts is not None else (max(timestamps) if timestamps else now))
        if self.full_end_ts<=self.full_start_ts: self.full_end_ts=self.full_start_ts+60
        if reset_view or old_source!=source or was_full:
            self.reset_zoom(notify=False)
        else:
            span=min(old_view_span,self.full_end_ts-self.full_start_ts)
            center=(self.view_start_ts+self.view_end_ts)/2
            self._set_view(center-span/2,center+span/2,notify=False)
        self._notify_zoom(); self.update()

    def release_data(self) -> None:
        self.donations=[]; self.viewers=[]; self.chat=[]; self.speech=[]; self._hover_targets=[]
        self.update()

    def reset_zoom(self, notify: bool=True) -> None:
        self.view_start_ts=self.full_start_ts; self.view_end_ts=self.full_end_ts
        if notify: self._notify_zoom()
        self.update()

    def zoom_in(self, factor: float=1.7, center_ts: float|None=None) -> None:
        self._zoom(float(factor),center_ts)

    def zoom_out(self, factor: float=1.7, center_ts: float|None=None) -> None:
        self._zoom(1.0/max(1.01,float(factor)),center_ts)

    def zoom_max(self) -> None:
        center=(self.view_start_ts+self.view_end_ts)/2
        min_span=min(2.0,self.full_end_ts-self.full_start_ts)
        if min_span<=0: return
        self._set_view(center-min_span/2,center+min_span/2)

    def _zoom(self, factor: float, center_ts: float|None=None) -> None:
        full_span=max(1.0,self.full_end_ts-self.full_start_ts)
        old_span=max(0.001,self.view_end_ts-self.view_start_ts)
        new_span=max(min(2.0,full_span),min(full_span,old_span/max(0.01,factor)))
        center=float(center_ts if center_ts is not None else (self.view_start_ts+self.view_end_ts)/2)
        ratio=(center-self.view_start_ts)/old_span
        ratio=max(0.0,min(1.0,ratio))
        start=center-new_span*ratio
        self._set_view(start,start+new_span)

    def _set_view(self,start: float,end: float,notify: bool=True) -> None:
        full_start,full_end=self.full_start_ts,self.full_end_ts
        full_span=max(1.0,full_end-full_start); span=max(0.001,min(end-start,full_span))
        if start<full_start: start=full_start; end=start+span
        if end>full_end: end=full_end; start=end-span
        self.view_start_ts=max(full_start,start); self.view_end_ts=min(full_end,end)
        if self.view_end_ts<=self.view_start_ts: self.view_end_ts=min(full_end,self.view_start_ts+1)
        if notify: self._notify_zoom()
        self.update()

    def _x(self,ts: float,left: float,right: float) -> float:
        return left+(right-left)*max(0.0,min(1.0,(float(ts)-self.view_start_ts)/max(1e-6,self.view_end_ts-self.view_start_ts)))

    @staticmethod
    def _bucket_rows(rows:list[dict],ts_key:str,start:float,end:float,bins:int=64) -> list[list[dict]]:
        result=[[] for _ in range(bins)]; span=max(1e-6,end-start)
        for row in rows:
            ts=float(row[ts_key])
            if ts<start or ts>end: continue
            idx=min(bins-1,max(0,int((ts-start)/span*bins)))
            result[idx].append(row)
        return result

    def _chart_bounds(self) -> tuple[float,float]:
        return 56.0,max(57.0,float(self.width())-32.0)

    def wheelEvent(self,event) -> None:
        # A normal wheel gesture belongs to the page, not the graph.  Previous
        # builds consumed every wheel event here, which made the Analysis page
        # feel "stuck" whenever the cursor happened to be over a chart.  Zoom
        # is now explicit: hold Ctrl while scrolling.
        if event.modifiers() & Qt.ControlModifier:
            delta=event.angleDelta().y()
            if delta==0:
                event.accept(); return
            left,right=self._chart_bounds(); x=float(event.position().x())
            frac=max(0.0,min(1.0,(x-left)/max(1.0,right-left)))
            center=self.view_start_ts+(self.view_end_ts-self.view_start_ts)*frac
            if delta>0: self.zoom_in(1.65,center)
            else: self.zoom_out(1.65,center)
            event.accept(); return

        # Forward ordinary wheel / trackpad scrolling to the containing
        # QScrollArea.  Doing this explicitly is more reliable than relying on
        # Qt's event bubbling through several nested cards and viewports.
        parent=self.parentWidget()
        while parent is not None and not isinstance(parent,QScrollArea):
            parent=parent.parentWidget()
        if isinstance(parent,QScrollArea):
            bar=parent.verticalScrollBar()
            pixel_delta=event.pixelDelta().y()
            if pixel_delta:
                scroll_amount=float(pixel_delta)
            else:
                angle_delta=event.angleDelta().y()
                # One wheel notch should move a comfortable chunk of the page.
                step=max(72.0,float(bar.singleStep())*4.0)
                scroll_amount=(float(angle_delta)/120.0)*step
            if scroll_amount:
                bar.setValue(bar.value()-int(round(scroll_amount)))
            event.accept(); return

        event.ignore()

    def mousePressEvent(self,event) -> None:
        if event.button()==Qt.LeftButton and self.zoom_percent()>100:
            self._dragging=True; self._drag_x=float(event.position().x()); self._drag_start=self.view_start_ts; self._drag_end=self.view_end_ts
            self.setCursor(Qt.ClosedHandCursor); event.accept(); return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event) -> None:
        if self._dragging and event.button()==Qt.LeftButton:
            self._dragging=False; self.unsetCursor(); event.accept(); return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self,event) -> None:
        if self._dragging:
            left,right=self._chart_bounds(); dx=float(event.position().x())-self._drag_x
            seconds=-(dx/max(1.0,right-left))*(self._drag_end-self._drag_start)
            self._set_view(self._drag_start+seconds,self._drag_end+seconds)
            event.accept(); return
        pos=event.position()
        for rect,tip in reversed(self._hover_targets):
            if rect.contains(pos): QToolTip.showText(event.globalPosition().toPoint(),tip,self); return
        QToolTip.hideText(); super().mouseMoveEvent(event)

    def leaveEvent(self,event) -> None:
        if not self._dragging: QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self,event) -> None:
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing,True); self._hover_targets=[]
        if self.mode=="light": text,muted,axis,panel=QColor("#172033"),QColor("#637089"),QColor("#8191aa"),QColor(255,255,255,190)
        elif self.mode=="night": text,muted,axis,panel=QColor("#f5f8ff"),QColor("#8290a7"),QColor("#51617a"),QColor(4,8,14,218)
        else: text,muted,axis,panel=QColor("#f4f6fb"),QColor("#9aa8bd"),QColor("#7186a4"),QColor(8,17,30,190)
        rect=QRectF(self.rect()).adjusted(8,8,-8,-8); painter.setBrush(panel); painter.setPen(QPen(axis,1)); painter.drawRoundedRect(rect,14,14)
        left,right=rect.left()+48,rect.right()-24; bottom=rect.bottom()-44; top=rect.top()+34; span=max(1e-6,self.view_end_ts-self.view_start_ts)
        painter.setPen(QPen(axis,1)); painter.drawLine(QPointF(left,bottom),QPointF(right,bottom))
        for i in range(6):
            x=left+(right-left)*(i/5); ts=self.view_start_ts+span*(i/5); painter.drawLine(QPointF(x,bottom-4),QPointF(x,bottom+4)); painter.setPen(muted)
            label=dt.datetime.fromtimestamp(ts).strftime("%d.%m\n%H:%M") if span>86400 else (dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S") if span<600 else dt.datetime.fromtimestamp(ts).strftime("%H:%M"))
            painter.drawText(QRectF(x-42,bottom+7,84,30),Qt.AlignHCenter|Qt.AlignTop,label); painter.setPen(QPen(axis,1))
        painter.setPen(muted); painter.setFont(QFont("Segoe UI",9)); painter.drawText(QRectF(left,rect.top()+7,right-left,18),Qt.AlignLeft,"Колесо мыши — масштаб · потяни график — перемещение")
        painter.drawText(QRectF(left,rect.top()+7,right-left,18),Qt.AlignRight,self.zoom_label())

        if self.source=="viewers":
            visible=[r for r in self.viewers if self.view_start_ts<=float(r["created_at"])<=self.view_end_ts]
            if not visible:
                painter.setPen(muted); painter.drawText(QRectF(left,top,right-left,bottom-top),Qt.AlignCenter,"Данных об онлайне в этом фрагменте нет")
            else:
                vals=[int(r["viewer_count"]) for r in visible]; vmax=max(1,max(vals)); pts=[]
                for r in visible:
                    x=self._x(float(r["created_at"]),left,right); y=bottom-10-(bottom-top-28)*(int(r["viewer_count"])/vmax); pt=QPointF(x,y); pts.append(pt)
                    tm=dt.datetime.fromtimestamp(float(r["created_at"])).strftime("%d.%m.%Y %H:%M:%S"); self._hover_targets.append((QRectF(x-8,y-8,16,16),f"{tm}\nЗрителей: {r['viewer_count']}"))
                painter.setPen(QPen(QColor("#58c8ff"),2.4))
                for a,b in zip(pts,pts[1:]): painter.drawLine(a,b)
                painter.setBrush(QColor("#58c8ff")); painter.setPen(Qt.NoPen)
                for pt in pts: painter.drawEllipse(pt,3.5,3.5)
                painter.setPen(muted); painter.drawText(QRectF(left,top,right-left,18),Qt.AlignRight,f"Пик видимого фрагмента: {vmax}")
        elif self.source in {"chat","speech"}:
            rows=self.chat if self.source=="chat" else self.speech; ts_key="created_at" if self.source=="chat" else "started_at"
            bins=max(48,min(120,int(max(1.0,right-left)/10)))
            buckets=self._bucket_rows(rows,ts_key,self.view_start_ts,self.view_end_ts,bins); counts=[len(b) for b in buckets]; m=max(counts or [0]); color=QColor("#b36dff") if self.source=="chat" else QColor("#ff7eb6")
            if m<=0:
                painter.setPen(muted); painter.drawText(QRectF(left,top,right-left,bottom-top),Qt.AlignCenter,"Сообщений чата в этом фрагменте нет" if self.source=="chat" else "Расшифрованной речи в этом фрагменте нет")
            else:
                bw=(right-left)/len(buckets)
                for i,bucket in enumerate(buckets):
                    val=len(bucket)
                    if val<=0: continue
                    h=(bottom-top-28)*(val/m); bar=QRectF(left+i*bw,bottom-h,max(2.0,bw-1),h); painter.fillRect(bar,color)
                    bstart=self.view_start_ts+(span*i/len(buckets)); bend=self.view_start_ts+(span*(i+1)/len(buckets)); kind="Сообщений" if self.source=="chat" else "Фрагментов речи"
                    tip=f"{dt.datetime.fromtimestamp(bstart):%d.%m.%Y %H:%M:%S} — {dt.datetime.fromtimestamp(bend):%H:%M:%S}\n{kind}: {val}"
                    if self.source=="chat" and bucket:
                        sample=bucket[-1]; tip += f"\nПоследнее: {sample.get('user_name') or 'Аноним'}: {str(sample.get('message_text') or '')[:110]}"
                    elif self.source=="speech" and bucket:
                        tip += f"\nФраза: {str(bucket[-1].get('text') or '')[:130]}"
                    self._hover_targets.append((bar.adjusted(-2,-3,2,0),tip))
                painter.setPen(muted); painter.drawText(QRectF(left,top,right-left,18),Qt.AlignRight,f"Пиковая активность: {m}")
        else:
            visible=[r for r in self.donations if self.view_start_ts<=r["event"].created_at<=self.view_end_ts]
            if not visible:
                painter.setPen(muted); painter.drawText(QRectF(left,top,right-left,bottom-top),Qt.AlignCenter,"Донатов в этом фрагменте нет")
            else:
                lane_count=max(5,min(11,int(max(1.0,bottom-top)/16)))
                lane_last=[-10_000.0]*lane_count
                lane_y=[top+18+(bottom-top-36)*(i/max(1,lane_count-1)) for i in range(lane_count)]
                for rec in visible:
                    e=rec["event"]; x=self._x(e.created_at,left,right); amount=float(e.credited_amount if e.credited_amount is not None else (e.amount or 0)); radius=4.5+min(6.5,math.log10(max(1,amount)+1)*1.7)
                    threshold=max(14.0,radius*2+5)
                    lane=next((i for i,last in enumerate(lane_last) if x-last>=threshold),None)
                    if lane is None: lane=min(range(lane_count),key=lambda i: lane_last[i])
                    lane_last[lane]=x; y=lane_y[lane]
                    painter.setBrush(QColor("#ffd34f")); painter.setPen(QPen(QColor("#fff6c4"),1)); painter.drawEllipse(QPointF(x,y),radius,radius)
                    tm=dt.datetime.fromtimestamp(e.created_at).strftime("%d.%m.%Y %H:%M:%S"); tip=f"{tm}\n{e.title or 'Аноним'} · {_format_money(e.amount,e.currency)}\nДобавлено: {_format_duration(e.seconds_delta,signed=True)}\n{rec.get('session_name') or 'Вне сессии'}"
                    self._hover_targets.append((QRectF(x-radius-7,y-radius-7,(radius+7)*2,(radius+7)*2),tip))



class WheelPreview(QWidget):
    """Animated wheel preview used on the Entertainment page."""
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshot = {"entries": [], "result": "", "title": "Рулетка", "spin_speed": "normal"}
        self._mode = "gradient"
        self._rotation = 0.0
        self._last_nonce = -1
        self._anim = QPropertyAnimation(self, b"rotation", self)
        self._anim.setEasingCurve(QEasingCurve.OutQuint)
        self.setMinimumSize(270, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    def getRotation(self) -> float:
        return float(self._rotation)

    def setRotation(self, value: float) -> None:
        self._rotation = float(value)
        self.update()

    rotation = Property(float, getRotation, setRotation)

    def set_snapshot(self, snapshot: dict) -> None:
        snap = snapshot or {"entries": []}
        nonce = int(snap.get("spin_nonce") or 0)
        target = float(snap.get("spin_angle") or 0.0)
        speed = "fast" if str(snap.get("spin_speed") or "normal") == "fast" else "normal"
        if self._last_nonce < 0:
            self._rotation = target
        elif nonce != self._last_nonce:
            current_mod = ((self._rotation % 360.0) + 360.0) % 360.0
            loops = 3 if speed == "fast" else 7
            delta = loops * 360.0 + ((target - current_mod + 360.0) % 360.0)
            self._anim.stop()
            self._anim.setDuration(1600 if speed == "fast" else 6200)
            self._anim.setStartValue(self._rotation)
            self._anim.setEndValue(self._rotation + delta)
            self._anim.start()
        self._last_nonce = nonce
        self._snapshot = snap
        self.update()

    def mousePressEvent(self, event) -> None:
        w, h = self.width(), self.height()
        side = max(120.0, min(w, h) - 34.0)
        rect = QRectF((w-side)/2, (h-side)/2+6, side, side)
        center = rect.center()
        dx = event.position().x() - center.x()
        dy = event.position().y() - center.y()
        if (dx * dx + dy * dy) <= (34.0 * 34.0):
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        side = max(120.0, min(w, h) - 34.0)
        rect = QRectF((w-side)/2, (h-side)/2+6, side, side)
        entries = list(self._snapshot.get("entries") or [])
        speed = str(self._snapshot.get("spin_speed") or "normal")
        if self._mode == "light":
            base, border, text, accent = QColor("#eef3fb"), QColor("#aabbd2"), QColor("#172033"), QColor("#5e68ff")
        elif self._mode == "night":
            base, border, text, accent = QColor("#050a11"), QColor("#566b88"), QColor("#f5f8ff"), QColor("#7f8cff")
        else:
            base, border, text, accent = QColor("#0c1625"), QColor("#6c63ff"), QColor("#f7f8ff"), QColor("#9a7cff")

        # background aura
        aura = QRectF(rect.adjusted(-12, -12, 12, 12))
        grad = QRadialGradient(aura.center(), aura.width()/2)
        aura_color = QColor(accent)
        aura_color.setAlpha(75)
        grad.setColorAt(0.0, aura_color)
        outer = QColor(accent)
        outer.setAlpha(0)
        grad.setColorAt(1.0, outer)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(aura)

        # drop shadow disc
        shadow = QRectF(rect.adjusted(6, 8, 6, 8))
        sh = QColor("#000000"); sh.setAlpha(95)
        painter.setBrush(sh); painter.drawEllipse(shadow)

        painter.setBrush(base); painter.setPen(Qt.NoPen); painter.drawEllipse(rect)
        total = sum(max(0.0, float(x.get("percent") or 0)) for x in entries)
        painter.save()
        painter.translate(rect.center())
        painter.rotate(self._rotation)
        local_rect = QRectF(-rect.width()/2, -rect.height()/2, rect.width(), rect.height())
        if entries and total > 0:
            start_deg = 90.0
            for item in entries:
                span = max(0.0, float(item.get("percent") or 0)) / total * 360.0
                color = QColor(str(item.get("color") or "#8b5cf6"))
                color2 = QColor(color); color2 = color2.lighter(120)
                con = QConicalGradient(QPointF(0,0), start_deg)
                con.setColorAt(0.0, color2)
                con.setColorAt(1.0, color)
                painter.setBrush(QBrush(con))
                painter.setPen(QPen(QColor(255,255,255,50), 1.2))
                painter.drawPie(local_rect, int(start_deg*16), int(-span*16))
                mid = start_deg - span/2.0
                painter.save()
                ang = math.radians(mid)
                radius = rect.width()*0.32
                tx = math.cos(ang)*radius
                ty = -math.sin(ang)*radius
                painter.translate(tx, ty)
                painter.rotate(-mid)
                font = QFont("Segoe UI", max(7, min(11, int(rect.width()/33))))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#ffffff"))
                label = str(item.get("label") or "")[:14]
                painter.drawText(QRectF(-40,-14,80,28), Qt.AlignCenter|Qt.TextWordWrap, label)
                painter.restore()
                start_deg -= span
        else:
            painter.setBrush(QColor("#223246"))
            painter.drawEllipse(local_rect)
        painter.restore()

        painter.setPen(QPen(border, 5)); painter.setBrush(Qt.NoBrush); painter.drawEllipse(rect)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(rect.adjusted(11,11,-11,-11))
        # pointer
        cx = rect.center().x(); top = rect.top()-5
        painter.setPen(Qt.NoPen); painter.setBrush(QColor("#ffffff"))
        from PySide6.QtGui import QPolygonF
        painter.drawPolygon(QPolygonF([QPointF(cx-16,top-10), QPointF(cx+16,top-10), QPointF(cx,top+20)]))
        # center hub + label
        hub = QRectF(rect.center().x()-31, rect.center().y()-31, 62, 62)
        painter.setBrush(QColor("#f8fafc")); painter.setPen(QPen(QColor("#111827"), 7)); painter.drawEllipse(hub)
        font=QFont("Segoe UI", 9); font.setBold(True); painter.setFont(font); painter.setPen(QColor("#111827")); painter.drawText(hub, Qt.AlignCenter, "GO")

        result = str(self._snapshot.get("result") or "")
        status = str(self._snapshot.get("result_status") or "")
        if result and not self._anim.state() == QPropertyAnimation.Running:
            box = QRectF(20, h-64, w-40, 50)
            painter.setPen(Qt.NoPen)
            panel = QColor(8,12,20,180) if self._mode != "light" else QColor(255,255,255,220)
            painter.setBrush(panel)
            painter.drawRoundedRect(box, 12, 12)
            painter.setPen(text)
            font=QFont("Segoe UI", max(9, int(side/38))); font.setBold(False); painter.setFont(font)
            painter.drawText(QRectF(box.left()+10, box.top()+6, box.width()-20, 16), Qt.AlignCenter, status)
            font=QFont("Segoe UI", max(11, int(side/28))); font.setBold(True); painter.setFont(font)
            painter.drawText(QRectF(box.left()+10, box.top()+20, box.width()-20, 22), Qt.AlignCenter, result[:42])


class MainWindow(QMainWindow):
    PAGE_HOME = 0
    PAGE_OVERLAY = 1
    PAGE_HISTORY = 2
    PAGE_DONATIONS = 3
    PAGE_ANALYSIS = 4
    PAGE_ENTERTAINMENT = 5
    PAGE_SESSIONS = 6
    PAGE_ACCOUNTS = 7
    PAGE_GUIDE = 8
    PAGE_SETTINGS = 9
    COMPACT_WIDTH = 940

    def __init__(self, state: AppState, storage: Storage, da_service: DonationAlertsService, twitch_service: TwitchService, speech_service: SpeechService, entertainment_service: EntertainmentService):
        super().__init__()
        self.state = state
        self.storage = storage
        self.da_service = da_service
        self.twitch_service = twitch_service
        self.speech_service = speech_service
        self.entertainment_service = entertainment_service
        self._compact = False
        self._history_signature: tuple | None = None
        self._sessions_signature: tuple | None = None
        self._donations_signature: tuple | None = None
        self._analysis_signature: tuple | None = None
        self._analysis_context_key: tuple | None = None
        self._analysis_last_refresh_at = 0.0
        self._analysis_release_generation = 0
        self._selected_session_id: int | None = None
        self._last_profile_check_at = 0.0
        self._last_history_refresh_at = 0.0
        self._last_sessions_refresh_at = 0.0
        self._last_donations_refresh_at = 0.0
        self._last_retention_check_at = 0.0
        if self.storage.get_setting("analytics_retention_days") is None:
            self.storage.set_setting("analytics_retention_days", "20")
        if self.storage.get_setting("analytics_auto_cleanup") is None:
            self.storage.set_setting("analytics_auto_cleanup", "1")
        self.ui_theme = (self.storage.get_setting("ui_theme") or "gradient").strip().lower()
        if self.ui_theme not in {"gradient", "light", "night"}: self.ui_theme = "gradient"
        self.selected_theme = "classic"
        self.theme_buttons: dict[str, QPushButton] = {}
        self.theme_widgets: dict[str, QFrame] = {}
        self.theme_apply_buttons: dict[str, QPushButton] = {}
        self.nav_buttons: list[QPushButton] = []

        self.setWindowTitle(f"Donathon Timer {APP_VERSION}")
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets" / "logo_icon.png")))
        self.setMinimumSize(780, 580)
        self.resize(1180, 800)
        self.setStyleSheet(_build_style(self.ui_theme))
        self._build_ui()
        self._install_no_wheel_handlers(self)
        self._refresh_profiles()
        self._refresh()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._periodic_refresh)
        self.refresh_timer.start(1200)
        QTimer.singleShot(0, self._update_responsive_layout)
        QTimer.singleShot(1800, self._run_auto_cleanup_if_due)


    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            if isinstance(obj, (QComboBox, QAbstractSpinBox, QDateTimeEdit)) and not (QApplication.keyboardModifiers() & Qt.ControlModifier):
                event.ignore()
                return True
        return super().eventFilter(obj, event)

    def _install_no_wheel_handlers(self, root: QWidget) -> None:
        # PySide6 QObject.findChildren accepts one type, never a tuple.
        # First find QWidget descendants, then use Python's normal isinstance.
        for widget in root.findChildren(QWidget):
            if not isinstance(widget, (QComboBox, QAbstractSpinBox, QDateTimeEdit)):
                continue
            widget.installEventFilter(self)
            try:
                widget.setFocusPolicy(Qt.StrongFocus)
            except Exception:
                pass

    def _card(self, accent: str = "neutral") -> QFrame:
        frame = QFrame(); frame.setObjectName("Card"); frame.setProperty("accent", accent)
        frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        return frame

    @staticmethod
    def _clear_layout(layout: QLayout) -> None:
        while layout.count():
            layout.takeAt(0)

    def _make_scroll_page(self) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); scroll.setFrameShape(QFrame.NoFrame)
        root = QWidget(); root.setMinimumWidth(0); root.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(root); layout.setSizeConstraint(QLayout.SetDefaultConstraint)
        layout.setContentsMargins(4, 4, 12, 18); layout.setSpacing(16); scroll.setWidget(root)
        return scroll, root, layout

    def _build_ui(self) -> None:
        self.central_root = GradientRoot(self.ui_theme); self.central_root.setObjectName("CentralRoot"); self.setCentralWidget(self.central_root)
        shell = QHBoxLayout(self.central_root); shell.setContentsMargins(0, 0, 0, 0); shell.setSpacing(0)

        # Sidebar
        self.sidebar = QFrame(); self.sidebar.setObjectName("Sidebar"); self.sidebar.setFixedWidth(202)
        side = QVBoxLayout(self.sidebar); side.setContentsMargins(13, 22, 13, 18); side.setSpacing(8)
        brand_row = QHBoxLayout(); brand_row.setSpacing(6)
        brand_icon = QLabel(); brand_icon.setPixmap(QPixmap(str(Path(__file__).resolve().parent / "assets" / "logo_icon.png")).scaled(28,28, Qt.KeepAspectRatio, Qt.SmoothTransformation)); brand_icon.setFixedSize(30,30)
        brand = QLabel("DONATHON"); brand.setObjectName("Brand"); brand.setMinimumWidth(122)
        brand_row.addWidget(brand_icon,0,Qt.AlignVCenter); brand_row.addWidget(brand,0,Qt.AlignVCenter); brand_row.addStretch()
        brand_sub = QLabel(f"Timer · v{APP_VERSION}"); brand_sub.setObjectName("BrandSub")
        side.addLayout(brand_row); side.addWidget(brand_sub); side.addSpacing(18)

        nav_items = [
            ("Главная", "Боевой экран стрима"),
            ("Оверлей", "Внешний вид таймера"),
            ("История", "События и действия"),
            ("Донаты", "Все донаты и статистика"),
            ("Анализ", "Все данные стрима на отдельных шкалах"),
            ("Развлечения", "Рулетки и голосования для чата"),
            ("Сессии", "Отдельные донатофоны"),
            ("Аккаунты", "DonationAlerts + Twitch"),
            ("Инструкция", "Подключение и работа"),
            ("Настройки", "OBS и приложение"),
        ]
        nav_accents = ["green", "orange", "cyan", "gold", "magenta", "purple", "blue", "purple", "teal", "neutral"]
        self.page_meta = nav_items
        self.nav_group = QButtonGroup(self); self.nav_group.setExclusive(True)
        for index, (name, _) in enumerate(nav_items):
            btn = QPushButton(name); btn.setObjectName("NavButton"); btn.setProperty("navAccent", nav_accents[index]); btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, i=index: self._switch_page(i))
            self.nav_group.addButton(btn, index); self.nav_buttons.append(btn); side.addWidget(btn)
        self.nav_buttons[0].setChecked(True)
        side.addStretch()
        safe = QLabel("Локальный контроллер\nOBS + DonationAlerts")
        safe.setObjectName("BrandSub"); safe.setWordWrap(True); side.addWidget(safe)
        mode_label = QLabel("Оформление приложения"); mode_label.setObjectName("BrandSub"); side.addWidget(mode_label)
        mode_row = QHBoxLayout(); mode_row.setSpacing(6)
        self.mode_group = QButtonGroup(self); self.mode_group.setExclusive(True); self.mode_buttons = {}
        for key, text, tip in (("light","☀","Дневной режим"),("gradient","◆","Градиентовый режим"),("night","☾","Ночной режим")):
            btn=QPushButton(text); btn.setObjectName("ModeButton"); btn.setCheckable(True); btn.setToolTip(tip); btn.setChecked(self.ui_theme==key)
            btn.clicked.connect(lambda checked=False,k=key:self._set_ui_theme(k)); self.mode_group.addButton(btn); self.mode_buttons[key]=btn; mode_row.addWidget(btn)
        side.addLayout(mode_row)
        support_btn=QPushButton("Связь с техподдержкой ↗")
        support_btn.setObjectName("SupportLink")
        support_btn.setToolTip("Открыть Telegram для связи с разработчиком")
        support_btn.clicked.connect(lambda: webbrowser.open("https://t.me/Cheese_Cake44"))
        side.addWidget(support_btn)
        shell.addWidget(self.sidebar)

        # Right workspace
        work = QWidget(); work.setMinimumWidth(0); work_l = QVBoxLayout(work); work_l.setContentsMargins(22, 18, 22, 0); work_l.setSpacing(12)
        header = QHBoxLayout(); title_box = QVBoxLayout()
        self.page_title = QLabel(nav_items[0][0]); self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel(nav_items[0][1]); self.page_subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(self.page_title); title_box.addWidget(self.page_subtitle)
        header.addLayout(title_box); header.addStretch()
        self.profile_combo = QComboBox(); self.profile_combo.setMinimumWidth(220); self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        header.addWidget(self.profile_combo); work_l.addLayout(header)
        self.stack = QStackedWidget(); self.stack.setMinimumWidth(0); work_l.addWidget(self.stack, 1); shell.addWidget(work, 1)

        self._build_home_page()
        self._build_overlay_page()
        self._build_history_page()
        self._build_donations_page()
        self._build_analysis_page()
        self._build_entertainment_page()
        self._build_sessions_page()
        self._build_accounts_page()
        self._build_guide_page()
        self._build_settings_page()
        self.stack.setCurrentIndex(0)
        self._arrange_wide()

    def _build_home_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        # Main stream dashboard. On wide windows the session panel occupies the
        # right side across two rows; on compact windows all blocks stack.
        self.home_top_grid = QGridLayout(); self.home_top_grid.setHorizontalSpacing(16); self.home_top_grid.setVerticalSpacing(14)

        self.status_card = self._card("green"); status = QVBoxLayout(self.status_card); status.setContentsMargins(20,18,20,18); status.setSpacing(7)
        st = QLabel("Система"); st.setObjectName("SectionTitle"); status.addWidget(st)
        self.timer_status = QLabel("● Таймер остановлен"); self.timer_status.setObjectName("Warn")
        self.obs_status = QLabel("● OBS-оверлей готов"); self.obs_status.setObjectName("Good")
        self.da_status = QLabel("● DonationAlerts не подключён"); self.da_status.setObjectName("Warn")
        self.twitch_home_status = QLabel("● Twitch не подключён"); self.twitch_home_status.setObjectName("Warn")
        status.addWidget(self.timer_status); status.addWidget(self.obs_status); status.addWidget(self.da_status); status.addWidget(self.twitch_home_status)
        home_timer_row=QHBoxLayout(); home_timer_row.setSpacing(8)
        self.home_timer_toggle=QPushButton("Показать таймер"); self.home_timer_toggle.setObjectName("OBSActionTimer"); self.home_timer_toggle.setCheckable(True); self.home_timer_toggle.toggled.connect(self._overlay_timer_visibility_changed)
        self.home_interactive_toggle=QPushButton("Показать рулетку"); self.home_interactive_toggle.setObjectName("OBSActionInteractive"); self.home_interactive_toggle.setCheckable(True); self.home_interactive_toggle.toggled.connect(self._entertainment_interactive_visibility_changed)
        home_timer_row.addWidget(self.home_timer_toggle); home_timer_row.addWidget(self.home_interactive_toggle); home_timer_row.addStretch(); status.addLayout(home_timer_row); status.addStretch()

        # Expanded current-session card.
        self.home_session_card = self._card("blue"); session = QVBoxLayout(self.home_session_card); session.setContentsMargins(20,18,20,18); session.setSpacing(8)
        sh = QHBoxLayout(); sl = QLabel("Текущая сессия"); sl.setObjectName("SectionTitle"); sh.addWidget(sl); sh.addStretch()
        manage_btn = QPushButton("Открыть сессии"); manage_btn.clicked.connect(lambda: self._switch_page(self.PAGE_SESSIONS)); sh.addWidget(manage_btn); session.addLayout(sh)
        self.home_session_actions = QGridLayout(); self.home_session_actions.setHorizontalSpacing(8); self.home_session_actions.setVerticalSpacing(8)
        self.home_start_session_btn = QPushButton("Начать сессию"); self.home_start_session_btn.setObjectName("Primary"); self.home_start_session_btn.clicked.connect(self._new_session)
        self.home_pause_session_btn = QPushButton("Приостановить сессию"); self.home_pause_session_btn.clicked.connect(self._toggle_session_pause)
        self.home_end_session_btn = QPushButton("Завершить сессию"); self.home_end_session_btn.setObjectName("Danger"); self.home_end_session_btn.clicked.connect(self._end_session)
        self.home_session_actions.addWidget(self.home_start_session_btn,0,0,1,2)
        self.home_session_actions.addWidget(self.home_pause_session_btn,1,0); self.home_session_actions.addWidget(self.home_end_session_btn,1,1)
        self.home_session_actions.setColumnStretch(0,1); self.home_session_actions.setColumnStretch(1,1); session.addLayout(self.home_session_actions)
        self.main_session_name = QLabel("Сессия не запущена"); self.main_session_name.setStyleSheet("font-size:18px;font-weight:800")
        self.main_session_meta = QLabel(""); self.main_session_meta.setObjectName("Muted"); self.main_session_meta.setWordWrap(True)
        self.main_session_elapsed = QLabel(""); self.main_session_elapsed.setStyleSheet("font-size:15px;font-weight:700")
        self.main_session_stats = QLabel("История продолжает записываться в профиль."); self.main_session_stats.setObjectName("Muted"); self.main_session_stats.setWordWrap(True)
        session.addWidget(self.main_session_name); session.addWidget(self.main_session_meta); session.addWidget(self.main_session_elapsed); session.addWidget(self.main_session_stats)
        recent_title = QLabel("Последние донаты"); recent_title.setStyleSheet("font-weight:750;margin-top:5px"); session.addWidget(recent_title)
        self.recent_donation_frames = []
        self.recent_donation_main_labels = []
        self.recent_donation_sub_labels = []
        for rank in range(3):
            frame = QFrame(); frame.setObjectName("RecentDonation"); frame.setProperty("rank", str(rank)); frame.setVisible(False)
            fl = QVBoxLayout(frame); fl.setContentsMargins(11,8,11,8); fl.setSpacing(2)
            main = QLabel("—"); main.setObjectName("RecentDonationMain")
            sub = QLabel(""); sub.setObjectName("RecentDonationSub"); sub.setWordWrap(True)
            fl.addWidget(main); fl.addWidget(sub)
            session.addWidget(frame)
            self.recent_donation_frames.append(frame); self.recent_donation_main_labels.append(main); self.recent_donation_sub_labels.append(sub)
        self.no_recent_donations = QLabel("Пока в этой сессии нет донатов."); self.no_recent_donations.setObjectName("Muted"); self.no_recent_donations.setWordWrap(True); session.addWidget(self.no_recent_donations)
        session.addStretch()

        # Rate card
        self.rate_card = self._card("purple"); rate = QVBoxLayout(self.rate_card); rate.setContentsMargins(22,20,22,20); rate.setSpacing(13)
        title = QLabel("Текущая ставка"); title.setObjectName("SectionTitle"); rate.addWidget(title)
        hint = QLabel("Меняется прямо во время стрима и применяется только к следующим донатам."); hint.setObjectName("Muted"); hint.setWordWrap(True); rate.addWidget(hint)
        self.rate_grid = QGridLayout(); self.rate_grid.setHorizontalSpacing(10); self.rate_grid.setVerticalSpacing(10)
        self.rate_amount = QDoubleSpinBox(); self.rate_amount.setRange(1,1_000_000); self.rate_amount.setDecimals(2); self.rate_amount.setSuffix(" ₽"); self.rate_amount.setMinimumWidth(145)
        self.rate_eq = QLabel("="); self.rate_eq.setStyleSheet("font-size:22px;font-weight:800")
        self.rate_minutes = QSpinBox(); self.rate_minutes.setRange(0,1440); self.rate_minutes.setSuffix(" мин")
        self.rate_seconds = QSpinBox(); self.rate_seconds.setRange(0,59); self.rate_seconds.setSuffix(" сек")
        self.apply_rate_btn = QPushButton("Применить ставку"); self.apply_rate_btn.setObjectName("Primary"); self.apply_rate_btn.clicked.connect(self._apply_rate)
        rate.addLayout(self.rate_grid)
        self.presets_grid = QGridLayout(); self.presets_grid.setHorizontalSpacing(10); self.presets_grid.setVerticalSpacing(8)
        self.preset_label = QLabel("Быстро:"); self.preset_buttons = []
        for minutes in (1,3,5,10):
            btn=QPushButton(f"100 ₽ = {minutes} мин"); btn.setObjectName("Chip"); btn.clicked.connect(lambda checked=False,m=minutes:self._preset(m)); self.preset_buttons.append(btn)
        rate.addLayout(self.presets_grid); rate.addStretch()

        # Responsive dashboard layout is filled by _arrange_wide/_arrange_compact.
        layout.addLayout(self.home_top_grid)

        # Time controls
        self.controls_card = self._card("purple"); controls = QVBoxLayout(self.controls_card); controls.setContentsMargins(22,20,22,20); controls.setSpacing(12)
        ct = QLabel("Управление временем"); ct.setObjectName("SectionTitle"); controls.addWidget(ct)
        self.adjustments_grid = QGridLayout(); self.adjustments_grid.setHorizontalSpacing(10); self.adjustments_grid.setVerticalSpacing(10)
        self.adjustment_buttons=[]
        for label, seconds in (("−30 мин",-1800),("−5 мин",-300),("−1 мин",-60),("+1 мин",60),("+5 мин",300),("+30 мин",1800)):
            btn=QPushButton(label); btn.clicked.connect(lambda checked=False,s=seconds,l=label:self._manual_adjust(s,l)); self.adjustment_buttons.append(btn)
        controls.addLayout(self.adjustments_grid)
        self.control_grid=QGridLayout(); self.control_grid.setHorizontalSpacing(10); self.control_grid.setVerticalSpacing(10)
        self.pause_btn=QPushButton("Пауза"); self.pause_btn.setObjectName("Primary"); self.pause_btn.clicked.connect(self._toggle)
        exact_btn=QPushButton("Точное время"); exact_btn.clicked.connect(self._exact_time)
        self.undo_btn=QPushButton("Отменить начисление…"); self.undo_btn.clicked.connect(self._choose_undo_event)
        reset_btn=QPushButton("Сбросить"); reset_btn.setObjectName("Danger"); reset_btn.clicked.connect(self._reset)
        self.exact_btn=exact_btn; self.reset_btn=reset_btn
        controls.addLayout(self.control_grid); layout.addWidget(self.controls_card)

        self.home_bottom_grid=QGridLayout(); self.home_bottom_grid.setHorizontalSpacing(16); self.home_bottom_grid.setVerticalSpacing(12)
        self.last_card=self._card("cyan"); last_l=QVBoxLayout(self.last_card); last_l.setContentsMargins(20,18,20,18)
        lt=QLabel("Последняя активность"); lt.setObjectName("SectionTitle"); last_l.addWidget(lt)
        self.last_event_label=QLabel("Пока нет событий"); self.last_event_label.setObjectName("Muted"); self.last_event_label.setWordWrap(True); last_l.addWidget(self.last_event_label)
        go_history=QPushButton("Открыть историю"); go_history.clicked.connect(lambda:self._switch_page(self.PAGE_HISTORY)); last_l.addWidget(go_history)

        self.quick_overlay_card=self._card("orange"); qo=QVBoxLayout(self.quick_overlay_card); qo.setContentsMargins(20,18,20,18)
        qt=QLabel("Выбранный оверлей —"); qt.setObjectName("SectionTitle"); qo.addWidget(qt)
        self.home_overlay_theme=QLabel("Классический")
        self.home_overlay_theme.setAlignment(Qt.AlignCenter)
        self.home_overlay_theme.setStyleSheet("font-size:21px;font-weight:800;padding:8px 6px 10px;")
        qo.addWidget(self.home_overlay_theme)
        qdesc=QLabel("Оформление отделено от боевого управления, чтобы на стриме ничего не мешало."); qdesc.setObjectName("Muted"); qdesc.setWordWrap(True); qo.addWidget(qdesc)
        go_overlay=QPushButton("Настроить оформление"); go_overlay.setObjectName("OrangePrimary"); go_overlay.clicked.connect(lambda:self._switch_page(self.PAGE_OVERLAY)); qo.addWidget(go_overlay)
        self.home_bottom_grid.addWidget(self.last_card,0,0); self.home_bottom_grid.addWidget(self.quick_overlay_card,0,1); self.home_bottom_grid.setColumnStretch(0,1); self.home_bottom_grid.setColumnStretch(1,1)
        layout.addLayout(self.home_bottom_grid); layout.addStretch()

    def _build_overlay_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        setup = self._card("orange"); sl=QVBoxLayout(setup); sl.setContentsMargins(22,20,22,20); sl.setSpacing(12)
        title=QLabel("Текст и элементы"); title.setObjectName("SectionTitle"); sl.addWidget(title)
        hint=QLabel("Верхняя надпись, строка ставки и индикатор паузы используют оформление выбранной темы. Текст можно менять независимо от стиля.")
        hint.setObjectName("Muted"); hint.setWordWrap(True); sl.addWidget(hint)
        sl.addWidget(QLabel("Текст над таймером"))
        self.overlay_title_edit=QLineEdit(); self.overlay_title_edit.setPlaceholderText("Например: ДОНАТОФОН — НЕ СПЛЮ ПОКА ЕСТЬ ВРЕМЯ"); self.overlay_title_edit.setClearButtonEnabled(True); sl.addWidget(self.overlay_title_edit)
        self.overlay_show_rate=QCheckBox("Показывать строку со ставкой под таймером"); self.overlay_show_rate.setChecked(True); sl.addWidget(self.overlay_show_rate)
        elements_apply_row=QHBoxLayout(); elements_note=QLabel("Можно изменить текст и видимость ставки, не пролистывая страницу к списку тем.")
        elements_note.setObjectName("Muted"); elements_note.setWordWrap(True); elements_apply_row.addWidget(elements_note,1)
        self.apply_elements_btn=QPushButton("Применить текст и элементы"); self.apply_elements_btn.setObjectName("OrangePrimary"); self.apply_elements_btn.clicked.connect(self._apply_overlay_elements)
        elements_apply_row.addWidget(self.apply_elements_btn); sl.addLayout(elements_apply_row)
        layout.addWidget(setup)

        themes = self._card("orange"); tl=QVBoxLayout(themes); tl.setContentsMargins(22,20,22,20); tl.setSpacing(12)
        tt=QLabel("Стиль таймера"); tt.setObjectName("SectionTitle"); tl.addWidget(tt)
        desc=QLabel("Нажми на нужный стиль — справа от выбранной карточки появится кнопка «Применить». Больше не нужно листать к общей кнопке внизу.")
        desc.setObjectName("Muted"); desc.setWordWrap(True); tl.addWidget(desc)
        self.theme_grid=QGridLayout(); self.theme_grid.setHorizontalSpacing(10); self.theme_grid.setVerticalSpacing(10)
        self.theme_group=QButtonGroup(self); self.theme_group.setExclusive(True)
        for name,key,subtitle in THEMES:
            item=QFrame(); item.setObjectName("ThemeItem")
            row=QHBoxLayout(item); row.setContentsMargins(0,0,0,0); row.setSpacing(10)
            btn=QPushButton(f"{name}\n12:34:56   ·   {subtitle}"); btn.setObjectName("ThemeCard"); btn.setCheckable(True); btn.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
            btn.clicked.connect(lambda checked=False,k=key:self._select_theme(k)); self.theme_group.addButton(btn); self.theme_buttons[key]=btn
            apply_btn=QPushButton("Применить"); apply_btn.setObjectName("ThemeApply"); apply_btn.setVisible(False)
            apply_btn.clicked.connect(lambda checked=False,k=key:self._apply_theme(k))
            row.addWidget(btn,1); row.addWidget(apply_btn)
            self.theme_widgets[key]=item; self.theme_apply_buttons[key]=apply_btn
        tl.addLayout(self.theme_grid)
        note=QLabel("Выбранная тема применяется в OBS сразу после нажатия кнопки рядом с ней, без перезапуска Browser Source.")
        note.setObjectName("Muted"); note.setWordWrap(True); tl.addWidget(note)
        layout.addWidget(themes)

        source = self._card("cyan"); ol=QVBoxLayout(source); ol.setContentsMargins(22,20,22,20); ol.setSpacing(10)
        ot=QLabel("OBS Browser Source"); ot.setObjectName("SectionTitle"); ol.addWidget(ot)
        visibility_row=QHBoxLayout(); visibility_row.setSpacing(10)
        self.overlay_timer_status=QLabel("Таймер в OBS скрыт"); self.overlay_timer_status.setObjectName("Muted"); visibility_row.addWidget(self.overlay_timer_status,1)
        self.overlay_timer_toggle=QPushButton("Показать таймер"); self.overlay_timer_toggle.setObjectName("OBSActionTimer"); self.overlay_timer_toggle.setCheckable(True); self.overlay_timer_toggle.toggled.connect(self._overlay_timer_visibility_changed); visibility_row.addWidget(self.overlay_timer_toggle)
        ol.addLayout(visibility_row)
        self.overlay_url_label=QLabel(OVERLAY_URL); self.overlay_url_label.setObjectName("Muted"); self.overlay_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse); self.overlay_url_label.setWordWrap(True); ol.addWidget(self.overlay_url_label)
        row=QHBoxLayout(); copy=QPushButton("Копировать ссылку"); copy.clicked.connect(self._copy_overlay); open_btn=QPushButton("Открыть превью"); open_btn.clicked.connect(lambda:webbrowser.open(OVERLAY_URL)); obs_help=QPushButton("Как добавить в OBS?"); obs_help.clicked.connect(lambda:self._switch_page(self.PAGE_GUIDE)); row.addWidget(copy); row.addWidget(open_btn); row.addWidget(obs_help); row.addStretch(); ol.addLayout(row)
        layout.addWidget(source); layout.addStretch()

    def _build_history_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)
        card=self._card("blue"); history=QVBoxLayout(card); history.setContentsMargins(22,20,22,20); history.setSpacing(10)
        hh=QHBoxLayout(); title=QLabel("История событий"); title.setObjectName("SectionTitle"); hh.addWidget(title); hh.addStretch()
        self.history_scope_label=QLabel("Последние события"); self.history_scope_label.setObjectName("Muted"); hh.addWidget(self.history_scope_label); history.addLayout(hh)
        info=QLabel("Здесь остаются донаты, изменения ставки, ручные корректировки времени, паузы, оформление и операции с сессиями."); info.setObjectName("Muted"); info.setWordWrap(True); history.addWidget(info)
        self.history_table=QTableWidget(0,4); self.history_table.setHorizontalHeaderLabels(["Время","Тип","Событие","Изменение"])
        self.history_table.verticalHeader().setVisible(False); self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.history_table.setSelectionMode(QAbstractItemView.NoSelection); self.history_table.setAlternatingRowColors(True); self.history_table.setMinimumHeight(390)
        self.history_table.setSortingEnabled(True)
        header=self.history_table.horizontalHeader(); header.setSectionsClickable(True); header.setSortIndicatorShown(True); header.setSortIndicator(0, Qt.DescendingOrder)
        header.setSectionResizeMode(0,QHeaderView.ResizeToContents); header.setSectionResizeMode(1,QHeaderView.ResizeToContents); header.setSectionResizeMode(2,QHeaderView.Stretch); header.setSectionResizeMode(3,QHeaderView.ResizeToContents)
        history.addWidget(self.history_table)
        row=QHBoxLayout(); self.history_undo_btn=QPushButton("Отменить начисление…"); self.history_undo_btn.clicked.connect(self._choose_undo_event); row.addWidget(self.history_undo_btn); row.addStretch(); history.addLayout(row)
        layout.addWidget(card); layout.addStretch()

    def _build_donations_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        filters = self._card("gold"); fl = QVBoxLayout(filters); fl.setContentsMargins(22,20,22,20); fl.setSpacing(10)
        ft = QLabel("Период и статистика"); ft.setObjectName("SectionTitle"); fl.addWidget(ft)
        hint = QLabel("Здесь собраны все донаты текущего профиля — и внутри сессий, и вне донатофона. Выбери период для сравнения.")
        hint.setObjectName("Muted"); hint.setWordWrap(True); fl.addWidget(hint)
        filter_grid = QGridLayout(); filter_grid.setHorizontalSpacing(10); filter_grid.setVerticalSpacing(8)
        self.donation_period_combo = QComboBox()
        self.donation_period_combo.addItems(["За всё время", "Сегодня", "Последние 7 дней", "Последние 30 дней", "Свой период"])
        self.donation_period_combo.currentIndexChanged.connect(self._donation_period_changed)
        filter_grid.addWidget(QLabel("Период:"),0,0); filter_grid.addWidget(self.donation_period_combo,0,1)
        self.refresh_donations_btn = QPushButton("Обновить"); self.refresh_donations_btn.clicked.connect(lambda: self._refresh_donations(force=True)); filter_grid.addWidget(self.refresh_donations_btn,0,2)
        filter_grid.setColumnStretch(1,1); fl.addLayout(filter_grid)

        # Custom dates only exist visually when they are actually used.
        self.donation_custom_widget=QWidget(); custom=QHBoxLayout(self.donation_custom_widget); custom.setContentsMargins(0,0,0,0); custom.setSpacing(8)
        self.donation_from = QDateTimeEdit(); self.donation_from.setCalendarPopup(True); self.donation_from.setDisplayFormat("dd.MM.yyyy HH:mm")
        self.donation_to = QDateTimeEdit(); self.donation_to.setCalendarPopup(True); self.donation_to.setDisplayFormat("dd.MM.yyyy HH:mm")
        now = dt.datetime.now(); start = now - dt.timedelta(days=7)
        self.donation_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(start.timestamp())))
        self.donation_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(now.timestamp())))
        self.donation_from.dateTimeChanged.connect(lambda _v: self._custom_period_changed())
        self.donation_to.dateTimeChanged.connect(lambda _v: self._custom_period_changed())
        custom.addWidget(QLabel("С:")); custom.addWidget(self.donation_from,1); custom.addWidget(QLabel("По:")); custom.addWidget(self.donation_to,1)
        fl.addWidget(self.donation_custom_widget)

        self.donation_metrics = QGridLayout(); self.donation_metrics.setHorizontalSpacing(10); self.donation_metrics.setVerticalSpacing(10)
        self.metric_labels = {}
        metric_defs = [
            ("all_total", "За всё время"),
            ("period_total", "За выбранный период"),
            ("period_count", "Донатов за период"),
            ("period_avg", "Средний донат"),
            ("period_top", "Топ донатер периода"),
            ("period_time", "Добавлено времени"),
        ]
        for i,(key,label) in enumerate(metric_defs):
            card = QFrame(); card.setObjectName("MetricCard")
            cl = QVBoxLayout(card); cl.setContentsMargins(14,12,14,12); cl.setSpacing(3)
            val = QLabel("—"); val.setObjectName("MetricBig"); val.setWordWrap(True)
            cap = QLabel(label); cap.setObjectName("MetricSmall"); cap.setWordWrap(True)
            cl.addWidget(val); cl.addWidget(cap)
            self.metric_labels[key] = val
            r,c = divmod(i,3); self.donation_metrics.addWidget(card,r,c); self.donation_metrics.setColumnStretch(c,1)
        fl.addLayout(self.donation_metrics); layout.addWidget(filters)

        card = self._card("cyan"); dl = QVBoxLayout(card); dl.setContentsMargins(22,20,22,20); dl.setSpacing(10)
        dh = QHBoxLayout(); title = QLabel("Все донаты"); title.setObjectName("SectionTitle"); dh.addWidget(title); dh.addStretch()
        self.donation_search = QLineEdit(); self.donation_search.setPlaceholderText("Поиск по донатеру…"); self.donation_search.setClearButtonEnabled(True); self.donation_search.textChanged.connect(self._filter_donation_rows); dh.addWidget(self.donation_search)
        dl.addLayout(dh)
        note = QLabel("Сессия показывает, в рамках какого донатофона пришёл донат. Если донат был вне активной сессии или во время её паузы — стоит прочерк. Нажми на любой донат, чтобы открыть карточку донатера и все его донаты.")
        note.setObjectName("Muted"); note.setWordWrap(True); dl.addWidget(note)
        self.donations_table = QTableWidget(0,6)
        self.donations_table.setHorizontalHeaderLabels(["Время", "Донатер", "Сумма", "Сессия", "Добавлено времени", "Статус"])
        self.donations_table.verticalHeader().setVisible(False); self.donations_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.donations_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.donations_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.donations_table.setAlternatingRowColors(True); self.donations_table.setMinimumHeight(400); self.donations_table.setSortingEnabled(True)
        h = self.donations_table.horizontalHeader(); h.setSectionsClickable(True); h.setSortIndicatorShown(True); h.setSortIndicator(0, Qt.DescendingOrder)
        h.setSectionResizeMode(0,QHeaderView.ResizeToContents); h.setSectionResizeMode(1,QHeaderView.Stretch); h.setSectionResizeMode(2,QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3,QHeaderView.Stretch); h.setSectionResizeMode(4,QHeaderView.ResizeToContents); h.setSectionResizeMode(5,QHeaderView.ResizeToContents)
        self.donations_table.cellClicked.connect(self._show_donor_details_from_row)
        dl.addWidget(self.donations_table); layout.addWidget(card); layout.addStretch()
        self._update_donation_filter_visibility()

    def _build_analysis_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        # One compact filter controls all analysis blocks below. Irrelevant
        # fields are hidden instead of occupying space.
        control=self._card("purple"); cl=QVBoxLayout(control); cl.setContentsMargins(20,16,20,16); cl.setSpacing(9)
        head=QHBoxLayout(); title=QLabel("Что показать"); title.setObjectName("SectionTitle"); head.addWidget(title); head.addStretch()
        refresh=QPushButton("Обновить"); refresh.setObjectName("Primary"); refresh.clicked.connect(lambda:self._refresh_analysis(force=True)); head.addWidget(refresh); cl.addLayout(head)
        hint=QLabel("Выбери один промежуток — все графики ниже обновятся одновременно."); hint.setObjectName("Muted"); hint.setWordWrap(True); cl.addWidget(hint)
        row=QHBoxLayout(); row.setSpacing(10)
        self.analysis_scope_combo=QComboBox(); self.analysis_scope_combo.addItems(["Период времени","Конкретная сессия"]); self.analysis_scope_combo.currentIndexChanged.connect(self._analysis_scope_changed)
        self.analysis_period_label=QLabel("Период:"); self.analysis_period_combo=QComboBox(); self.analysis_period_combo.addItems(["Сегодня","Последние 7 дней","Последние 30 дней","За всё время","Свой период"]); self.analysis_period_combo.currentIndexChanged.connect(self._analysis_period_changed)
        self.analysis_session_label=QLabel("Сессия:"); self.analysis_session_combo=QComboBox(); self.analysis_session_combo.activated.connect(lambda _i:self._analysis_session_changed(self.analysis_session_combo))
        row.addWidget(QLabel("Смотреть:")); row.addWidget(self.analysis_scope_combo); row.addSpacing(8); row.addWidget(self.analysis_period_label); row.addWidget(self.analysis_period_combo,1); row.addWidget(self.analysis_session_label); row.addWidget(self.analysis_session_combo,2); cl.addLayout(row)
        now=dt.datetime.now(); start=now-dt.timedelta(days=7)
        self.analysis_custom_widget=QWidget(); custom=QHBoxLayout(self.analysis_custom_widget); custom.setContentsMargins(0,0,0,0); custom.setSpacing(8)
        self.analysis_from=QDateTimeEdit(); self.analysis_from.setCalendarPopup(True); self.analysis_from.setDisplayFormat("dd.MM.yyyy HH:mm"); self.analysis_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(start.timestamp())))
        self.analysis_to=QDateTimeEdit(); self.analysis_to.setCalendarPopup(True); self.analysis_to.setDisplayFormat("dd.MM.yyyy HH:mm"); self.analysis_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(now.timestamp())))
        self.analysis_from.dateTimeChanged.connect(lambda _v:self._analysis_custom_period_changed()); self.analysis_to.dateTimeChanged.connect(lambda _v:self._analysis_custom_period_changed())
        custom.addWidget(QLabel("С:")); custom.addWidget(self.analysis_from,1); custom.addWidget(QLabel("По:")); custom.addWidget(self.analysis_to,1); cl.addWidget(self.analysis_custom_widget)
        self.analysis_context_label=QLabel("—"); self.analysis_context_label.setObjectName("Muted"); self.analysis_context_label.setWordWrap(True); cl.addWidget(self.analysis_context_label)
        layout.addWidget(control)

        self.analysis_section_metrics={}
        def metric_strip(parent_layout, section: str):
            grid=QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8); labels=[]
            for i in range(4):
                box=QFrame(); box.setObjectName("MetricCard"); bl=QVBoxLayout(box); bl.setContentsMargins(12,9,12,9); bl.setSpacing(2)
                value=QLabel("—"); value.setObjectName("MetricBig"); cap=QLabel("—"); cap.setObjectName("MetricSmall"); cap.setWordWrap(True); bl.addWidget(value); bl.addWidget(cap); grid.addWidget(box,0,i); grid.setColumnStretch(i,1); labels.append((value,cap))
            self.analysis_section_metrics[section]=labels; parent_layout.addLayout(grid)

        def add_timeline(parent_layout, widget: StreamAnalyticsTimeline):
            parent_layout.addWidget(widget)
            controls=QHBoxLayout(); controls.setSpacing(7)
            hint=QLabel("Колёсико листает страницу. Ctrl + колёсико или кнопки +/− меняют масштаб. Увеличенный график можно двигать левой кнопкой мыши.")
            hint.setObjectName("Muted"); hint.setWordWrap(True); controls.addWidget(hint,1)
            minus=QPushButton("−"); minus.setToolTip("Отдалить"); minus.clicked.connect(widget.zoom_out)
            reset=QPushButton("100%"); reset.setToolTip("Показать весь выбранный период"); reset.clicked.connect(widget.reset_zoom)
            plus=QPushButton("+"); plus.setToolTip("Приблизить"); plus.clicked.connect(widget.zoom_in)
            maximum=QPushButton("Макс."); maximum.setToolTip("Максимальное приближение вокруг текущего центра"); maximum.clicked.connect(widget.zoom_max)
            zoom_label=QLabel("100%"); zoom_label.setObjectName("Muted"); zoom_label.setMinimumWidth(68); zoom_label.setAlignment(Qt.AlignCenter)
            widget.set_zoom_callback(lambda value, label=zoom_label: label.setText(str(value)))
            for button in (minus,reset,plus,maximum): controls.addWidget(button)
            controls.addWidget(zoom_label)
            parent_layout.addLayout(controls)

        donations=self._card("gold"); dl=QVBoxLayout(donations); dl.setContentsMargins(20,17,20,17); dl.setSpacing(9)
        dtl=QLabel("Донаты"); dtl.setObjectName("SectionTitle"); dl.addWidget(dtl); metric_strip(dl,"donations")
        self.analysis_donation_timeline=StreamAnalyticsTimeline(); self.analysis_donation_timeline.set_mode(self.ui_theme); add_timeline(dl,self.analysis_donation_timeline); layout.addWidget(donations)

        viewers=self._card("cyan"); vl=QVBoxLayout(viewers); vl.setContentsMargins(20,17,20,17); vl.setSpacing(9)
        vtl=QLabel("Онлайн зрителей"); vtl.setObjectName("SectionTitle"); vl.addWidget(vtl); metric_strip(vl,"viewers")
        self.analysis_viewer_timeline=StreamAnalyticsTimeline(); self.analysis_viewer_timeline.set_mode(self.ui_theme); add_timeline(vl,self.analysis_viewer_timeline); layout.addWidget(viewers)

        chat_card=self._card("magenta"); chl=QVBoxLayout(chat_card); chl.setContentsMargins(20,17,20,17); chl.setSpacing(9)
        cht=QLabel("Чат Twitch"); cht.setObjectName("SectionTitle"); chl.addWidget(cht); metric_strip(chl,"chat")
        self.analysis_chat_timeline=StreamAnalyticsTimeline(); self.analysis_chat_timeline.set_mode(self.ui_theme); add_timeline(chl,self.analysis_chat_timeline)
        cloud_title=QLabel("О чём чаще всего пишет чат"); cloud_title.setStyleSheet("font-size:16px;font-weight:750;margin-top:5px"); chl.addWidget(cloud_title)
        cloud_hint=QLabel("Часто повторяемые слова показаны крупнее. Например, «игра» будет больше, если зрители пишут её чаще."); cloud_hint.setObjectName("Muted"); cloud_hint.setWordWrap(True); chl.addWidget(cloud_hint)
        self.analysis_chat_cloud=WordCloudWidget(); self.analysis_chat_cloud.set_mode(self.ui_theme); chl.addWidget(self.analysis_chat_cloud); layout.addWidget(chat_card)

        speech_card=self._card("orange"); stl=QVBoxLayout(speech_card); stl.setContentsMargins(20,17,20,17); stl.setSpacing(9)
        sht=QLabel("Речь стримера"); sht.setObjectName("SectionTitle"); stl.addWidget(sht); metric_strip(stl,"speech")
        self.analysis_speech_timeline=StreamAnalyticsTimeline(); self.analysis_speech_timeline.set_mode(self.ui_theme); add_timeline(stl,self.analysis_speech_timeline)
        sc_title=QLabel("Частые слова стримера"); sc_title.setStyleSheet("font-size:16px;font-weight:750;margin-top:5px"); stl.addWidget(sc_title)
        self.analysis_speech_cloud=WordCloudWidget(); self.analysis_speech_cloud.set_mode(self.ui_theme); self.analysis_speech_cloud.set_empty_message("Распознанных слов пока нет. Запиши голос во время сессии, затем запусти распознавание ниже."); stl.addWidget(self.analysis_speech_cloud); layout.addWidget(speech_card)

        speech=self._card("teal"); spl=QVBoxLayout(speech); spl.setContentsMargins(20,17,20,17); spl.setSpacing(9)
        setup_title=QLabel("Настройка анализа речи"); setup_title.setObjectName("SectionTitle"); spl.addWidget(setup_title)
        desc=QLabel("Twitch и трансляция OBS не нужны. Включи запись голоса ДО начала сессии, поговори в выбранный микрофон, заверши сессию и нажми «Распознать». Первый запуск может скачать модель речи из интернета."); desc.setObjectName("Muted"); desc.setWordWrap(True); spl.addWidget(desc)
        self.speech_status_label=QLabel("—"); self.speech_status_label.setObjectName("Muted"); self.speech_status_label.setWordWrap(True); spl.addWidget(self.speech_status_label)
        self.speech_progress_bar=QProgressBar(); self.speech_progress_bar.setRange(0,100); self.speech_progress_bar.setValue(0); self.speech_progress_bar.setFormat("0%"); self.speech_progress_bar.hide(); spl.addWidget(self.speech_progress_bar)
        self.speech_recording_info=QLabel("Выбери сессию, чтобы проверить запись голоса."); self.speech_recording_info.setObjectName("Muted"); self.speech_recording_info.setWordWrap(True); spl.addWidget(self.speech_recording_info)
        speech_grid=QGridLayout(); speech_grid.setHorizontalSpacing(10); speech_grid.setVerticalSpacing(8)
        self.speech_enabled=QCheckBox("Сохранять голос для анализа во время активной сессии"); self.speech_enabled.setChecked(self.speech_service.enabled()); self.speech_enabled.toggled.connect(self._speech_enabled_changed)
        self.speech_delete_audio=QCheckBox("Удалять временную аудиозапись после успешной расшифровки"); self.speech_delete_audio.setChecked(self.speech_service.delete_audio_after_transcription()); self.speech_delete_audio.toggled.connect(self.speech_service.set_delete_audio_after_transcription)
        self.speech_device_combo=QComboBox(); self.speech_device_combo.currentIndexChanged.connect(self._speech_device_changed); self.speech_model_combo=QComboBox(); self.speech_model_combo.addItem("Быстро", "tiny"); self.speech_model_combo.addItem("Сбалансировано", "base"); self.speech_model_combo.addItem("Точнее", "small")
        current_model=self.speech_service.model_name()
        for i in range(self.speech_model_combo.count()):
            if self.speech_model_combo.itemData(i)==current_model: self.speech_model_combo.setCurrentIndex(i); break
        self.speech_model_combo.currentIndexChanged.connect(self._speech_model_changed)
        reload_devices=QPushButton("Обновить список микрофонов"); reload_devices.clicked.connect(self._refresh_speech_devices)
        self.transcribe_btn=QPushButton("Распознать речь выбранной сессии"); self.transcribe_btn.setObjectName("Primary"); self.transcribe_btn.clicked.connect(self._transcribe_selected_session)
        speech_grid.addWidget(self.speech_enabled,0,0,1,2); speech_grid.addWidget(self.speech_delete_audio,1,0,1,2); speech_grid.addWidget(QLabel("Микрофон:"),2,0); speech_grid.addWidget(self.speech_device_combo,2,1)
        speech_grid.addWidget(QLabel("Точность:"),3,0); speech_grid.addWidget(self.speech_model_combo,3,1); speech_grid.addWidget(reload_devices,4,1); speech_grid.setColumnStretch(1,1); spl.addLayout(speech_grid)
        transcribe_row=QHBoxLayout(); transcribe_row.setSpacing(8)
        self.speech_session_combo=QComboBox(); self.speech_session_combo.setMinimumWidth(200)
        self.speech_session_combo.setToolTip("Выбери сессию — графики выше обновятся автоматически. Колесо мыши не меняет выбор.")
        self.speech_session_combo.activated.connect(lambda _i:self._analysis_session_changed(self.speech_session_combo))
        transcribe_row.addWidget(QLabel("Сессия:")); transcribe_row.addWidget(self.speech_session_combo,2)
        transcribe_row.addWidget(self.transcribe_btn,2); spl.addLayout(transcribe_row)
        help_row=QHBoxLayout(); install_hint=QLabel("Компонент распознавания ставится прямо из приложения. В установочной версии компонент скачивается и устанавливается по кнопке. Для него нужен интернет. Первая модель речи загрузится отдельно при распознавании."); install_hint.setObjectName("Muted"); install_hint.setWordWrap(True); help_row.addWidget(install_hint,1)
        self.install_speech_btn=QPushButton("Установить анализ речи"); self.install_speech_btn.clicked.connect(self._install_speech_ai); help_row.addWidget(self.install_speech_btn)
        guide_btn=QPushButton("Показать инструкцию"); guide_btn.clicked.connect(lambda:self._switch_page(self.PAGE_GUIDE)); help_row.addWidget(guide_btn); spl.addLayout(help_row); layout.addWidget(speech)
        layout.addStretch()
        self._refresh_speech_devices(); self._populate_analysis_sessions(); self._analysis_scope_changed(); self._clear_analysis_sections("Выбери период или сессию — графики загрузятся, когда откроешь Анализ.")

    def _build_guide_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        intro=self._card("teal"); il=QVBoxLayout(intro); il.setContentsMargins(22,20,22,20); il.setSpacing(9)
        title=QLabel("Настройка Donathon Timer"); title.setObjectName("SectionTitle"); il.addWidget(title)
        text=QLabel("Пройди шаги сверху вниз. Для первого запуска достаточно подключить DonationAlerts и добавить таймер в OBS. Twitch и анализ речи можно настроить позже.")
        text.setObjectName("Muted"); text.setWordWrap(True); il.addWidget(text)
        quick=QHBoxLayout(); go_accounts=QPushButton("Открыть Аккаунты"); go_accounts.setObjectName("Primary"); go_accounts.clicked.connect(lambda:self._switch_page(self.PAGE_ACCOUNTS)); go_overlay=QPushButton("Открыть Оверлей"); go_overlay.clicked.connect(lambda:self._switch_page(self.PAGE_OVERLAY)); quick.addWidget(go_accounts); quick.addWidget(go_overlay); quick.addStretch(); il.addLayout(quick); layout.addWidget(intro)

        def add_step(accent,title_text,body,buttons):
            card=self._card(accent); cl=QVBoxLayout(card); cl.setContentsMargins(22,18,22,18); cl.setSpacing(8)
            h=QLabel(title_text); h.setObjectName("SectionTitle"); cl.addWidget(h)
            b=QLabel(body); b.setObjectName("Muted"); b.setWordWrap(True); b.setTextInteractionFlags(Qt.TextSelectableByMouse); cl.addWidget(b)
            if buttons:
                row=QHBoxLayout(); row.setSpacing(8)
                for label,action,primary in buttons:
                    btn=QPushButton(label); btn.setObjectName("Primary" if primary else ""); btn.clicked.connect(action); row.addWidget(btn)
                row.addStretch(); cl.addLayout(row)
            layout.addWidget(card)

        add_step("purple","1 · Подключи DonationAlerts",
            "1) Открой страницу приложений DonationAlerts и нажми «Create New App».\n"
            f"2) В Redirect URI вставь точно: {DONATIONALERTS_REDIRECT_URI}\n"
            "3) Сохрани приложение. Число в колонке App ID — это нужный нам Client ID.\n"
            "4) Вернись в Donathon Timer → Аккаунты → «Ввести Client ID», вставь App ID и нажми «Подключить DonationAlerts».\n"
            "5) Разреши доступ в открывшемся браузере. После этого на Главной статус DonationAlerts станет зелёным.",
            [("Открыть приложения DonationAlerts",lambda:webbrowser.open("https://www.donationalerts.com/application/clients"),True),("Официальная справка API",lambda:webbrowser.open("https://www.donationalerts.com/apidoc"),False)])

        add_step("cyan","2 · Добавь таймер в OBS",
            "1) В OBS открой Источники → + → Браузер.\n"
            f"2) Вставь адрес: {OVERLAY_URL}\n"
            "3) Поставь размер 1920 × 1080.\n"
            "4) Обычный виджет DonationAlerts с твоими звуками и анимациями оставь как есть — Donathon Timer работает отдельным источником.\n"
            "5) Вернись на Главную: строка OBS станет зелёной, когда источник действительно откроет оверлей.",
            [("Копировать ссылку",self._copy_overlay,True),("Открыть справку OBS",lambda:webbrowser.open("https://obsproject.com/kb/browser-source"),False),("Открыть превью",lambda:webbrowser.open(OVERLAY_URL),False)])

        add_step("orange","3 · Настрой донатофон",
            "На Главной задай ставку, например 100 ₽ = 5 минут. Во вкладке «Оверлей» выбери внешний вид, напиши текст над таймером и нажми «Применить». Новая ставка действует только на следующие донаты. Уже добавленное время не пересчитывается.",
            [("На Главную",lambda:self._switch_page(self.PAGE_HOME),True),("Настроить оверлей",lambda:self._switch_page(self.PAGE_OVERLAY),False)])

        add_step("blue","4 · Используй сессии",
            "Сессия отделяет один донатофон от другого. Запусти её с Главной, дай понятное название и после стрима нажми «Завершить». Сумма донатов, добавленное время и топ донатеров останутся в архиве сессий. При необходимости сессию можно поставить на паузу.",
            [("Открыть Сессии",lambda:self._switch_page(self.PAGE_SESSIONS),True)])

        add_step("magenta","5 · Подключи Twitch для онлайна и чата",
            "1) Открой Twitch Developer Console и зарегистрируй приложение. Если Twitch попросит Redirect URL, укажи http://localhost:3000.\n"
            "2) Открой созданное приложение и скопируй Client ID. Секретный ключ в Donathon Timer вводить не нужно.\n"
            "3) Donathon Timer → Аккаунты → «Ввести Twitch Client ID».\n"
            "4) Нажми «Подключить Twitch». Браузер откроет страницу Twitch; введи код, который покажет Donathon Timer, и разреши доступ.\n"
            "5) После подключения приложение начнёт собирать онлайн и новые сообщения чата для будущего анализа.",
            [("Открыть Twitch Developer Console",lambda:webbrowser.open("https://dev.twitch.tv/console/apps"),True),("Официальная инструкция Twitch",lambda:webbrowser.open("https://dev.twitch.tv/docs/authentication/register-app"),False)])

        add_step("gold","6 · Пользуйся Анализом",
            "Во вкладке «Анализ» выбери один период или конкретную сессию. Ниже сразу видны четыре независимых блока: донаты, онлайн, чат и речь стримера. Наводи курсор на точки и столбцы графиков — появятся детали выбранного момента. В облаке слов крупнее показано то, что чат или стример повторяли чаще.",
            [("Открыть Анализ",lambda:self._switch_page(self.PAGE_ANALYSIS),True)])


        add_step("purple","7 · Рулетки и голосования",
            "Открой «Развлечения». Там есть четыре режима: обычная рулетка, розыгрыш по слову из Twitch-чата, донат-рулетка с шансом по сумме и голосование из чата.\n"
            "Рулетки и голосование по умолчанию скрыты в OBS. Выбери нужный режим, настрой его и рядом с колесом нажми «Показать рулетку» или «Показать голосование». Там же можно отдельно показать или скрыть основной таймер. Дополнительный источник OBS создавать не нужно.",
            [("Открыть Развлечения",lambda:self._switch_page(self.PAGE_ENTERTAINMENT),True)])

        add_step("teal","8 · Если нужен анализ речи стримера",
            "1) Открой «Анализ» и установи компонент речи, если он ещё не установлен.\n"
            "2) Выбери микрофон и включи «Сохранять голос» ДО запуска сессии. Можно проверить речь без Twitch и стрима OBS.\n"
            "3) Заверши сессию, выбери её внизу Анализа и проверь строку «Запись найдена». Затем нажми «Распознать речь».\n"
            "4) Дождись окончания. Ход распознавания показан ниже настроек. Если слова не нашлись, проверь микрофон — запись не удалится.\n"
            "Тяжёлая обработка запускается после стрима отдельно от основного окна. В установочной версии приложения отдельный файл запускать не потребуется.",
            [("Открыть Анализ",lambda:self._switch_page(self.PAGE_ANALYSIS),True)])

        add_step("gold","9 · Хранилище и автоочистка",
            "По умолчанию Donathon Timer хранит тяжёлую аналитику за последние 20 дней: сообщения чата, замеры онлайна, расшифровки и временные аудиофайлы. Старые данные очищаются автоматически раз в день. Донаты и сессии при этом не удаляются.\n"
            "В Настройки → Хранилище и производительность можно изменить срок, вручную выбрать категории для очистки, посмотреть занимаемое место или освободить неиспользуемую оперативную память.",
            [("Открыть Настройки",lambda:self._switch_page(self.PAGE_SETTINGS),True)])

        add_step("neutral","10 · Если что-то пошло не так",
            "• Донат пришёл, но время начислено неверно → История → «Отменить начисление…» и выбери конкретную запись.\n"
            "• OBS не меняется → открой превью оверлея. Если превью работает, обнови кэш Browser Source в OBS.\n"
            "• Twitch не собирает данные → проверь зелёный статус Twitch на Главной и переподключи аккаунт во вкладке «Аккаунты».\n"
            "• Речь не распознаётся → проверь, что запись голоса была включена до начала сессии. Внизу «Анализа» показаны запись и причина ошибки.\n"
            "• Если нужна помощь → нажми «Связь с техподдержкой» слева внизу. Никогда не отправляй пароль и секретные ключи.",
            [("Открыть Аккаунты",lambda:self._switch_page(self.PAGE_ACCOUNTS),False),("Открыть Историю",lambda:self._switch_page(self.PAGE_HISTORY),False)])
        layout.addStretch()

    def _build_entertainment_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        # Управление показом OBS и анимацией находится рядом с самим колесом ниже,
        # чтобы верх страницы оставался компактным и начинался сразу с выбора режима.
        self.entertainment_obs_status=QLabel("OBS-интерактив скрыт")
        self.entertainment_obs_status.setObjectName("Muted")

        choose=self._card("magenta"); cl=QVBoxLayout(choose); cl.setContentsMargins(22,18,22,18); cl.setSpacing(10)
        ct=QLabel("Выбери режим"); ct.setObjectName("SectionTitle"); cl.addWidget(ct)
        mode_row=QHBoxLayout(); mode_row.setSpacing(8)
        self.entertainment_mode_group=QButtonGroup(self); self.entertainment_mode_group.setExclusive(True); self.entertainment_mode_buttons=[]
        modes=[("Обычная рулетка","Варианты задаёт стример"),("Чат-рулетка","Участники по слову из чата"),("Донат-рулетка","Шанс зависит от суммы"),("Голосование","Голоса из Twitch-чата")]
        for i,(name,tip) in enumerate(modes):
            b=QPushButton(name); b.setObjectName("Chip"); b.setCheckable(True); b.setToolTip(tip); b.setMinimumHeight(42)
            b.clicked.connect(lambda checked=False,idx=i:self._set_entertainment_mode(idx)); self.entertainment_mode_group.addButton(b,i); self.entertainment_mode_buttons.append(b); mode_row.addWidget(b)
        self.entertainment_mode_buttons[0].setChecked(True); cl.addLayout(mode_row); layout.addWidget(choose)

        self.entertainment_stack=QStackedWidget(); self.entertainment_stack.setMinimumHeight(170)

        # Manual roulette
        manual=QWidget(); ml=QVBoxLayout(manual); ml.setContentsMargins(0,0,0,0); ml.setSpacing(10)
        mc=self._card("orange"); mcl=QVBoxLayout(mc); mcl.setContentsMargins(22,18,22,18); mcl.setSpacing(9)
        mt=QLabel("Обычная рулетка"); mt.setObjectName("SectionTitle"); mcl.addWidget(mt)
        row=QHBoxLayout(); row.addWidget(QLabel("Название:")); self.manual_roulette_title=QLineEdit("Что выбираем?"); row.addWidget(self.manual_roulette_title,1); mcl.addLayout(row)
        mcl.addWidget(QLabel("Варианты — по одному на строку:")); self.manual_roulette_options=QPlainTextEdit(); self.manual_roulette_options.setPlaceholderText("Cyberpunk\nГарри Поттер\nCS2"); self.manual_roulette_options.setMinimumHeight(120); mcl.addWidget(self.manual_roulette_options)
        self.manual_roulette_overlay=QCheckBox("Показывать в OBS над таймером"); self.manual_roulette_overlay.setChecked(True); self.manual_roulette_overlay.setVisible(False)
        br=QHBoxLayout(); prep=QPushButton("Подготовить рулетку"); prep.setObjectName("Primary"); prep.setObjectName("Primary"); prep.clicked.connect(self._prepare_manual_roulette); spin=QPushButton("Крутить"); spin.setObjectName("OrangePrimary"); spin.clicked.connect(self._spin_roulette); clear=QPushButton("Очистить"); clear.setObjectName("Danger"); clear.clicked.connect(self._clear_roulette)
        br.addWidget(prep); br.addWidget(spin); br.addWidget(clear); br.addStretch(); mcl.addLayout(br); ml.addWidget(mc); self.entertainment_stack.addWidget(manual)

        # Chat roulette
        chat=QWidget(); chl=QVBoxLayout(chat); chl.setContentsMargins(0,0,0,0); chl.setSpacing(10)
        cc=self._card("cyan"); ccl=QVBoxLayout(cc); ccl.setContentsMargins(22,18,22,18); ccl.setSpacing(9)
        tt=QLabel("Чат-рулетка"); tt.setObjectName("SectionTitle"); ccl.addWidget(tt)
        hint=QLabel("Зритель пишет ключевое слово в Twitch-чате и один раз попадает в список участников. После окончания сбора выбирается один победитель."); hint.setObjectName("Muted"); hint.setWordWrap(True); ccl.addWidget(hint)
        cr=QHBoxLayout(); cr.addWidget(QLabel("Название:")); self.chat_roulette_title=QLineEdit("Розыгрыш среди зрителей"); cr.addWidget(self.chat_roulette_title,1); cr.addWidget(QLabel("Слово:")); self.chat_roulette_keyword=QLineEdit("ХОЧУ"); self.chat_roulette_keyword.setMaximumWidth(220); cr.addWidget(self.chat_roulette_keyword); ccl.addLayout(cr)
        cr2=QHBoxLayout(); cr2.addWidget(QLabel("Условие:")); self.chat_roulette_match=QComboBox(); self.chat_roulette_match.addItem("Сообщение ровно равно слову","exact"); self.chat_roulette_match.addItem("Слово встречается в сообщении","contains"); cr2.addWidget(self.chat_roulette_match,1); self.chat_roulette_overlay=QCheckBox("Показывать в OBS"); self.chat_roulette_overlay.setChecked(True); self.chat_roulette_overlay.setVisible(False); cr2.addWidget(self.chat_roulette_overlay); ccl.addLayout(cr2)
        cb=QHBoxLayout(); start=QPushButton("Начать сбор"); start.setObjectName("Primary"); start.setObjectName("Primary"); start.clicked.connect(self._start_chat_roulette); stop=QPushButton("Остановить сбор"); stop.setObjectName("Chip"); stop.clicked.connect(self._stop_roulette_collection); spin=QPushButton("Выбрать победителя"); spin.setObjectName("OrangePrimary"); spin.clicked.connect(self._spin_roulette); clear=QPushButton("Очистить"); clear.setObjectName("Danger"); clear.clicked.connect(self._clear_roulette)
        for b in (start,stop,spin,clear): cb.addWidget(b)
        cb.addStretch(); ccl.addLayout(cb); chl.addWidget(cc); self.entertainment_stack.addWidget(chat)

        # Donation roulette
        donation=QWidget(); dl=QVBoxLayout(donation); dl.setContentsMargins(0,0,0,0); dl.setSpacing(10)
        dc=self._card("gold"); dcl=QVBoxLayout(dc); dcl.setContentsMargins(22,18,22,18); dcl.setSpacing(9)
        dtit=QLabel("Донат-рулетка"); dtit.setObjectName("SectionTitle"); dcl.addWidget(dtit)
        dh=QLabel("После запуска каждый новый донат с текстом становится вариантом. Одинаковые сообщения объединяются, суммы складываются, а шанс на колесе пропорционален общей сумме."); dh.setObjectName("Muted"); dh.setWordWrap(True); dcl.addWidget(dh)
        dr=QHBoxLayout(); dr.addWidget(QLabel("Название:")); self.donation_roulette_title=QLineEdit("Что делаем?"); dr.addWidget(self.donation_roulette_title,1); self.donation_roulette_overlay=QCheckBox("Показывать в OBS"); self.donation_roulette_overlay.setChecked(True); self.donation_roulette_overlay.setVisible(False); dr.addWidget(self.donation_roulette_overlay); dcl.addLayout(dr)
        db=QHBoxLayout(); start=QPushButton("Начать сбор"); start.setObjectName("Primary"); start.setObjectName("Primary"); start.clicked.connect(self._start_donation_roulette); stop=QPushButton("Закрыть сбор"); stop.setObjectName("Chip"); stop.clicked.connect(self._stop_roulette_collection); spin=QPushButton("Крутить"); spin.setObjectName("OrangePrimary"); spin.clicked.connect(self._spin_roulette); clear=QPushButton("Очистить"); clear.setObjectName("Danger"); clear.clicked.connect(self._clear_roulette)
        for b in (start,stop,spin,clear): db.addWidget(b)
        db.addStretch(); dcl.addLayout(db); dl.addWidget(dc); self.entertainment_stack.addWidget(donation)

        # Poll
        poll=QWidget(); pl=QVBoxLayout(poll); pl.setContentsMargins(0,0,0,0); pl.setSpacing(10)
        pc=self._card("teal"); pcl=QVBoxLayout(pc); pcl.setContentsMargins(22,18,22,18); pcl.setSpacing(9)
        pt=QLabel("Голосование в Twitch-чате"); pt.setObjectName("SectionTitle"); pcl.addWidget(pt)
        ph=QLabel("Зрители голосуют названием варианта или его номером. Результаты в реальном времени отображаются в OBS над таймером."); ph.setObjectName("Muted"); ph.setWordWrap(True); pcl.addWidget(ph)
        pr=QHBoxLayout(); pr.addWidget(QLabel("Вопрос:")); self.poll_question=QLineEdit("Во что играем дальше?"); pr.addWidget(self.poll_question,1); pcl.addLayout(pr)
        pcl.addWidget(QLabel("Варианты — по одному на строку:")); self.poll_options=QPlainTextEdit("Cyberpunk\nГарри Поттер\nCS2"); self.poll_options.setMinimumHeight(110); pcl.addWidget(self.poll_options)
        pr2=QHBoxLayout(); pr2.addWidget(QLabel("Подсчёт:")); self.poll_vote_mode=QComboBox(); self.poll_vote_mode.addItem("Один голос от пользователя","unique"); self.poll_vote_mode.addItem("Считать каждое сообщение","all"); self.poll_vote_mode.addItem("Пользователь может изменить голос","change"); pr2.addWidget(self.poll_vote_mode,1); self.poll_overlay=QCheckBox("Показывать в OBS"); self.poll_overlay.setChecked(True); self.poll_overlay.setVisible(False); pr2.addWidget(self.poll_overlay); pcl.addLayout(pr2)
        pb=QHBoxLayout(); start=QPushButton("Начать голосование"); start.setObjectName("Primary"); start.setObjectName("Primary"); start.clicked.connect(self._start_poll); stop=QPushButton("Завершить"); stop.setObjectName("Chip"); stop.clicked.connect(self._stop_poll); clear=QPushButton("Очистить"); clear.setObjectName("Danger"); clear.clicked.connect(self._clear_poll)
        for b in (start,stop,clear): pb.addWidget(b)
        pb.addStretch(); pcl.addLayout(pb); pl.addWidget(pc); self.entertainment_stack.addWidget(poll)
        layout.addWidget(self.entertainment_stack)

        # Live roulette preview + list
        self.entertainment_roulette_live_card=self._card("orange"); rl=QGridLayout(self.entertainment_roulette_live_card); rl.setContentsMargins(22,18,22,18); rl.setHorizontalSpacing(18); rl.setVerticalSpacing(8)
        live_title=QLabel("Текущее колесо"); live_title.setObjectName("SectionTitle"); rl.addWidget(live_title,0,0,1,2)
        controls=QHBoxLayout(); controls.setSpacing(8)
        self.entertainment_show_interactive=QPushButton("Показать интерактив"); self.entertainment_show_interactive.setObjectName("OBSActionInteractive"); self.entertainment_show_interactive.setCheckable(True); self.entertainment_show_interactive.toggled.connect(self._entertainment_interactive_visibility_changed); controls.addWidget(self.entertainment_show_interactive)
        self.entertainment_show_timer=QPushButton("Показать таймер"); self.entertainment_show_timer.setObjectName("OBSActionTimer"); self.entertainment_show_timer.setCheckable(True); self.entertainment_show_timer.toggled.connect(self._entertainment_timer_visibility_changed); controls.addWidget(self.entertainment_show_timer)
        controls.addWidget(QLabel("Прокрут:")); self.roulette_spin_speed=QComboBox(); self.roulette_spin_speed.addItem("Моментальная", "fast"); self.roulette_spin_speed.addItem("Плавная", "normal"); self.roulette_spin_speed.currentIndexChanged.connect(self._roulette_spin_speed_changed); self.roulette_spin_speed.setMaximumWidth(160); controls.addWidget(self.roulette_spin_speed)
        self.manual_roulette_mode_label=QLabel("Режим:"); controls.addWidget(self.manual_roulette_mode_label)
        self.manual_roulette_mode=QComboBox(); self.manual_roulette_mode.addItem("Выбрать победителя", "winner"); self.manual_roulette_mode.addItem("Выпавший выбывает", "elimination")
        self.manual_roulette_mode.setToolTip("Режим меняется сразу. В режиме победителя выпавший останется на колесе до следующей прокрутки.")
        self.manual_roulette_mode.setMinimumWidth(150); self.manual_roulette_mode.currentIndexChanged.connect(self._manual_roulette_mode_changed)
        controls.addWidget(self.manual_roulette_mode); controls.addStretch(); controls.addWidget(self.entertainment_obs_status)
        rl.addLayout(controls,1,0,1,2)
        self.entertainment_wheel=WheelPreview(); self.entertainment_wheel.set_mode(self.ui_theme); self.entertainment_wheel.clicked.connect(self._spin_roulette); rl.addWidget(self.entertainment_wheel,2,0)
        side=QVBoxLayout()
        self.last_winner_label=QLabel("Последний победитель: пока нет")
        self.last_winner_label.setWordWrap(True)
        self.last_winner_label.setStyleSheet("background:#173a32;color:#dbffdc;border:1px solid #36b995;border-radius:9px;padding:10px;font-weight:750;")
        side.addWidget(self.last_winner_label)
        self.roulette_live_status=QLabel("Рулетка ещё не подготовлена"); self.roulette_live_status.setObjectName("Muted"); self.roulette_live_status.setWordWrap(True); side.addWidget(self.roulette_live_status)
        self.roulette_live_table=QTableWidget(0,4); self.roulette_live_table.setHorizontalHeaderLabels(["Участник / вариант","Вес","Шанс","Дополнительно"]); self.roulette_live_table.verticalHeader().setVisible(False); self.roulette_live_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.roulette_live_table.setSelectionMode(QAbstractItemView.NoSelection); self.roulette_live_table.setAlternatingRowColors(True); self.roulette_live_table.setMinimumHeight(210)
        hh=self.roulette_live_table.horizontalHeader(); hh.setSectionResizeMode(0,QHeaderView.Stretch); hh.setSectionResizeMode(1,QHeaderView.ResizeToContents); hh.setSectionResizeMode(2,QHeaderView.ResizeToContents); hh.setSectionResizeMode(3,QHeaderView.ResizeToContents)
        side.addWidget(self.roulette_live_table,1); rl.addLayout(side,2,1); rl.setColumnStretch(0,1); rl.setColumnStretch(1,2); layout.addWidget(self.entertainment_roulette_live_card)

        # Live poll results
        self.entertainment_poll_live_card=self._card("teal"); poll_l=QVBoxLayout(self.entertainment_poll_live_card); poll_l.setContentsMargins(22,18,22,18); poll_l.setSpacing(9)
        self.poll_live_title=QLabel("Результаты голосования"); self.poll_live_title.setObjectName("SectionTitle"); poll_l.addWidget(self.poll_live_title)
        poll_controls=QHBoxLayout(); poll_controls.setSpacing(8)
        self.poll_show_interactive=QPushButton("Показать интерактив"); self.poll_show_interactive.setObjectName("OBSActionInteractive"); self.poll_show_interactive.setCheckable(True); self.poll_show_interactive.toggled.connect(self._entertainment_interactive_visibility_changed); poll_controls.addWidget(self.poll_show_interactive)
        self.poll_show_timer=QPushButton("Показать таймер"); self.poll_show_timer.setObjectName("OBSActionTimer"); self.poll_show_timer.setCheckable(True); self.poll_show_timer.toggled.connect(self._entertainment_timer_visibility_changed); poll_controls.addWidget(self.poll_show_timer); poll_controls.addStretch(); poll_l.addLayout(poll_controls)
        self.poll_live_status=QLabel("Голосование ещё не запущено"); self.poll_live_status.setObjectName("Muted"); poll_l.addWidget(self.poll_live_status)
        self.poll_live_table=QTableWidget(0,4); self.poll_live_table.setHorizontalHeaderLabels(["Вариант","Голосов","Доля","Как голосовать"]); self.poll_live_table.verticalHeader().setVisible(False); self.poll_live_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.poll_live_table.setSelectionMode(QAbstractItemView.NoSelection); self.poll_live_table.setAlternatingRowColors(True); self.poll_live_table.setMinimumHeight(210)
        phh=self.poll_live_table.horizontalHeader(); phh.setSectionResizeMode(0,QHeaderView.Stretch)
        for c in range(1,4): phh.setSectionResizeMode(c,QHeaderView.ResizeToContents)
        poll_l.addWidget(self.poll_live_table); layout.addWidget(self.entertainment_poll_live_card)
        layout.addStretch()
        saved_ent=self.entertainment_service.snapshot(); saved_r=saved_ent.get("roulette",{})
        initial_mode={"manual":0,"chat":1,"donation":2,"poll":3}.get(str(saved_ent.get("active_mode") or saved_r.get("mode") or "manual"),0)
        self._set_entertainment_mode(initial_mode)

    def _entertainment_timer_visibility_changed(self, checked: bool) -> None:
        self.entertainment_service.set_timer_visible(bool(checked))
        self._sync_timer_visibility_buttons(bool(checked))

    def _overlay_timer_visibility_changed(self, checked: bool) -> None:
        self.entertainment_service.set_timer_visible(bool(checked))
        self._sync_timer_visibility_buttons(bool(checked))

    def _sync_timer_visibility_buttons(self, visible: bool) -> None:
        for name in ("entertainment_show_timer", "poll_show_timer", "overlay_timer_toggle", "home_timer_toggle"):
            btn=getattr(self,name,None)
            if btn is not None:
                btn.blockSignals(True); btn.setChecked(bool(visible)); btn.setText("Скрыть таймер" if visible else "Показать таймер"); btn.blockSignals(False)
        if hasattr(self,"overlay_timer_status"):
            self.overlay_timer_status.setText("Таймер отображается в OBS" if visible else "Таймер в OBS скрыт")

    def _entertainment_interactive_visibility_changed(self, checked: bool) -> None:
        self.entertainment_service.set_interactive_visible(bool(checked))
        snap=self.entertainment_service.snapshot(max_entries=1)
        self._sync_interactive_visibility_buttons(bool(checked), str(snap.get("active_mode") or "manual"))

    def _sync_interactive_visibility_buttons(self, visible: bool, active_mode: str) -> None:
        noun="голосование" if active_mode=="poll" else "рулетку"
        for name in ("entertainment_show_interactive", "poll_show_interactive", "home_interactive_toggle"):
            btn=getattr(self,name,None)
            if btn is not None:
                btn.blockSignals(True)
                btn.setChecked(bool(visible))
                btn.setText(("Скрыть " if visible else "Показать ")+noun)
                btn.blockSignals(False)

    def _roulette_spin_speed_changed(self, *args) -> None:
        if not hasattr(self, "roulette_spin_speed"):
            return
        self.entertainment_service.set_roulette_spin_speed(str(self.roulette_spin_speed.currentData() or "normal"))

    def _manual_roulette_mode_changed(self, *args) -> None:
        if not hasattr(self,"manual_roulette_mode"):
            return
        mode=str(self.manual_roulette_mode.currentData() or "winner")
        try:
            self.entertainment_service.set_manual_selection_mode(mode)
            self.statusBar().showMessage("Режим рулетки изменён · применяется со следующей прокрутки",3200)
            self._refresh_entertainment()
        except ValueError as exc:
            QMessageBox.warning(self,"Рулетка",str(exc))

    def _set_entertainment_mode(self, index: int) -> None:
        index=max(0,min(3,int(index)))
        mode=("manual","chat","donation","poll")[index]
        title=None
        if mode=="manual" and hasattr(self,"manual_roulette_title"): title=self.manual_roulette_title.text()
        elif mode=="chat" and hasattr(self,"chat_roulette_title"): title=self.chat_roulette_title.text()
        elif mode=="donation" and hasattr(self,"donation_roulette_title"): title=self.donation_roulette_title.text()
        self.entertainment_service.select_mode(mode, title)
        if hasattr(self,"entertainment_stack"):
            self.entertainment_stack.setCurrentIndex(index)
            self.entertainment_stack.setFixedHeight((390,255,230,400)[index])
        active_state=self.entertainment_service.snapshot(max_entries=1)
        self._sync_interactive_visibility_buttons(bool(active_state.get("interactive_visible",False)),mode)
        if hasattr(self,"entertainment_mode_buttons"):
            for i,b in enumerate(self.entertainment_mode_buttons):
                b.blockSignals(True); b.setChecked(i==index); b.blockSignals(False)
        if hasattr(self,"entertainment_roulette_live_card"):
            self.entertainment_roulette_live_card.setVisible(index<3)
            self.entertainment_poll_live_card.setVisible(index==3)
            self.manual_roulette_mode_label.setVisible(index==0)
            self.manual_roulette_mode.setVisible(index==0)
        self._refresh_entertainment()

    @staticmethod
    def _lines_from_edit(edit: QPlainTextEdit) -> list[str]:
        return [x.strip() for x in edit.toPlainText().splitlines() if x.strip()]

    def _prepare_manual_roulette(self) -> None:
        try:
            self.entertainment_service.configure_manual(self.manual_roulette_title.text(), self._lines_from_edit(self.manual_roulette_options), self.manual_roulette_mode.currentData(), self.manual_roulette_overlay.isChecked())
            self.statusBar().showMessage("Рулетка подготовлена",2500); self._refresh_entertainment()
        except Exception as exc: QMessageBox.warning(self,"Рулетка",str(exc))

    def _start_chat_roulette(self) -> None:
        try:
            self.entertainment_service.start_chat_roulette(self.chat_roulette_title.text(), self.chat_roulette_keyword.text(), self.chat_roulette_match.currentData(), self.chat_roulette_overlay.isChecked())
            self.statusBar().showMessage("Сбор участников из чата начат",2500); self._refresh_entertainment()
        except Exception as exc: QMessageBox.warning(self,"Чат-рулетка",str(exc))

    def _start_donation_roulette(self) -> None:
        try:
            self.entertainment_service.start_donation_roulette(self.donation_roulette_title.text(), self.donation_roulette_overlay.isChecked())
            self.statusBar().showMessage("Сбор вариантов из донатов начат",2500); self._refresh_entertainment()
        except Exception as exc: QMessageBox.warning(self,"Донат-рулетка",str(exc))

    def _stop_roulette_collection(self) -> None:
        self.entertainment_service.stop_roulette_collection(); self._refresh_entertainment(); self.statusBar().showMessage("Сбор остановлен",2200)

    def _spin_roulette(self) -> None:
        try:
            result=self.entertainment_service.spin_roulette()
            self._refresh_entertainment()
            self.statusBar().showMessage("Колесо крутится…", int((float(result.get("duration") or 6.2)+0.5)*1000))
        except Exception as exc: QMessageBox.warning(self,"Рулетка",str(exc))

    def _clear_roulette(self) -> None:
        if QMessageBox.question(self,"Очистить рулетку","Очистить текущую рулетку и её участников / варианты?")!=QMessageBox.Yes:return
        self.entertainment_service.clear_roulette(); self._refresh_entertainment()

    def _start_poll(self) -> None:
        try:
            self.entertainment_service.start_poll(self.poll_question.text(), self._lines_from_edit(self.poll_options), self.poll_vote_mode.currentData(), self.poll_overlay.isChecked())
            self.statusBar().showMessage("Голосование запущено",2500); self._refresh_entertainment()
        except Exception as exc: QMessageBox.warning(self,"Голосование",str(exc))

    def _stop_poll(self) -> None:
        self.entertainment_service.stop_poll(keep_overlay=self.poll_overlay.isChecked()); self._refresh_entertainment(); self.statusBar().showMessage("Голосование завершено",2500)

    def _clear_poll(self) -> None:
        if QMessageBox.question(self,"Очистить голосование","Очистить результаты текущего голосования?")!=QMessageBox.Yes:return
        self.entertainment_service.clear_poll(); self._refresh_entertainment()

    def _refresh_entertainment(self) -> None:
        if not hasattr(self,"entertainment_wheel"): return
        snap=self.entertainment_service.snapshot(); r=snap.get("roulette",{}); p=snap.get("poll",{})
        display=snap.get("display_type")
        show_timer = bool(snap.get("timer_visible", False))
        interactive_visible = bool(snap.get("interactive_visible", False))
        self._sync_timer_visibility_buttons(show_timer)
        active_mode=str(snap.get("active_mode") or r.get("mode") or "manual")
        interactive_noun="голосование" if active_mode=="poll" else "рулетку"
        self._sync_interactive_visibility_buttons(interactive_visible, active_mode)
        spin_speed = str(r.get("spin_speed") or "normal")
        if hasattr(self,"manual_roulette_mode"):
            current_mode=str(r.get("manual_mode") or "winner")
            idx=self.manual_roulette_mode.findData(current_mode)
            if idx>=0 and self.manual_roulette_mode.currentIndex()!=idx:
                self.manual_roulette_mode.blockSignals(True)
                self.manual_roulette_mode.setCurrentIndex(idx)
                self.manual_roulette_mode.blockSignals(False)
        if hasattr(self, "roulette_spin_speed"):
            self.roulette_spin_speed.blockSignals(True)
            idx = self.roulette_spin_speed.findData(spin_speed)
            self.roulette_spin_speed.setCurrentIndex(max(0, idx))
            self.roulette_spin_speed.blockSignals(False)
        suffix=" + таймер" if show_timer else ""
        names={None:"Интерактив в OBS скрыт","roulette":"В OBS: рулетка"+suffix,"poll":"В OBS: голосование"+suffix}
        self.entertainment_obs_status.setText(names.get(display,"OBS-интерактив активен"))
        self.entertainment_wheel.set_snapshot(r)
        self.last_winner_label.setText("Последний победитель: " + (str(r.get("last_winner")) if r.get("last_winner") else "пока нет"))
        if (not r.get("spinning") and r.get("mode")=="manual" and
                r.get("result") and int(r.get("spin_nonce") or 0)>0):
            nonce=int(r.get("spin_nonce") or 0)
            if getattr(self, "_last_completed_manual_spin_nonce", None)!=nonce:
                self._last_completed_manual_spin_nonce=nonce
                self.manual_roulette_options.setPlainText("\n".join(r.get("manual_options") or []))
        entries=list(r.get("entries") or []); visible_entries=entries[:500]; self.roulette_live_table.setRowCount(len(visible_entries))
        for row,item in enumerate(visible_entries):
            self.roulette_live_table.setItem(row,0,QTableWidgetItem(str(item.get("label") or "")))
            weight=float(item.get("weight") or 0)
            mode=r.get("mode")
            self.roulette_live_table.setItem(row,1,QTableWidgetItem(f"{weight:.2f} ₽" if mode=="donation" else "1"))
            self.roulette_live_table.setItem(row,2,QTableWidgetItem(f"{float(item.get('percent') or 0):.1f}%"))
            meta=str(item.get("meta") or "")
            if mode=="donation":
                meta=f"донатов: {int(item.get('donors') or 0)}"
            self.roulette_live_table.setItem(row,3,QTableWidgetItem(meta))
        collect=" · идёт сбор" if r.get("collecting") else ""
        result=(" · колесо крутится…" if r.get("spinning") else (f" · {r.get('result_status')}: {r.get('result')}" if r.get("result") else ""))
        hidden_note=(f" · в таблице показаны первые {len(visible_entries)}" if len(entries)>len(visible_entries) else "")
        self.roulette_live_status.setText(f"{r.get('title','Рулетка')} · {int(r.get('count') or len(entries))} вариантов / участников{collect}{result}{hidden_note}")
        # sync overlay checkboxes with persisted state for the active roulette definition
        if r.get("mode")=="manual": self.manual_roulette_overlay.setChecked(bool(r.get("overlay_enabled",True)))
        elif r.get("mode")=="chat": self.chat_roulette_overlay.setChecked(bool(r.get("overlay_enabled",True)))
        elif r.get("mode")=="donation": self.donation_roulette_overlay.setChecked(bool(r.get("overlay_enabled",True)))

        results=list(p.get("results") or []); self.poll_live_table.setRowCount(len(results)); self.poll_live_title.setText(str(p.get("question") or "Результаты голосования"))
        for row,item in enumerate(results):
            self.poll_live_table.setItem(row,0,QTableWidgetItem(str(item.get("label") or "")))
            self.poll_live_table.setItem(row,1,QTableWidgetItem(str(int(item.get("votes") or 0))))
            self.poll_live_table.setItem(row,2,QTableWidgetItem(f"{float(item.get('percent') or 0):.1f}%"))
            self.poll_live_table.setItem(row,3,QTableWidgetItem(f"{row+1} или {item.get('label','')}"))
        self.poll_live_status.setText(("● Голосование идёт" if p.get("active") else "Голосование завершено / не запущено")+f" · всего голосов: {int(p.get('total_votes') or 0)}")
        self.poll_overlay.setChecked(bool(p.get("overlay_enabled",True)))

    def _build_sessions_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        # Active session
        card=self._card("blue"); l=QVBoxLayout(card); l.setContentsMargins(22,20,22,20); l.setSpacing(11)
        row=QHBoxLayout(); title=QLabel("Текущая сессия"); title.setObjectName("SectionTitle"); row.addWidget(title); row.addStretch(); l.addLayout(row)
        self.rename_active_session_btn=QPushButton("Переименовать"); self.rename_active_session_btn.clicked.connect(self._rename_active_session)
        self.pause_session_btn=QPushButton("Приостановить"); self.pause_session_btn.clicked.connect(self._toggle_session_pause)
        self.new_session_btn=QPushButton("Новая сессия"); self.new_session_btn.setObjectName("Primary"); self.new_session_btn.clicked.connect(self._new_session)
        self.end_session_btn=QPushButton("Завершить"); self.end_session_btn.setObjectName("Danger"); self.end_session_btn.clicked.connect(self._end_session)
        session_actions=QGridLayout(); session_actions.setHorizontalSpacing(8); session_actions.setVerticalSpacing(8)
        session_actions.addWidget(self.rename_active_session_btn,0,0); session_actions.addWidget(self.pause_session_btn,0,1)
        session_actions.addWidget(self.new_session_btn,1,0); session_actions.addWidget(self.end_session_btn,1,1)
        session_actions.setColumnStretch(0,1); session_actions.setColumnStretch(1,1); l.addLayout(session_actions)
        self.session_name_label=QLabel("Сессия не запущена"); self.session_name_label.setStyleSheet("font-size:20px;font-weight:750"); l.addWidget(self.session_name_label)
        self.session_meta_label=QLabel("История всё равно ведётся, но сессия позволяет отделить один донатофон от другого."); self.session_meta_label.setObjectName("Muted"); self.session_meta_label.setWordWrap(True); l.addWidget(self.session_meta_label)
        self.session_elapsed_label=QLabel(""); self.session_elapsed_label.setStyleSheet("font-size:15px;font-weight:700"); l.addWidget(self.session_elapsed_label)
        self.session_stats_label=QLabel(""); self.session_stats_label.setObjectName("Muted"); self.session_stats_label.setWordWrap(True); l.addWidget(self.session_stats_label)
        layout.addWidget(card)

        # Session archive / comparison table
        archive=self._card("cyan"); al=QVBoxLayout(archive); al.setContentsMargins(22,20,22,20); al.setSpacing(10)
        ah=QHBoxLayout(); at=QLabel("История сессий"); at.setObjectName("SectionTitle"); ah.addWidget(at); ah.addStretch()
        self.rename_selected_session_btn=QPushButton("Переименовать выбранную"); self.rename_selected_session_btn.clicked.connect(self._rename_selected_session)
        self.delete_selected_session_btn=QPushButton("Удалить выбранную"); self.delete_selected_session_btn.setObjectName("Danger"); self.delete_selected_session_btn.clicked.connect(self._delete_selected_session)
        ah.addWidget(self.rename_selected_session_btn); ah.addWidget(self.delete_selected_session_btn); al.addLayout(ah)
        hint=QLabel("Каждая строка — отдельный донатофон. Выбери сессию, чтобы ниже увидеть её итоги и рейтинг донатеров."); hint.setObjectName("Muted"); hint.setWordWrap(True); al.addWidget(hint)
        self.sessions_table=QTableWidget(0,7)
        self.sessions_table.setHorizontalHeaderLabels(["Название","Старт","Финиш","Длительность","Донатов","Получено","Добавлено времени"])
        self.sessions_table.verticalHeader().setVisible(False); self.sessions_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.sessions_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.sessions_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sessions_table.setAlternatingRowColors(True); self.sessions_table.setMinimumHeight(250)
        header=self.sessions_table.horizontalHeader(); header.setSectionResizeMode(0,QHeaderView.Stretch)
        for col in range(1,7): header.setSectionResizeMode(col,QHeaderView.ResizeToContents)
        self.sessions_table.itemSelectionChanged.connect(self._session_selection_changed)
        al.addWidget(self.sessions_table); layout.addWidget(archive)

        # Selected session details + donor leaderboard
        detail=self._card("purple"); dl=QVBoxLayout(detail); dl.setContentsMargins(22,20,22,20); dl.setSpacing(10)
        dh=QHBoxLayout(); dtl=QLabel("Итоги выбранной сессии"); dtl.setObjectName("SectionTitle"); dh.addWidget(dtl); dh.addStretch(); dl.addLayout(dh)
        self.selected_session_name=QLabel("Выбери сессию выше"); self.selected_session_name.setStyleSheet("font-size:19px;font-weight:800"); dl.addWidget(self.selected_session_name)
        self.selected_session_meta=QLabel(""); self.selected_session_meta.setObjectName("Muted"); self.selected_session_meta.setWordWrap(True); dl.addWidget(self.selected_session_meta)
        self.selected_session_stats=QLabel(""); self.selected_session_stats.setObjectName("Muted"); self.selected_session_stats.setWordWrap(True); dl.addWidget(self.selected_session_stats)
        rank_title=QLabel("Топ донатеров"); rank_title.setStyleSheet("font-size:16px;font-weight:750;margin-top:5px"); dl.addWidget(rank_title)
        self.donor_ranking_table=QTableWidget(0,4)
        self.donor_ranking_table.setHorizontalHeaderLabels(["Донатер","Донатов","Сумма","Добавил времени"])
        self.donor_ranking_table.verticalHeader().setVisible(False); self.donor_ranking_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.donor_ranking_table.setSelectionMode(QAbstractItemView.NoSelection); self.donor_ranking_table.setAlternatingRowColors(True); self.donor_ranking_table.setMinimumHeight(230)
        rh=self.donor_ranking_table.horizontalHeader(); rh.setSectionResizeMode(0,QHeaderView.Stretch)
        for col in range(1,4): rh.setSectionResizeMode(col,QHeaderView.ResizeToContents)
        dl.addWidget(self.donor_ranking_table); layout.addWidget(detail); layout.addStretch()

    def _build_accounts_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)

        status=self._card("green"); sl=QVBoxLayout(status); sl.setContentsMargins(22,20,22,20); sl.setSpacing(9)
        t=QLabel("DonationAlerts"); t.setObjectName("SectionTitle"); sl.addWidget(t)
        self.account_status_label=QLabel("Статус подключения"); self.account_status_label.setObjectName("Warn"); sl.addWidget(self.account_status_label)
        self.account_profile_label=QLabel(""); self.account_profile_label.setObjectName("Muted"); self.account_profile_label.setWordWrap(True); sl.addWidget(self.account_profile_label)
        da_help=QLabel("Первое подключение: создай приложение DonationAlerts, вставь его App ID и разреши доступ в браузере. Если делаешь это впервые — открой пошаговую инструкцию."); da_help.setObjectName("Muted"); da_help.setWordWrap(True); sl.addWidget(da_help)
        buttons=QHBoxLayout(); self.connect_da_btn=QPushButton("Подключить DonationAlerts"); self.connect_da_btn.setObjectName("Primary"); self.connect_da_btn.clicked.connect(self._connect_da)
        setup_btn=QPushButton("Ввести Client ID"); setup_btn.clicked.connect(self._setup_da); help_btn=QPushButton("Пошаговая настройка"); help_btn.clicked.connect(lambda:self._switch_page(self.PAGE_GUIDE)); buttons.addWidget(self.connect_da_btn); buttons.addWidget(setup_btn); buttons.addWidget(help_btn); buttons.addStretch(); sl.addLayout(buttons); layout.addWidget(status)

        twitch=self._card("magenta"); tl=QVBoxLayout(twitch); tl.setContentsMargins(22,20,22,20); tl.setSpacing(9)
        tt=QLabel("Twitch · онлайн и чат"); tt.setObjectName("SectionTitle"); tl.addWidget(tt)
        self.twitch_status_label=QLabel("● Twitch не подключён"); self.twitch_status_label.setObjectName("Warn"); tl.addWidget(self.twitch_status_label)
        self.twitch_profile_label=QLabel("Twitch нужен для графика онлайна и анализа чата. Таймер и DonationAlerts работают независимо от него.")
        self.twitch_profile_label.setObjectName("Muted"); self.twitch_profile_label.setWordWrap(True); tl.addWidget(self.twitch_profile_label)
        twitch_help=QLabel("Если подключаешь впервые: сначала создай приложение в Twitch Developer Console, затем вставь Client ID сюда."); twitch_help.setObjectName("Muted"); twitch_help.setWordWrap(True); tl.addWidget(twitch_help)
        tr=QHBoxLayout(); self.connect_twitch_btn=QPushButton("Подключить Twitch"); self.connect_twitch_btn.setObjectName("Primary"); self.connect_twitch_btn.clicked.connect(self._connect_twitch)
        twitch_setup=QPushButton("Ввести Twitch Client ID"); twitch_setup.clicked.connect(self._setup_twitch); twitch_guide=QPushButton("Пошаговая настройка"); twitch_guide.clicked.connect(lambda:self._switch_page(self.PAGE_GUIDE))
        tr.addWidget(self.connect_twitch_btn); tr.addWidget(twitch_setup); tr.addWidget(twitch_guide); tr.addStretch(); tl.addLayout(tr); layout.addWidget(twitch)

        multi=self._card("neutral"); ml=QVBoxLayout(multi); ml.setContentsMargins(22,20,22,20); ml.setSpacing(7)
        mt=QLabel("Несколько аккаунтов"); mt.setObjectName("SectionTitle"); ml.addWidget(mt)
        text=QLabel("Каждый DonationAlerts-профиль может быть связан со своим Twitch-каналом. При переключении профиля приложение автоматически переключает и сбор Twitch-аналитики. OBS-ссылка при этом остаётся той же.")
        text.setObjectName("Muted"); text.setWordWrap(True); ml.addWidget(text); layout.addWidget(multi); layout.addStretch()

    def _build_settings_page(self) -> None:
        scroll, _, layout = self._make_scroll_page(); self.stack.addWidget(scroll)
        obs=self._card("cyan"); ol=QVBoxLayout(obs); ol.setContentsMargins(22,20,22,20); ol.setSpacing(9)
        t=QLabel("OBS"); t.setObjectName("SectionTitle"); ol.addWidget(t)
        txt=QLabel("Добавь источник «Браузер» размером 1920 × 1080. Donathon Timer работает отдельным источником и не меняет твои существующие оповещения DonationAlerts, их звуки, анимации или сцены.")
        txt.setObjectName("Muted"); txt.setWordWrap(True); ol.addWidget(txt)
        url=QLabel(OVERLAY_URL); url.setTextInteractionFlags(Qt.TextSelectableByMouse); url.setObjectName("Muted"); url.setWordWrap(True); ol.addWidget(url)
        row=QHBoxLayout(); copy=QPushButton("Копировать ссылку"); copy.clicked.connect(self._copy_overlay); preview=QPushButton("Открыть превью"); preview.clicked.connect(lambda:webbrowser.open(OVERLAY_URL)); row.addWidget(copy); row.addWidget(preview); row.addStretch(); ol.addLayout(row); layout.addWidget(obs)

        storage_card=self._card("gold"); sl=QVBoxLayout(storage_card); sl.setContentsMargins(22,20,22,20); sl.setSpacing(10)
        st=QLabel("Хранилище и производительность"); st.setObjectName("SectionTitle"); sl.addWidget(st)
        desc=QLabel("Тяжёлые данные аналитики можно очищать автоматически. Донаты и список сессий по умолчанию сохраняются — они занимают мало места и нужны для долгосрочной статистики.")
        desc.setObjectName("Muted"); desc.setWordWrap(True); sl.addWidget(desc)
        self.storage_usage_label=QLabel("Считаю занятое место…"); self.storage_usage_label.setObjectName("Muted"); self.storage_usage_label.setWordWrap(True); sl.addWidget(self.storage_usage_label)
        retention=QHBoxLayout(); self.auto_cleanup_checkbox=QCheckBox("Автоматически удалять тяжёлую аналитику старше"); self.auto_cleanup_checkbox.setChecked((self.storage.get_setting("analytics_auto_cleanup") or "1")!="0")
        self.retention_days_spin=QSpinBox(); self.retention_days_spin.setRange(1,365); self.retention_days_spin.setValue(max(1,int(self.storage.get_setting("analytics_retention_days") or "20"))); self.retention_days_spin.setSuffix(" дн.")
        save_retention=QPushButton("Сохранить"); save_retention.clicked.connect(self._save_retention_settings)
        retention.addWidget(self.auto_cleanup_checkbox); retention.addWidget(self.retention_days_spin); retention.addWidget(save_retention); retention.addStretch(); sl.addLayout(retention)
        cleanup_row=QHBoxLayout(); cleanup=QPushButton("Очистить данные…"); cleanup.setObjectName("Danger"); cleanup.clicked.connect(self._manual_cleanup)
        ram=QPushButton("Освободить оперативную память"); ram.clicked.connect(self._release_ram_now); refresh_usage=QPushButton("Обновить размер"); refresh_usage.clicked.connect(self._refresh_storage_usage)
        cleanup_row.addWidget(cleanup); cleanup_row.addWidget(ram); cleanup_row.addWidget(refresh_usage); cleanup_row.addStretch(); sl.addLayout(cleanup_row)
        cleanup_hint=QLabel("Автоочистка затрагивает чат Twitch, замеры онлайна, расшифровки и временные аудиофайлы. Полную историю донатов и сессий приложение не удаляет автоматически.")
        cleanup_hint.setObjectName("Muted"); cleanup_hint.setWordWrap(True); sl.addWidget(cleanup_hint); layout.addWidget(storage_card)

        app=self._card("neutral"); al=QVBoxLayout(app); al.setContentsMargins(22,20,22,20)
        at=QLabel("Служебная информация"); at.setObjectName("SectionTitle"); al.addWidget(at)
        note=QLabel("Обычно эти данные не нужны. Они пригодятся только при переносе базы или обращении за поддержкой."); note.setObjectName("Muted"); note.setWordWrap(True); al.addWidget(note)
        v=QLabel(f"Версия: {APP_VERSION}\nФайл данных: {DB_PATH}\nАдрес возврата DonationAlerts: {DONATIONALERTS_REDIRECT_URI}"); v.setObjectName("Muted"); v.setTextInteractionFlags(Qt.TextSelectableByMouse); v.setWordWrap(True); al.addWidget(v); layout.addWidget(app); layout.addStretch()

    def _switch_page(self, index: int) -> None:
        index=max(0,min(index,self.stack.count()-1)); old=self.stack.currentIndex()
        self.stack.setCurrentIndex(index); self.nav_buttons[index].setChecked(True)
        name, subtitle = self.page_meta[index]; self.page_title.setText(name); self.page_subtitle.setText(subtitle)
        self._refresh_status_only()
        if index==self.PAGE_HOME:
            self._refresh_session()
            ent_state=self.entertainment_service.snapshot(max_entries=1)
            self._sync_timer_visibility_buttons(bool(ent_state.get("timer_visible",False)))
            self._sync_interactive_visibility_buttons(bool(ent_state.get("interactive_visible",False)), str(ent_state.get("active_mode") or "manual"))
        elif index==self.PAGE_OVERLAY:
            ent_state=self.entertainment_service.snapshot(max_entries=1)
            self._sync_timer_visibility_buttons(bool(ent_state.get("timer_visible",False)))
        elif index==self.PAGE_DONATIONS:
            self._refresh_donations(force=self._donations_signature is None)
        elif index==self.PAGE_ANALYSIS:
            self._analysis_release_generation += 1
            self._populate_analysis_sessions()
            self._refresh_analysis(force=self._analysis_signature is None)
        elif index==self.PAGE_ENTERTAINMENT:
            self._refresh_entertainment()
        elif index==self.PAGE_SESSIONS:
            self._refresh_session(); self._refresh_sessions_archive(force=self._sessions_signature is None)
        elif index==self.PAGE_HISTORY:
            self._refresh_history(force=self._history_signature is None)
        elif index==self.PAGE_SETTINGS:
            self._refresh_storage_usage()
        if old==self.PAGE_ANALYSIS and index!=self.PAGE_ANALYSIS:
            self._analysis_release_generation += 1
            token=self._analysis_release_generation
            QTimer.singleShot(30000, lambda t=token:self._maybe_release_analysis_memory(t))

    def _maybe_release_analysis_memory(self, token: int) -> None:
        if token==self._analysis_release_generation and self.stack.currentIndex()!=self.PAGE_ANALYSIS:
            self._release_analysis_memory()

    def _set_ui_theme(self, mode: str) -> None:
        mode = mode if mode in {"light", "gradient", "night"} else "gradient"
        self.ui_theme = mode
        self.storage.set_setting("ui_theme", mode)
        self.setStyleSheet(_build_style(mode))
        if hasattr(self, "mode_buttons"):
            for key, btn in self.mode_buttons.items():
                btn.blockSignals(True); btn.setChecked(key == mode); btn.blockSignals(False)
        if hasattr(self, "central_root"):
            self.central_root.set_mode(mode)
        for name in ("analysis_donation_timeline","analysis_viewer_timeline","analysis_chat_timeline","analysis_speech_timeline","analysis_chat_cloud","analysis_speech_cloud","entertainment_wheel"):
            widget=getattr(self,name,None)
            if widget is not None:
                widget.set_mode(mode)
        names={"light":"Дневной режим","gradient":"Градиентовый режим","night":"Ночной режим"}
        self.statusBar().showMessage(f"{names[mode]} включён", 2200)

    def _select_theme(self, theme: str) -> None:
        if theme not in self.theme_buttons:
            theme="classic"
        self.selected_theme=theme
        for key,btn in self.theme_buttons.items():
            btn.blockSignals(True); btn.setChecked(key==theme); btn.blockSignals(False)
            apply_btn = self.theme_apply_buttons.get(key)
            if apply_btn is not None:
                apply_btn.setVisible(key == theme)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event); self._update_responsive_layout()

    def _update_responsive_layout(self) -> None:
        compact=self.width()<self.COMPACT_WIDTH
        if compact==self._compact:
            return
        self._compact=compact
        self.sidebar.setFixedWidth(156 if compact else 182)
        self._arrange_compact() if compact else self._arrange_wide()

    def _arrange_wide(self) -> None:
        self._clear_layout(self.home_top_grid)
        for col in range(3): self.home_top_grid.setColumnStretch(col,0)
        # Возвращаем боевую компоновку: слева система + ставка, справа расширенная сессия.
        # Левая колонка немного шире, чтобы управление ставкой не выталкивало интерфейс за границы окна.
        self.home_top_grid.addWidget(self.status_card,0,0)
        self.home_top_grid.addWidget(self.rate_card,1,0)
        self.home_top_grid.addWidget(self.home_session_card,0,1,2,1)
        self.home_top_grid.setColumnStretch(0,11); self.home_top_grid.setColumnStretch(1,9)
        self._clear_layout(self.rate_grid)
        for col in range(6): self.rate_grid.setColumnStretch(col,0)
        # Поля ставки остаются в одной строке, а кнопка применения находится сразу под ними.
        # Так двухколоночная Главная комфортно помещается даже в обычном оконном режиме.
        self.rate_grid.addWidget(self.rate_amount,0,0); self.rate_grid.addWidget(self.rate_eq,0,1); self.rate_grid.addWidget(self.rate_minutes,0,2); self.rate_grid.addWidget(self.rate_seconds,0,3)
        self.rate_grid.addWidget(self.apply_rate_btn,1,0,1,4)
        self.rate_grid.setColumnStretch(0,2); self.rate_grid.setColumnStretch(2,1); self.rate_grid.setColumnStretch(3,1)
        self._clear_layout(self.presets_grid)
        for col in range(4): self.presets_grid.setColumnStretch(col,0)
        self.presets_grid.addWidget(self.preset_label,0,0,1,4)
        for i,btn in enumerate(self.preset_buttons):
            self.presets_grid.addWidget(btn,1,i); self.presets_grid.setColumnStretch(i,1)
        self._clear_layout(self.adjustments_grid)
        for col in range(6): self.adjustments_grid.setColumnStretch(col,0)
        for i,btn in enumerate(self.adjustment_buttons): self.adjustments_grid.addWidget(btn,0,i); self.adjustments_grid.setColumnStretch(i,1)
        self._clear_layout(self.control_grid)
        for col in range(5): self.control_grid.setColumnStretch(col,0)
        self.control_grid.addWidget(self.pause_btn,0,0); self.control_grid.addWidget(self.exact_btn,0,1); self.control_grid.addWidget(self.undo_btn,0,2); self.control_grid.setColumnStretch(3,1); self.control_grid.addWidget(self.reset_btn,0,4)
        self._arrange_theme_grid(2)
        self._clear_layout(self.home_bottom_grid)
        for col in range(3): self.home_bottom_grid.setColumnStretch(col,0)
        self.home_bottom_grid.addWidget(self.last_card,0,0); self.home_bottom_grid.addWidget(self.quick_overlay_card,0,1)
        self.home_bottom_grid.setColumnStretch(0,1); self.home_bottom_grid.setColumnStretch(1,1)

    def _arrange_compact(self) -> None:
        self._clear_layout(self.home_top_grid)
        for col in range(3): self.home_top_grid.setColumnStretch(col,0)
        self.home_top_grid.addWidget(self.status_card,0,0)
        self.home_top_grid.addWidget(self.home_session_card,1,0)
        self.home_top_grid.addWidget(self.rate_card,2,0)
        self.home_top_grid.setColumnStretch(0,1)
        self._clear_layout(self.rate_grid)
        for col in range(6): self.rate_grid.setColumnStretch(col,0)
        self.rate_grid.addWidget(self.rate_amount,0,0); self.rate_grid.addWidget(self.rate_eq,0,1); self.rate_grid.addWidget(self.rate_minutes,0,2); self.rate_grid.addWidget(self.rate_seconds,0,3); self.rate_grid.addWidget(self.apply_rate_btn,1,0,1,4)
        self.rate_grid.setColumnStretch(0,2); self.rate_grid.setColumnStretch(2,1); self.rate_grid.setColumnStretch(3,1)
        self._clear_layout(self.presets_grid)
        for col in range(6): self.presets_grid.setColumnStretch(col,0)
        self.presets_grid.addWidget(self.preset_label,0,0,1,2)
        for i,btn in enumerate(self.preset_buttons):
            row,col=1+i//2,i%2; self.presets_grid.addWidget(btn,row,col); self.presets_grid.setColumnStretch(col,1)
        self._clear_layout(self.adjustments_grid)
        for col in range(6): self.adjustments_grid.setColumnStretch(col,0)
        for i,btn in enumerate(self.adjustment_buttons):
            row,col=divmod(i,3); self.adjustments_grid.addWidget(btn,row,col); self.adjustments_grid.setColumnStretch(col,1)
        self._clear_layout(self.control_grid)
        for col in range(5): self.control_grid.setColumnStretch(col,0)
        for i,btn in enumerate((self.pause_btn,self.exact_btn,self.undo_btn,self.reset_btn)):
            row,col=divmod(i,2); self.control_grid.addWidget(btn,row,col); self.control_grid.setColumnStretch(col,1)
        self._arrange_theme_grid(1)
        self._clear_layout(self.home_bottom_grid)
        for col in range(3): self.home_bottom_grid.setColumnStretch(col,0)
        self.home_bottom_grid.addWidget(self.last_card,0,0); self.home_bottom_grid.addWidget(self.quick_overlay_card,1,0); self.home_bottom_grid.setColumnStretch(0,1)

    def _arrange_theme_grid(self, columns: int) -> None:
        self._clear_layout(self.theme_grid)
        for col in range(3): self.theme_grid.setColumnStretch(col,0)
        for i,(_,key,_) in enumerate(THEMES):
            row,col=divmod(i,columns); self.theme_grid.addWidget(self.theme_widgets[key],row,col); self.theme_grid.setColumnStretch(col,1)

    # ---------- refresh ----------

    def _refresh_profiles(self) -> None:
        current_id=self.state.profile.id
        self.profile_combo.blockSignals(True); self.profile_combo.clear()
        for profile in self.storage.list_profiles():
            label=profile.name if profile.da_user_id else f"{profile.name} · локальный"
            self.profile_combo.addItem(label,profile.id)
            if profile.id==current_id: self.profile_combo.setCurrentIndex(self.profile_combo.count()-1)
        self.profile_combo.blockSignals(False)

    def _profile_changed(self,index:int) -> None:
        profile_id=self.profile_combo.itemData(index)
        if profile_id and profile_id!=self.state.profile.id:
            if hasattr(self,"analysis_donation_timeline"): self._release_analysis_memory()
            self.state.switch_profile(int(profile_id)); self._history_signature=None; self._sessions_signature=None; self._donations_signature=None; self._analysis_signature=None; self._analysis_context_key=None; self._selected_session_id=None; self._refresh()

    def _periodic_refresh(self) -> None:
        """Keep the live dashboard fresh without rebuilding hidden pages."""
        now=time.time(); page=self.stack.currentIndex()
        self._refresh_status_only()
        if page in {self.PAGE_HOME,self.PAGE_SESSIONS}:
            self._refresh_session()
        if page==self.PAGE_HISTORY and now-self._last_history_refresh_at>=2.0:
            self._last_history_refresh_at=now; self._refresh_history()
        elif page==self.PAGE_SESSIONS and now-self._last_sessions_refresh_at>=2.0:
            self._last_sessions_refresh_at=now; self._refresh_sessions_archive()
        elif page==self.PAGE_DONATIONS and now-self._last_donations_refresh_at>=3.0:
            self._last_donations_refresh_at=now; self._refresh_donations()
        elif page==self.PAGE_ANALYSIS and now-self._analysis_last_refresh_at>=6.0:
            self._refresh_analysis()
        elif page==self.PAGE_ENTERTAINMENT:
            self._refresh_entertainment()

        # Account discovery does not need to hit SQLite every UI tick.
        # A long donathon can keep the app open for days, so retention is checked
        # periodically instead of only once at startup. The actual cleanup still
        # runs at most once per calendar day.
        if now-self._last_retention_check_at>=3600.0:
            self._last_retention_check_at=now
            self._run_auto_cleanup_if_due()

        if now-self._last_profile_check_at>=5.0:
            self._last_profile_check_at=now
            known={self.profile_combo.itemData(i) for i in range(self.profile_combo.count())}; actual={p.id for p in self.storage.list_profiles()}
            if known!=actual: self._refresh_profiles()
            pending=(self.storage.get_setting("pending_connected_profile_id") or "").strip()
            if pending.isdigit():
                profile_id=int(pending); self.storage.set_setting("pending_connected_profile_id",""); self._refresh_profiles()
                for i in range(self.profile_combo.count()):
                    if self.profile_combo.itemData(i)==profile_id:
                        self.profile_combo.setCurrentIndex(i)
                        if self.state.profile.id!=profile_id: self.state.switch_profile(profile_id)
                        self._history_signature=None; self._sessions_signature=None; self._donations_signature=None; self._analysis_signature=None; self._analysis_context_key=None; self._selected_session_id=None; self._refresh(); self.statusBar().showMessage("DonationAlerts-аккаунт подключён и выбран",4000); break

    def _refresh(self) -> None:
        """Refresh only visible/cheap state; heavy pages load on demand."""
        p=self.state.profile
        self.rate_amount.setValue(p.rate_amount); self.rate_minutes.setValue(p.rate_seconds//60); self.rate_seconds.setValue(p.rate_seconds%60)
        self.overlay_title_edit.setText(p.overlay_title); self.overlay_show_rate.setChecked(p.overlay_show_rate); self._select_theme(p.overlay_theme)
        self.home_overlay_theme.setText(THEME_NAMES.get(p.overlay_theme,"Классический"))
        ent_state=self.entertainment_service.snapshot(max_entries=1)
        self._sync_timer_visibility_buttons(bool(ent_state.get("timer_visible",False)))
        self._sync_interactive_visibility_buttons(bool(ent_state.get("interactive_visible",False)), str(ent_state.get("active_mode") or "manual"))
        self._history_signature=None; self._sessions_signature=None; self._donations_signature=None; self._analysis_signature=None; self._analysis_context_key=None
        self._refresh_status_only(); self._refresh_session()
        page=self.stack.currentIndex()
        if page==self.PAGE_HISTORY: self._refresh_history(force=True)
        elif page==self.PAGE_SESSIONS: self._refresh_sessions_archive(force=True)
        elif page==self.PAGE_DONATIONS: self._refresh_donations(force=True)
        elif page==self.PAGE_ANALYSIS: self._populate_analysis_sessions(); self._refresh_analysis(force=True)
        elif page==self.PAGE_ENTERTAINMENT: self._refresh_entertainment()
        elif page==self.PAGE_SETTINGS: self._refresh_storage_usage()

    @staticmethod
    def _set_status_label(label: QLabel, text: str, object_name: str) -> None:
        changed_style=label.objectName()!=object_name
        if label.text()!=text: label.setText(text)
        if changed_style:
            label.setObjectName(object_name); label.style().unpolish(label); label.style().polish(label)

    def _refresh_status_only(self) -> None:
        remaining=self.state.remaining_seconds(); running=self.state.profile.running and remaining>0
        if running:
            self._set_status_label(self.timer_status,"● Таймер запущен","Good"); self.pause_btn.setText("Пауза")
        elif remaining>0:
            self._set_status_label(self.timer_status,"● Таймер на паузе","Warn"); self.pause_btn.setText("Продолжить")
        else:
            self._set_status_label(self.timer_status,"● Таймер остановлен","Warn"); self.pause_btn.setText("Запустить")
        overlay_live=self.state.overlay_seen_recently()
        self._set_status_label(self.obs_status,"● Оверлей получает данные" if overlay_live else "● Сервер оверлея готов · источник не активен","Good" if overlay_live else "Warn")
        da=self.da_service.status(); good=da.code=="online"
        self._set_status_label(self.da_status,"● "+da.text,"Good" if good else "Warn")
        self._set_status_label(self.account_status_label,"● "+da.text,"Good" if good else "Warn")
        p=self.state.profile
        self.account_profile_label.setText(f"Активный профиль: {p.name}" + (f" · DonationAlerts ID {p.da_user_id}" if p.da_user_id else " · локальный профиль"))
        tw=self.twitch_service.status(); tw_good=tw.code=="online"
        if hasattr(self,"twitch_home_status"):
            self._set_status_label(self.twitch_home_status,"● "+tw.text,"Good" if tw_good else "Warn")
        if hasattr(self,"twitch_status_label"):
            self._set_status_label(self.twitch_status_label,"● "+tw.text,"Good" if tw_good else "Warn")
            if p.twitch_user_id:
                self.twitch_profile_label.setText(f"Связан канал: {p.twitch_display_name or p.twitch_login or p.twitch_user_id}. Онлайн и новые сообщения чата собираются автоматически, пока приложение запущено.")
            else:
                self.twitch_profile_label.setText("Twitch ещё не связан с этим профилем. Подключи его, чтобы собирать онлайн и чат для будущего анализа.")
        if hasattr(self,"speech_status_label"):
            self._update_speech_install_ui()
        if self.stack.currentIndex() in {self.PAGE_HOME,self.PAGE_HISTORY}:
            can_undo=bool(self.storage.list_reversible_events(self.state.profile.id, limit=1))
            self.undo_btn.setEnabled(can_undo); self.history_undo_btn.setEnabled(can_undo)

    def _refresh_session(self) -> None:
        session=self.state.active_session()
        if not session:
            self.session_name_label.setText("Сессия не запущена")
            self.session_meta_label.setText("История всё равно ведётся, но сессия позволяет отделить один донатофон от другого.")
            self.session_elapsed_label.setText("")
            self.session_stats_label.setText("")
            self.end_session_btn.setEnabled(False); self.rename_active_session_btn.setEnabled(False); self.pause_session_btn.setEnabled(False)
            self.home_start_session_btn.setEnabled(True); self.home_pause_session_btn.setEnabled(False); self.home_end_session_btn.setEnabled(False)
            self.pause_session_btn.setText("Приостановить"); self.home_pause_session_btn.setText("Приостановить сессию")
            self.history_scope_label.setText("Последние события профиля")
            self.main_session_name.setText("Сессия не запущена")
            self.main_session_meta.setText("")
            self.main_session_elapsed.setText("")
            self.main_session_stats.setText("История продолжает записываться в профиль.")
            for frame in self.recent_donation_frames: frame.setVisible(False)
            self.no_recent_donations.setText("Запусти сессию — здесь появятся три последних доната."); self.no_recent_donations.setVisible(True)
            return

        started_dt=dt.datetime.fromtimestamp(session.started_at)
        started_full=started_dt.strftime("%d.%m.%Y · %H:%M:%S")
        elapsed=self.storage.session_elapsed_seconds(session)
        stats=self.storage.session_stats(session.id)
        paused=session.paused_at is not None
        status_text="ПАУЗА" if paused else "АКТИВНА"
        stat_text=f"Донатов: {stats['donation_count']} · Получено: {_format_money(stats['donation_amount'],'RUB')} · Добавлено: {_format_duration(stats['donation_seconds'])}"

        self.session_name_label.setText(session.name)
        self.session_meta_label.setText(f"Запущена: {started_full} · Статус: {status_text} · Стартовое время таймера: {_format_duration(session.starting_seconds)}")
        self.session_elapsed_label.setText(f"Сессия {'на паузе' if paused else 'идёт'}: {_format_duration(elapsed)}")
        self.session_stats_label.setText(stat_text)
        self.end_session_btn.setEnabled(True); self.rename_active_session_btn.setEnabled(True); self.pause_session_btn.setEnabled(True)
        self.home_start_session_btn.setEnabled(False); self.home_pause_session_btn.setEnabled(True); self.home_end_session_btn.setEnabled(True)
        self.pause_session_btn.setText("Продолжить" if paused else "Приостановить")
        self.home_pause_session_btn.setText("Продолжить сессию" if paused else "Приостановить сессию")
        self.history_scope_label.setText("Текущая сессия · пауза" if paused else "Текущая сессия")

        self.main_session_name.setText(session.name)
        self.main_session_meta.setText(f"Старт: {started_full} · {status_text}")
        self.main_session_elapsed.setText(f"{'На паузе' if paused else 'Идёт уже'}: {_format_duration(elapsed)}")
        self.main_session_stats.setText(stat_text)

        donations=self.storage.recent_donations(self.state.profile.id, session_id=session.id, limit=3)
        self.no_recent_donations.setVisible(not donations)
        if not donations:
            self.no_recent_donations.setText("Пока в этой сессии нет донатов.")
        for i, frame in enumerate(self.recent_donation_frames):
            if i >= len(donations):
                frame.setVisible(False); continue
            event=donations[i]
            when=dt.datetime.fromtimestamp(event.created_at).strftime("%H:%M:%S")
            donor=event.title or "Аноним"
            self.recent_donation_main_labels[i].setText(f"{when} · {donor}")
            delta=_format_duration(event.seconds_delta, signed=True) if event.seconds_delta else "+00:00:00"
            status=" · ОТМЕНЕНО" if event.undone else ""
            self.recent_donation_sub_labels[i].setText(f"{_format_money(event.amount,event.currency)} · добавил {delta}{status}")
            frame.setVisible(True)

    def _summary_duration(self, summary: dict, now: float | None = None) -> int:
        now = dt.datetime.now().timestamp() if now is None else float(now)
        endpoint = summary['ended_at'] if summary['ended_at'] is not None else now
        paused = float(summary.get('paused_total') or 0)
        if summary['ended_at'] is None and summary.get('paused_at') is not None:
            paused += max(0.0, now - float(summary['paused_at']))
        return max(0, int(endpoint - summary['started_at'] - paused))

    def _refresh_sessions_archive(self, force: bool=False) -> None:
        summaries=self.storage.list_session_summaries(self.state.profile.id, limit=150)
        signature=tuple((x['id'],x['name'],x['ended_at'],x.get('paused_at'),round(float(x.get('paused_total') or 0),2),x['donation_count'],round(x['donation_amount'],2),x['donation_seconds']) for x in summaries)

        if force or signature!=self._sessions_signature:
            selected=self._selected_session_id
            self._sessions_signature=signature
            self.sessions_table.blockSignals(True)
            self.sessions_table.setRowCount(len(summaries))
            now=dt.datetime.now().timestamp()
            select_row=-1
            for row,summary in enumerate(summaries):
                ended=summary['ended_at']
                duration=self._summary_duration(summary, now)
                finish_text = dt.datetime.fromtimestamp(ended).strftime("%d.%m.%Y %H:%M") if ended else ("Пауза" if summary.get('paused_at') is not None else "Идёт сейчас")
                values=(
                    summary['name'],
                    dt.datetime.fromtimestamp(summary['started_at']).strftime("%d.%m.%Y %H:%M"),
                    finish_text,
                    _format_duration(duration),
                    str(summary['donation_count']),
                    _format_money(summary['donation_amount'],'RUB'),
                    _format_duration(summary['donation_seconds']),
                )
                for col,text in enumerate(values):
                    item=QTableWidgetItem(text); item.setData(Qt.UserRole, summary['id']); self.sessions_table.setItem(row,col,item)
                if selected==summary['id']:
                    select_row=row
            if select_row<0 and summaries:
                active=next((x for x in summaries if x['ended_at'] is None),None)
                wanted=(active or summaries[0])['id']; self._selected_session_id=wanted
                select_row=next((i for i,x in enumerate(summaries) if x['id']==wanted),0)
            if select_row>=0:
                self.sessions_table.selectRow(select_row)
            self.sessions_table.blockSignals(False)
        else:
            now=dt.datetime.now().timestamp()
            for row,summary in enumerate(summaries):
                if summary['ended_at'] is None:
                    item=self.sessions_table.item(row,3)
                    if item: item.setText(_format_duration(self._summary_duration(summary, now)))
                    finish=self.sessions_table.item(row,2)
                    if finish: finish.setText("Пауза" if summary.get('paused_at') is not None else "Идёт сейчас")

        selected_summary=next((x for x in summaries if x['id']==self._selected_session_id),None)
        self.rename_selected_session_btn.setEnabled(bool(selected_summary))
        self.delete_selected_session_btn.setEnabled(bool(selected_summary and selected_summary['ended_at'] is not None))
        self._refresh_selected_session_detail(summaries)

    def _refresh_selected_session_detail(self, summaries: list[dict] | None = None) -> None:
        if summaries is None:
            summaries=self.storage.list_session_summaries(self.state.profile.id, limit=150)
        summary=next((x for x in summaries if x['id']==self._selected_session_id),None)
        if not summary:
            self.selected_session_name.setText("Выбери сессию выше")
            self.selected_session_meta.setText("")
            self.selected_session_stats.setText("")
            self.donor_ranking_table.setRowCount(0)
            self.rename_selected_session_btn.setEnabled(False)
            self.delete_selected_session_btn.setEnabled(False)
            return

        ended=summary['ended_at']; now=dt.datetime.now().timestamp(); duration=self._summary_duration(summary, now)
        start_text=dt.datetime.fromtimestamp(summary['started_at']).strftime("%d.%m.%Y %H:%M:%S")
        end_text=dt.datetime.fromtimestamp(ended).strftime("%d.%m.%Y %H:%M:%S") if ended else ("пауза" if summary.get('paused_at') is not None else "идёт сейчас")
        self.selected_session_name.setText(summary['name'])
        self.selected_session_meta.setText(f"Старт: {start_text} · Завершение: {end_text} · Длительность: {_format_duration(duration)}")
        self.selected_session_stats.setText(
            f"Донатов: {summary['donation_count']} · Получено: {_format_money(summary['donation_amount'],'RUB')} · "
            f"Таймер продлён на: {_format_duration(summary['donation_seconds'])}"
        )
        ranking=self.storage.session_donor_ranking(summary['id'], limit=100)
        self.donor_ranking_table.setRowCount(len(ranking))
        for row,item_data in enumerate(ranking):
            values=(item_data['donor'],str(item_data['donation_count']),_format_money(item_data['donation_amount'],'RUB'),_format_duration(item_data['donation_seconds']))
            for col,text in enumerate(values):
                item=QTableWidgetItem(text); self.donor_ranking_table.setItem(row,col,item)
        self.rename_selected_session_btn.setEnabled(True)
        self.delete_selected_session_btn.setEnabled(summary['ended_at'] is not None)

    def _session_selection_changed(self) -> None:
        rows=self.sessions_table.selectionModel().selectedRows()
        if not rows:
            return
        item=self.sessions_table.item(rows[0].row(),0)
        if not item:
            return
        self._selected_session_id=int(item.data(Qt.UserRole))
        self._refresh_selected_session_detail()

    def _refresh_history(self, force: bool=False) -> None:
        session=self.state.active_session(); session_id=session.id if session else None
        events=self.storage.list_events(self.state.profile.id,limit=200,session_id=session_id)
        signature=tuple((e.id,e.undone,e.seconds_delta,e.title) for e in events)
        if not force and signature==self._history_signature: return
        self._history_signature=signature
        labels={"donation":"Донат","manual":"Время","rate":"Ставка","overlay":"Оверлей","timer":"Таймер","session":"Сессия","undo":"Отмена"}
        header=self.history_table.horizontalHeader()
        sort_col=header.sortIndicatorSection(); sort_order=header.sortIndicatorOrder()
        self.history_table.setSortingEnabled(False)
        self.history_table.setRowCount(len(events))
        for row,e in enumerate(events):
            when=dt.datetime.fromtimestamp(e.created_at).strftime("%d.%m.%Y %H:%M:%S")
            type_text=labels.get(e.kind,e.kind); detail=e.title
            if e.kind=="donation": detail=f"{e.title} · {_format_money(e.amount,e.currency)}"
            if e.undone: detail += " · ОТМЕНЕНО"
            delta=_format_duration(e.seconds_delta,signed=True) if e.seconds_delta else "—"
            items=(
                SortTableItem(when, e.created_at),
                SortTableItem(type_text, type_text.casefold()),
                SortTableItem(detail, detail.casefold()),
                SortTableItem(delta, e.seconds_delta),
            )
            for col,item in enumerate(items):
                item.setToolTip(detail); self.history_table.setItem(row,col,item)
        self.history_table.setSortingEnabled(True)
        self.history_table.sortItems(sort_col if sort_col >= 0 else 0, sort_order)
        self.history_table.resizeRowsToContents()
        if events:
            e=events[0]; when=dt.datetime.fromtimestamp(e.created_at).strftime("%H:%M:%S"); detail=e.title
            if e.kind=="donation": detail=f"Донат: {e.title} · {_format_money(e.amount,e.currency)} · {_format_duration(e.seconds_delta,signed=True)}"
            self.last_event_label.setText(f"{when} · {detail}")
        else:
            self.last_event_label.setText("Пока нет событий")

    def _donation_period_bounds(self) -> tuple[float | None, float | None]:
        index = self.donation_period_combo.currentIndex()
        now = dt.datetime.now()
        if index == 0:
            return None, None
        if index == 1:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start.timestamp(), now.timestamp()
        if index == 2:
            return (now - dt.timedelta(days=7)).timestamp(), now.timestamp()
        if index == 3:
            return (now - dt.timedelta(days=30)).timestamp(), now.timestamp()
        start = float(self.donation_from.dateTime().toSecsSinceEpoch())
        end = float(self.donation_to.dateTime().toSecsSinceEpoch())
        if start > end:
            start, end = end, start
        return start, end

    def _update_donation_filter_visibility(self) -> None:
        if hasattr(self,"donation_custom_widget"):
            self.donation_custom_widget.setVisible(self.donation_period_combo.currentIndex()==4)

    def _donation_filter_key(self) -> tuple:
        idx=self.donation_period_combo.currentIndex(); today=dt.date.today().isoformat()
        if idx==4:
            return (idx,int(self.donation_from.dateTime().toSecsSinceEpoch()),int(self.donation_to.dateTime().toSecsSinceEpoch()))
        return (idx,today)

    def _donation_period_changed(self) -> None:
        if not hasattr(self, "donation_period_combo"):
            return
        self._update_donation_filter_visibility()
        self._donations_signature = None
        if self.stack.currentIndex()==self.PAGE_DONATIONS:
            self._refresh_donations(force=True)

    def _custom_period_changed(self) -> None:
        if hasattr(self, "donation_period_combo") and self.donation_period_combo.currentIndex() == 4:
            self._donations_signature = None
            if self.stack.currentIndex()==self.PAGE_DONATIONS:
                self._refresh_donations(force=True)

    def _refresh_donations(self, force: bool=False) -> None:
        if not hasattr(self, "donations_table"):
            return
        profile_id=self.state.profile.id
        signature=(profile_id,self._donation_filter_key(),self.storage.donation_revision(profile_id))
        if not force and signature == self._donations_signature:
            return
        self._donations_signature = signature
        start_ts, end_ts = self._donation_period_bounds()
        all_summary = self.storage.donation_summary(profile_id)
        summary = self.storage.donation_summary(profile_id, start_ts=start_ts, end_ts=end_ts)
        records = self.storage.donation_records(profile_id, start_ts=start_ts, end_ts=end_ts, limit=2000)

        self.metric_labels["all_total"].setText(_format_money(all_summary["total"], "RUB"))
        self.metric_labels["period_total"].setText(_format_money(summary["total"], "RUB"))
        self.metric_labels["period_count"].setText(str(summary["count"]))
        self.metric_labels["period_avg"].setText(_format_money(summary["average"], "RUB"))
        top = summary["top_donor"]
        top_total = _format_money(summary["top_donor_total"], "RUB")
        self.metric_labels["period_top"].setText(f"{top}\n{top_total}" if summary["count"] else "—")
        self.metric_labels["period_time"].setText(_format_duration(summary["seconds"]))

        header = self.donations_table.horizontalHeader()
        sort_col = header.sortIndicatorSection(); sort_order = header.sortIndicatorOrder()
        self.donations_table.setSortingEnabled(False)
        self.donations_table.setRowCount(len(records))
        for row, record in enumerate(records):
            event = record["event"]
            when = dt.datetime.fromtimestamp(event.created_at).strftime("%d.%m.%Y %H:%M:%S")
            donor = event.title or "Аноним"
            amount = _format_money(event.amount, event.currency)
            credited = event.credited_amount if event.credited_amount is not None else float(event.amount or 0)
            if event.currency and event.currency.upper() not in {"RUB","RUR"}:
                amount = f"{amount} → {_format_money(credited,'RUB')}"
            session_name = record["session_name"] or "—"
            delta = _format_duration(event.seconds_delta, signed=True) if event.seconds_delta else "+00:00:00"
            status = "Отменено" if event.undone else "Учтён"
            items = (
                SortTableItem(when, event.created_at),
                SortTableItem(donor, donor.casefold()),
                SortTableItem(amount, float(credited or 0)),
                SortTableItem(session_name, session_name.casefold()),
                SortTableItem(delta, event.seconds_delta),
                SortTableItem(status, 1 if event.undone else 0),
            )
            for col,item in enumerate(items):
                item.setData(Qt.UserRole, event.id)
                self.donations_table.setItem(row,col,item)
        self.donations_table.setSortingEnabled(True)
        self.donations_table.sortItems(sort_col if sort_col >= 0 else 0, sort_order)
        self._filter_donation_rows()

    def _filter_donation_rows(self) -> None:
        if not hasattr(self, "donations_table"):
            return
        query = self.donation_search.text().strip().casefold() if hasattr(self, "donation_search") else ""
        for row in range(self.donations_table.rowCount()):
            item = self.donations_table.item(row, 1)
            donor = item.text().casefold() if item else ""
            self.donations_table.setRowHidden(row, bool(query and query not in donor))

    def _show_donor_details_from_row(self, row: int, column: int) -> None:
        if row < 0 or not hasattr(self, "donations_table"):
            return
        donor_item = self.donations_table.item(row, 1)
        if not donor_item:
            return
        donor = donor_item.text().strip() or "Аноним"
        summary = self.storage.donation_summary(self.state.profile.id, donor=donor)
        records = self.storage.donation_records(self.state.profile.id, donor=donor, limit=10000)
        dlg = DonorDetailsDialog(donor, summary, records, self)
        dlg.exec()

    def _analysis_scope_changed(self) -> None:
        if not hasattr(self,"analysis_scope_combo"):
            return
        by_session=self.analysis_scope_combo.currentIndex()==1
        self.analysis_period_label.setVisible(not by_session); self.analysis_period_combo.setVisible(not by_session)
        # Keep the session selector discoverable even if the current filter is a
        # time period. Selecting any session switches the complete page to it.
        self.analysis_session_label.setVisible(True); self.analysis_session_combo.setVisible(True)
        self._populate_analysis_sessions()
        self._update_analysis_filter_visibility()
        self._analysis_signature=None; self._analysis_context_key=None
        if self.stack.currentIndex()==self.PAGE_ANALYSIS:
            self._refresh_analysis(force=True)

    def _update_analysis_filter_visibility(self) -> None:
        if not hasattr(self,"analysis_custom_widget"):
            return
        by_session=self.analysis_scope_combo.currentIndex()==1
        custom=(not by_session) and self.analysis_period_combo.currentIndex()==4
        self.analysis_custom_widget.setVisible(custom)

    def _analysis_period_changed(self) -> None:
        if not hasattr(self,"analysis_period_combo"):
            return
        self._update_analysis_filter_visibility()
        self._analysis_signature=None; self._analysis_context_key=None
        if self.stack.currentIndex()==self.PAGE_ANALYSIS:
            self._refresh_analysis(force=True)

    def _analysis_custom_period_changed(self) -> None:
        if hasattr(self,"analysis_period_combo") and self.analysis_scope_combo.currentIndex()==0 and self.analysis_period_combo.currentIndex()==4:
            self._analysis_signature=None; self._analysis_context_key=None
            if self.stack.currentIndex()==self.PAGE_ANALYSIS:
                self._refresh_analysis(force=True)

    def _populate_analysis_sessions(self) -> None:
        """Reconcile both selectors without rebuilding an open Qt popup.

        Recreating QComboBox items every 1.2 seconds closes its dropdown and
        makes it seem impossible to click a session. Rebuild only if the DB
        contents changed, e.g. after creating, renaming or ending a session.
        """
        if not hasattr(self, "analysis_session_combo"):
            return
        sessions=self.storage.list_sessions(self.state.profile.id,limit=500)
        items=[]
        for item in sessions:
            started=dt.datetime.fromtimestamp(item.started_at).strftime("%d.%m.%Y %H:%M")
            suffix=" · идёт" if item.ended_at is None else ""
            items.append((f"{item.name} · {started}{suffix}",item.id))
        profile=self.state.profile.id
        signature=(profile,tuple(items))
        if signature==getattr(self,"_analysis_sessions_list_signature",None):
            return
        combos=[self.analysis_session_combo]
        if hasattr(self,"speech_session_combo"):
            combos.append(self.speech_session_combo)
        # Never replace a popup's model while the user is clicking an entry.
        if any(c.view().isVisible() for c in combos):
            return
        same_profile=profile==getattr(self,"_analysis_sessions_profile",None)
        previous=self.analysis_session_combo.currentData() if same_profile else None
        self._analysis_sessions_profile=profile
        self._analysis_sessions_list_signature=signature
        valid_ids={item_id for _,item_id in items}
        chosen=previous if previous in valid_ids else (items[0][1] if items else None)
        for combo in combos:
            combo.blockSignals(True)
            combo.clear()
            if not items:
                combo.addItem("Нет сессий — сначала создай сессию",None)
            else:
                for label,session_id in items:
                    combo.addItem(label,session_id)
                index=combo.findData(chosen)
                if index>=0: combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _analysis_session_changed(self, sender: QComboBox) -> None:
        """Sync top/bottom selection, even on re-click of the only item.

        The QComboBox.activated signal is deliberate: currentIndexChanged does
        not fire when clicking an already-selected (often only) session.
        """
        if not hasattr(self,"speech_session_combo"):
            return
        session_id=sender.currentData()
        if session_id is None:
            return
        for combo in (self.analysis_session_combo,self.speech_session_combo):
            if combo is not sender:
                index=combo.findData(session_id)
                if index>=0:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(index)
                    combo.blockSignals(False)
        self._analysis_signature=None
        self._analysis_context_key=None
        self._speech_recording_info_key=None
        if self.analysis_scope_combo.currentIndex()!=1:
            # Emits _analysis_scope_changed(), which updates all four graphs.
            self.analysis_scope_combo.setCurrentIndex(1)
        elif self.stack.currentIndex()==self.PAGE_ANALYSIS:
            self._refresh_analysis(force=True)
        self._update_speech_install_ui()

    def _analysis_period_bounds(self) -> tuple[float|None,float|None]:
        idx=self.analysis_period_combo.currentIndex(); now=dt.datetime.now()
        if idx==0:
            start=now.replace(hour=0,minute=0,second=0,microsecond=0); return start.timestamp(),now.timestamp()
        if idx==1: return (now-dt.timedelta(days=7)).timestamp(),now.timestamp()
        if idx==2: return (now-dt.timedelta(days=30)).timestamp(),now.timestamp()
        if idx==3: return None,None
        start=float(self.analysis_from.dateTime().toSecsSinceEpoch()); end=float(self.analysis_to.dateTime().toSecsSinceEpoch())
        if end<start: start,end=end,start
        return start,end

    def _analysis_context(self) -> tuple[int|None,float|None,float|None,str]:
        by_session=self.analysis_scope_combo.currentIndex()==1
        if by_session:
            session_id=self.analysis_session_combo.currentData()
            if session_id is None: return None,None,None,"Создай или выбери сессию — после этого здесь появятся её графики."
            session=self.storage.get_session(self.state.profile.id,int(session_id))
            if not session: return None,None,None,"Сессия не найдена"
            start_ts=session.started_at; end_ts=session.ended_at or time.time()
            return int(session_id),start_ts,end_ts,f"Сессия «{session.name}» · {dt.datetime.fromtimestamp(start_ts):%d.%m.%Y %H:%M} — {dt.datetime.fromtimestamp(end_ts):%d.%m.%Y %H:%M}"
        start_ts,end_ts=self._analysis_period_bounds()
        if start_ts is None and end_ts is None: return None,None,None,"За всё время текущего профиля"
        return None,start_ts,end_ts,f"{dt.datetime.fromtimestamp(start_ts):%d.%m.%Y %H:%M} — {dt.datetime.fromtimestamp(end_ts):%d.%m.%Y %H:%M}"

    def _set_analysis_section_metrics(self, section: str, entries: list[tuple[str,str]]) -> None:
        for idx,(value_label,caption_label) in enumerate(self.analysis_section_metrics.get(section,[])):
            value,caption=entries[idx] if idx<len(entries) else ("—","—")
            value_label.setText(str(value)); caption_label.setText(str(caption))

    def _clear_analysis_sections(self, caption: str) -> None:
        self.analysis_context_label.setText(caption)
        for section in ("donations","viewers","chat","speech"):
            self._set_analysis_section_metrics(section,[("—","Нет данных"),("—","—"),("—","—"),("—","—")])
        empty=dict(donations=[],viewers=[],chat=[],speech=[],start_ts=None,end_ts=None,query="")
        self.analysis_donation_timeline.set_data(source="donations",**empty)
        self.analysis_viewer_timeline.set_data(source="viewers",**empty)
        self.analysis_chat_timeline.set_data(source="chat",**empty)
        self.analysis_speech_timeline.set_data(source="speech",**empty)
        self.analysis_chat_cloud.set_words(Counter()); self.analysis_speech_cloud.set_words(Counter())

    def _analysis_filter_key(self, session_id: int | None) -> tuple:
        if self.analysis_scope_combo.currentIndex()==1:
            session=self.storage.get_session(self.state.profile.id,int(session_id)) if session_id is not None else None
            return ("session",session_id,session.ended_at if session else None)
        idx=self.analysis_period_combo.currentIndex()
        if idx==4:
            return ("period",idx,int(self.analysis_from.dateTime().toSecsSinceEpoch()),int(self.analysis_to.dateTime().toSecsSinceEpoch()))
        # Relative presets only need a new refresh when data changes or the day changes.
        return ("period",idx,dt.date.today().isoformat())

    def _refresh_analysis(self, force: bool=False) -> None:
        if not hasattr(self,"analysis_donation_timeline"):
            return
        session_id,start_ts,end_ts,caption=self._analysis_context(); profile_id=self.state.profile.id
        if self.analysis_scope_combo.currentIndex()==1 and session_id is None:
            signature=(profile_id,"no-session")
            if not force and signature==self._analysis_signature:
                self._analysis_last_refresh_at=time.time(); return
            self._analysis_signature=signature; self._analysis_context_key=("no-session",); self._analysis_last_refresh_at=time.time(); self._clear_analysis_sections(caption); self.transcribe_btn.setEnabled(False); self._update_speech_install_ui(); return

        filter_key=self._analysis_filter_key(session_id)
        context_changed=filter_key!=self._analysis_context_key
        revision=self.storage.analytics_revision(profile_id)
        signature=(profile_id,filter_key,revision)
        if not force and signature==self._analysis_signature:
            self._analysis_last_refresh_at=time.time(); self._update_speech_install_ui(); return
        self._analysis_signature=signature; self._analysis_context_key=filter_key; self._analysis_last_refresh_at=time.time(); self.analysis_context_label.setText(caption)

        # These are the only sizeable Python lists retained by the Analysis page.
        # Each chart now keeps only its own list, not four duplicate copies.
        donations=self.storage.donation_records(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id,limit=10000)
        viewers=self.storage.viewer_records(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id,limit=30000)
        chat=self.storage.chat_records(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id,limit=30000)
        speech=self.storage.speech_records(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id,limit=30000)
        donation_summary=self.storage.donation_summary(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id)
        viewer_summary=self.storage.viewer_summary(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id)
        chat_summary=self.storage.chat_summary(profile_id,start_ts=start_ts,end_ts=end_ts,session_id=session_id)
        chat_counts,_=_word_counter(chat,"message_text",None); speech_counts,_=_word_counter(speech,"text",None)
        speech_seconds=sum(max(0.0,float(r["ended_at"])-float(r["started_at"])) for r in speech); speech_words=sum(speech_counts.values())
        max_amount=max([float(r["event"].credited_amount if r["event"].credited_amount is not None else (r["event"].amount or 0)) for r in donations] or [0])
        self._set_analysis_section_metrics("donations",[(_format_money(donation_summary["total"],"RUB"),"Сумма"),(str(donation_summary["count"]),"Донатов"),(_format_money(donation_summary["average"],"RUB"),"Средний"),(_format_money(max_amount,"RUB") if donations else "—","Максимальный")])
        self._set_analysis_section_metrics("viewers",[(f"{viewer_summary['average']:.0f}" if viewer_summary["count"] else "—","Средний онлайн"),(str(viewer_summary["maximum"]) if viewer_summary["count"] else "—","Пик"),(str(viewer_summary["minimum"]) if viewer_summary["count"] else "—","Минимум"),(str(viewer_summary["count"]),"Замеров")])
        top_chat=chat_counts.most_common(1)[0][0] if chat_counts else "—"
        self._set_analysis_section_metrics("chat",[(str(chat_summary["count"]),"Сообщений"),(str(chat_summary["unique_users"]),"Участников"),(f"{chat_summary['messages_per_minute']:.1f}","Сообщ./мин"),(top_chat,"Частое слово")])
        top_speech=speech_counts.most_common(1)[0][0] if speech_counts else "—"
        self._set_analysis_section_metrics("speech",[(_format_duration(int(speech_seconds)),"Распознано"),(str(speech_words),"Слов"),(str(len(speech)),"Фрагментов"),(top_speech,"Частое слово")])

        self.analysis_donation_timeline.set_mode(self.ui_theme); self.analysis_donation_timeline.set_data(source="donations",donations=donations,viewers=[],chat=[],speech=[],start_ts=start_ts,end_ts=end_ts,reset_view=context_changed)
        self.analysis_viewer_timeline.set_mode(self.ui_theme); self.analysis_viewer_timeline.set_data(source="viewers",donations=[],viewers=viewers,chat=[],speech=[],start_ts=start_ts,end_ts=end_ts,reset_view=context_changed)
        self.analysis_chat_timeline.set_mode(self.ui_theme); self.analysis_chat_timeline.set_data(source="chat",donations=[],viewers=[],chat=chat,speech=[],start_ts=start_ts,end_ts=end_ts,reset_view=context_changed)
        self.analysis_speech_timeline.set_mode(self.ui_theme); self.analysis_speech_timeline.set_data(source="speech",donations=[],viewers=[],chat=[],speech=speech,start_ts=start_ts,end_ts=end_ts,reset_view=context_changed)
        self.analysis_chat_cloud.set_mode(self.ui_theme); self.analysis_chat_cloud.set_words(chat_counts)
        self.analysis_speech_cloud.set_mode(self.ui_theme); self.analysis_speech_cloud.set_words(speech_counts)
        self._update_speech_install_ui()
        self.transcribe_btn.setEnabled(self.speech_service.has_transcriber() and self.analysis_session_combo.currentData() is not None and self.speech_service.status().code not in {"transcribing", "progress"})

    def _release_analysis_memory(self) -> None:
        for name in ("analysis_donation_timeline","analysis_viewer_timeline","analysis_chat_timeline","analysis_speech_timeline"):
            widget=getattr(self,name,None)
            if widget is not None: widget.release_data()
        if hasattr(self,"analysis_chat_cloud"): self.analysis_chat_cloud.set_words(Counter())
        if hasattr(self,"analysis_speech_cloud"): self.analysis_speech_cloud.set_words(Counter())
        self._analysis_signature=None
        # Let Python release large temporary lists after leaving the analytics page.
        QTimer.singleShot(50, gc.collect)

    def _update_speech_install_ui(self) -> None:
        if not hasattr(self,"speech_status_label"): return
        status=self.speech_service.status()
        active=status.code in {"transcribing", "progress"}
        elapsed=f" · прошло {int(time.time()-self._speech_started_at)} сек." if active and getattr(self,"_speech_started_at",None) else ""
        self.speech_status_label.setText(status.text+elapsed)
        self.speech_progress_bar.setVisible(active or (status.code in {"done", "error"} and status.progress is not None))
        if status.progress is not None:
            self.speech_progress_bar.setRange(0,100)
            self.speech_progress_bar.setValue(max(0,min(100,int(status.progress))))
            self.speech_progress_bar.setFormat("%p%")
        elif active:
            self.speech_progress_bar.setRange(0,0)
        else:
            self.speech_progress_bar.setRange(0,100)
            self.speech_progress_bar.setValue(0)
        # Avoid re-opening audio files on every lightweight UI update.
        sid=self.speech_session_combo.currentData() if hasattr(self,"speech_session_combo") else None
        key=(self.state.profile.id,sid,status.code)
        if getattr(self,"_speech_recording_info_key",None)!=key:
            self._speech_recording_info_key=key
            self.speech_recording_info.setText(self.speech_service.recording_summary(self.state.profile.id,sid))
        if hasattr(self,"install_speech_btn"):
            installed=self.speech_service.has_transcriber(); installing=self.speech_service.installing()
            self.install_speech_btn.setEnabled(not installed and not installing)
            self.install_speech_btn.setText("Анализ речи установлен" if installed else ("Установка…" if installing else "Установить анализ речи"))
        if hasattr(self,"transcribe_btn"):
            self.transcribe_btn.setEnabled(self.speech_service.has_transcriber() and self.analysis_session_combo.currentData() is not None and status.code not in {"transcribing", "progress"})

    def _install_speech_ai(self) -> None:
        if self.speech_service.has_transcriber():
            self._update_speech_install_ui(); return
        answer=QMessageBox.question(self,"Установить анализ речи","Дополнительный компонент анализа речи будет загружен из интернета и установлен в папку приложения для текущего пользователя. Python и BAT-файлы не нужны. Первое распознавание также загрузит модель речи. Продолжить?",QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if answer!=QMessageBox.Yes: return
        try:
            self.speech_service.install_transcriber(); self._update_speech_install_ui(); self.statusBar().showMessage("Установка анализа речи началась в фоне",4000)
        except RuntimeError as exc:
            QMessageBox.information(self,"Анализ речи",str(exc))

    def _speech_model_changed(self, index: int) -> None:
        model=self.speech_model_combo.itemData(index)
        if model:
            self.speech_service.set_model_name(str(model))

    def _refresh_speech_devices(self) -> None:
        if not hasattr(self,"speech_device_combo"): return
        current=self.speech_service.device_index(); self.speech_device_combo.blockSignals(True); self.speech_device_combo.clear(); self.speech_device_combo.addItem("Системный микрофон по умолчанию",None)
        for idx,name in self.speech_service.available_devices(): self.speech_device_combo.addItem(name,idx)
        for i in range(self.speech_device_combo.count()):
            if self.speech_device_combo.itemData(i)==current: self.speech_device_combo.setCurrentIndex(i); break
        self.speech_device_combo.blockSignals(False)

    def _speech_device_changed(self, index: int) -> None:
        self.speech_service.set_device_index(self.speech_device_combo.itemData(index))

    def _speech_enabled_changed(self, checked: bool) -> None:
        self.speech_service.set_enabled(bool(checked)); self._refresh_analysis(force=True)

    def _transcribe_selected_session(self) -> None:
        session_id=self.speech_session_combo.currentData() if hasattr(self,"speech_session_combo") else self.analysis_session_combo.currentData()
        if session_id is None:
            QMessageBox.information(self,"Речь стримера","Сначала создай сессию и запиши голос во время неё.")
            return
        # Transcription should work directly from the footer, even when the
        # viewer was inspecting a time period before clicking this button.
        if self.analysis_scope_combo.currentIndex()!=1 or self.analysis_session_combo.currentData()!=session_id:
            self._analysis_session_changed(self.speech_session_combo)
        try:
            self.speech_service.transcribe_session(self.state.profile.id,int(session_id))
            self._speech_started_at=time.time()
            self._speech_recording_info_key=None
            self._update_speech_install_ui()
            self.statusBar().showMessage("Распознавание запущено. Ход работы виден внизу раздела «Анализ».",6000)
        except RuntimeError as exc:
            QMessageBox.information(self,"Речь стримера",str(exc))

    @staticmethod
    def _format_bytes(value: int) -> str:
        n=float(max(0,int(value)))
        for unit in ("Б","КБ","МБ","ГБ","ТБ"):
            if n<1024 or unit=="ТБ":
                return f"{n:.0f} {unit}" if unit in {"Б","КБ"} else f"{n:.1f} {unit}"
            n/=1024
        return f"{n:.1f} ТБ"

    def _refresh_storage_usage(self) -> None:
        if not hasattr(self,"storage_usage_label"): return
        try:
            db_size=0
            for path in (Path(str(DB_PATH)),Path(str(DB_PATH)+"-wal"),Path(str(DB_PATH)+"-shm")):
                if path.exists(): db_size+=path.stat().st_size
            audio_size=0
            if RECORDINGS_DIR.exists():
                for path in RECORDINGS_DIR.rglob("*"):
                    try:
                        if path.is_file(): audio_size+=path.stat().st_size
                    except OSError: pass
            stats=self.storage.storage_stats()
            self.storage_usage_label.setText(
                f"База: {self._format_bytes(db_size)} · Временное аудио: {self._format_bytes(audio_size)} · "
                f"Чат: {stats['chat']} сообщений · Онлайн: {stats['viewers']} замеров · Расшифровка: {stats['speech_segments']} фрагментов"
            )
        except Exception as exc:
            self.storage_usage_label.setText(f"Не удалось посчитать размер данных: {exc}")

    def _save_retention_settings(self) -> None:
        days=self.retention_days_spin.value(); enabled=self.auto_cleanup_checkbox.isChecked()
        self.storage.set_setting("analytics_retention_days",str(days)); self.storage.set_setting("analytics_auto_cleanup","1" if enabled else "0")
        self.statusBar().showMessage(f"Автоочистка: {'включена' if enabled else 'выключена'} · срок {days} дней",3500)

    @staticmethod
    def _remove_recording_paths(paths: list[str]) -> int:
        removed=0
        for raw in paths:
            try:
                path=Path(raw)
                if path.exists(): path.unlink(); removed+=1
            except Exception:
                pass
        return removed

    def _manual_cleanup(self) -> None:
        default_days=max(1,int(self.storage.get_setting("analytics_retention_days") or "20"))
        dlg=CleanupDialog(default_days,self)
        if dlg.exec()!=QDialog.Accepted: return
        options=dlg.options()
        if not any(options[k] for k in ("delete_chat","delete_viewers","delete_speech_segments","delete_speech_recordings","delete_non_donation_events")):
            QMessageBox.information(self,"Очистка данных","Ничего не выбрано."); return
        cutoff=time.time()-int(options.pop("days"))*86400
        answer=QMessageBox.question(self,"Очистить данные?","Выбранные данные старше указанного срока будут удалены. Донаты и сессии останутся. Продолжить?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer!=QMessageBox.Yes: return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result=self.storage.cleanup_old_data(cutoff,**options)
            files=self._remove_recording_paths(result.pop("recording_paths",[]))
            # Manual cleanup is explicit, so compact the DB immediately and return disk space to Windows.
            self.storage.vacuum()
            self._history_signature=None; self._donations_signature=None; self._analysis_signature=None; self._analysis_context_key=None
            gc.collect()
        finally:
            QApplication.restoreOverrideCursor()
        self._refresh_storage_usage()
        removed=sum(int(v) for v in result.values())+files
        QMessageBox.information(self,"Очистка завершена",f"Удалено записей/файлов: {removed}.\nДонаты и сессии сохранены.")

    def _run_auto_cleanup_if_due(self) -> None:
        if (self.storage.get_setting("analytics_auto_cleanup") or "1")=="0": return
        today=dt.date.today().isoformat()
        if (self.storage.get_setting("analytics_last_cleanup_day") or "")==today: return
        days=max(1,int(self.storage.get_setting("analytics_retention_days") or "20"))
        self.storage.set_setting("analytics_last_cleanup_day",today)
        cutoff=time.time()-days*86400
        def worker() -> None:
            try:
                result=self.storage.cleanup_old_data(cutoff,delete_chat=True,delete_viewers=True,delete_speech_segments=True,delete_speech_recordings=True,delete_non_donation_events=False)
                self._remove_recording_paths(result.get("recording_paths",[]))
                # SQLite reuses freed pages, so a daily VACUUM is unnecessary. Manual cleanup has a compact step.
            except Exception:
                pass
        threading.Thread(target=worker,name="analytics-retention",daemon=True).start()

    def _release_ram_now(self) -> None:
        if self.stack.currentIndex()!=self.PAGE_ANALYSIS:
            self._release_analysis_memory()
        gc.collect()
        # On Windows this asks the OS to trim unused pages from the process working set.
        # It is only a finishing touch; the real fix is avoiding repeated allocations above.
        if os.name=="nt":
            try:
                import ctypes
                handle=ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.psapi.EmptyWorkingSet(handle)
            except Exception:
                pass
        self.statusBar().showMessage("Неиспользуемая оперативная память освобождена",3500)


    # ---------- actions ----------

    def _copy_overlay(self) -> None:
        QGuiApplication.clipboard().setText(OVERLAY_URL); self.statusBar().showMessage("Ссылка оверлея скопирована",2500)

    def _preset(self,minutes:int) -> None:
        self.rate_amount.setValue(100); self.rate_minutes.setValue(minutes); self.rate_seconds.setValue(0); self._apply_rate()

    def _apply_rate(self) -> None:
        seconds=self.rate_minutes.value()*60+self.rate_seconds.value()
        try: self.state.set_rate(self.rate_amount.value(),seconds)
        except ValueError as exc: QMessageBox.warning(self,"Ставка",str(exc)); return
        self._history_signature=None; self._refresh_history(); self.statusBar().showMessage("Новая ставка применяется ко всем следующим донатам",3500)

    def _manual_adjust(self,seconds:int,label:str) -> None:
        self.state.add_seconds(seconds,f"Ручная корректировка {label}"); self._history_signature=None; self._refresh_history()

    def _apply_theme(self, theme: str) -> None:
        """Apply only the selected visual theme, preserving saved text/element settings."""
        if theme not in self.theme_buttons:
            theme = "classic"
        self._select_theme(theme)
        profile = self.state.profile
        try:
            self.state.set_overlay_settings(theme, profile.overlay_title, profile.overlay_show_rate)
        except ValueError as exc:
            QMessageBox.warning(self,"Оформление OBS",str(exc)); return
        self.home_overlay_theme.setText(THEME_NAMES.get(theme,theme))
        self._history_signature=None; self._refresh_history()
        self.statusBar().showMessage(f"Стиль «{THEME_NAMES.get(theme, theme)}» применён в OBS",3000)

    def _apply_overlay_elements(self) -> None:
        """Apply title/rate visibility without accidentally applying an unconfirmed theme selection."""
        profile = self.state.profile
        try:
            self.state.set_overlay_settings(profile.overlay_theme,self.overlay_title_edit.text(),self.overlay_show_rate.isChecked())
        except ValueError as exc:
            QMessageBox.warning(self,"Оформление OBS",str(exc)); return
        self._history_signature=None; self._refresh_history()
        self.statusBar().showMessage("Текст и элементы оверлея обновлены",3000)

    def _apply_overlay_settings(self) -> None:
        """Backward-compatible combined action used by older internal call sites, if any."""
        try:
            self.state.set_overlay_settings(self.selected_theme,self.overlay_title_edit.text(),self.overlay_show_rate.isChecked())
        except ValueError as exc:
            QMessageBox.warning(self,"Оформление OBS",str(exc)); return
        self.home_overlay_theme.setText(THEME_NAMES.get(self.selected_theme,self.selected_theme))
        self._history_signature=None; self._refresh_history(); self.statusBar().showMessage("Оформление OBS обновлено",3000)

    def _toggle(self) -> None:
        if self.state.remaining_seconds()<=0: self._exact_time(); return
        self.state.toggle_running(); self._history_signature=None; self._refresh_history()

    def _exact_time(self) -> None:
        dlg=ExactTimeDialog(int(self.state.remaining_seconds()),self)
        if dlg.exec()==QDialog.Accepted:
            self.state.set_remaining(dlg.total_seconds()); self._history_signature=None; self._refresh_history()

    def _reset(self) -> None:
        current=_format_duration(self.state.remaining_seconds())
        result=QMessageBox.question(self,"Сброс таймера",f"Сбросить оставшееся время {current} до нуля?\n\nДействие попадёт в историю и его можно будет отменить.")
        if result==QMessageBox.Yes:
            self.state.reset(); self._history_signature=None; self._refresh_history()

    def _choose_undo_event(self) -> None:
        events=self.storage.list_reversible_events(self.state.profile.id, limit=150)
        if not events:
            QMessageBox.information(self,"Отмена","Нет начислений или изменений времени, которые можно отменить.")
            return
        dlg=UndoEventDialog(events,self)
        if dlg.exec()!=QDialog.Accepted:
            return
        event_id=dlg.selected_event_id()
        if event_id is None:
            return
        event=next((e for e in events if e.id==event_id),None)
        if event is None:
            return
        detail=event.title
        if event.amount is not None:
            detail += f" · {_format_money(event.amount,event.currency)}"
        result=QMessageBox.question(
            self,
            "Подтвердить отмену",
            f"Отменить выбранное начисление?\n\n{detail}\n"
            f"Изменение: {_format_duration(event.seconds_delta,signed=True)}\n\n"
            "Запись останется в истории с пометкой «ОТМЕНЕНО». Если это донат, его ID останется обработанным и повторно он не начислится."
        )
        if result!=QMessageBox.Yes:
            return
        undone=self.state.undo_time_event(event_id)
        if undone:
            self._history_signature=None
            self._refresh_history(force=True)
            self._donations_signature=None
            self._refresh_session(); self._refresh_donations(force=True)
            self.statusBar().showMessage("Выбранное начисление отменено",3000)
        else:
            QMessageBox.warning(self,"Отмена","Это начисление уже недоступно для отмены. История могла измениться — открой список ещё раз.")

    def _toggle_session_pause(self) -> None:
        session=self.state.active_session()
        if not session:
            QMessageBox.information(self,"Сессии","Активная сессия не запущена.")
            return
        was_paused=session.paused_at is not None
        updated=self.state.toggle_session_pause()
        if not updated:
            return
        self._history_signature=None; self._sessions_signature=None; self._donations_signature=None
        self._refresh_session(); self._refresh_sessions_archive(force=True); self._refresh_history(force=True); self._refresh_donations(force=True)
        if was_paused:
            self.statusBar().showMessage("Сессия продолжена",3000)
        else:
            self.statusBar().showMessage("Сессия приостановлена. Донаты во время паузы останутся в общей статистике, но не попадут в эту сессию.",5000)

    def _delete_selected_session(self) -> None:
        if self._selected_session_id is None:
            QMessageBox.information(self,"Сессии","Сначала выбери сессию в списке.")
            return
        session=self.storage.get_session(self.state.profile.id,self._selected_session_id)
        if not session:
            QMessageBox.information(self,"Сессии","Сессия не найдена. Обнови список и попробуй ещё раз.")
            return
        if session.ended_at is None:
            QMessageBox.information(self,"Сессии","Активную сессию нельзя удалить. Сначала заверши её.")
            return
        stats=self.storage.session_stats(session.id)
        result=QMessageBox.question(
            self,
            "Удалить сессию",
            f"Удалить сессию «{session.name}»?\n\n"
            f"Донатов: {stats['donation_count']} · Получено: {_format_money(stats['donation_amount'],'RUB')}\n\n"
            "Сами донаты и события НЕ удалятся: они останутся в общей истории и во вкладке «Донаты», но перестанут быть привязаны к этой сессии."
        )
        if result!=QMessageBox.Yes:
            return
        try:
            deleted=self.state.delete_session(session.id)
        except ValueError as exc:
            QMessageBox.warning(self,"Сессии",str(exc)); return
        if deleted:
            self._selected_session_id=None; self._sessions_signature=None; self._history_signature=None; self._donations_signature=None
            self._refresh_sessions_archive(force=True); self._refresh_history(force=True); self._refresh_donations(force=True)
            self.statusBar().showMessage(f"Сессия «{deleted.name}» удалена; донаты сохранены",4000)

    def _rename_session(self, session_id: int) -> None:
        from PySide6.QtWidgets import QInputDialog
        session=self.storage.get_session(self.state.profile.id, int(session_id))
        if not session:
            QMessageBox.information(self,"Сессии","Сессия не найдена. Обнови список и попробуй ещё раз.")
            return
        text,ok=QInputDialog.getText(self,"Переименовать сессию","Новое название:",text=session.name)
        if not ok:
            return
        name=text.strip()
        if not name:
            QMessageBox.warning(self,"Сессии","Название сессии не может быть пустым.")
            return
        try:
            renamed=self.state.rename_session(session.id,name)
        except ValueError as exc:
            QMessageBox.warning(self,"Сессии",str(exc)); return
        if renamed:
            self._sessions_signature=None; self._history_signature=None; self._donations_signature=None
            self._refresh_session(); self._refresh_sessions_archive(force=True); self._refresh_history(force=True); self._refresh_donations(force=True)
            self.statusBar().showMessage(f"Сессия переименована: {renamed.name}",3000)

    def _rename_active_session(self) -> None:
        session=self.state.active_session()
        if session:
            self._rename_session(session.id)

    def _rename_selected_session(self) -> None:
        if self._selected_session_id is None:
            QMessageBox.information(self,"Сессии","Сначала выбери сессию в списке.")
            return
        self._rename_session(self._selected_session_id)

    def _new_session(self) -> None:
        dlg=NewSessionDialog(int(self.state.remaining_seconds()),self)
        if dlg.exec()!=QDialog.Accepted: return
        existing=self.state.active_session()
        if existing:
            result=QMessageBox.question(self,"Новая сессия",f"Сейчас активна сессия «{existing.name}». Она будет завершена, а новая начнётся сразу. Продолжить?")
            if result!=QMessageBox.Yes: return
        session=self.state.start_session(dlg.session_name(),dlg.total_seconds()); self._history_signature=None; self._sessions_signature=None; self._donations_signature=None; self._selected_session_id=session.id; self._refresh_session(); self._refresh_history(force=True); self._refresh_sessions_archive(force=True); self._refresh_donations(force=True); self.statusBar().showMessage(f"Сессия «{session.name}» начата",3500)

    def _end_session(self) -> None:
        session=self.state.active_session()
        if not session: return
        result=QMessageBox.question(self,"Завершить сессию",f"Завершить сессию «{session.name}»?\n\nТаймер не будет сброшен и продолжит работать как сейчас.")
        if result!=QMessageBox.Yes: return
        ended=self.state.end_session(); self._history_signature=None; self._sessions_signature=None; self._donations_signature=None; self._selected_session_id=ended.id if ended else self._selected_session_id; self._refresh_session(); self._refresh_history(force=True); self._refresh_sessions_archive(force=True); self._refresh_donations(force=True); self.statusBar().showMessage("Сессия завершена",3000)

    def _setup_da(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        current=self.da_service.client_id()
        text,ok=QInputDialog.getText(self,"DonationAlerts Client ID","Client ID приложения DonationAlerts:\n\nRedirect URI при регистрации должен быть:\n"+DONATIONALERTS_REDIRECT_URI,text=current)
        if not ok: return
        try: self.da_service.set_client_id(text)
        except ValueError as exc: QMessageBox.warning(self,"DonationAlerts",str(exc)); return
        self.statusBar().showMessage("DonationAlerts Client ID сохранён",3000)

    def _connect_da(self) -> None:
        server = getattr(self, "local_server", None)
        if server is not None and not server.is_ready():
            error = server.startup_error or "Локальный сервер ещё не запустился или порт 17321 занят."
            QMessageBox.warning(
                self, "DonationAlerts — локальный сервер не работает",
                "Не могу начать авторизацию: сервер Donathon Timer недоступен на "
                "http://127.0.0.1:17321.\n\n"
                + error + "\n\nПодробности в файле:\n" + str(server.log_path)
                + "\n\nПерезапусти программу. Если проблема сохранится, проверь порт 17321.",
            )
            return
        if not self.da_service.client_id():
            QMessageBox.information(self,"DonationAlerts","Сначала один раз укажи Client ID приложения DonationAlerts. При регистрации приложения используй Redirect URI:\n\n"+DONATIONALERTS_REDIRECT_URI)
            self._setup_da()
            if not self.da_service.client_id(): return
        try: self.da_service.open_authorization()
        except Exception as exc: QMessageBox.warning(self,"DonationAlerts",f"Не удалось открыть авторизацию: {exc}")


    def _setup_twitch(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        current=self.twitch_service.client_id()
        text,ok=QInputDialog.getText(
            self,
            "Twitch Client ID",
            "Скопируй Client ID со страницы своего приложения в Twitch Developer Console и вставь сюда.\n\nСекретный ключ вводить не нужно. Если не знаешь, где взять Client ID, открой вкладку «Инструкция».",
            text=current,
        )
        if not ok: return
        try: self.twitch_service.set_client_id(text)
        except ValueError as exc: QMessageBox.warning(self,"Twitch",str(exc)); return
        self.statusBar().showMessage("Twitch Client ID сохранён",3000)

    def _connect_twitch(self) -> None:
        if not self.twitch_service.client_id():
            QMessageBox.information(self,"Twitch","Сначала введи Twitch Client ID во вкладке «Аккаунты». Если не знаешь, где его взять, открой «Инструкцию».")
            self._setup_twitch()
            if not self.twitch_service.client_id(): return
        try:
            auth=self.twitch_service.begin_device_authorization()
        except Exception as exc:
            QMessageBox.warning(self,"Twitch",f"Не удалось начать авторизацию Twitch: {exc}"); return
        QGuiApplication.clipboard().setText(auth.user_code)
        QMessageBox.information(
            self,
            "Подключение Twitch",
            f"Браузер уже открыт. На странице Twitch введи код:\n\n{auth.user_code}\n\nКод также скопирован в буфер обмена. После подтверждения вернись в Donathon Timer — подключение завершится автоматически.",
        )
