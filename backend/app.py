from fastapi import FastAPI, Request, WebSocket, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from client_routes import router as client_router
from admin_routes import router as admin_router
from whatsapp_routes import router as whatsapp_router
from whatsapp_manager import WhatsAppServiceManager
from database import close_database, get_database
from pause_service import ConversationPauseService
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ValidationError
from datetime import datetime
import logging
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import ConnectionError
from url_detection import get_environment_info

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="WhatsApp Chatbot API")

# Initialize services
service_manager = WhatsAppServiceManager()
pause_service = ConversationPauseService()
active_websockets = []

# MongoDB connection with retry
mongo_url = os.getenv("MONGO_URL")
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
    db = client[os.getenv("DB_NAME", "clients_db")]
    logger.info("MongoDB connection established")
except Exception as e:
    logger.error(f"Failed to initialize MongoDB: {str(e)}")
    raise

# Initialize pause service
async def initialize_pause_service():
    try:
        await pause_service.initialize(db)
        logger.info("Pause service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize pause service: {str(e)}")
        raise

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(client_router)
app.include_router(admin_router)
app.include_router(whatsapp_router)

class EvolutionWebhookPayload(BaseModel):
    event: str
    instance: str
    data: dict

@app.post("/api/admin/webhook")
async def admin_webhook(payload: EvolutionWebhookPayload, db=Depends(get_database)):
    try:
        instance_name = payload.instance
        if not instance_name:
            logger.error("Webhook received without instance name")
            raise HTTPException(status_code=400, detail="Missing instance name in webhook payload")

        actual_client_id = instance_name.replace("client-", "") if instance_name.startswith("client-") else instance_name
        clients_collection = db.clients
        client_data = await clients_collection.find_one({"id": actual_client_id})
        if not client_data:
            logger.error(f"Client {actual_client_id} not found for webhook")
            raise HTTPException(status_code=404, detail=f"Client {actual_client_id} not found")

        await service_manager.handle_webhook(actual_client_id, payload.dict(), db, active_websockets)
        return {"status": "received"}
    except ValidationError as e:
        logger.error(f"Invalid webhook payload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid webhook payload: {str(e)}")
    except HTTPException as e:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/admin/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    logger.info("WebSocket connection established")
    try:
        while True:
            await websocket.receive_text()
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        active_websockets.remove(websocket)
        await websocket.close()
        logger.info("WebSocket connection closed")

@app.get("/health")
async def health_check():
    env_info = get_environment_info()
    return {"status": "running", "timestamp": datetime.utcnow().isoformat(), "environment": env_info}

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Starting WhatsApp Chatbot API")
    env_info = get_environment_info()
    logger.info(f"Environment info: {env_info}")
    try:
        await db.command("ping")
        logger.info("✅ Connected to MongoDB")
        await initialize_pause_service()
    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Shutting down WhatsApp Chatbot API")
    client.close()
    logger.info("✅ MongoDB connection closed")
    await close_database()