
from app.retrieval.corpus import load_chunks

chunks = load_chunks()

for chunk in chunks:
    if "Madras Bar Association" in chunk["text"]:
        print(f"File: {chunk['file']}")
        print(f"Page: {chunk['page']}")
        print("\nFULL CHUNK:\n")
        print(chunk["text"])
        print("\n" + "=" * 80)
