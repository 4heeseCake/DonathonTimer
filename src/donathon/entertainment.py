from __future__ import annotations

import json
import math
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Any

from .state import AppState
from .storage import Storage


COLORS = [
    "#2dd4bf", "#8b5cf6", "#f59e0b", "#ec4899", "#3b82f6",
    "#22c55e", "#f97316", "#06b6d4", "#eab308", "#a855f7",
    "#ef4444", "#14b8a6", "#6366f1", "#84cc16", "#f43f5e",
]


def _norm_text(value: str) -> str:
    value = (value or "").strip().casefold()
    value = re.sub(r"[^\w\sа-яё-]", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _safe_label(value: str, fallback: str = "Без текста") -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text[:120] or fallback


class EntertainmentService:
    """Live stream interactions: roulettes and Twitch-chat polls.

    State is persisted as compact JSON in app_settings per profile. Live Twitch chat
    and DonationAlerts events are received through lightweight callbacks from the
    existing collectors, so no second network connection is needed.
    """

    def __init__(self, state: AppState, storage: Storage, da_service, twitch_service):
        self.state = state
        self.storage = storage
        self.da_service = da_service
        self.twitch_service = twitch_service
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []
        self._rng = random.SystemRandom()
        self._last_live_save = 0.0
        self._profile_id = state.profile.id
        self._data = self._load(self._profile_id)
        self.state.add_listener(self._on_state_change)
        if hasattr(self.da_service, "add_donation_listener"):
            self.da_service.add_donation_listener(self._on_donation)
        if hasattr(self.twitch_service, "add_chat_listener"):
            self.twitch_service.add_chat_listener(self._on_chat)

    # ---------- persistence ----------

    def _key(self, profile_id: int) -> str:
        return f"entertainment_state_v1:{int(profile_id)}"

    def _default(self) -> dict:
        return {
            "display_type": None,
            "timer_visible": False,
            "interactive_visible": False,
            "active_mode": "manual",  # manual | chat | donation | poll
            "show_timer_with_interactive": False,
            "roulette": {
                "mode": "manual",  # manual | chat | donation
                "title": "Рулетка",
                "collecting": False,
                "overlay_enabled": True,
                "manual_mode": "winner",  # winner | elimination
                "manual_options": [],
                "chat_keyword": "ХОЧУ",
                "chat_match": "exact",  # exact | contains
                "chat_entries": {},  # normalized username -> display name
                "donation_options": {},  # normalized message -> {label, amount, donors}
                "result": "",
                "result_status": "",
                "spin_nonce": 0,
                "spin_angle": 0.0,
                "spin_speed": "normal",  # fast | normal
                "pending_spin": None,     # outcome is committed only after wheel stops
                "spin_started_at": None,
                "spin_ends_at": None,
                "started_at": None,
            },
            "poll": {
                "question": "Во что играем дальше?",
                "options": ["Cyberpunk", "Гарри Поттер", "CS2"],
                "active": False,
                "overlay_enabled": True,
                "vote_mode": "unique",  # unique | all | change
                "votes": {},  # option index str -> count
                "user_votes": {},  # user id/name -> index
                "started_at": None,
                "finished_at": None,
            },
        }

    def _load(self, profile_id: int) -> dict:
        base = self._default()
        raw = self.storage.get_setting(self._key(profile_id))
        if not raw:
            return base
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return base
        except Exception:
            return base
        # Conservative merge so future fields get defaults.
        for k in ("display_type","timer_visible","interactive_visible","active_mode","show_timer_with_interactive"):
            if k in parsed:
                base[k] = parsed[k]
        # Old 0.9.0/0.9.1 installs did not have independent visibility flags.
        # New flags intentionally default to False so OBS starts clean after update.
        if "active_mode" not in parsed:
            if parsed.get("display_type") == "poll":
                base["active_mode"] = "poll"
            else:
                mode = str((parsed.get("roulette") or {}).get("mode") or "manual")
                base["active_mode"] = mode if mode in {"manual","chat","donation"} else "manual"
        for section in ("roulette", "poll"):
            if isinstance(parsed.get(section), dict):
                base[section].update(parsed[section])
        return base

    def _save_locked(self) -> None:
        self.storage.set_setting(self._key(self._profile_id), json.dumps(self._data, ensure_ascii=False, separators=(",", ":")))
        self._last_live_save = time.time()

    def _save_live_locked(self) -> None:
        # During a busy poll/chat we keep counting fully in memory but avoid one
        # SQLite transaction per chat message. Persist at most ~twice per second.
        if time.time() - self._last_live_save >= 0.6:
            self._save_locked()

    def _on_state_change(self) -> None:
        profile_id = self.state.profile.id
        with self._lock:
            if profile_id == self._profile_id:
                return
            self._profile_id = profile_id
            self._data = self._load(profile_id)
        self._notify()

    def add_listener(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    # ---------- roulette ----------

    def configure_manual(self, title: str, options: list[str], mode: str = "winner", overlay_enabled: bool = True) -> None:
        cleaned = []
        seen = set()
        for item in options:
            label = _safe_label(item, "")
            key = _norm_text(label)
            if label and key and key not in seen:
                seen.add(key); cleaned.append(label)
        if len(cleaned) < 2:
            raise ValueError("Добавьте минимум два варианта")
        with self._lock:
            r = self._data["roulette"]
            r.update({"mode":"manual", "title":_safe_label(title,"Рулетка"), "manual_mode": mode if mode in {"winner","elimination"} else "winner",
                      "manual_options":cleaned, "collecting":False, "overlay_enabled":bool(overlay_enabled), "result":"", "result_status":""})
            self._data["active_mode"] = "manual"
            self._save_locked()
        self._notify()

    def start_chat_roulette(self, title: str, keyword: str, match: str = "exact", overlay_enabled: bool = True) -> None:
        keyword = _safe_label(keyword, "")
        if not keyword:
            raise ValueError("Введите слово для участия")
        with self._lock:
            r = self._data["roulette"]
            r.update({"mode":"chat", "title":_safe_label(title,"Розыгрыш из чата"), "chat_keyword":keyword,
                      "chat_match":match if match in {"exact","contains"} else "exact", "chat_entries":{}, "collecting":True,
                      "overlay_enabled":bool(overlay_enabled), "result":"", "result_status":"", "started_at":time.time()})
            self._data["active_mode"] = "chat"
            self._save_locked()
        self._notify()

    def start_donation_roulette(self, title: str, overlay_enabled: bool = True) -> None:
        with self._lock:
            r = self._data["roulette"]
            r.update({"mode":"donation", "title":_safe_label(title,"Донат-рулетка"), "donation_options":{}, "collecting":True,
                      "overlay_enabled":bool(overlay_enabled), "result":"", "result_status":"", "started_at":time.time()})
            self._data["active_mode"] = "donation"
            self._save_locked()
        self._notify()

    def stop_roulette_collection(self) -> None:
        with self._lock:
            self._data["roulette"]["collecting"] = False
            self._save_locked()
        self._notify()

    def clear_roulette(self) -> None:
        with self._lock:
            old = self._data["roulette"]
            active_mode = str(self._data.get("active_mode") or old.get("mode") or "manual")
            self._data["roulette"] = self._default()["roulette"]
            self._data["roulette"]["overlay_enabled"] = bool(old.get("overlay_enabled", True))
            self._data["roulette"]["spin_speed"] = str(old.get("spin_speed") or "normal")
            if active_mode in {"manual", "chat", "donation"}:
                self._data["roulette"]["mode"] = active_mode
            self._save_locked()
        self._notify()

    def set_timer_visible(self, enabled: bool) -> None:
        with self._lock:
            self._data["timer_visible"] = bool(enabled)
            self._data["show_timer_with_interactive"] = bool(enabled)
            self._save_locked()
        self._notify()

    def set_interactive_visible(self, enabled: bool) -> None:
        with self._lock:
            self._data["interactive_visible"] = bool(enabled)
            self._save_locked()
        self._notify()

    def select_mode(self, mode: str, title: str | None = None) -> None:
        mode = mode if mode in {"manual", "chat", "donation", "poll"} else "manual"
        with self._lock:
            previous = str(self._data.get("active_mode") or "manual")
            self._data["active_mode"] = mode
            changed = previous != mode
            if mode != "poll":
                r = self._data["roulette"]
                if r.get("mode") != mode:
                    r["pending_spin"] = None
                    r["spin_started_at"] = None
                    r["spin_ends_at"] = None
                    r["mode"] = mode
                    r["result"] = ""
                    r["result_status"] = ""
                    changed = True
                if title is not None:
                    clean_title = _safe_label(title, "Рулетка")
                    if r.get("title") != clean_title:
                        r["title"] = clean_title
                        changed = True
            if changed:
                self._save_locked()
        self._notify()

    def set_roulette_spin_speed(self, speed: str) -> None:
        with self._lock:
            self._data["roulette"]["spin_speed"] = "fast" if speed == "fast" else "normal"
            self._save_locked()
        self._notify()

    def set_roulette_overlay(self, enabled: bool) -> None:
        with self._lock:
            self._data["roulette"]["overlay_enabled"] = bool(enabled)
            self._save_locked()
        self._notify()

    def _finish_spin_locked(self, now: float | None = None) -> bool:
        """Commit an elimination only after both clients have finished spinning.

        Called from snapshots as well as mutations: survives restarts, without a
        background worker or a timer racing OBS. The spin outcome is kept private
        until its deadline; only the visual angle is exposed beforehand.
        """
        r = self._data["roulette"]
        pending = r.get("pending_spin")
        if not isinstance(pending, dict):
            return False
        if (time.time() if now is None else now) < float(r.get("spin_ends_at") or 0):
            return False
        if pending.get("remove"):
            options = list(r.get("manual_options") or [])
            target = str(pending.get("removed_label") or "")
            try:
                options.remove(target)
            except ValueError:
                pass
            r["manual_options"] = options
        r["result"] = str(pending.get("display_label") or "")
        r["result_status"] = str(pending.get("display_status") or "")
        r["pending_spin"] = None
        r["spin_started_at"] = None
        r["spin_ends_at"] = None
        self._save_locked()
        return True

    def _roulette_entries_locked(self) -> list[dict]:
        r = self._data["roulette"]
        mode = r.get("mode")
        if mode == "manual":
            return [{"key":str(i), "label":label, "weight":1.0, "meta":"равный шанс"} for i,label in enumerate(r.get("manual_options") or [])]
        if mode == "chat":
            values = list((r.get("chat_entries") or {}).values())
            return [{"key":str(i), "label":name, "weight":1.0, "meta":"участник"} for i,name in enumerate(values)]
        if mode == "donation":
            rows=[]
            for key, item in (r.get("donation_options") or {}).items():
                amount=max(0.0,float(item.get("amount") or 0))
                rows.append({"key":key, "label":str(item.get("label") or key), "weight":amount, "meta":f"{amount:.2f} ₽", "donors":int(item.get("donors") or 0)})
            return rows
        return []

    def spin_roulette(self) -> dict:
        with self._lock:
            self._finish_spin_locked()
            r = self._data["roulette"]
            if r.get("pending_spin"):
                raise ValueError("Колесо ещё крутится — дождитесь остановки")
            entries = self._roulette_entries_locked()
            if not entries:
                raise ValueError("В рулетке пока нет вариантов")
            weights = [max(0.0, float(x["weight"])) for x in entries]
            if sum(weights) <= 0:
                weights = [1.0] * len(entries)
            chosen = self._rng.choices(entries, weights=weights, k=1)[0]
            total = sum(weights)
            cursor = 0.0
            target_point = 0.0
            for item, weight in zip(entries, weights):
                span = 360.0 * weight / total
                if item["key"] == chosen["key"]:
                    pad = min(12.0, span * 0.18)
                    low = cursor + pad
                    high = max(low, cursor + span - pad)
                    target_point = self._rng.uniform(low, high)
                    break
                cursor += span
            # Both Qt and CSS use a top-mounted pointer and clockwise sectors.
            # Positive visual rotation lands point `target_point` under the top pointer.
            target_rotation = (360.0 - target_point) % 360.0
            mode = str(r.get("mode") or "")
            manual_mode = str(r.get("manual_mode") or "")
            remove = (mode == "manual" and manual_mode == "elimination" and len(entries) > 1)
            if remove:
                if len(entries) == 2:
                    # Last round: show the one remaining as winner, not the one eliminated.
                    remaining = next(item["label"] for item in entries if item["key"] != chosen["key"])
                    display_label, display_status = remaining, "ПОБЕДИТЕЛЬ"
                else:
                    display_label, display_status = chosen["label"], "ВЫБЫВШИЙ"
            else:
                display_label, display_status = chosen["label"], "ПОБЕДИТЕЛЬ"
            duration = 1.6 if str(r.get("spin_speed") or "normal") == "fast" else 6.2
            now = time.time()
            r["spin_nonce"] = int(r.get("spin_nonce") or 0) + 1
            r["spin_angle"] = target_rotation
            r["spin_started_at"] = now
            # Allow a little time for the 500ms OBS poll + frame scheduling.
            r["spin_ends_at"] = now + duration + 0.8
            r["pending_spin"] = {
                "remove": remove,
                "removed_label": chosen["label"] if remove else "",
                "display_label": display_label,
                "display_status": display_status,
            }
            # Important: no winner or eliminated name may leak before stop.
            r["result"] = ""
            r["result_status"] = ""
            if mode in {"manual", "chat", "donation"}:
                # Freeze collection while wheel turns: the displayed sectors
                # and their probabilities must not change mid-animation.
                r["collecting"] = False
            self._save_locked()
        self._notify()
        return {"status": "КРУТИТСЯ", "duration": duration}

    # ---------- poll ----------

    def start_poll(self, question: str, options: list[str], vote_mode: str = "unique", overlay_enabled: bool = True) -> None:
        clean=[]; seen=set()
        for x in options:
            label=_safe_label(x,""); key=_norm_text(label)
            if label and key and key not in seen:
                seen.add(key); clean.append(label)
        if len(clean)<2:
            raise ValueError("Добавьте минимум два варианта голосования")
        if len(clean)>10:
            raise ValueError("Максимум 10 вариантов")
        with self._lock:
            p=self._data["poll"]
            p.update({"question":_safe_label(question,"Голосование"), "options":clean, "active":True,
                      "overlay_enabled":bool(overlay_enabled), "vote_mode": vote_mode if vote_mode in {"unique","all","change"} else "unique",
                      "votes":{str(i):0 for i in range(len(clean))}, "user_votes":{}, "started_at":time.time(), "finished_at":None})
            self._data["active_mode"] = "poll"
            self._save_locked()
        self._notify()

    def stop_poll(self, keep_overlay: bool = True) -> None:
        with self._lock:
            p=self._data["poll"]; p["active"]=False; p["finished_at"]=time.time()
            p["overlay_enabled"] = bool(keep_overlay)
            if keep_overlay: self._data["display_type"]="poll"
            elif self._data.get("display_type")=="poll": self._data["display_type"]=None
            self._save_locked()
        self._notify()

    def clear_poll(self) -> None:
        with self._lock:
            enabled=bool(self._data["poll"].get("overlay_enabled", True))
            self._data["poll"]=self._default()["poll"]; self._data["poll"]["overlay_enabled"]=enabled
            if self._data.get("display_type")=="poll": self._data["display_type"]=None
            self._save_locked()
        self._notify()

    def set_show_timer_with_interactive(self, enabled: bool) -> None:
        self.set_timer_visible(enabled)

    def set_poll_overlay(self, enabled: bool) -> None:
        with self._lock:
            self._data["poll"]["overlay_enabled"] = bool(enabled)
            self._save_locked()
        self._notify()

    # ---------- live events ----------

    def _on_chat(self, item: dict) -> None:
        if int(item.get("profile_id") or -1) != self.state.profile.id:
            return
        changed=False
        text=str(item.get("text") or "").strip()
        user_name=str(item.get("user_name") or "Аноним").strip() or "Аноним"
        user_id=str(item.get("user_id") or user_name.casefold())
        with self._lock:
            r=self._data["roulette"]
            if r.get("mode")=="chat" and r.get("collecting"):
                kw=_norm_text(str(r.get("chat_keyword") or "")); msg=_norm_text(text)
                match = (msg==kw) if r.get("chat_match")=="exact" else bool(kw and re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", msg))
                if match:
                    entries=r.setdefault("chat_entries",{})
                    key=user_id.casefold()
                    if key not in entries:
                        entries[key]=user_name; changed=True
            p=self._data["poll"]
            if p.get("active"):
                match_idx=self._match_poll_option(text, p.get("options") or [])
                if match_idx is not None:
                    mode=p.get("vote_mode","unique"); votes=p.setdefault("votes",{}); users=p.setdefault("user_votes",{})
                    ukey=user_id.casefold(); previous=users.get(ukey)
                    if mode=="all":
                        votes[str(match_idx)]=int(votes.get(str(match_idx),0))+1; changed=True
                    elif mode=="unique":
                        if previous is None:
                            users[ukey]=match_idx; votes[str(match_idx)]=int(votes.get(str(match_idx),0))+1; changed=True
                    else:  # change
                        if previous != match_idx:
                            if previous is not None:
                                votes[str(previous)]=max(0,int(votes.get(str(previous),0))-1)
                            users[ukey]=match_idx; votes[str(match_idx)]=int(votes.get(str(match_idx),0))+1; changed=True
            if changed:self._save_live_locked()
        if changed:self._notify()

    @staticmethod
    def _match_poll_option(text: str, options: list[str]) -> int | None:
        msg=_norm_text(text)
        if not msg:return None
        if msg.isdigit():
            n=int(msg)
            if 1<=n<=len(options):return n-1
        for i,label in enumerate(options):
            if msg==_norm_text(label):return i
        return None

    def _on_donation(self, donation: dict) -> None:
        if int(donation.get("profile_id") or -1) != self.state.profile.id:
            return
        with self._lock:
            r=self._data["roulette"]
            if r.get("mode")!="donation" or not r.get("collecting"):
                return
            message=_safe_label(str(donation.get("message") or ""), "")
            key=_norm_text(message)
            if not key:
                return
            amount=float(donation.get("effective_amount") or donation.get("amount") or 0)
            opts=r.setdefault("donation_options",{})
            item=opts.get(key) or {"label":message,"amount":0.0,"donors":0}
            item["amount"]=float(item.get("amount") or 0)+max(0.0,amount)
            item["donors"]=int(item.get("donors") or 0)+1
            opts[key]=item
            self._save_live_locked()
        self._notify()

    # ---------- snapshots ----------

    def snapshot(self, max_entries: int | None = None) -> dict:
        with self._lock:
            self._finish_spin_locked()
            r=dict(self._data["roulette"]); p=dict(self._data["poll"])
            r["spinning"] = bool(r.get("pending_spin"))
            r.pop("pending_spin", None)
            entries=self._roulette_entries_locked()
            raw_total=sum(max(0.0,float(x["weight"])) for x in entries)
            equal_weights = raw_total <= 0 and bool(entries)
            total = float(len(entries)) if equal_weights else raw_total
            enriched=[]
            for idx,item in enumerate(entries):
                weight=1.0 if equal_weights else max(0.0,float(item["weight"]))
                pct=(weight/total*100.0) if total else 0.0
                enriched.append({**item,"percent":pct,"color":COLORS[idx%len(COLORS)]})
            total_count=len(enriched)
            if max_entries is not None and total_count > int(max_entries):
                limit=max(1,int(max_entries))
                if r.get("mode")=="donation":
                    visible=sorted(enriched,key=lambda x:float(x.get("weight") or 0),reverse=True)[:limit]
                else:
                    visible=enriched[:limit]
                # For a very large equal-chance chat wheel, displayed slices are a
                # visual sample only. Re-normalize them so the circle remains full.
                if r.get("mode")=="chat" and visible:
                    for item in visible: item["percent"]=100.0/len(visible)
                enriched=visible
            r["entries"]=enriched
            r["count"]=total_count
            r["total_weight"]=raw_total
            # Never expose large internal lookup maps to the OBS endpoint/UI snapshot.
            r.pop("chat_entries",None); r.pop("donation_options",None)
            options=list(p.get("options") or []); votes=p.get("votes") or {}; total_votes=sum(int(votes.get(str(i),0)) for i in range(len(options)))
            p["results"]=[{"label":label,"votes":int(votes.get(str(i),0)),"percent":((int(votes.get(str(i),0))/total_votes*100.0) if total_votes else 0.0),"color":COLORS[i%len(COLORS)]} for i,label in enumerate(options)]
            p["total_votes"]=total_votes
            p.pop("user_votes",None)
            active_mode = str(self._data.get("active_mode") or "manual")
            interactive_visible = bool(self._data.get("interactive_visible", False))
            if interactive_visible:
                display = "poll" if active_mode == "poll" else "roulette"
            else:
                display = None
            return {
                "display_type": display,
                "active_mode": active_mode,
                "timer_visible": bool(self._data.get("timer_visible", False)),
                "interactive_visible": interactive_visible,
                "show_timer_with_interactive": bool(self._data.get("timer_visible", False)),
                "roulette": r,
                "poll": p,
            }

