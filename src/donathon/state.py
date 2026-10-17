from __future__ import annotations

import math
import threading
import time
from typing import Callable

from .storage import Event, Profile, Session, Storage


class AppState:
    def __init__(self, storage: Storage):
        self.storage = storage
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []
        self._overlay_last_seen = 0.0
        self._profile = self.storage.get_profile(self.storage.active_profile_id())
        self._normalize_expired()

    @property
    def profile(self) -> Profile:
        with self._lock:
            return self._profile

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def mark_overlay_seen(self) -> None:
        with self._lock:
            self._overlay_last_seen = time.time()

    def overlay_seen_recently(self, within_seconds: float = 3.0) -> bool:
        with self._lock:
            return (time.time() - self._overlay_last_seen) <= float(within_seconds)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                pass

    def _normalize_expired(self) -> None:
        if self._profile.running and self._profile.end_epoch is not None:
            if self._profile.end_epoch <= time.time():
                self._profile.running = False
                self._profile.end_epoch = None
                self._profile.paused_remaining = 0
                self._persist_timer()

    def switch_profile(self, profile_id: int) -> None:
        with self._lock:
            self.storage.set_active_profile(profile_id)
            self._profile = self.storage.get_profile(profile_id)
            self._normalize_expired()
        self._notify()

    def remaining_seconds(self) -> float:
        with self._lock:
            if self._profile.running and self._profile.end_epoch is not None:
                return max(0.0, self._profile.end_epoch - time.time())
            return max(0.0, self._profile.paused_remaining)

    def _persist_timer(self) -> None:
        self.storage.update_timer(
            self._profile.id,
            running=self._profile.running,
            end_epoch=self._profile.end_epoch,
            paused_remaining=self._profile.paused_remaining,
        )

    def _set_remaining_locked(self, seconds: float) -> None:
        seconds = max(0.0, float(seconds))
        if self._profile.running:
            self._profile.end_epoch = time.time() + seconds if seconds else None
            if not seconds:
                self._profile.running = False
            self._profile.paused_remaining = 0
        else:
            self._profile.paused_remaining = seconds
            self._profile.end_epoch = None
        self._persist_timer()

    def set_remaining(self, seconds: float, *, record_event: bool = True, title: str = "Установлено точное время") -> None:
        seconds = max(0.0, float(seconds))
        with self._lock:
            before = self.remaining_seconds()
            self._set_remaining_locked(seconds)
            actual_delta = int(round(seconds - before))
            if record_event:
                self.storage.add_event(self._profile.id, "manual", title, actual_delta)
        self._notify()

    def add_seconds(self, seconds: int, title: str = "Ручное изменение") -> None:
        if seconds == 0:
            return
        with self._lock:
            before = self.remaining_seconds()
            new_value = max(0.0, before + int(seconds))
            self._set_remaining_locked(new_value)
            actual_delta = int(round(new_value - before))
            if actual_delta:
                self.storage.add_event(self._profile.id, "manual", title, actual_delta)
        self._notify()

    def toggle_running(self) -> bool:
        with self._lock:
            if self._profile.running:
                remaining = self.remaining_seconds()
                self._profile.running = False
                self._profile.end_epoch = None
                self._profile.paused_remaining = remaining
                title = "Таймер поставлен на паузу"
            else:
                remaining = max(0.0, self._profile.paused_remaining)
                if remaining > 0:
                    self._profile.running = True
                    self._profile.end_epoch = time.time() + remaining
                    self._profile.paused_remaining = 0
                    title = "Таймер продолжен"
                else:
                    title = "Запуск таймера без времени"
            self._persist_timer()
            running = self._profile.running
            self.storage.add_event(self._profile.id, "timer", title, 0)
        self._notify()
        return running

    def reset(self) -> None:
        with self._lock:
            before = self.remaining_seconds()
            self._profile.running = False
            self._profile.end_epoch = None
            self._profile.paused_remaining = 0
            self._persist_timer()
            self.storage.add_event(self._profile.id, "manual", "Сброс таймера", -int(round(before)))
        self._notify()

    def set_rate(self, amount: float, seconds: int) -> None:
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        if seconds <= 0:
            raise ValueError("Время должно быть больше нуля")
        with self._lock:
            old_amount = self._profile.rate_amount
            old_seconds = self._profile.rate_seconds
            self._profile.rate_amount = float(amount)
            self._profile.rate_seconds = int(seconds)
            self.storage.update_rate(self._profile.id, amount, seconds)
            self.storage.add_event(
                self._profile.id,
                "rate",
                f"Ставка: {self._fmt_money(old_amount)} ₽ / {self._fmt_time(old_seconds)} → {self._fmt_money(amount)} ₽ / {self._fmt_time(seconds)}",
                0,
            )
        self._notify()

    @staticmethod
    def _fmt_money(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _fmt_time(seconds: int) -> str:
        seconds = int(seconds)
        if seconds % 60 == 0:
            return f"{seconds // 60} мин"
        return f"{seconds} сек"

    def set_overlay_settings(self, theme: str, title: str, show_rate: bool = True) -> None:
        allowed = {"classic", "neon", "minimal", "retro", "glass", "cyber", "streamer", "gaming", "elegant", "scoreboard"}
        theme = (theme or "classic").strip().lower()
        if theme not in allowed:
            raise ValueError("Неизвестный стиль оверлея")
        title = (title or "").strip()
        with self._lock:
            self._profile.overlay_theme = theme
            self._profile.overlay_title = title
            self._profile.overlay_show_rate = bool(show_rate)
            self.storage.update_overlay_settings(
                self._profile.id,
                theme=theme,
                title=title,
                show_rate=bool(show_rate),
            )
            self.storage.add_event(
                self._profile.id,
                "overlay",
                f"Оформление OBS: {theme}",
                0,
            )
        self._notify()

    # ---------- stream sessions ----------

    def active_session(self) -> Session | None:
        return self.storage.active_session(self._profile.id)

    def start_session(self, name: str, starting_seconds: int) -> Session:
        with self._lock:
            current = self.storage.active_session(self._profile.id)
            if current:
                self.storage.add_event(
                    self._profile.id,
                    "session",
                    f"Сессия завершена: {current.name}",
                    0,
                    session_id=current.id,
                )
                self.storage.end_session(self._profile.id)
            session = self.storage.start_session(self._profile.id, name, starting_seconds)
            self._set_remaining_locked(max(0, int(starting_seconds)))
            self.storage.add_event(
                self._profile.id,
                "session",
                f"Сессия начата: {session.name}",
                0,
                session_id=session.id,
            )
        self._notify()
        return session

    def toggle_session_pause(self) -> Session | None:
        with self._lock:
            current = self.storage.active_session(self._profile.id)
            if not current:
                return None
            pause = current.paused_at is None
            updated = self.storage.set_session_paused(self._profile.id, current.id, pause)
            if updated:
                self.storage.add_event(
                    self._profile.id,
                    "session",
                    f"Сессия {'приостановлена' if pause else 'продолжена'}: {current.name}",
                    0,
                    session_id=current.id,
                )
        self._notify()
        return updated

    def end_session(self) -> Session | None:
        with self._lock:
            current = self.storage.active_session(self._profile.id)
            if not current:
                return None
            self.storage.add_event(
                self._profile.id,
                "session",
                f"Сессия завершена: {current.name}",
                0,
                session_id=current.id,
            )
            ended = self.storage.end_session(self._profile.id)
        self._notify()
        return ended

    def rename_session(self, session_id: int, name: str) -> Session | None:
        with self._lock:
            current = self.storage.get_session(self._profile.id, int(session_id))
            if not current:
                return None
            new_name = (name or "").strip()
            if not new_name:
                raise ValueError("Название сессии не может быть пустым")
            if new_name == current.name:
                return current
            renamed = self.storage.rename_session(self._profile.id, current.id, new_name)
            if renamed:
                self.storage.add_event(
                    self._profile.id,
                    "session",
                    f"Сессия переименована: {current.name} → {new_name}",
                    0,
                    session_id=current.id,
                )
        self._notify()
        return renamed

    def delete_session(self, session_id: int) -> Session | None:
        with self._lock:
            session = self.storage.get_session(self._profile.id, int(session_id))
            if not session:
                return None
            deleted = self.storage.delete_session(self._profile.id, session.id)
            if deleted:
                self.storage.add_event(
                    self._profile.id,
                    "session",
                    f"Сессия удалена: {deleted.name}",
                    0,
                    session_id=None,
                    auto_session=False,
                )
        self._notify()
        return deleted

    def undo_time_event(self, event_id: int) -> Event | None:
        with self._lock:
            event = self.storage.get_reversible_event(self._profile.id, int(event_id))
            if not event:
                return None
            before = self.remaining_seconds()
            new_value = max(0.0, before - event.seconds_delta)
            self._set_remaining_locked(new_value)
            if not self.storage.undo_event(event):
                self._set_remaining_locked(before)
                return None
        self._notify()
        return event

    def undo_last_time_event(self) -> Event | None:
        event = self.storage.last_reversible_event(self._profile.id)
        return self.undo_time_event(event.id) if event else None

    def apply_donation(
        self,
        donation_id: str,
        sender: str,
        amount: float,
        currency: str,
        *,
        amount_in_user_currency: float | None = None,
    ) -> int:
        """Apply a donation proportionally. Duplicate donation IDs are ignored."""
        with self._lock:
            effective_amount = amount_in_user_currency if amount_in_user_currency is not None else amount
            seconds = math.floor((effective_amount / self._profile.rate_amount) * self._profile.rate_seconds)
            seconds = max(0, int(seconds))
            donation_key = str(donation_id)
            if not self.storage.mark_processed(self._profile.id, donation_key):
                return 0

            # Keep the original amount/currency for the audit log. The timer itself
            # is based on amount_in_user_currency when DonationAlerts supplies it.
            self.storage.add_event(
                self._profile.id,
                "donation",
                sender or "Аноним",
                seconds,
                amount=amount,
                currency=currency,
                credited_amount=effective_amount,
                external_id=donation_key,
            )
            if seconds:
                current = self.remaining_seconds()
                self._set_remaining_locked(current + seconds)
        self._notify()
        return seconds

    def snapshot(self) -> dict:
        with self._lock:
            remaining = self.remaining_seconds()
            return {
                "server_now": time.time(),
                "profile_id": self._profile.id,
                "profile_name": self._profile.name,
                "running": bool(self._profile.running and remaining > 0),
                "remaining_seconds": remaining,
                "end_epoch": self._profile.end_epoch if self._profile.running else None,
                "rate_amount": self._profile.rate_amount,
                "rate_seconds": self._profile.rate_seconds,
                "currency": "RUB",
                "overlay_theme": self._profile.overlay_theme,
                "overlay_title": self._profile.overlay_title,
                "overlay_show_rate": self._profile.overlay_show_rate,
            }
