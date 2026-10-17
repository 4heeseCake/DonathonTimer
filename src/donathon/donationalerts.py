from __future__ import annotations

import asyncio
import json
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Any

import httpx
import keyring
import websockets

from .config import DONATIONALERTS_REDIRECT_URI, DONATIONALERTS_SCOPES
from .state import AppState
from .storage import Storage, Profile

API_BASE = "https://www.donationalerts.com/api/v1"
OAUTH_AUTHORIZE = "https://www.donationalerts.com/oauth/authorize"
CENTRIFUGO_WS = "wss://centrifugo.donationalerts.com/connection/websocket"
TOKEN_SERVICE = "DonathonTimer.DonationAlerts"


@dataclass(slots=True)
class DAStatus:
    code: str
    text: str


class DonationAlertsService:
    """OAuth + one active DonationAlerts realtime listener.

    A new profile activation establishes a fresh baseline, so donations received while
    that profile wasn't selected don't unexpectedly affect the timer. Reconnects inside
    the same activation session recover unprocessed recent donations.
    """

    def __init__(self, state: AppState, storage: Storage):
        self.state = state
        self.storage = storage
        self._lock = threading.RLock()
        self._generation = 0
        self._status = DAStatus("disconnected", "DonationAlerts не подключён")
        self._last_error = ""
        self._donation_listeners = []
        self.state.add_listener(self._on_state_change)
        self.activate_profile(self.state.profile)

    def add_donation_listener(self, callback) -> None:
        self._donation_listeners.append(callback)

    def _notify_donation(self, payload: dict) -> None:
        for callback in list(self._donation_listeners):
            try:
                callback(payload)
            except Exception:
                pass

    def client_id(self) -> str:
        return (self.storage.get_setting("da_client_id") or "").strip()

    def set_client_id(self, client_id: str) -> None:
        value = client_id.strip()
        if not value.isdigit():
            raise ValueError("Client ID должен состоять из цифр")
        self.storage.set_setting("da_client_id", value)

    def authorization_url(self) -> str:
        client_id = self.client_id()
        if not client_id:
            raise ValueError("Сначала укажите DonationAlerts Client ID")
        query = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": DONATIONALERTS_REDIRECT_URI,
                "response_type": "token",
                "scope": DONATIONALERTS_SCOPES,
            }
        )
        return f"{OAUTH_AUTHORIZE}?{query}"

    def open_authorization(self) -> None:
        webbrowser.open(self.authorization_url())

    def status(self) -> DAStatus:
        with self._lock:
            return DAStatus(self._status.code, self._status.text)

    def _set_status(self, code: str, text: str) -> None:
        with self._lock:
            self._status = DAStatus(code, text)

    def _token_key(self, user_id: str) -> str:
        return f"user:{user_id}"

    def _save_token(self, user_id: str, token: str) -> None:
        keyring.set_password(TOKEN_SERVICE, self._token_key(user_id), token)

    def _get_token(self, user_id: str) -> str | None:
        try:
            return keyring.get_password(TOKEN_SERVICE, self._token_key(user_id))
        except Exception:
            return None

    async def complete_oauth(self, access_token: str) -> dict[str, Any]:
        """Validate browser token, save account, and baseline historical donations."""
        async with httpx.AsyncClient(timeout=15) as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get(f"{API_BASE}/user/oauth", headers=headers)
            response.raise_for_status()
            payload = response.json()["data"]

            user_id = str(payload["id"])
            profile_id = self.storage.upsert_da_profile(
                user_id=user_id,
                code=str(payload.get("code") or ""),
                name=str(payload.get("name") or payload.get("code") or f"DA {user_id}"),
                avatar_url=payload.get("avatar"),
            )
            self._save_token(user_id, access_token)
            self.storage.set_setting("pending_connected_profile_id", str(profile_id))

            # Baseline existing donations so connecting an account never adds its old history.
            try:
                donations = await self._fetch_recent_donations(client, access_token)
                for donation in donations:
                    donation_id = donation.get("id")
                    if donation_id is not None:
                        self.storage.mark_processed(profile_id, str(donation_id))
            except Exception:
                # OAuth connection itself is still valid even if history lookup has a transient error.
                pass

        return {
            "profile_id": profile_id,
            "user_id": user_id,
            "name": payload.get("name") or payload.get("code") or user_id,
        }

    def _on_state_change(self) -> None:
        # Only a profile switch should restart the listener. Timer/rate updates reuse same profile.
        profile = self.state.profile
        with self._lock:
            current = getattr(self, "_active_profile_id", None)
        if current != profile.id:
            self.activate_profile(profile)

    def activate_profile(self, profile: Profile) -> None:
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._active_profile_id = profile.id

        if not profile.da_user_id:
            self._set_status("local", "Локальный профиль — донаты не подключены")
            return
        token = self._get_token(profile.da_user_id)
        if not token:
            self._set_status("auth_required", "Нужно повторно подключить DonationAlerts")
            return

        self._set_status("connecting", f"Подключение: {profile.name}…")
        thread = threading.Thread(
            target=self._thread_entry,
            args=(profile.id, str(profile.da_user_id), token, generation),
            daemon=True,
            name=f"donationalerts-{profile.id}",
        )
        thread.start()

    def _thread_entry(self, profile_id: int, user_id: str, token: str, generation: int) -> None:
        try:
            asyncio.run(self._session(profile_id, user_id, token, generation))
        except Exception as exc:
            if self._is_current(generation):
                self._set_status("error", f"Ошибка DonationAlerts: {type(exc).__name__}")
                self._last_error = str(exc)

    def _is_current(self, generation: int) -> bool:
        with self._lock:
            return generation == self._generation

    async def _session(self, profile_id: int, user_id: str, token: str, generation: int) -> None:
        # Fresh activation baseline: donations while this profile wasn't selected are ignored.
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                for donation in await self._fetch_recent_donations(client, token):
                    if donation.get("id") is not None:
                        self.storage.mark_processed(profile_id, str(donation["id"]))
            except Exception:
                pass

        delay = 1
        while self._is_current(generation):
            try:
                await self._listen_once(profile_id, user_id, token, generation)
                delay = 1
            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not self._is_current(generation):
                    return
                self._last_error = str(exc)
                self._set_status("reconnecting", "Связь потеряна — переподключаюсь…")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 15)

    async def _listen_once(self, profile_id: int, user_id: str, token: str, generation: int) -> None:
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            user_response = await client.get(f"{API_BASE}/user/oauth", headers=headers)
            user_response.raise_for_status()
            user_data = user_response.json()["data"]
            socket_token = user_data["socket_connection_token"]

            async with websockets.connect(CENTRIFUGO_WS, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"params": {"token": socket_token}, "id": 1}))
                auth_message = await self._recv_json(ws)
                client_id = auth_message.get("result", {}).get("client")
                if not client_id:
                    raise RuntimeError("DonationAlerts не вернул Centrifugo client id")

                channel = f"$alerts:donation_{user_id}"
                sub_response = await client.post(
                    f"{API_BASE}/centrifuge/subscribe",
                    headers=headers,
                    json={"channels": [channel], "client": client_id},
                )
                sub_response.raise_for_status()
                channels = sub_response.json().get("channels", [])
                channel_token = next((c.get("token") for c in channels if c.get("channel") == channel), None)
                if not channel_token:
                    raise RuntimeError("DonationAlerts не вернул токен подписки")

                await ws.send(
                    json.dumps(
                        {
                            "params": {"channel": channel, "token": channel_token},
                            "method": 1,
                            "id": 2,
                        }
                    )
                )
                await self._recv_json(ws)  # subscription acknowledgement

                # Close the race between baseline and WebSocket subscription.
                await self._recover_recent(client, token, profile_id)
                self._set_status("online", f"DonationAlerts онлайн · {self.state.profile.name}")

                while self._is_current(generation):
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=2)
                    except asyncio.TimeoutError:
                        continue
                    for message in self._parse_frames(raw):
                        donation = self._extract_donation(message)
                        if donation:
                            self._apply_donation_dict(profile_id, donation)

    async def _recv_json(self, ws) -> dict:
        raw = await asyncio.wait_for(ws.recv(), timeout=20)
        frames = self._parse_frames(raw)
        if not frames:
            raise RuntimeError("Пустой ответ Centrifugo")
        return frames[0]

    @staticmethod
    def _parse_frames(raw: str | bytes) -> list[dict]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        result = []
        for part in str(raw).splitlines():
            part = part.strip()
            if not part:
                continue
            try:
                value = json.loads(part)
                if isinstance(value, dict):
                    result.append(value)
            except json.JSONDecodeError:
                continue
        return result

    @staticmethod
    def _extract_donation(message: dict) -> dict | None:
        result = message.get("result")
        if not isinstance(result, dict):
            return None
        channel = str(result.get("channel") or "")
        if not channel.startswith("$alerts:donation_"):
            return None
        data = result.get("data")
        if not isinstance(data, dict):
            return None
        donation = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(donation, dict) and donation.get("id") is not None and donation.get("amount") is not None:
            return donation
        return None

    async def _fetch_recent_donations(
        self, client: httpx.AsyncClient, token: str, page: int = 1
    ) -> list[dict]:
        response = await client.get(
            f"{API_BASE}/alerts/donations",
            headers={"Authorization": f"Bearer {token}"},
            params={"page": page},
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        return [x for x in data if isinstance(x, dict)]

    async def _recover_recent(self, client: httpx.AsyncClient, token: str, profile_id: int) -> None:
        # Walk backward until we hit an already-known donation. This lets reconnect recovery
        # survive bursts larger than a single API page while still keeping a sane upper bound.
        pending: list[dict] = []
        found_known = False
        for page in range(1, 21):
            donations = await self._fetch_recent_donations(client, token, page=page)
            if not donations:
                break
            for donation in donations:
                donation_id = donation.get("id")
                if donation_id is None:
                    continue
                if self.storage.is_processed(profile_id, str(donation_id)):
                    found_known = True
                    break
                pending.append(donation)
            if found_known or len(donations) < 30:
                break

        # Pages and each page are newest-first; reverse all pending events for natural order.
        for donation in reversed(pending):
            self._apply_donation_dict(profile_id, donation)

    def _apply_donation_dict(self, profile_id: int, donation: dict) -> None:
        # Ignore stale listener events if the user switched profile mid-frame.
        if self.state.profile.id != profile_id:
            return
        sender = donation.get("username") or donation.get("name") or "Аноним"
        amount = float(donation.get("amount") or 0)
        amount_user = donation.get("amount_in_user_currency")
        try:
            amount_user = float(amount_user) if amount_user is not None else None
        except (TypeError, ValueError):
            amount_user = None
        donation_id = str(donation["id"])
        already_processed = self.storage.is_processed(profile_id, donation_id)
        self.state.apply_donation(
            donation_id,
            str(sender),
            amount,
            str(donation.get("currency") or ""),
            amount_in_user_currency=amount_user,
        )
        if not already_processed:
            self._notify_donation({
                "profile_id": profile_id,
                "id": donation_id,
                "sender": str(sender),
                "amount": amount,
                "currency": str(donation.get("currency") or ""),
                "effective_amount": amount_user if amount_user is not None else amount,
                "message": str(donation.get("message") or donation.get("message_text") or ""),
                "created_at": time.time(),
            })
