"""List the models a provider offers, and optionally ping some of them.

    python scripts/list_provider_models.py unorouter              # list all model ids
    python scripts/list_provider_models.py unorouter --grep free  # only ids containing "free"
    python scripts/list_provider_models.py unorouter --ping gpt-oss-20b glm-5.2:free
    python scripts/list_provider_models.py unorouter --ping gpt-oss-120b:free --structured
    python scripts/list_provider_models.py nvidia --grep gpt-oss

Providers and their keys are defined in app/llm.py (PROVIDERS). No scoring is done here.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI  # noqa: E402
from app.llm import PROVIDERS, provider_key  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("provider", choices=sorted(PROVIDERS))
    ap.add_argument("--grep", default="", help="show only ids containing this text (case-insensitive)")
    ap.add_argument("--ping", nargs="*", default=None, help="model ids to send a one-line test prompt")
    ap.add_argument("--structured", action="store_true",
                    help="with --ping: test structured output (what the judge needs) instead of plain text")
    args = ap.parse_args()

    base_url, _ = PROVIDERS[args.provider]
    client = OpenAI(base_url=base_url, api_key=provider_key(args.provider), timeout=60)

    if args.ping is None:
        try:
            ids = sorted(m.id for m in client.models.list())
        except Exception as e:
            raise SystemExit(f"Could not list models from {base_url}: {type(e).__name__}: {str(e)[:200]}")
        shown = [i for i in ids if args.grep.lower() in i.lower()]
        for i in shown:
            print(i)
        print(f"\n{len(shown)} shown / {len(ids)} total on {args.provider}")
        return

    if args.structured:
        from pydantic import BaseModel
        from app.llm import make_llm

        class Out(BaseModel):
            level: int
            reason: str

        prompt = ("Score this UPSC answer from 0 to 5 and give a one-sentence reason: "
                  "'Social justice reduces inequality.'")
        for m in args.ping:
            for method in ("json_schema", "function_calling"):
                t = time.time()
                try:
                    r = make_llm(m, timeout=180, provider=args.provider).with_structured_output(
                        Out, method=method).invoke(prompt)
                    print(f"OK    {m} [{method}] ({time.time() - t:.0f}s): {r}")
                except Exception as e:
                    print(f"FAIL  {m} [{method}] ({time.time() - t:.0f}s): {type(e).__name__}: {str(e)[:150]}")
        return

    for m in args.ping:
        t = time.time()
        try:
            r = client.chat.completions.create(model=m, max_tokens=200,
                                               messages=[{"role": "user", "content": "Reply with just: OK"}])
            print(f"OK    {m}  ({time.time() - t:.0f}s): {r.choices[0].message.content!r}")
        except Exception as e:
            print(f"FAIL  {m}  ({time.time() - t:.0f}s): {type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    main()