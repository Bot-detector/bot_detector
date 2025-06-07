# Define the to_jagex_name dependency
async def to_jagex_name(name: str) -> str:
    return name.lower().replace("_", " ").replace("-", " ").strip()