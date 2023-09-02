import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4, UUID
from datetime import datetime

from aiohttp import ClientSession
from fastapi import FastAPI, APIRouter, Depends, Body, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy import func, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, MappedAsDataclass
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import settings


class DI:
    pass

di = DI()

class BaseModel(MappedAsDataclass, DeclarativeBase):
    ...

class UserModel(BaseModel):
    __tablename__ = 'users'

    
    email: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), default=None)
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)

class TokenModel(BaseModel):
    __tablename__ = 'tokens'

    expired_at: Mapped[datetime]
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), default=None)
    id: Mapped[UUID] = mapped_column(primary_key=True, default_factory=uuid4)
    


router = APIRouter(prefix='/v1')

@router.get("/info")
async def get_info(
    token: str = Depends(APIKeyHeader(name='Authorization')),
) -> dict:
    try:
        token = UUID(token)
    except ValueError:
        raise HTTPException(status_code=401)
    stmt = select(UserModel).join(TokenModel, TokenModel.user_id == UserModel.id).where(TokenModel.id == token)
    async with di.db() as sess:

        user = await sess.scalar(stmt)
        if not user:
            raise HTTPException(status_code=401)
    print(user)  
    return {'time': int(time.time()), 'email': user.email, 'userId': user.id }


@router.post("/auth/google")
async def auth_google(
    token_data: dict = Body(None, description=""),
) -> dict:
    url = f'https://www.googleapis.com/oauth2/v3/userinfo?access_token={token_data["access_token"]}'
    async with di.http.get(url) as resp:
        data = await resp.json()
        print(data)
        # {'sub': '105707397947012573437', 'name': 'Рома Дубровский', 'given_name': 'Рома', 'family_name': 'Дубровский', 'picture': 'https://lh3.googleusercontent.com/a/AAcHTtfGAG5YCkl0NxifWARp89YoHk6Lrgsbyw5iJDyOySGjkw=s96-c', 'email': 'romik8jones@gmail.com', 'email_verified': True, 'locale': 'ru'}
    email = data['email']
    async with di.db() as sess:
        stmt = select(UserModel).where(UserModel.email == email)
        user = await sess.scalar(stmt)
        if not user:
            user = UserModel(email=email)
            sess.add(user)
            await sess.flush()
        token = TokenModel(user_id=user.id, expired_at=datetime.fromtimestamp(time.time() + 84600))
        sess.add(token)
        await sess.commit()
    # get or create user from db
    # create token for user 
    return {'token': token.id.hex} 



@asynccontextmanager
async def lifespan(app):
    try:
        db_url = f'postgresql+psycopg://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}/{settings.DB_NAME}'
        engine = create_async_engine(db_url)
        session = async_sessionmaker(bind=engine, expire_on_commit=False)
        di.db = session
        di.http = ClientSession()
        async with engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        yield
    finally:
        await asyncio.wait([engine.dispose(), di.http.close()])

def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    return app