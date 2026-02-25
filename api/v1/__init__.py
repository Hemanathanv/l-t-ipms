from fastapi import FastAPI
from .header import router as header_router
from .chat import router as chat_router
from .sidebar import router as sidebar_router
from .admin import router as admin_router

def register_routes(app: FastAPI, agent=None):    
    app.include_router(chat_router)
    app.include_router(header_router)
    app.include_router(sidebar_router)
    app.include_router(admin_router)
    
    if agent:
        chat_router.set_agent(agent)
        sidebar_router.set_agent(agent)

__all__ = ["register_routes"]