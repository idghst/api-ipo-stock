from fastapi import FastAPI

app = FastAPI(title="IPO Stock API")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "IPO Stock API"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
