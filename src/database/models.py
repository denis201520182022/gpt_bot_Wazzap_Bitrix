# src/database/models.py
from sqlalchemy import Column, Integer, String, DateTime, func
from .db import Base

class Dialog(Base):
    __tablename__ = 'dialogs'

    id = Column(Integer, primary_key=True, index=True)
    # chatId - это номер телефона клиента, по нему мы будем искать диалог
    chat_id = Column(String, unique=True, index=True, nullable=False)
    # Состояние диалога, например: 'welcome_sent', 'awaiting_debtor_info', 'escalated'
    current_state = Column(String, default='idle', nullable=False)
    
    # Дата и время последнего обновления записи
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())