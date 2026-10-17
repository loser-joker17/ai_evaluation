import os, time
from dotenv import load_dotenv
from openai import OpenAI
import sys

load_dotenv()
client = OpenAI(base_url="https://integrate.api.nvidia.com/v1",
                api_key=os.getenv("NVIDIA_API_KEY"), timeout=60)
models = sys.argv[1:] or [os.getenv("FAST_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
                          os.getenv("JUDGE_MODEL", "z-ai/glm-5.3")]
for m in models:
    t = time.time()
    try:
        r = client.chat.completions.create(model=m, max_tokens=5,
              messages=[{"role": "user", "content": "Say OK"}])
        print(f"OK    {m}  ({time.time()-t:.0f}s): {r.choices[0].message.content!r}")
    except Exception as e:
        print(f"FAIL  {m}  ({time.time()-t:.0f}s): {type(e).__name__}: {str(e)[:200]}")