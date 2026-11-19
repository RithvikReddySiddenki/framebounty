"""Authenticated agent conversations and explicit user tool intentions."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agents import SessionIntent, create_session, execute_tool, message_turn, owned_session
from .auth import current_wallet
from .db import session
from .domain import ClosedModel
from .models import AgentSession, AgentTurn

router = APIRouter()


class MessageRequest(ClosedModel):
    message: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")


class ToolRequest(ClosedModel):
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict = Field(default_factory=dict)
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")


@router.post("/agent-sessions")
def start(body: SessionIntent, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = create_session(db, wallet, body)
    return {"id": item.id, "role": item.role, "job_id": item.job_id, "profile": item.profile}


@router.get("/agent-sessions")
def sessions(wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    items = db.scalars(select(AgentSession).where(AgentSession.wallet == wallet).order_by(AgentSession.created_at.desc()).limit(30)).all()
    return {"sessions": [{"id": item.id, "role": item.role, "job_id": item.job_id, "profile": item.profile} for item in items]}


@router.get("/agent-sessions/{session_id}")
def history(session_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = owned_session(db, wallet, session_id)
    turns = db.scalars(select(AgentTurn).where(AgentTurn.session_id == item.id).order_by(AgentTurn.created_at.desc()).limit(50)).all()
    return {"id": item.id, "role": item.role, "job_id": item.job_id, "profile": item.profile,
        "turns": [{"id": turn.id, "request_id": turn.request_id, "message": turn.message,
                   "tool": turn.tool, "arguments": turn.arguments, "state": turn.state, "result": turn.result} for turn in reversed(turns)]}


@router.post("/agent-sessions/{session_id}/messages")
def message(session_id: str, body: MessageRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    return message_turn(db, wallet, session_id, body.message, body.request_id)


@router.post("/agent-sessions/{session_id}/tools")
def tool(session_id: str, body: ToolRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    if len(json.dumps(body.arguments)) > 20000:
        raise HTTPException(422, "Tool arguments exceed their input limit")
    return execute_tool(db, wallet, session_id, body.tool, body.arguments, body.request_id)
