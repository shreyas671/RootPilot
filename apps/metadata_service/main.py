from fastapi import FastAPI

app = FastAPI(
    title="RootPilot Metadata Service",
    version="0.1.0",
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "metadata-service",
    }