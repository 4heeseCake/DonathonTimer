import sys
import multiprocessing as mp

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from pathlib import Path

from .config import APP_NAME, DB_PATH, SERVER_HOST, SERVER_PORT
from .donationalerts import DonationAlertsService
from .main_window import MainWindow
from .server import OverlayServer
from .speech import SpeechService
from .state import AppState
from .storage import Storage
from .twitch import TwitchService
from .entertainment import EntertainmentService


def run() -> None:
    mp.freeze_support()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    icon_path = Path(__file__).resolve().parent / "assets" / "logo_icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setQuitOnLastWindowClosed(True)

    storage = Storage(DB_PATH)
    state = AppState(storage)
    da_service = DonationAlertsService(state, storage)
    twitch_service = TwitchService(state, storage)
    entertainment_service = EntertainmentService(state, storage, da_service, twitch_service)
    speech_service = SpeechService(state, storage)
    server = OverlayServer(state, da_service, entertainment_service, SERVER_HOST, SERVER_PORT)
    server.start()

    window = MainWindow(state, storage, da_service, twitch_service, speech_service, entertainment_service)
    window.local_server = server
    app.aboutToQuit.connect(speech_service.shutdown)
    window.show()
    raise SystemExit(app.exec())
