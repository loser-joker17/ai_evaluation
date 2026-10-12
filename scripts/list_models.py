import os
import time

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

load_dotenv()

CANDIDATES = [
    "nvidia/nemotron-3-ultra-550b-a55b",
    "moonshotai/kimi-k3",
    "mistralai/mistral-large-2-instruct",
]

CANDIDATES2 = [
    "moonshotai/kimi-k3",
    "deepseek-ai/deepseek-v4.1-flash",
    "z-ai/glm-5.3"
]

class Out(BaseModel):
    level: int
    reason: str


PROMPT = (
    "Score this answer from 0 to 5 and give a one-sentence reason: "
    "'Social justice reduces inequality.'"
)

for name in CANDIDATES2:
    llm = ChatOpenAI(
        model=name,
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=os.getenv("NVIDIA_API_KEY"),
        temperature=0,
        max_retries=1,
        timeout=360,
    )
    for method in ("json_schema", "function_calling"):
        start = time.time()
        try:
            r = llm.with_structured_output(Out, method=method).invoke(PROMPT)
            print(f"OK    {name} [{method}] {time.time() - start:.1f}s -> {r}")
        except Exception as e:
            print(f"FAIL  {name} [{method}] {time.time() - start:.1f}s {type(e).__name__}: {str(e)[:120]}")