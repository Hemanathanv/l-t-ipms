from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from config import settings
from db import get_prisma, close_prisma
from redis_client import get_redis_client, close_redis
from agent import create_agent, create_checkpointer
from api.v1 import register_routes

_agent = None
_checkpointer_cm = None
_checkpointer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _checkpointer_cm, _checkpointer
        
    print("🚀 Starting L&T IPMS Conversational API...")
    
    try:
        prisma = await get_prisma()
        print("✅ PostgreSQL (Prisma) connected")
    except Exception as e:
        print(f"⚠️  Warning: Could not connect to Prisma: {e}")
    
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        print("✅ Redis connected")
    except Exception as e:
        print(f"⚠️  Warning: Could not connect to Redis: {e}")
    
    try:
        _checkpointer_cm = create_checkpointer()
        _checkpointer = await _checkpointer_cm.__aenter__()
        await _checkpointer.setup()
        print("✅ LangGraph checkpointer initialized")
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize checkpointer: {e}")
    
    try:
        _agent = await create_agent(checkpointer=_checkpointer)
        print("✅ LangGraph agent compiled")
    except Exception as e:
        print(f"⚠️  Warning: Could not create agent: {e}")
    
    try:
        from api.v1.chat.router import set_agent as set_chat_agent
        from api.v1.sidebar.router import set_agent as set_sidebar_agent
        
        set_chat_agent(_agent)
        set_sidebar_agent(_agent)
    except (ImportError, AttributeError) as e:
        print(f"⚠️  Warning: Could not set agent on route modules: {e}")
    
    print(f"🌐 API ready at http://localhost:8000")
    
    yield
    print("🛑 Shutting down...")
    try:
        await close_prisma()
    except Exception as e:
        print(f"⚠️  Warning during Prisma cleanup: {e}")
    
    try:
        await close_redis()
    except Exception as e:
        print(f"⚠️  Warning during Redis cleanup: {e}")
    
    try:
        if _checkpointer_cm:
            await _checkpointer_cm.__aexit__(None, None, None)
    except Exception as e:
        print(f"⚠️  Warning during checkpointer cleanup: {e}")
    
    print("✅ All connections closed")


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description="Conversational AI API powered by LangGraph with Redis caching and PostgreSQL persistence",
    lifespan=lifespan,
    docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_routes(app, agent=None)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)