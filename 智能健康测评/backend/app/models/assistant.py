from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, ForeignKey

from app.core.database import Base
from app.core.data_protection import EncryptedText, EncryptedJSON


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String(64), primary_key=True)
    user_name = Column(String(100), nullable=False, default="匿名用户")
    sex = Column(String(10), default="其他")
    age = Column(Integer)
    height_cm = Column(Integer)
    weight_kg = Column(Integer)
    goal = Column(String(200), default="保持健康")
    allergies = Column(EncryptedText, default="")
    conditions = Column(EncryptedText, default="")
    preferences = Column(EncryptedText, default="")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AssistantConversation(Base):
    __tablename__ = "assistant_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    title = Column(String(200), default="健康咨询")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(EncryptedText, nullable=False)
    agent = Column(String(30), default="health")
    created_at = Column(DateTime, default=datetime.now)


class AssistantMemory(Base):
    """Explicit user-approved facts retained beyond the recent conversation window."""

    __tablename__ = "assistant_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    category = Column(String(30), nullable=False, default="preference")
    content = Column(EncryptedText, nullable=False)
    source = Column(String(30), nullable=False, default="user")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class AgentRun(Base):
    """Persisted LangGraph execution envelope for conversation replay and audit."""

    __tablename__ = "assistant_agent_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    request_text = Column(EncryptedText, nullable=False)
    final_answer = Column(EncryptedText, default="")
    agent_plan = Column(EncryptedJSON, default=list)
    status = Column(String(20), nullable=False, default="completed")
    started_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, default=datetime.now)


class AgentStep(Base):
    """One specialist/tool hand-off inside an AgentRun."""

    __tablename__ = "assistant_agent_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("assistant_agent_runs.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    agent = Column(String(30), nullable=False)
    input_summary = Column(EncryptedText, default="")
    output_text = Column(EncryptedText, default="")
    tool_calls = Column(EncryptedJSON, default=list)
    sources = Column(EncryptedJSON, default=list)
    duration_ms = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="completed")
    error = Column(EncryptedText, default="")
