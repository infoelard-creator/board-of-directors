import os
import json
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, DateTime, Integer, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# Загружаем .env файл
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не установлена в .env файле!")

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ===== СУЩЕСТВУЮЩИЕ МОДЕЛИ =====

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Связь с сессиями терапии
    therapy_sessions = relationship("TherapySession", back_populates="user")


# ===== НОВЫЕ МОДЕЛИ ДЛЯ ТЕРАПЕВТА =====

class TherapySession(Base):
    """Сессия диалога с Терапевтом."""
    __tablename__ = "therapy_sessions"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Исходная проблема (первое сообщение пользователя)
    initial_problem = Column(Text, nullable=False)
    
    # Статус сессии: ongoing, ready_for_board, archived
    status = Column(String, default="ongoing", index=True)
    
    # Финальная гипотеза (когда пользователь выбрал и отправил на Board)
    final_hypothesis_id = Column(String, ForeignKey("therapy_hypotheses.id"), nullable=True)
    
    # Связи
    user = relationship("User", back_populates="therapy_sessions")
    messages = relationship("TherapyMessage", back_populates="session", cascade="all, delete-orphan")
    key_insights = relationship("TherapyKeyInsight", back_populates="session", cascade="all, delete-orphan")
    hypotheses = relationship("TherapyHypothesis", foreign_keys="[TherapyHypothesis.session_id]", back_populates="session", cascade="all, delete-orphan")


class TherapyMessage(Base):
    """История сообщений в сессии терапии (полная история)."""
    __tablename__ = "therapy_messages"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("therapy_sessions.id"), nullable=False, index=True)
    
    # role: "user" или "therapist"
    role = Column(String, nullable=False)
    
    # Содержимое сообщения
    content = Column(Text, nullable=False)
    
    # Метаданные (опционально: usage токенов, latency и т.д.)
    message_metadata = Column(Text, default="{}")  # JSON как строка
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Связь
    session = relationship("TherapySession", back_populates="messages")


class TherapyKeyInsight(Base):
    """Ключевые знания, извлечённые из диалога (Q&A пользователя)."""
    __tablename__ = "therapy_key_insights"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("therapy_sessions.id"), nullable=False, index=True)
    
    # Вопрос Терапевта и ответ пользователя
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    
    # Выжимка ключевого знания (одна строка, как баббл)
    insight_summary = Column(String(200), nullable=True)  # Может быть None если инсайт не выявлен
    
    # Уверенность Терапевта в этом знании (0-100)
    confidence = Column(Integer, default=80)
    
    # Важность этого знания для решения проблемы (0-100)
    importance = Column(Integer, default=80)
    
    # Порядок отображения в панели
    display_order = Column(Integer, default=0)
    
    # Был ли этот инсайт удалён пользователем
    is_deleted_by_user = Column(Boolean, default=False)
    
    # Когда был удалён
    deleted_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Связь
    session = relationship("TherapySession", back_populates="key_insights")


class TherapyHypothesis(Base):
    """Гипотезы, которые генерирует Терапевт."""
    __tablename__ = "therapy_hypotheses"

    id = Column(String, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("therapy_sessions.id"), nullable=False, index=True)
    
    # Гипотеза в человекочитаемом формате
    hypothesis_text = Column(Text, nullable=False)
    
    # Гипотеза в JSON формате (для отправки на Board)
    hypothesis_json = Column(Text, nullable=True)  # JSON как строка
    
    # Уверенность Терапевта в этой гипотезе (0-100)
    confidence = Column(Integer, default=50)
    
    # Показывать ли эту гипотезу в боковой панели
    is_active = Column(Boolean, default=True)
    
    # Выбрал ли пользователь эту гипотезу для отправки на Board
    is_selected_by_user = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Связь
    session = relationship("TherapySession", back_populates="hypotheses", foreign_keys="[TherapyHypothesis.session_id]")


# ===== ИНИЦИАЛИЗАЦИЯ БД =====

def init_db() -> None:
    """
    Создаёт все таблицы, описанные в моделях.
    Если таблица уже существует — ничего не делает.
    """
    Base.metadata.create_all(bind=engine)


# ===== ЗАВИСИМОСТЬ ДЛЯ FASTAPI =====

def get_db():
    """Выдаёт сессию БД для FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ===== УТИЛИТЫ ДЛЯ РАБОТЫ С ПОЛЬЗОВАТЕЛЕМ =====

def create_user_if_not_exists(db, user_id: str) -> None:
    """
    Если пользователя с таким id нет — создаём.
    Если есть — обновляем last_seen_at.
    """
    user = db.get(User, user_id)
    now = datetime.now(timezone.utc)

    if user is None:
        user = User(id=user_id, created_at=now, last_seen_at=now)
        db.add(user)
    else:
        user.last_seen_at = now

    db.commit()
