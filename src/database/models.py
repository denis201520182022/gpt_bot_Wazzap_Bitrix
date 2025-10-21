# src/database/models.py
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from .db import Base

class Dialog(Base):
    __tablename__ = 'dialogs'

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, index=True, nullable=False)
    current_state = Column(String, default='idle', nullable=False)
    history = Column(JSONB, nullable=False, server_default='[]')
    
    # --- НОВЫЕ ПОЛЯ ДЛЯ ОЧЕРЕДИ ---
    # Здесь будут храниться сообщения, ожидающие обработки
    pending_messages = Column(JSONB, nullable=False, server_default='[]')
    # Время, когда было добавлено последнее сообщение в очередь
    pending_since = Column(DateTime, nullable=True)
    # -----------------------------
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())