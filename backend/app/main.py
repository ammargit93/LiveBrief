from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def read_root():
    """
    Basic health‑check endpoint.
    Returns a simple JSON message.
    """
    return {"message": "Hello, FastAPI!"}


if __name__ == "__main__":
    import uvicorn

    # Run the application with hot‑reload for development.
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
