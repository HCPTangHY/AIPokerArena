from pydantic import BaseModel, Field


class AIPlayerConfig(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str
    api_endpoint: str  # e.g., "https://api.openai.com"
    api_key: str
    model_name: str
    enable_thinking: bool = False
    thinking_visible: bool = False
    thinking_budget_tokens: int = Field(ge=0, le=32768, default=4096)  # Claude; 0 = not used
    reasoning_effort: str = "high"  # DeepSeek: "high" or "max"
    prompt_override: str = ""
    avatar_url: str = ""
