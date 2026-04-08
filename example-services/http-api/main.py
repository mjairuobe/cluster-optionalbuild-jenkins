"""Minimaler HTTP-Service (Beispiel)."""

from fastapi import FastAPI

app = FastAPI(title="http-api", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
