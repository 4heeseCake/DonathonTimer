from __future__ import annotations

import threading
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from .config import OVERLAY_BUILD
from .donationalerts import DonationAlertsService
from .state import AppState
from .entertainment import EntertainmentService


class OAuthTokenPayload(BaseModel):
    access_token: str


class OverlayServer:
    def __init__(self, state: AppState, da_service: DonationAlertsService, entertainment: EntertainmentService, host: str, port: int):
        self.state = state
        self.da_service = da_service
        self.entertainment = entertainment
        self.host = host
        self.port = port
        self.app = FastAPI(title="Donathon Timer Local Server", docs_url=None, redoc_url=None)
        self._thread: threading.Thread | None = None
        self._configure_routes()

    def _configure_routes(self) -> None:
        templates = Path(__file__).parent / "templates"
        no_cache = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        }

        @self.app.get("/overlay", response_class=HTMLResponse)
        async def overlay():
            # Inject the build number at response time so the HTML and backend can
            # never drift apart after an update. A hard-coded PAGE_BUILD caused an
            # endless self-refresh loop in 0.5.0, which made OBS appear connected
            # while all live state changes were ignored.
            html = (templates / "overlay.html").read_text(encoding="utf-8")
            html = html.replace("__OVERLAY_BUILD__", OVERLAY_BUILD)
            return HTMLResponse(html, headers=no_cache)

        @self.app.get("/api/state")
        async def get_state():
            self.state.mark_overlay_seen()
            data = self.state.snapshot()
            data["entertainment"] = self.entertainment.snapshot(max_entries=60)
            data["overlay_build"] = OVERLAY_BUILD
            return JSONResponse(data, headers=no_cache)

        @self.app.get("/api/version")
        async def version():
            return JSONResponse({"overlay_build": OVERLAY_BUILD}, headers=no_cache)

        @self.app.get("/health")
        async def health():
            return {"ok": True, "overlay_build": OVERLAY_BUILD}

        @self.app.get("/oauth/callback", response_class=HTMLResponse)
        async def oauth_callback():
            return HTMLResponse(
                """
<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Donathon Timer</title>
<style>
body{margin:0;background:#0d1017;color:#f4f6fb;font-family:Segoe UI,system-ui;display:grid;place-items:center;min-height:100vh}
.card{width:min(520px,calc(100% - 48px));background:#151a24;border:1px solid #242b38;border-radius:18px;padding:28px}
h2{margin-top:0}.muted{color:#929cad}.ok{color:#64d98b}.bad{color:#ff9caa}
</style></head><body><div class="card"><h2>Donathon Timer</h2><p id="status" class="muted">Завершаю подключение DonationAlerts…</p></div>
<script>
(async()=>{
 const el=document.getElementById('status');
 const p=new URLSearchParams(location.hash.slice(1));
 const token=p.get('access_token');
 const err=p.get('error_description')||p.get('error');
 if(!token){el.className='bad';el.textContent=err?'DonationAlerts: '+err:'Токен не получен. Можно закрыть это окно.';return;}
 try{
  const r=await fetch('/api/oauth/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_token:token})});
  const d=await r.json(); if(!r.ok) throw new Error(d.detail||'Ошибка подключения');
  el.className='ok';el.textContent='Аккаунт «'+d.name+'» подключён. Можно закрыть это окно и вернуться в Donathon Timer.';
  history.replaceState(null,'',location.pathname);
 }catch(e){el.className='bad';el.textContent='Не удалось подключить аккаунт: '+e.message;}
})();
</script></body></html>
                """,
                headers=no_cache,
            )

        @self.app.post("/api/oauth/complete")
        async def oauth_complete(payload: OAuthTokenPayload):
            try:
                return await self.da_service.complete_oauth(payload.access_token)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        def runner():
            config = uvicorn.Config(
                self.app,
                host=self.host,
                port=self.port,
                log_level="warning",
                access_log=False,
            )
            uvicorn.Server(config).run()

        self._thread = threading.Thread(target=runner, name="overlay-server", daemon=True)
        self._thread.start()
