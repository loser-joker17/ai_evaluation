
# import os

# from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI

# load_dotenv()


# def get_llm() -> ChatOpenAI:
#     """Create and return the configured chat model."""

#     api_key = os.getenv("NVIDIA_API_KEY")

#     if not api_key:
#         raise RuntimeError(
#             "NVIDIA_API_KEY is missing. Check your .env file."
#         )

#     return ChatOpenAI(
#         model="openai/gpt-oss-20b",
#         base_url="https://integrate.api.nvidia.com/v1",
#         api_key=api_key,
#         temperature=0,
#         max_retries=4,
#         timeout=90,
#     )

# llm = get_llm()
# # print(llm.invoke("Say OK").content)

import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

# provider name -> (base URL, name of the .env variable holding its key)
PROVIDERS = {
    "nvidia": ("https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY"),
    "unorouter": ("https://api.unorouter.com/v1", "UNOROUTER_API_KEY"),
}
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "nvidia")


def provider_key(provider: str) -> str:
    if provider not in PROVIDERS:
        raise RuntimeError(f"Unknown provider {provider!r}. Choose one of: {', '.join(PROVIDERS)}")
    env = PROVIDERS[provider][1]
    key = os.getenv(env)
    if not key:
        raise RuntimeError(f"{env} is missing. Check your .env file.")
    return key


def make_llm(model: str, timeout: int = 180, provider: "str | None" = None,
             max_tokens: "int | None" = None) -> ChatOpenAI:
    provider = provider or DEFAULT_PROVIDER
    if max_tokens is None and provider != "nvidia":
        # Other providers (UnoRouter) default to a small output limit that cuts off
        # gpt-oss's reasoning and JSON. NVIDIA has no such limit, so nothing is sent there.
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "16000"))
    extra = {"max_tokens": max_tokens} if max_tokens else {}
    return ChatOpenAI(
        **extra,
        model=model,
        base_url=PROVIDERS.get(provider, ("", ""))[0],
        api_key=provider_key(provider),
        temperature=0,
        max_retries=2,
        timeout=timeout,
        seed=7,
    )


# Each role can use its own provider: FAST_PROVIDER, JUDGE_PROVIDER, LIGHT_PROVIDER
# (each falls back to LLM_PROVIDER, then "nvidia").
fast_llm = make_llm(
    os.getenv("FAST_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
    provider=os.getenv("FAST_PROVIDER"),
)

class _StructuredWithBackup:
    """Calls the main judge; if that call fails (provider down, busy, bad output),
    the same request goes to the backup judge and a line is printed saying so."""

    def __init__(self, primary, backup, backup_name):
        self.primary, self.backup, self.backup_name = primary, backup, backup_name

    def invoke(self, *args, **kwargs):
        try:
            return self.primary.invoke(*args, **kwargs)
        except Exception as exc:
            print(f"[judge-backup] main judge failed ({type(exc).__name__}); using {self.backup_name}")
            return self.backup.invoke(*args, **kwargs)


class _JudgeWithBackup:
    """Looks like a normal chat model to scoring.py. Only with_structured_output (what the
    judge uses) gets the backup; everything else goes straight to the main judge."""

    def __init__(self, primary, backup, backup_name):
        self.primary, self.backup, self.backup_name = primary, backup, backup_name

    def with_structured_output(self, *args, **kwargs):
        return _StructuredWithBackup(self.primary.with_structured_output(*args, **kwargs),
                                     self.backup.with_structured_output(*args, **kwargs),
                                     self.backup_name)

    def __getattr__(self, name):
        return getattr(self.primary, name)


_judge_timeout = int(os.getenv("JUDGE_TIMEOUT", "300"))
# Room for gpt-oss's reasoning plus the full scoring JSON. Some providers default to a
# small output limit and cut the JSON off ("max completion tokens reached").
# NVIDIA has no small default, so no limit is sent there (8000 cut off long gpt-oss reasoning).
_judge_max_tokens = int(os.getenv("JUDGE_MAX_TOKENS", "16000"))


def _judge_tokens(provider):
    provider = provider or DEFAULT_PROVIDER
    return None if provider == "nvidia" and not os.getenv("JUDGE_MAX_TOKENS") else _judge_max_tokens
judge_llm = make_llm(
    os.getenv("JUDGE_MODEL", "z-ai/glm-5.3"),
    timeout=_judge_timeout,
    provider=os.getenv("JUDGE_PROVIDER"),
    max_tokens=_judge_tokens(os.getenv("JUDGE_PROVIDER")),
)

# Optional backup judge, e.g. the same gpt-oss-20b on another provider:
#   JUDGE_BACKUP_PROVIDER=unorouter
#   JUDGE_BACKUP_MODEL=gpt-oss-20b:free
# Off unless JUDGE_BACKUP_MODEL is set.
if os.getenv("JUDGE_BACKUP_MODEL"):
    _backup_provider = os.getenv("JUDGE_BACKUP_PROVIDER") or DEFAULT_PROVIDER
    judge_llm = _JudgeWithBackup(
        judge_llm,
        make_llm(os.getenv("JUDGE_BACKUP_MODEL"), timeout=_judge_timeout, provider=_backup_provider,
                 max_tokens=_judge_tokens(_backup_provider)),
        f"{_backup_provider}/{os.getenv('JUDGE_BACKUP_MODEL')}",
    )

llm = fast_llm  # Existing imports keep working


# Smaller/faster model for question analysis and feature extraction.
# Same as FAST_MODEL unless LIGHT_MODEL is set in .env.
light_llm = make_llm(
    os.getenv("LIGHT_MODEL")
    or os.getenv("FAST_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
    provider=os.getenv("LIGHT_PROVIDER") or os.getenv("FAST_PROVIDER"),
)
