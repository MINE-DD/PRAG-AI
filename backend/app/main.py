from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, collections, papers
from app.core.config import settings

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
app.include_router(collections.router, tags=["collections"])
app.include_router(papers.router, tags=["papers"])


@app.get("/")
def root():
    return {"message": "PRAG-v2 API", "version": "0.1.0"}
