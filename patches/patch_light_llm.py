"""Adds a separate, smaller 'light' model for question analysis and feature extraction.
Nothing changes until you set LIGHT_MODEL in .env: the default is the same model as before.
Edits: app/llm.py, app/evaluator/question_analysis.py, app/evaluator/features.py
Run from the project root:   python patch_light_llm.py
Changes NOTHING if an expected line is missing or appears twice."""
from pathlib import Path

LLM = Path("app/llm.py")
EDITS = [
    (Path("app/evaluator/question_analysis.py"), "from app.llm import llm\n"),
    (Path("app/evaluator/features.py"), "from app.llm import llm\n"),
]
NEW_IMPORT = "from app.llm import light_llm as llm  # LIGHT_MODEL; same model as before unless you set it\n"

ADDITION = '''

# Smaller/faster model for question analysis and feature extraction.
# Same as FAST_MODEL unless LIGHT_MODEL is set in .env.
light_llm = make_llm(
    os.getenv("LIGHT_MODEL")
    or os.getenv("FAST_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
)
'''


def read(p):
    raw = p.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), "\r\n" in raw


def write(p, s, crlf):
    p.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))


plans = []
llm_text, llm_crlf = read(LLM)
if "light_llm" in llm_text:
    raise SystemExit("Already patched. Nothing was changed.")
if llm_text.count("def make_llm(") != 1:
    raise SystemExit("[llm.py] expected exactly one 'def make_llm('. Nothing was changed.")
plans.append((LLM, llm_text.rstrip("\n") + "\n" + ADDITION, llm_crlf))

for path, old in EDITS:
    text, crlf = read(path)
    if text.count(old) != 1:
        raise SystemExit(f"[{path}] expected exactly 1 match of {old.strip()!r}, found {text.count(old)}. "
                         "Nothing was changed.")
    plans.append((path, text.replace(old, NEW_IMPORT), crlf))

for path, text, crlf in plans:
    write(path, text, crlf)
print("patched llm.py, question_analysis.py, features.py")
print("Now add a line like  LIGHT_MODEL=openai/gpt-oss-20b  to your .env to use a smaller model.")