from fastapi import FastAPI, Request
from src.api.routes import router

app = FastAPI(title="Paper Lens API")


@app.middleware("http")
async def add_monitoring_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Monitoring-Log"] = "src/monitoring/logs/paper_lens_monitoring.jsonl"
    return response


app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True)
