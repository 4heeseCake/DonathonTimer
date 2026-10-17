from pathlib import Path
import os

APP_NAME = "Donathon Timer"
APP_ID = "donathon.timer"
APP_VERSION = "0.9.4 Beta 1"
OVERLAY_BUILD = "0.9.4-beta1"
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 17321
OVERLAY_BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}/overlay"
# Versioned URL forces one clean reload when upgrading from pre-0.3 builds.
# From 0.3 onward the overlay can also detect future build changes itself.
OVERLAY_URL = f"{OVERLAY_BASE_URL}?v={OVERLAY_BUILD}"

DATA_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / "DonathonTimer"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "donathon.db"
RECORDINGS_DIR = DATA_DIR / "recordings"

DONATIONALERTS_CLIENT_ID = os.getenv("DONATIONALERTS_CLIENT_ID", "").strip()
DONATIONALERTS_REDIRECT_URI = f"http://{SERVER_HOST}:{SERVER_PORT}/oauth/callback"
DONATIONALERTS_SCOPES = "oauth-user-show oauth-donation-subscribe oauth-donation-index"
