from contextlib import asynccontextmanager
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, conversations, documents, feedback, support, tickets
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.seed import seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_create_tables:
        if engine.dialect.name == "postgresql":
            with engine.begin() as connection:
                connection.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(engine)
    if settings.seed_demo:
        with SessionLocal() as db:
            seed_demo(db)
    yield


settings = get_settings()
app = FastAPI(
    title="SupportPilot API",
    version="1.0.0",
    description="B2B SaaS 智能客户支持与工单 Agent",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(conversations.router, prefix=settings.api_prefix)
app.include_router(tickets.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(feedback.router, prefix=settings.api_prefix)
app.include_router(support.router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"name": settings.app_name, "docs": "/docs", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    with engine.connect() as connection:
        connection.execute(sa.text("SELECT 1"))
    return {"status": "ready", "database": engine.dialect.name}
