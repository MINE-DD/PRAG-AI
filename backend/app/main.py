from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api import health
from backend.app.core.config import settings

app = FastAPI(
    title="PRAG-v2 API",
    description="RAG system for academic research papers",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])


@app.get("/")
def root():
    return {"message": "PRAG-v2 API", "version": "0.1.0"}
