from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List
import uuid
from datetime import datetime
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import ConnectionError
from url_detection import get_environment_info

# Import all routes
from whatsapp_routes import router as whatsapp_router
from admin_routes import router as admin_router
from client_routes import router as client_router
from cleanup_service import start_cleanup_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection with retry
mongo_url = os.environ.get('MONGO_URL')
if not mongo_url:
    logger.error("MONGO_URL environment variable not set")
    raise ValueError("MONGO_URL is required")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(ConnectionError))
async def connect_to_mongo():
    try:
        client = AsyncIOMotorClient(mongo_url, server_selection_timeout_ms=5000)
        await client.server_info()  # Test connection
        return client
    except ConnectionError as e:
        logger.error(f"Failed to connect to MongoDB: {str(e)}")
        raise

# Initialize MongoDB client
try:
    client = asyncio.get_event_loop().run_until_complete(connect_to_mongo())
    db = client[os.environ.get('DB_NAME', 'whatsapp_assistant')]
    logger.info("MongoDB connection established")
except Exception as e:
    logger.error(f"Failed to initialize MongoDB: {str(e)}")
    raise

# Create the main app
app = FastAPI(
    title="WhatsApp Assistant Multi-Tenant Platform",
    description="Platform for managing multiple WhatsApp AI assistants",
    version="2.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Define Models
class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class StatusCheckCreate(BaseModel):
    client_name: str

# Legacy routes
@api_router.get("/")
async def root():
    env_info = get_environment_info()
    return {"message": "WhatsApp Assistant Multi-Tenant API is running", "environment": env_info}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.dict()
    status_obj = StatusCheck(**status_dict)
    await db.status_checks.insert_one(status_obj.dict())
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find().to_list(1000)
    return [StatusCheck(**status_check) for status_check in status_checks]

# Include all routers
app.include_router(api_router)
app.include_router(whatsapp_router)
app.include_router(admin_router)
app.include_router(client_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Starting WhatsApp Assistant Multi-Tenant Platform")
    env_info = get_environment_info()
    logger.info(f"Environment info: {env_info}")
    
    # Start cleanup service in background
    try:
        asyncio.create_task(start_cleanup_service())
        logger.info("Cleanup service started")
    except Exception as e:
        logger.error(f"Failed to start cleanup service: {str(e)}")
    
    logger.info("✅ All services initialized successfully")

@app.on_event("shutdown")
async def shutdown_db_client():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down platform...")
    client.close()
    logger.info("✅ Shutdown complete")