from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import webbrowser
from dataclasses import dataclass
from typing import Any

import httpx
import keyring
import websockets

from .state import AppState
from .storage import Profile, Storage

TWITCH_DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_API_BASE = "https://api.twitch.tv/helix"
TWITCH_EVENTSUB_WS = "wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=30"
TWITCH_SCOPES = "user:read:chat"
TOKEN_SERVICE = "DonathonTimer.Twitch"


@dataclass(slots=True)
class TwitchStatus:
    code: str
    text: str
    viewers: int | None = None


@dataclass(slots=True)
class DeviceAuthorization:
    user_code: str
    verification_uri: str
    expires_in: int


class TwitchService:
    """Twitch OAuth + lightweight live analytics collector.

    Uses the Device Code flow so the desktop app never needs a client secret.
    Once connected it keeps a WebSocket EventSub subscription for chat and polls
    Get Streams once per minute for viewer count. Both collectors run in daemon
    threads and write only small rows to SQLite, so the in-stream CPU cost stays tiny.
    """

    def __init__(self, state: AppState, storage: Storage):
        self.state = state
        self.storage = storage
        self._lock = threading.RLock()
        self._generation = 0
        self._status = TwitchStatus("disconnected", "Twitch не подключён", None)
        self._active_profile_id: int | None = None
        self._last_error = ""
        self._chat_queue: queue.Queue[dict] = queue.Queue(maxsize=10000)
        self._chat_listeners = []
        threading.Thread(target=self._chat_writer_loop, name="twitch-chat-writer", daemon=True).start()
        self.state.add_listener(self._on_state_change)
        self.activate_profile(self.state.profile)

    def add_chat_listener(self, callback) -> None:
        self._chat_listeners.append(callback)

    def _notify_chat(self, item: dict) -> None:
        for callback in list(self._chat_listeners):
            try:
                callback(item)
            except Exception:
                pass

    def _chat_writer_loop(self) -> None:
        while True:
            try:
                first=self._chat_queue.get()
                batch=[first]
                deadline=time.time()+0.35
                while len(batch)<250 and time.time()<deadline:
                    try: batch.append(self._chat_queue.get(timeout=0.03))
                    except queue.Empty: break
                self.storage.add_chat_messages(batch)
            except Exception:
                time.sleep(0.2)

    def client_id(self) -> str:
        return (self.storage.get_setting("twitch_client_id") or "").strip()

    def set_client_id(self, client_id: str) -> None:
        value = client_id.strip()
        if not value:
            raise ValueError("Client ID Twitch не может быть пустым")
        self.storage.set_setting("twitch_client_id", value)

    def status(self) -> TwitchStatus:
        with self._lock:
            return TwitchStatus(self._status.code, self._status.text, self._status.viewers)

    def _set_status(self, code: str, text: str, viewers: int | None = None) -> None:
        with self._lock:
            current_viewers = self._status.viewers if viewers is None and code == self._status.code else viewers
            self._status = TwitchStatus(code, text, current_viewers)

    @staticmethod
    def _access_key(user_id: str) -> str:
        return f"access:{user_id}"

    @staticmethod
    def _refresh_key(user_id: str) -> str:
        return f"refresh:{user_id}"

    def _save_tokens(self, user_id: str, access_token: str, refresh_token: str | None) -> None:
        keyring.set_password(TOKEN_SERVICE, self._access_key(user_id), access_token)
        if refresh_token:
            keyring.set_password(TOKEN_SERVICE, self._refresh_key(user_id), refresh_token)

    def _get_access_token(self, user_id: str) -> str | None:
        try:
            return keyring.get_password(TOKEN_SERVICE, self._access_key(user_id))
        except Exception:
            return None

    def _get_refresh_token(self, user_id: str) -> str | None:
        try:
            return keyring.get_password(TOKEN_SERVICE, self._refresh_key(user_id))
        except Exception:
            return None

    def begin_device_authorization(self) -> DeviceAuthorization:
        client_id = self.client_id()
        if not client_id:
            raise ValueError("Сначала укажите Twitch Client ID")
        response = httpx.post(
            TWITCH_DEVICE_URL,
            data={"client_id": client_id, "scopes": TWITCH_SCOPES},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        auth = DeviceAuthorization(
            user_code=str(payload["user_code"]),
            verification_uri=str(payload["verification_uri"]),
            expires_in=int(payload.get("expires_in", 1800)),
        )
        device_code = str(payload["device_code"])
        interval = max(2, int(payload.get("interval", 5)))
        profile_id = self.state.profile.id
        self._set_status("authorizing", f"Ожидаю подтверждение Twitch · код {auth.user_code}")
        webbrowser.open(auth.verification_uri)
        threading.Thread(
            target=self._poll_device_code,
            args=(profile_id, device_code, interval, auth.expires_in),
            name="twitch-device-auth",
            daemon=True,
        ).start()
        return auth

    def _poll_device_code(self, profile_id: int, device_code: str, interval: int, expires_in: int) -> None:
        deadline = time.time() + max(30, expires_in)
        delay = interval
        client_id = self.client_id()
        while time.time() < deadline:
            try:
                response = httpx.post(
                    TWITCH_TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "scopes": TWITCH_SCOPES,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    timeout=15,
                )
                if response.status_code == 200:
                    payload = response.json()
                    self._complete_login(profile_id, str(payload["access_token"]), payload.get("refresh_token"))
                    return
                try:
                    error = str(response.json().get("message") or response.json().get("error") or "")
                except Exception:
                    error = response.text
                lowered = error.casefold()
                if "slow" in lowered:
                    delay += 2
                elif "pending" not in lowered and response.status_code not in {400, 428}:
                    raise RuntimeError(error or f"HTTP {response.status_code}")
            except Exception as exc:
                self._last_error = str(exc)
            time.sleep(delay)
        self._set_status("auth_required", "Время подтверждения Twitch истекло — подключите снова")

    def _complete_login(self, profile_id: int, access_token: str, refresh_token: str | None) -> None:
        client_id = self.client_id()
        headers = {"Authorization": f"OAuth {access_token}"}
        response = httpx.get(TWITCH_VALIDATE_URL, headers=headers, timeout=15)
        response.raise_for_status()
        validation = response.json()
        user_id = str(validation["user_id"])
        login = str(validation.get("login") or user_id)
        api_headers = {"Authorization": f"Bearer {access_token}", "Client-Id": client_id}
        display_name = login
        try:
            r = httpx.get(f"{TWITCH_API_BASE}/users", headers=api_headers, timeout=15)
            r.raise_for_status()
            data = r.json().get("data") or []
            if data:
                display_name = str(data[0].get("display_name") or login)
                login = str(data[0].get("login") or login)
        except Exception:
            pass
        self.storage.link_twitch_profile(profile_id, user_id=user_id, login=login, display_name=display_name)
        self._save_tokens(user_id, access_token, refresh_token)
        self.storage.set_setting("pending_twitch_profile_id", str(profile_id))
        if self.state.profile.id == profile_id:
            # Reload profile fields and start the listener immediately.
            self.state.switch_profile(profile_id)
            self.activate_profile(self.state.profile, force=True)
        self._set_status("connecting", f"Twitch подключён: {display_name} · запускаю аналитику…")

    def _on_state_change(self) -> None:
        profile = self.state.profile
        with self._lock:
            current = self._active_profile_id
        if current != profile.id:
            self.activate_profile(profile)

    def activate_profile(self, profile: Profile, force: bool = False) -> None:
        with self._lock:
            if not force and self._active_profile_id == profile.id:
                return
            self._generation += 1
            generation = self._generation
            self._active_profile_id = profile.id
        if not profile.twitch_user_id:
            self._set_status("disconnected", "Twitch не подключён", None)
            return
        access = self._get_access_token(profile.twitch_user_id)
        if not access:
            self._set_status("auth_required", "Нужно повторно подключить Twitch", None)
            return
        self._set_status("connecting", f"Twitch: подключение к {profile.twitch_display_name or profile.twitch_login or profile.twitch_user_id}…", None)
        threading.Thread(
            target=self._thread_entry,
            args=(profile.id, str(profile.twitch_user_id), access, generation),
            name=f"twitch-{profile.id}",
            daemon=True,
        ).start()

    def _thread_entry(self, profile_id: int, user_id: str, access_token: str, generation: int) -> None:
        try:
            asyncio.run(self._monitor(profile_id, user_id, access_token, generation))
        except Exception as exc:
            if self._is_current(generation):
                self._last_error = str(exc)
                self._set_status("error", f"Ошибка Twitch: {type(exc).__name__}")

    def _is_current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation

    async def _validate_or_refresh(self, user_id: str, access_token: str) -> str:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(TWITCH_VALIDATE_URL, headers={"Authorization": f"OAuth {access_token}"})
            if r.status_code == 200:
                return access_token
            refresh_token = self._get_refresh_token(user_id)
            if not refresh_token:
                raise RuntimeError("Twitch token expired")
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id(),
            }
            rr = await client.post(TWITCH_TOKEN_URL, data=payload)
            rr.raise_for_status()
            data = rr.json()
            new_access = str(data["access_token"])
            self._save_tokens(user_id, new_access, data.get("refresh_token") or refresh_token)
            return new_access

    async def _monitor(self, profile_id: int, user_id: str, access_token: str, generation: int) -> None:
        access_token = await self._validate_or_refresh(user_id, access_token)
        delay = 1
        while self._is_current(generation):
            try:
                await self._monitor_once(profile_id, user_id, access_token, generation)
                delay = 1
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not self._is_current(generation):
                    return
                self._last_error = str(exc)
                self._set_status("reconnecting", "Twitch: связь потеряна — переподключаюсь…")
                try:
                    access_token = await self._validate_or_refresh(user_id, access_token)
                except Exception:
                    self._set_status("auth_required", "Twitch: требуется повторная авторизация")
                    return
                await asyncio.sleep(delay)
                delay = min(delay * 2, 20)

    async def _monitor_once(self, profile_id: int, user_id: str, access_token: str, generation: int) -> None:
        # Viewer polling and chat are independent long-running collectors.  If
        # either one stops (for example because the access token expired),
        # restart the pair so token refresh is handled centrally by _monitor().
        viewer_task = asyncio.create_task(self._viewer_loop(profile_id, user_id, access_token, generation))
        chat_task = asyncio.create_task(self._chat_loop(profile_id, user_id, access_token, generation))
        tasks = {viewer_task, chat_task}
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
            if self._is_current(generation):
                raise RuntimeError("Twitch collector disconnected")
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    async def _viewer_loop(self, profile_id: int, user_id: str, access_token: str, generation: int) -> None:
        headers = {"Authorization": f"Bearer {access_token}", "Client-Id": self.client_id()}
        async with httpx.AsyncClient(timeout=15) as client:
            while self._is_current(generation):
                viewers: int | None = None
                live = False
                try:
                    r = await client.get(f"{TWITCH_API_BASE}/streams", headers=headers, params={"user_id": user_id})
                    if r.status_code == 401:
                        raise RuntimeError("Twitch token expired")
                    r.raise_for_status()
                    data = r.json().get("data") or []
                    if data:
                        viewers = int(data[0].get("viewer_count") or 0)
                        live = True
                    elif self.storage.active_session(profile_id):
                        viewers = 0
                    if viewers is not None:
                        self.storage.add_viewer_sample(profile_id, viewers, live=live)
                    name = self.state.profile.twitch_display_name or self.state.profile.twitch_login or "Twitch"
                    status_text = f"Twitch онлайн · {name}" + (f" · {viewers} зр." if live and viewers is not None else " · канал офлайн")
                    self._set_status("online", status_text, viewers if live else 0)
                except Exception:
                    raise
                await asyncio.sleep(60)

    async def _chat_loop(self, profile_id: int, user_id: str, access_token: str, generation: int) -> None:
        ws_url = TWITCH_EVENTSUB_WS
        inherited_subscriptions = False
        headers = {"Authorization": f"Bearer {access_token}", "Client-Id": self.client_id(), "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=15) as client:
            while self._is_current(generation):
                async with websockets.connect(ws_url, ping_interval=None, close_timeout=5) as ws:
                    raw = await asyncio.wait_for(ws.recv(), timeout=15)
                    welcome = json.loads(raw)
                    if welcome.get("metadata", {}).get("message_type") != "session_welcome":
                        raise RuntimeError("Twitch EventSub did not send welcome")
                    session = welcome.get("payload", {}).get("session", {})
                    session_id = session.get("id")
                    keepalive_timeout = max(10, int(session.get("keepalive_timeout_seconds") or 30))
                    if not session_id:
                        raise RuntimeError("Twitch EventSub session id missing")
                    if not inherited_subscriptions:
                        sub = await client.post(
                            f"{TWITCH_API_BASE}/eventsub/subscriptions",
                            headers=headers,
                            json={
                                "type": "channel.chat.message",
                                "version": "1",
                                "condition": {"broadcaster_user_id": user_id, "user_id": user_id},
                                "transport": {"method": "websocket", "session_id": session_id},
                            },
                        )
                        if sub.status_code not in {202, 409}:
                            raise RuntimeError(f"EventSub subscription failed: {sub.status_code} {sub.text[:240]}")
                    reconnect_url = None
                    while self._is_current(generation):
                        # Twitch asks clients to reconnect if no keepalive/event
                        # arrives within the advertised timeout window.
                        raw = await asyncio.wait_for(ws.recv(), timeout=keepalive_timeout + 10)
                        message = json.loads(raw)
                        metadata = message.get("metadata", {})
                        msg_type = metadata.get("message_type")
                        if msg_type == "notification":
                            event = message.get("payload", {}).get("event", {})
                            text = str((event.get("message") or {}).get("text") or "")
                            message_id = str(event.get("message_id") or metadata.get("message_id") or "")
                            if text:
                                item={
                                    "profile_id": profile_id,
                                    "external_id": message_id or None,
                                    "user_id": str(event.get("chatter_user_id") or ""),
                                    "user_name": str(event.get("chatter_user_name") or event.get("chatter_user_login") or "Аноним"),
                                    "text": text,
                                    "created_at": self._parse_timestamp(metadata.get("message_timestamp")),
                                }
                                self._notify_chat(item)
                                try: self._chat_queue.put_nowait(item)
                                except queue.Full: pass
                        elif msg_type == "session_reconnect":
                            reconnect_url = message.get("payload", {}).get("session", {}).get("reconnect_url")
                            break
                        elif msg_type == "revocation":
                            raise RuntimeError("Twitch revoked chat subscription")
                    if reconnect_url:
                        # Twitch's reconnect URL carries the existing subscriptions.
                        # Do not create duplicates on the new socket.
                        ws_url = str(reconnect_url); inherited_subscriptions = True
                    else:
                        return

    @staticmethod
    def _parse_timestamp(value: Any) -> float:
        if not value:
            return time.time()
        try:
            from datetime import datetime
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
        except Exception:
            return time.time()


# contextlib is imported late to keep the public part of the module compact.
import contextlib
