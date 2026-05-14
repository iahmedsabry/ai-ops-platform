"""FastAPI routes for chat metadata and message handling."""

from fastapi import APIRouter

from agent_controller.chat_orchestrator import ChatOrchestrator
from agent_controller.models import ChatRequest

router = APIRouter()
_orchestrator = ChatOrchestrator()


@router.get("/chat")
def chat_metadata():
    return _orchestrator.chat_metadata()


@router.post("/chat")
def chat(request: ChatRequest):
    return _orchestrator.handle_chat(request)
