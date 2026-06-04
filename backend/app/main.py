from fastapi import FastAPI

app = FastAPI(
    title="My Backend API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "Backend is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }