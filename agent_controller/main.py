"""Agent-controller FastAPI entrypoint."""

from fastapi import FastAPI

from agent_controller.routes.chat import router as chat_router

app = FastAPI()

app.include_router(chat_router)


@app.get("/")
def root():
    return {"status": "Agent Controller running"}
