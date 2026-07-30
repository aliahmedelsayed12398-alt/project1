def chunk_text(text: str, size: int = 500) -> list[str]:
    return [text[i:i+size] for i in range(0, len(text), size)]
