import time
from fastapi import WebSocket


class ConnectionManager:
    """Room-based WebSocket connection manager."""

    def __init__(self):
        self.rooms: dict[str, set[WebSocket]] = {}
        self.meta: dict[WebSocket, dict] = {}
        self.chat_history: dict[str, list[dict]] = {}
        self.active_thinking: dict[str, dict[str, dict]] = {}

    def reset_room_history(self, room: str):
        for target_room in self._target_rooms(room):
            self.chat_history[target_room] = []
            self.active_thinking[target_room] = {}

    def clear_thinking(self, room: str, player_id: str):
        for target_room in self._target_rooms(room):
            self.active_thinking.get(target_room, {}).pop(player_id, None)

    @staticmethod
    def _target_rooms(room: str) -> list[str]:
        if room == "main":
            return ["main"]
        return [room, "main"]

    async def send_room_snapshot(self, ws: WebSocket, room: str):
        try:
            await ws.send_json(self._build_room_snapshot(room))
        except Exception:
            self.disconnect(ws)

    async def broadcast_room_snapshot(self, room: str):
        await self.broadcast(room, self._build_room_snapshot(room))

    def _build_room_snapshot(self, room: str) -> dict:
        active_items = list(self.active_thinking.get(room, {}).values())
        active_thinking = active_items[-1] if active_items else None
        return {
            "type": "history_snapshot",
            "data": {
                "chat_messages": list(self.chat_history.get(room, [])),
                "active_thinking": active_thinking,
            },
            "timestamp": time.time(),
        }

    async def connect(self, ws: WebSocket, room: str, user_info: dict):
        await ws.accept()
        self.rooms.setdefault(room, set()).add(ws)
        self.chat_history.setdefault(room, [])
        self.active_thinking.setdefault(room, {})
        self.meta[ws] = {**user_info, "connected_at": time.time()}

    def disconnect(self, ws: WebSocket):
        for room in self.rooms.values():
            room.discard(ws)
        self.meta.pop(ws, None)

    async def broadcast(self, room: str, message: dict):
        dead = set()
        for ws in self.rooms.get(room, set()).copy():
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast_state(self, room: str, state) -> None:
        from app.models.game import GameState
        if isinstance(state, GameState):
            data = state.to_public_dict()
        else:
            data = state
        payload = {
            "type": "game_state",
            "data": data,
            "timestamp": time.time(),
        }
        for target_room in self._target_rooms(room):
            await self.broadcast(target_room, payload)

    async def broadcast_event(self, room: str, event_type: str, payload: dict):
        message = {
            "type": "game_event",
            "data": {"event_type": event_type, **payload},
            "timestamp": time.time(),
        }
        for target_room in self._target_rooms(room):
            await self.broadcast(target_room, message)

    async def broadcast_chat(
        self,
        room: str,
        player_id: str,
        player_name: str,
        message: str,
        is_thinking: bool = False,
        is_spectator: bool = False,
    ):
        payload = {
            "type": "chat",
            "player_id": player_id,
            "player_name": player_name,
            "message": message,
            "is_thinking": is_thinking,
            "is_spectator": is_spectator,
            "timestamp": time.time(),
        }
        for target_room in self._target_rooms(room):
            self.chat_history.setdefault(target_room, []).append(payload)
            self.chat_history[target_room] = self.chat_history[target_room][-500:]
        if not is_spectator:
            self.clear_thinking(room, player_id)
        for target_room in self._target_rooms(room):
            await self.broadcast(target_room, payload)

    async def broadcast_debug_prompt(self, room: str, player_id: str, player_name: str,
                                      system_prompt: str, user_message: str):
        """Broadcast debug prompt to spectators."""
        payload = {
            "type": "debug_prompt",
            "player_id": player_id,
            "player_name": player_name,
            "system_prompt": system_prompt,
            "user_message": user_message,
            "timestamp": time.time(),
        }
        for target_room in self._target_rooms(room):
            await self.broadcast(target_room, payload)

    async def broadcast_thinking_chunk(self, room: str, player_id: str, player_name: str, chunk: str):
        """Broadcast a streaming thinking chunk to spectators."""
        payload = {
            "type": "thinking_chunk",
            "player_id": player_id,
            "player_name": player_name,
            "chunk": chunk,
            "timestamp": time.time(),
        }
        for target_room in self._target_rooms(room):
            room_active = self.active_thinking.setdefault(target_room, {})
            room_active[player_id] = {
                "player_id": player_id,
                "player_name": player_name,
                "text": chunk,
            }
            await self.broadcast(target_room, payload)

    async def finalize_thinking(
        self,
        room: str,
        player_id: str,
        player_name: str,
        fallback_text: str = "",
    ):
        room_active = self.active_thinking.setdefault(room, {})
        text = room_active.get(player_id, {}).get("text", "") or fallback_text
        self.clear_thinking(room, player_id)
        if text.strip():
            await self.broadcast_chat(
                room,
                player_id,
                player_name,
                text,
                is_thinking=True,
            )

    async def broadcast_error(self, ws: WebSocket, error: str):
        try:
            await ws.send_json({"type": "error", "data": {"message": error}})
        except Exception:
            pass

    def spectator_count(self, room: str) -> int:
        return len(self.rooms.get(room, set()))

    def get_spectator_count(self, room: str) -> int:
        return self.spectator_count(room)
