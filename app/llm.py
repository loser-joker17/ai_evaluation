
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


def make_llm(model: str, timeout: int = 180) -> ChatOpenAI:
    key = os.getenv("NVIDIA_API_KEY")

    if not key:
        raise RuntimeError("NVIDIA_API_KEY is missing. Check your .env file.")

    return ChatOpenAI(
        model=model,
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=key,
        temperature=0,
        max_retries=2,
        timeout=timeout,
        seed=7,
    )


fast_llm = make_llm(
    os.getenv("FAST_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
)

judge_llm = make_llm(
    os.getenv("JUDGE_MODEL", "z-ai/glm-5.3"),
    timeout=300,
)

llm = fast_llm  # Existing imports keep working


# Smaller/faster model for question analysis and feature extraction.
# Same as FAST_MODEL unless LIGHT_MODEL is set in .env.
light_llm = make_llm(
    os.getenv("LIGHT_MODEL")
    or os.getenv("FAST_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
)
