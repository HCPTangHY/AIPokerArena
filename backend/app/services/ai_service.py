import asyncio
import re
import json
import httpx
import inspect
from typing import AsyncGenerator
from app.models.player import AIPlayerConfig
from app.models.tournament import ActionType
from app.models.game import GameState, PlayerAction
from app.prompts.builder import PromptBuilder


class AIService:
    """Calls external LLM APIs for poker decisions.

    Supported formats (auto-detected from api_endpoint):
    - OpenAI-compatible: POST /v1/chat/completions (DeepSeek, OpenAI, Ollama, etc.)
    - Claude Messages API: POST /v1/messages (Anthropic native)
    - Gemini API: POST /v1beta/models/{model}:generateContent
    """

    def __init__(self, prompt_builder: PromptBuilder | None = None, timeout: float = 120.0):
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.timeout = timeout
        self.client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            import logging
            logger = logging.getLogger("ai_service")
            t = httpx.Timeout(timeout=self.timeout, connect=30.0)
            logger.info(f"AIService HTTP timeout: {self.timeout}s (read), connect=30s")
            self.client = httpx.AsyncClient(timeout=t)
        return self.client

    def _detect_provider(self, endpoint: str) -> str:
        el = endpoint.lower()
        if "anthropic" in el or "claude" in el:
            return "claude"
        if "googleapis" in el or "gemini" in el:
            return "gemini"
        return "openai"

    def _stringify_chunk_value(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return "".join(self._stringify_chunk_value(item) for item in value)
        if isinstance(value, dict):
            for key in ("text", "content", "thinking", "reasoning_content", "output_text", "value"):
                if key in value:
                    return self._stringify_chunk_value(value[key])
            return "".join(self._stringify_chunk_value(item) for item in value.values())
        return str(value)

    # ============================================================
    # Public methods
    # ============================================================

    async def get_action(
        self, player: AIPlayerConfig, state: GameState,
        legal_actions: list[ActionType], retries: int = 2,
        prompt_builder: PromptBuilder | None = None,
    ) -> PlayerAction:
        pb = prompt_builder or self.prompt_builder
        system_prompt = pb.build_system_prompt(player, state)
        user_message = pb.build_user_message(player, state, legal_actions)

        provider = self._detect_provider(player.api_endpoint)

        for attempt in range(retries + 1):
            try:
                if provider == "claude":
                    raw = await asyncio.wait_for(
                        self._call_claude(player, system_prompt, user_message),
                        timeout=self.timeout,
                    )
                elif provider == "gemini":
                    raw = await asyncio.wait_for(
                        self._call_gemini(player, system_prompt, user_message),
                        timeout=self.timeout,
                    )
                else:
                    raw = await asyncio.wait_for(
                        self._call_openai(player, system_prompt, user_message),
                        timeout=self.timeout,
                    )
                return self._parse_response(raw, player.id, provider)
            except Exception as e:
                if attempt == retries:
                    return PlayerAction(
                        player_id=player.id, action_type=ActionType.FOLD,
                        amount=0, thinking_content=f"Error: {e}", raw_response=str(e),
                    )
        return PlayerAction(player_id=player.id, action_type=ActionType.FOLD, amount=0)

    async def stream_action(
        self, player: AIPlayerConfig, state: GameState,
        legal_actions: list[ActionType], on_thinking: callable = None,
        prompt_builder: PromptBuilder | None = None,
    ) -> PlayerAction:
        pb = prompt_builder or self.prompt_builder
        system_prompt = pb.build_system_prompt(player, state)
        user_message = pb.build_user_message(player, state, legal_actions)

        provider = self._detect_provider(player.api_endpoint)
        thinking_text = ""
        content_text = ""

        try:
            async def consume_stream():
                nonlocal thinking_text, content_text
                if provider == "claude":
                    stream = self._call_claude_stream(player, system_prompt, user_message)
                elif provider == "gemini":
                    stream = self._call_gemini_stream(player, system_prompt, user_message)
                else:
                    stream = self._call_openai_stream(player, system_prompt, user_message)

                async for chunk in stream:
                    if chunk.get("thinking"):
                        thinking_text += chunk["thinking"]
                        if on_thinking:
                            maybe_awaitable = on_thinking(thinking_text)
                            if inspect.isawaitable(maybe_awaitable):
                                await maybe_awaitable
                    if chunk.get("content"):
                        content_text += chunk["content"]

            await asyncio.wait_for(consume_stream(), timeout=self.timeout)

            return self._parse_response_from_text(
                content_text, thinking_text, player.id,
            )
        except Exception as e:
            # Avoid spending another full timeout window on a fallback request.
            if content_text.strip() or thinking_text.strip():
                if thinking_text.strip() and not content_text.strip():
                    content_text = "ACTION: fold"
                return self._parse_response_from_text(
                    content_text,
                    thinking_text or f"Error: {e}",
                    player.id,
                )
            raise

    async def ask_reveal(
        self, player: AIPlayerConfig, state: GameState,
        prompt_builder: PromptBuilder | None = None,
        on_thinking: callable = None,
    ) -> bool:
        pb = prompt_builder or self.prompt_builder
        system = pb.build_system_prompt(player, state)
        user = pb.build_reveal_prompt(player, state)
        provider = self._detect_provider(player.api_endpoint)

        try:
            if player.enable_thinking and on_thinking:
                content_text = ""
                thinking_text = ""

                async def consume_stream():
                    nonlocal content_text, thinking_text
                    if provider == "claude":
                        stream = self._call_claude_stream(player, system, user)
                    elif provider == "gemini":
                        stream = self._call_gemini_stream(player, system, user)
                    else:
                        stream = self._call_openai_stream(player, system, user)

                    async for chunk in stream:
                        if chunk.get("thinking"):
                            thinking_text += chunk["thinking"]
                            maybe_awaitable = on_thinking(thinking_text)
                            if inspect.isawaitable(maybe_awaitable):
                                await maybe_awaitable
                        if chunk.get("content"):
                            content_text += chunk["content"]

                await asyncio.wait_for(consume_stream(), timeout=self.timeout)
                return "yes" in content_text.lower()
            else:
                if provider == "claude":
                    raw = await asyncio.wait_for(
                        self._call_claude(player, system, user),
                        timeout=self.timeout,
                    )
                elif provider == "gemini":
                    raw = await asyncio.wait_for(
                        self._call_gemini(player, system, user),
                        timeout=self.timeout,
                    )
                else:
                    raw = await asyncio.wait_for(
                        self._call_openai(player, system, user),
                        timeout=self.timeout,
                    )
                content = self._extract_content(raw, provider)
                return "yes" in content.lower()
        except Exception:
            return False

    # ============================================================
    # OpenAI-compatible
    # ============================================================

    async def _call_openai(self, player: AIPlayerConfig, system: str, user: str) -> dict:
        client = await self._get_client()
        ep = player.api_endpoint.rstrip("/")
        url = f"{ep}/chat/completions"
        headers = {"Authorization": f"Bearer {player.api_key}", "Content-Type": "application/json"}

        body: dict = {
            "model": player.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 8192 if "R1" in player.model_name else 65535,
        }

        self._add_thinking_openai(body, player)

        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json()

    def _add_thinking_openai(self, body: dict, player: AIPlayerConfig):
        if not player.enable_thinking:
            return
        el = player.api_endpoint.lower()
        mn = player.model_name.lower()
        if "R1" in mn:
            body["thinking"] = None
        elif "deepseek" in el:
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = player.reasoning_effort
        elif "openai" in el:
            body["reasoning_effort"] = player.reasoning_effort
        elif "4.7" in mn or "4-7" in mn:
            # Claude 4.7+ / 4.6+: adaptive thinking with output_config.effort
            body["thinking"] = {"type": "adaptive"}
            body["output_config"] = {"effort": player.reasoning_effort}
        else:
            body["thinking"] = {"type": "enabled"}
            if player.thinking_budget_tokens > 0:
                body["thinking"]["budget_tokens"] = player.thinking_budget_tokens

    async def _call_openai_stream(
        self, player: AIPlayerConfig, system: str, user: str
    ) -> AsyncGenerator[dict, None]:
        client = await self._get_client()
        ep = player.api_endpoint.rstrip("/")
        url = f"{ep}/chat/completions"
        headers = {"Authorization": f"Bearer {player.api_key}", "Content-Type": "application/json"}

        body: dict = {
            "model": player.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 65535,
            "stream": True,
        }
        if not player.enable_thinking:
            body["temperature"] = 0.7
        self._add_thinking_openai(body, player)

        async with client.stream("POST", url, json=body, headers=headers) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                ds = line[6:]
                if ds.strip() == "[DONE]":
                    break
                try:
                    d = json.loads(ds)
                    if "choices" in d and d["choices"]:
                        delta = d["choices"][0].get("delta", {})
                        t = (
                            self._stringify_chunk_value(delta.get("reasoning_content"))
                            or self._stringify_chunk_value(delta.get("reasoning"))
                            or self._stringify_chunk_value(delta.get("thinking"))
                        )
                        c = (
                            self._stringify_chunk_value(delta.get("content"))
                            or self._stringify_chunk_value(delta.get("text"))
                        )
                        if t or c:
                            yield {"thinking": t, "content": c}
                except json.JSONDecodeError:
                    continue

    # ============================================================
    # Claude Messages API (Anthropic native)
    # ============================================================

    async def _call_claude(self, player: AIPlayerConfig, system: str, user: str) -> dict:
        client = await self._get_client()
        ep = player.api_endpoint.rstrip("/")
        url = f"{ep}/messages"
        headers = {
            "x-api-key": player.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        body: dict = {
            "model": player.model_name,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": 65535,
        }
        if not player.enable_thinking:
            body["temperature"] = 0.7

        if player.enable_thinking:
            mn = player.model_name.lower()
            if "4.7" in mn or "4-7" in mn or "4.6" in mn or "4-6" in mn:
                tc = {"type": "adaptive"}
                tc["output_config"] = {"effort": player.reasoning_effort}
            else:
                tc = {"type": "enabled"}
                if player.thinking_budget_tokens > 0:
                    tc["budget_tokens"] = player.thinking_budget_tokens
            body["thinking"] = tc

        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json()

    async def _call_claude_stream(
        self, player: AIPlayerConfig, system: str, user: str
    ) -> AsyncGenerator[dict, None]:
        client = await self._get_client()
        ep = player.api_endpoint.rstrip("/")
        url = f"{ep}/messages"
        headers = {
            "x-api-key": player.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        body: dict = {
            "model": player.model_name,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": 65535,
            "stream": True,
        }
        if not player.enable_thinking:
            body["temperature"] = 0.7

        if player.enable_thinking:
            mn = player.model_name.lower()
            if "4.7" in mn or "4-7" in mn or "4.6" in mn or "4-6" in mn:
                tc = {"type": "adaptive"}
                tc["output_config"] = {"effort": player.reasoning_effort}
            else:
                tc = {"type": "enabled"}
                if player.thinking_budget_tokens > 0:
                    tc["budget_tokens"] = player.thinking_budget_tokens
            body["thinking"] = tc

        async with client.stream("POST", url, json=body, headers=headers) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line.startswith("data: "):
                    continue
                ds = line[6:]
                if ds.strip() == "[DONE]":
                    break
                try:
                    d = json.loads(ds)
                    event_type = d.get("type", "")
                    if event_type in ("content_block_delta", "content_block_start"):
                        delta = d.get("delta", {})
                        if event_type == "content_block_start":
                            delta = d.get("content_block", {})
                        t = (
                            self._stringify_chunk_value(delta.get("thinking"))
                            or self._stringify_chunk_value(delta.get("reasoning"))
                        )
                        c = self._stringify_chunk_value(delta.get("text"))
                        if t or c:
                            yield {"thinking": t, "content": c}
                except json.JSONDecodeError:
                    continue

    # ============================================================
    # Gemini API (Google v1beta)
    # ============================================================

    async def _call_gemini(self, player: AIPlayerConfig, system: str, user: str) -> dict:
        client = await self._get_client()
        ep = player.api_endpoint.rstrip("/")
        # endpoint like: https://generativelanguage.googleapis.com/v1beta
        url = f"{ep}/models/{player.model_name}:generateContent"
        headers = {"x-goog-api-key": player.api_key, "Content-Type": "application/json"}

        body: dict = {
            "contents": [
                {"role": "user", "parts": [{"text": user}]}
            ],
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        gen_config: dict = {}
        if not player.enable_thinking:
            gen_config["temperature"] = 0.7

        if player.enable_thinking:
            gen_config["thinkingConfig"] = {
                "thinkingLevel": player.reasoning_effort if player.reasoning_effort in ("high", "low") else "high",
            }

        if gen_config:
            body["generationConfig"] = gen_config

        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json()

    async def _call_gemini_stream(
        self, player: AIPlayerConfig, system: str, user: str
    ) -> AsyncGenerator[dict, None]:
        # Gemini streaming returns different format; fall back to non-streaming
        raw = await self._call_gemini(player, system, user)
        # Yield as a single chunk
        content = self._extract_content(raw, "gemini")
        thinking = self._extract_thinking(raw, "gemini")
        if thinking:
            yield {"thinking": thinking, "content": ""}
        if content:
            yield {"thinking": "", "content": content}

    # ============================================================
    # Response parsing
    # ============================================================

    def _extract_content(self, raw: dict, provider: str) -> str:
        if provider == "claude":
            blocks = raw.get("content", [])
            for b in blocks if isinstance(blocks, list) else []:
                if b.get("type") == "text":
                    return self._stringify_chunk_value(b.get("text"))
            return ""

        if provider == "gemini":
            candidates = raw.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                return "".join(self._stringify_chunk_value(p.get("text")) for p in parts)
            return ""

        # OpenAI-compatible
        if "choices" in raw and raw["choices"]:
            return self._stringify_chunk_value(raw["choices"][0].get("message", {}).get("content", ""))
        return str(raw)

    def _extract_thinking(self, raw: dict, provider: str) -> str:
        if provider == "claude":
            blocks = raw.get("content", [])
            for b in blocks if isinstance(blocks, list) else []:
                if b.get("type") == "thinking":
                    return self._stringify_chunk_value(b.get("thinking"))
            return ""

        if provider == "gemini":
            candidates = raw.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for p in parts:
                    if "thought" in p:
                        return self._stringify_chunk_value(p.get("thought"))
            return ""

        # OpenAI-compatible
        if "choices" in raw and raw["choices"]:
            message = raw["choices"][0].get("message", {})
            return (
                self._stringify_chunk_value(message.get("reasoning_content"))
                or self._stringify_chunk_value(message.get("reasoning"))
                or self._stringify_chunk_value(message.get("thinking"))
            )
        return ""

    def _parse_response(self, raw: dict, player_id: str, provider: str) -> PlayerAction:
        content = self._extract_content(raw, provider)
        thinking = self._extract_thinking(raw, provider)
        return self._parse_response_from_text(content, thinking, player_id)

    def _parse_response_from_text(self, content: str, thinking_content: str, player_id: str) -> PlayerAction:
        action_type = ActionType.FOLD
        amount = 0

        action_match = re.search(
            r'(?:ACTION|action|Action)[:：]\s*(.+?)$',
            content, re.MULTILINE,
        )
        action_text = ""
        if action_match:
            action_text = action_match.group(1).strip().lower()
        else:
            for line in content.split("\n"):
                ll = line.strip().lower()
                if any(a in ll for a in ["fold", "check", "call", "raise", "all_in", "all in"]):
                    action_text = ll
                    break

        action_text = action_text.rstrip(".,;! ")

        if "all_in" in action_text or "all in" in action_text or "all-in" in action_text:
            action_type = ActionType.ALL_IN
        elif action_text.startswith("raise"):
            nums = re.findall(r'\d+', action_text)
            amount = int(nums[0]) if nums else 0
            action_type = ActionType.RAISE
        elif action_text == "call" or action_text.startswith("call"):
            action_type = ActionType.CALL
            nums = re.findall(r'\d+', action_text)
            amount = int(nums[0]) if nums else 0
        elif action_text == "check":
            action_type = ActionType.CHECK
        elif action_text == "fold":
            action_type = ActionType.FOLD
        else:
            if "raise" in action_text:
                action_type = ActionType.RAISE
                nums = re.findall(r'\d+', action_text)
                amount = int(nums[0]) if nums else 0
            elif "call" in action_text:
                action_type = ActionType.CALL
            elif "check" in action_text:
                action_type = ActionType.CHECK

        return PlayerAction(
            player_id=player_id,
            action_type=action_type,
            amount=amount,
            thinking_content=thinking_content,
            raw_response=content,
        )

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None
