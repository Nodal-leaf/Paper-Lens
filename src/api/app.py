from fastapi import FastAPI
from src.api.routes import router

app = FastAPI(title="KSKS Parser API")

app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    # To run this, you can execute: python -m api.app
    # Or simply: uvicorn api.app:app --reload
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, reload=True)
