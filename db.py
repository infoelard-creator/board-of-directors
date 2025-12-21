import os
from datetime import datetime
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)  # user_id
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)


# Создание таблиц при старте
def init_db() -> None:
    """
    Создаёт все таблицы, описанные в моделях (в т.ч. users).
    Если таблица уже есть — ничего не делает.
    """
    Base.metadata.create_all(bind=engine)


# Зависимость для FastAPI — выдаёт сессию БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Создание/обновление пользователя
def create_user_if_not_exists(db, user_id: str) -> None:
    """
    Если пользователя с таким id нет — создаём.
    Если есть — обновляем last_seen_at.
    """
    user = db.get(User, user_id)
    now = datetime.utcnow()

    if user is None:
        user = User(id=user_id, created_at=now, last_seen_at=now)
        db.add(user)
    else:
        user.last_seen_at = now

    db.commit()
