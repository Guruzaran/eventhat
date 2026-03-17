import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from db.pool import create_pool
from db.redis import get_redis
from routes.chat import router as chat_router

load_dotenv()

app = FastAPI(title="Eventhat API", version="1.0.0")

# Session middleware — must be added before CORS
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-secret-change-in-production"),
    max_age=7200,           # 2 hours, matches session lifetime
    https_only=False,       # set True in production
    same_site="lax",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await create_pool()
    await get_redis()


@app.get("/health")
async def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}


app.include_router(chat_router)
