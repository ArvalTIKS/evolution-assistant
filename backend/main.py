import os
import uuid
import logging
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from evolutionapi.client import EvolutionClient
from evolutionapi.models.instance import InstanceConfig, WebhookConfig
from evolutionapi.models.message import TextMessage
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import AsyncOpenAI
from dotenv import load_dotenv
from enum import Enum
from evolutionapi.exceptions import EvolutionAPIError

active_connections: List[WebSocket] = []

# Configurar logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logging.getLogger('pymongo.serverSelection').setLevel(logging.CRITICAL)

# Cargar variables de entorno
load_dotenv()
EVOLUTION_BASE_URL = os.getenv("EVOLUTION_BASE_URL")
EVOLUTION_API_TOKEN = os.getenv("EVOLUTION_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "tikschile@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "whatsapp_db")
BACKEND_URL = os.getenv("BASE_URL", "http://localhost:8000")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

# Inicializar MongoDB
client = AsyncIOMotorClient(MONGODB_URI)
database = client[DB_NAME]

async def init_db_indexes(db):
    """Create necessary MongoDB indexes on startup."""
    try:
        await db.clients.create_index("unique_url", unique=True)
        await db.clients.create_index("id")
        await db.chats.create_index([("client_id", 1), ("phone_number", 1), ("timestamp", -1)])
        await db.threads.create_index([("client_id", 1), ("phone_number", 1)])
        await db.paused_conversations.create_index([("client_id", 1), ("phone_number", 1)])
        logger.info("MongoDB indexes created successfully")
    except Exception as e:
        logger.error(f"Error ensuring MongoDB indexes: {str(e)}")

async def get_database():
    """Returns the database instance for FastAPI dependencies."""
    try:
        await client.admin.command('ping')  # Check connection
        return database
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

async def get_database_direct():
    """Returns the database instance for direct access (e.g., background services)."""
    return database

async def close_database():
    """Close database connection."""
    client.close()
    logger.info("MongoDB connection closed.")

# Modelos Pydantic
class ClientStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    CONNECTING = "connecting"
    AWAITING_SCAN = "awaiting_scan"
    OPEN = "open"

class ClientCreate(BaseModel):
    name: str = Field(..., description="Client name or company", min_length=3)
    email: EmailStr = Field(..., description="Client email")
    openai_api_key: str = Field(..., description="Client's OpenAI API key", pattern=r"^sk-.{10,}$")
    openai_assistant_id: str = Field(..., description="Client's OpenAI Assistant ID", pattern=r"^asst_[a-zA-Z0-9]{24}$")

class Client(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    email: Optional[EmailStr]
    openai_api_key: Optional[str]
    openai_assistant_id: Optional[str]
    unique_url: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: ClientStatus = ClientStatus.PENDING
    connected_phone: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: Optional[datetime] = None
    whatsapp: Optional[dict] = {}

class ClientResponse(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    openai_api_key: Optional[str] = ""
    openai_assistant_id: Optional[str] = ""
    status: ClientStatus
    connected: bool
    connected_phone: Optional[str] = None
    unique_url: str
    created_at: datetime
    last_activity: Optional[datetime]
    messageCount: Optional[int] = None
    pausedCount: Optional[int] = None
    globalPause: Optional[bool] = None

class ClientMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    phone_number: str
    message: str
    timestamp: datetime
    is_from_ai: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Thread(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    phone_number: str
    thread_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class EmailTemplate(BaseModel):
    to_email: str
    client_name: str
    landing_url: str

class ToggleClientRequest(BaseModel):
    action: str  # "connect" or "disconnect"

class UpdateEmailRequest(BaseModel):
    new_email: EmailStr

class PausedConversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    phone_number: str
    paused_at: datetime = Field(default_factory=datetime.utcnow)
    paused_by: str = "client"

class ClientUpdate(BaseModel):
    email: EmailStr | None = None
    name: str | None = None
    is_active: bool | None = None

class OutgoingMessage(BaseModel):
    phone_number: str
    message: str
    instance_id: str

class EvolutionWebhookPayload(BaseModel):
    event: str
    instance: str
    data: Any

# Inicializar FastAPI
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WhatsAppServiceManager:
    def __init__(self):
        if not EVOLUTION_API_TOKEN:
            raise ValueError("EVOLUTION_API_KEY environment variable is required")
        if not SMTP_PASSWORD:
            logger.warning("SMTP_PASSWORD not configured - emails will not be sent")
        self.services: Dict[str, dict] = {}
        self.evolution_client = EvolutionClient(base_url=EVOLUTION_BASE_URL, api_token=EVOLUTION_API_TOKEN)
        self.openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.commands = {
            'pausar': self.pause_conversation,
            'reactivar': self.reactivate_conversation,
            'pausar todo': self.pause_all_conversations,
            'activar todo': self.activate_all_conversations,
            'estado': self.get_conversation_status
        }
        self.running = True

    async def send_client_invitation(self, template: EmailTemplate) -> bool:
        """Send HTML invitation email to client with their landing page URL"""
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Tu Asistente WhatsApp</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #25D366, #128C7E); padding: 30px 20px; text-align: center; color: white; }}
                .header h1 {{ margin: 0; font-size: 28px; font-weight: 300; }}
                .content {{ padding: 40px 30px; }}
                .greeting {{ font-size: 18px; margin-bottom: 20px; color: #2c3e50; }}
                .message {{ font-size: 16px; margin-bottom: 30px; color: #555; }}
                .cta-button {{ display: inline-block; background: linear-gradient(135deg, #25D366, #128C7E); color: white; padding: 15px 30px; text-decoration: none; border-radius: 50px; font-weight: 600; font-size: 16px; margin: 20px 0; transition: transform 0.2s ease; }}
                .cta-button:hover {{ transform: translateY(-2px); box-shadow: 0 6px 12px rgba(37, 211, 102, 0.3); }}
                .instructions {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #25D366; }}
                .instructions h3 {{ margin-top: 0; color: #25D366; }}
                .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 14px; color: #666; }}
                .emoji {{ font-size: 24px; margin: 0 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1><span class="emoji">🤖</span> Tu Asistente WhatsApp</h1>
                    <p>¡Ya está listo para usar!</p>
                </div>
                <div class="content">
                    <div class="greeting">¡Hola <strong>{template.client_name}</strong>! 👋</div>
                    <div class="message">Tu asistente inteligente de WhatsApp ha sido configurado exitosamente.</div>
                    <div style="text-align: center;">
                        <a href="{template.landing_url}" class="cta-button"><span class="emoji">📱</span> Activar mi Asistente</a>
                    </div>
                    <div class="instructions">
                        <h3>📋 Instrucciones de activación:</h3>
                        <ol>
                            <li>Haz clic en el botón de arriba</li>
                            <li><strong>Espera 1-2 minutos</strong> para el código QR</li>
                            <li>Abre WhatsApp → Menú → Dispositivos vinculados</li>
                            <li>Toca "Vincular un dispositivo" y escanea el código QR</li>
                            <li>¡Tu asistente comenzará a responder automáticamente!</li>
                        </ol>
                    </div>
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 5px; padding: 15px; margin: 20px 0;">
                        <strong>⏱️ Importante:</strong> El código QR puede tardar 1-2 minutos en aparecer.
                    </div>
                    <div style="background: #e8f5e8; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <strong>🔒 Importante:</strong> Solo se puede conectar un teléfono por asistente.
                    </div>
                    <div style="text-align: center; margin-top: 30px;">
                        <p style="color: #666; font-size: 14px;">
                            ¿Necesitas ayuda? <br>
                            Contáctanos: <a href="mailto:{SMTP_USER}" style="color: #25D366;">{SMTP_USER}</a>
                        </p>
                    </div>
                </div>
                <div class="footer">
                    <p>TIKS - Plataforma de Asistentes WhatsApp</p>
                    <p style="font-size: 12px;">Si no solicitaste este servicio, ignora este email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = SMTP_USER
            msg['To'] = template.to_email
            msg['Subject'] = f"🤖 Tu Asistente WhatsApp está listo - {template.client_name}"
            msg.attach(MIMEText(html_content, 'html'))
            async with aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=True) as smtp:
                await smtp.login(SMTP_USER, SMTP_PASSWORD)
                await smtp.send_message(msg)
            logger.info(f"Client invitation email sent to {template.to_email}")
            return True
        except Exception as e:
            logger.error(f"Error sending client invitation to {template.to_email}: {str(e)}")
            return False

    async def send_email(self, to_email: str, subject: str, message: str) -> bool:
        """Send plain-text email for general notifications"""
        try:
            msg = MIMEMultipart()
            msg['From'] = SMTP_USER
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))
            async with aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=True) as smtp:
                await smtp.login(SMTP_USER, SMTP_PASSWORD)
                await smtp.send_message(msg)
            logger.info(f"Email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False

    async def notify_admin_and_client(self, client: Client, db: AsyncIOMotorDatabase, event_type: str, phone: str = None):
        try:
            client_data = await db["clients"].find_one({"id": client.id})
            if not client_data:
                logger.error(f"Client {client.id} not found")
                return
            messages = {
                "qr_generated": (f"Se ha generado un nuevo código QR para tu instancia {client.id}. Accede a tu página de cliente en {BACKEND_URL}/client/{client.id}/landing.", "Código QR generado"),
                "connected": (f"Tu instancia {client.id} se ha conectado con el número {phone}. Accede a tu página de cliente en {BACKEND_URL}/client/{client.id}/landing.", "Servicio conectado"),
                "disconnected": (f"Tu instancia {client.id} ha sido desconectada. Accede a tu página de cliente en {BACKEND_URL}/client/{client.id}/landing.", "Servicio desconectado"),
                "paused": (f"Tu conversación con {phone} ha sido pausada.", "Conversación pausada"),
                "reactivated": (f"Tu conversación con {phone} ha sido reactivada.", "Conversación reactivada"),
                "paused_all": (f"Todas las conversaciones para tu instancia {client.id} han sido pausadas.", "Bot pausado"),
                "reactivated_all": (f"Todas las conversaciones para tu instancia {client.id} han sido reactivadas.", "Bot reactivado"),
                "restarted": (f"Tu instancia {client.id} ha sido reiniciada para garantizar su funcionamiento.", "Servicio reiniciado"),
                "email_updated": (f"Tu email ha sido actualizado a {client.email}.", "Email actualizado")
            }
            if event_type == "created":
                await self.send_client_invitation(EmailTemplate(
                    to_email=client.email,
                    client_name=client.name,
                    landing_url=f"{BACKEND_URL}/client/{client.id}/landing"
                ))
            elif event_type in messages:
                body, subject = messages[event_type]
                await self.send_email(client.email, subject, body)
            if ADMIN_EMAIL:
                await self.send_email(
                    ADMIN_EMAIL,
                    f"Notificación: {event_type} para cliente {client.name}",
                    f"Evento {event_type} para cliente {client.name} (ID: {client.id}, Teléfono: {phone or 'N/A'})."
                )
        except Exception as e:
            logger.error(f"Error sending notification for client {client.id}: {str(e)}")

    async def update_webhook_settings(self, instance_name: str, client_id: str, instance_token: str) -> bool:
        try:
            webhook_url = f"{BACKEND_URL.rstrip('/')}/api/client/{client_id}/webhook"
            webhook_config = WebhookConfig(
                url=webhook_url,
                enabled=True,
                webhook_by_events=True,
                events=["qrcode.updated", "connection.update", "messages.upsert"]
            )
            logger.debug(f"Updating webhook settings for {instance_name}: {webhook_config}")
            await self.evolution_client.webhook.set_webhook(instance_name, webhook_config, instance_token)
            logger.info(f"Webhook settings updated successfully for {instance_name}")
            return True
        except Exception as e:
            logger.error(f"Error updating webhook settings for {instance_name}: {str(e)}")
            return False

    async def get_active_clients(self, db: AsyncIOMotorDatabase):
        """Obtener clientes activos de la base de datos"""
        clients = await db["clients"].find({"status": ClientStatus.ACTIVE}).to_list(length=None)
        return clients

    async def check_service_health(self, client_id: str, instance_token: str) -> bool:
        """Verificar si un servicio de Evolution API está respondiendo y conectado"""
        try:
            status = await self.evolution_client.instance_operations.get_connection_state(client_id, instance_token)
            logger.info(f"Health check for {client_id[:8]}: {status}")
            return status == ClientStatus.OPEN
        except Exception as e:
            logger.error(f"Error checking health for {client_id[:8]}: {str(e)}")
            return False

    async def restart_service(self, client_id: str, instance_token: str, db: AsyncIOMotorDatabase) -> bool:
        """Reiniciar servicio de un cliente específico usando Evolution API"""
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id[:8]} not found")
                return False
            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
            logger.info(f"Attempting to disconnect instance: {client_id[:8]}")
            await self.evolution_client.instances.logout_instance(client_id, instance_token)
            await asyncio.sleep(5)  # Wait for disconnection
            logger.info(f"Attempting to connect instance: {client_id[:8]}")
            await self.evolution_client.instance_operations.connect(client_id, instance_token)
            logger.info(f"Service {client_id[:8]} restarted successfully")
            await self.notify_admin_and_client(client, db, "restarted")
            return True
        except Exception as e:
            logger.error(f"Exception restarting {client_id[:8]}: {str(e)}")
            return False

    async def monitor_loop(self, db: AsyncIOMotorDatabase = None):
        """Loop principal de monitoreo"""
        if not db:
            db = await get_database_direct()
        logger.info("🔄 Starting WhatsApp Recovery Service")
        while self.running:
            try:
                active_clients = await self.get_active_clients(db)
                logger.info(f"📊 Monitoring {len(active_clients)} active clients")
                for client in active_clients:
                    client_id = client['id']
                    client_name = client['name']
                    instance_token = client['instance_token']
                    if not await self.check_service_health(client_id, instance_token):
                        logger.warning(f"⚠️ Service {client_name} (ID: {client_id[:8]}) is not connected or not responding")
                        if await self.restart_service(client_id, instance_token, db):
                            logger.info(f"🔄 Waiting for {client_name} initialization...")
                            await asyncio.sleep(45)  # Wait for initialization
                        else:
                            logger.error(f"❌ Failed to restart {client_name}")
                    else:
                        status = await self.evolution_client.instance_operations.get_connection_state(client_id, instance_token)
                        if status in [ClientStatus.CONNECTING, ClientStatus.INACTIVE]:
                            logger.info(f"🔄 {client_name} (ID: {client_id[:8]}) needs QR or is disconnected, forcing restart...")
                            await self.restart_service(client_id, instance_token, db)
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(60)  # Wait longer if error

    def stop(self):
        """Detener el servicio de recovery"""
        self.running = False
        logger.info("🛑 Recovery service stopped")

    async def _provision_instance_for_client(self, client_model: Client, db: AsyncIOMotorDatabase) -> tuple[str, str]:
    
        instance_name = str(uuid.uuid4())
        instance_token = f"token_{instance_name}"
        try:
            config = InstanceConfig(
                instanceName=instance_name,
                integration="WHATSAPP-BAILEYS",
                qrcode=True,
                token=instance_token,
                number="",
                rejectCall=True,
                alwaysOnline=True,
                readMessages=True,
                readStatus=True
            )
            self.evolution_client.instances.create_instance(config)
            logger.info(f"Instance {instance_name} created successfully for client {client_model.name}")

            # Update the client's record with the new instance details
            await db["clients"].update_one(
                {"id": client_model.id},
                {"$set": {
                    "instance_id": instance_name,
                    "instance_token": instance_token,
                    "status": ClientStatus.AWAITING_SCAN, # Set to awaiting scan after provisioning
                    "whatsapp.status": "connecting",
                    "last_activity": datetime.utcnow()
                }}
            )
            # Update the in-memory services dictionary
            self.services[instance_name] = {
                'instance_name': instance_name,
                'instance_token': instance_token,
                'status': 'connecting',
                'client_name': client_model.name,
                'qr_code': None,
                'qr_expiry': None,
                'connected_phone': None
            }
            await self.update_webhook_settings(instance_name, instance_name, instance_token)
            await self.notify_admin_and_client(client_model, db, "qr_generated") # Notify about QR generated
            return instance_name, instance_token
        except Exception as e:
            logger.error(f"Error provisioning instance for client {client_model.name}: {str(e)}")
            raise # Re-raise the exception to be caught by the caller

    async def create_service_for_client(self, client: ClientCreate, db: AsyncIOMotorDatabase, existing_client_id: Optional[str] = None) -> Optional[Client]:
        logger.info(f"Attempting to create/re-provision instance for client {client.name} (ID: {existing_client_id or 'new'})")
        instance_name = existing_client_id if existing_client_id else str(uuid.uuid4())
        instance_token = f"token_{instance_name}"
        client_model = Client(
            id=instance_name, # Use the provided or generated instance_name as the client ID
            name=client.name,
            email=client.email,
            openai_api_key=client.openai_api_key,
            openai_assistant_id=client.openai_assistant_id,
            unique_url=str(uuid.uuid4())[:8],
            status=ClientStatus.AWAITING_SCAN,
            whatsapp={"status": "connecting"}
        )
        try:
            config = InstanceConfig(
                instanceName=instance_name,
                integration="WHATSAPP-BAILEYS",
                qrcode=True
            )
            logger.info(f"Calling Evolution API to create instance {instance_name}...")
            await self.evolution_client.instances.create_instance(config)
            logger.info(f"Evolution API instance {instance_name} created successfully.")
            logger.info(f"Instance {instance_name} created successfully for client {client.name}")

            await db["clients"].update_one(
                {"id": instance_name}, # Use instance_name for update_one
                {"$set": {
                    "id": client_model.id,
                    "name": client_model.name,
                    "email": client_model.email,
                    "openai_api_key": client_model.openai_api_key,
                    "openai_assistant_id": client_model.openai_assistant_id,
                    "unique_url": client_model.unique_url,
                    "instance_id": instance_name,
                    "instance_token": instance_token,
                    "status": client_model.status,
                    "created_at": client_model.created_at,
                    "last_activity": client_model.last_activity,
                    "whatsapp": client_model.whatsapp
                }},
                upsert=True
            )
            await self.update_webhook_settings(instance_name, instance_name, instance_token)
            self.services[instance_name] = {
                'instance_name': instance_name,
                'instance_token': instance_token,
                'status': 'connecting',
                'client_name': client.name,
                'qr_code': None,
                'qr_expiry': None,
                'connected_phone': None
            }
            await self.notify_admin_and_client(client_model, db, "created")
            return client_model
        except EvolutionAPIError as e:
            logger.error(f"Evolution API Error creating instance {instance_name} for client {client.name}: {e.args[0]}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error creating instance {instance_name} for client {client.name}: {str(e)}")
            if "already in use" in str(e).lower():
                logger.info(f"Instance {instance_name} already exists for client {client.name}")
                # If instance already exists, just update the DB record and webhook settings
                await self.update_webhook_settings(instance_name, instance_name, instance_token)
                await db["clients"].update_one(
                    {"id": instance_name},
                    {"$set": {
                        "id": instance_name,
                        "name": client.name,
                        "email": client.email,
                        "openai_api_key": client.openai_api_key,
                        "openai_assistant_id": client.openai_assistant_id,
                        "unique_url": str(uuid.uuid4())[:8],
                        "instance_id": instance_name,
                        "instance_token": instance_token,
                        "status": ClientStatus.AWAITING_SCAN,
                        "created_at": datetime.utcnow(),
                        "last_activity": datetime.utcnow(),
                        "whatsapp": {"status": "connecting"}
                    }},
                    upsert=True
                )
                await self.notify_admin_and_client(client_model, db, "created")
                return client_model
            return None

    async def update_client(self, client_id: str, update_data: ClientUpdate, db: AsyncIOMotorDatabase) -> bool:
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return False
            update_dict = {}
            if update_data.email:
                update_dict["email"] = update_data.email
            if update_data.name:
                update_dict["name"] = update_data.name
            if update_data.is_active is not None:
                update_dict["status"] = ClientStatus.ACTIVE if update_data.is_active else ClientStatus.INACTIVE
                if update_data.is_active:
                    await self.evolution_client.instance_operations.connect(client_data["instance_id"], client_data["instance_token"])
                else:
                    await self.evolution_client.instances.logout_instance(client_data["instance_id"], client_data["instance_token"])
            if update_dict:
                update_dict["last_activity"] = datetime.utcnow()
                await db["clients"].update_one({"id": client_id}, {"$set": update_dict})
                updated_client = await db["clients"].find_one({"id": client_id})
                client_model = Client(**{k: v for k, v in updated_client.items() if k != '_id'})
                if update_data.email:
                    await self.notify_admin_and_client(client_model, db, "email_updated")
            return True
        except Exception as e:
            logger.error(f"Error updating client {client_id}: {str(e)}")
            return False

    async def update_client_email(self, client_id: str, update_data: UpdateEmailRequest, db: AsyncIOMotorDatabase) -> bool:
        try:
            # Buscar el cliente
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return False

            # Actualizar el email y la fecha de última actividad
            await db["clients"].update_one(
                {"id": client_id},
                {
                    "$set": {
                        "email": update_data.new_email,
                        "last_activity": datetime.utcnow()
                    }
                }
            )

            # Crear un modelo actualizado sin el _id de Mongo
            client_model_data = {k: v for k, v in client_data.items() if k != "_id"}
            client_model_data["email"] = update_data.new_email
            client_model = Client(**client_model_data)

            # Notificar al admin y al cliente
            await self.notify_admin_and_client(client_model, db, "email_updated")
            return True

        except Exception as e:
            logger.error(f"Error updating email for client {client_id}: {str(e)}")
            return False

    async def toggle_client(self, client_id: str, toggle_data: ToggleClientRequest, db: AsyncIOMotorDatabase) -> bool:
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found in DB for toggle.")
                return False

            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
            instance_id = client_data.get("instance_id")
            instance_token = client_data.get("instance_token")

            if toggle_data.action == "connect":
                # If instance details are missing, go straight to creation
                if not instance_id or not instance_token:
                    logger.warning(f"Instance details missing for client {client_id}. Forcing instance creation.")
                    created_client = await self.create_service_for_client(
                        ClientCreate(
                            name=client.name,
                            email=client.email,
                            openai_api_key=client.openai_api_key,
                            openai_assistant_id=client.openai_assistant_id
                        ),
                        db,
                        existing_client_id=client_id
                    )
                    if not created_client:
                        logger.error(f"Failed to create new instance for client {client_id}.")
                        return False
                    # After creation, we can try to connect
                    client_data = await db["clients"].find_one({"id": client_id})
                    instance_id = client_data.get("instance_id")
                    instance_token = client_data.get("instance_token")
                    await self.evolution_client.instance_operations.connect(instance_id, instance_token)
                    new_status = ClientStatus.CONNECTING
                else:
                    try:
                        # Check if instance exists in Evolution API
                        status = await self.evolution_client.instance_operations.get_connection_state(instance_id, instance_token)
                        logger.info(f"Instance {instance_id} found with status: {status}")
                        if status != ClientStatus.OPEN:
                            await self.evolution_client.instance_operations.connect(instance_id, instance_token)
                            new_status = ClientStatus.CONNECTING
                        else:
                            new_status = ClientStatus.ACTIVE
                    except EvolutionAPIError: # Catch any EvolutionAPIError
                        logger.warning(f"Instance {instance_id} not found in Evolution API or other API error. Creating new instance for client {client_id}.")
                        # Re-provision the instance
                        created_client = await self.create_service_for_client(
                            ClientCreate(
                                name=client.name,
                                email=client.email,
                                openai_api_key=client.openai_api_key,
                                openai_assistant_id=client.openai_assistant_id
                            ),
                            db,
                            existing_client_id=client_id
                        )
                        if not created_client:
                            logger.error(f"Failed to create new instance for client {client_id}.")
                            return False
                        # Fetch updated client data after re-provisioning
                        client_data = await db["clients"].find_one({"id": client_id})
                        instance_id = client_data.get("instance_id")
                        instance_token = client_data.get("instance_token")
                        # Attempt to connect the newly created instance
                        await self.evolution_client.instance_operations.connect(instance_id, instance_token)
                        new_status = ClientStatus.CONNECTING
            elif toggle_data.action == "disconnect":
                try:
                    # If no instance, nothing to disconnect.
                    if not instance_id or not instance_token:
                        logger.warning(f"Instance details missing for client {client_id}. Assuming already disconnected.")
                        new_status = ClientStatus.INACTIVE
                    else:
                        await self.evolution_client.instances.logout_instance(instance_id, instance_token)
                        new_status = ClientStatus.INACTIVE
                except EvolutionAPIError: # Catch any EvolutionAPIError
                    logger.warning(f"Instance {instance_id} not found in Evolution API or other API error. Assuming already disconnected.")
                    new_status = ClientStatus.INACTIVE
            else:
                logger.error(f"Invalid toggle action: {toggle_data.action}")
                return False

            # Update client status in database
            await db["clients"].update_one(
                {"id": client_id},
                {
                    "$set": {
                        "status": new_status,
                        "last_activity": datetime.utcnow(),
                        "whatsapp.status": new_status.value
                    }
                }
            )

            # Notify admin and client
            await self.notify_admin_and_client(client, db, toggle_data.action)
            logger.info(f"Client {client_id} toggled to {toggle_data.action} with status {new_status}")
            return True
        except Exception as e:
            logger.error(f"Unexpected error toggling client {client_id}: {str(e)}")
            return False

    async def stop_service_for_client(self, client_id: str, db: AsyncIOMotorDatabase) -> bool:
        logger.info(f"Attempting to delete client with id: {client_id}")
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return False
            instance_name = client_data.get("instance_id")
            instance_token = client_data.get("instance_token")
            if instance_name and instance_token:
                try:
                    await self.evolution_client.instances.delete_instance(instance_name, instance_token)
                    logger.info(f"Deleted instance {instance_name} for client {client_id}")
                except EvolutionAPIError as e:
                    logger.warning(f"Could not delete instance {instance_name} from Evolution API, it might be already deleted: {e}")

            if client_id in self.services:
                del self.services[client_id]

            await db["clients"].delete_one({"id": client_id})
            await db["paused_conversations"].delete_many({"client_id": client_id})
            await db["threads"].delete_many({"client_id": client_id})
            
            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
            await self.send_email(
                client.email,
                "Cuenta eliminada",
                "Tu cuenta y tu instancia han sido eliminadas del sistema."
            )
            return True
        except Exception as e:
            logger.error(f"Error stopping service for client {client_id}: {str(e)}")
            return False

    async def disconnect_client_whatsapp(self, client_id: str, db: AsyncIOMotorDatabase) -> dict:
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return {"success": False, "error": "Client not found"}
            instance_name = client_data["instance_id"]
            instance_token = client_data["instance_token"]
            await self.evolution_client.instances.logout_instance(instance_name, instance_token)
            logger.info(f"WhatsApp logout successful for client {client_id}")
            if client_id in self.services:
                self.services[client_id]['status'] = 'stopped'
                self.services[client_id]['qr_code'] = None
                self.services[client_id]['qr_expiry'] = None
                self.services[client_id]['connected_phone'] = None
            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
            await db["clients"].update_one(
                {"id": client_id},
                {
                    "$set": {
                        "status": ClientStatus.INACTIVE,
                        "whatsapp.connected": False,
                        "whatsapp.connected_phone": None,
                        "whatsapp.qr_code": None,
                        "whatsapp.status": "close",
                        "last_activity": datetime.utcnow()
                    }
                }
            )
            await db["paused_conversations"].delete_many({"client_id": client_id})
            await db["threads"].delete_many({"client_id": client_id})
            await self.notify_admin_and_client(client, db, "disconnected")
            return {"success": True, "error": None}
        except Exception as e:
            logger.error(f"Error disconnecting client {client_id}: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_whatsapp_status_for_client(self, client_id: str, db: AsyncIOMotorDatabase = None):
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return {"status": ClientStatus.INACTIVE, "error": "Client not found"}
            instance_name = client_data["instance_id"]
            instance_token = client_data["instance_token"]
            status = await self.evolution_client.instance_operations.get_connection_state(instance_name, instance_token)
            logger.info(f"Instance {instance_name} status: {status}")
            if status == "close" and db:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                success = await self.create_service_for_client(ClientCreate(
                    name=client.name,
                    email=client.email,
                    openai_api_key=client.openai_api_key,
                    openai_assistant_id=client.openai_assistant_id
                ), db)
                if success:
                    return {"status": ClientStatus.CONNECTING, "instance": {"instanceName": instance_name, "status": "connecting"}}
            return {"status": status, "instance": {"instanceName": instance_name, "status": status}}
        except Exception as e:
            logger.error(f"Error fetching status for client {client_id}: {str(e)}")
            if "instance not found" in str(e).lower() and db:
                client_data = await db["clients"].find_one({"id": client_id})
                if client_data:
                    client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                    success = await self.create_service_for_client(ClientCreate(
                        name=client.name,
                        email=client.email,
                        openai_api_key=client.openai_api_key,
                        openai_assistant_id=client.openai_assistant_id
                    ), db, existing_client_id=client_id) # Pass existing_client_id here
                    if success:
                        return {"status": ClientStatus.CONNECTING, "instance": {"instanceName": instance_name, "status": "connecting"}}
            return {"status": ClientStatus.INACTIVE, "error": str(e)}

    async def get_qr_code(self, client_id: str, db: AsyncIOMotorDatabase):
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return {"qr": None, "error": "Client not found", "state": None}
            instance_name = client_data["instance_id"]
            instance_token = client_data["instance_token"]
            if not instance_token:
                logger.error(f"No instance token for client {client_id}")
                return {"qr": None, "error": "No instance token found", "state": None}

            if client_id not in self.services:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                success = await self.create_service_for_client(ClientCreate(
                    name=client.name,
                    email=client.email,
                    openai_api_key=client.openai_api_key,
                    openai_assistant_id=client.openai_assistant_id
                ), db)
                if not success:
                    return {"qr": None, "error": f"Failed to create instance '{instance_name}'", "state": None}

            qr_code = await self.evolution_client.instances.get_instance_qrcode(instance_name, instance_token)
            status = await self.evolution_client.instance_operations.get_connection_state(instance_name, instance_token)
            if status == ClientStatus.OPEN:
                logger.info(f"Instance {instance_name} is already in 'open' state")
                return {"qr": None, "error": None, "state": ClientStatus.OPEN}
            if not qr_code:
                logger.error(f"No QR code returned for {instance_name}")
                return {"qr": None, "error": "No QR code provided by Evolution API", "state": ClientStatus.CONNECTING}
            logger.info(f"QR code fetched for {instance_name}")
            return {"qr": qr_code, "error": None, "state": ClientStatus.CONNECTING, "qr_timeout": 25000}
        except Exception as e:
            logger.error(f"Error fetching QR code for {instance_name}: {str(e)}")
            if "instance does not exist" in str(e).lower():
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                success = await self.create_service_for_client(ClientCreate(
                    name=client.name,
                    email=client.email,
                    openai_api_key=client.openai_api_key,
                    openai_assistant_id=client.openai_assistant_id
                ), db)
                if success:
                    qr_code = await self.evolution_client.instances.get_instance_qrcode(instance_name, instance_token)
                    if qr_code:
                        return {"qr": qr_code, "error": None, "state": ClientStatus.CONNECTING, "qr_timeout": 25000}
                return {"qr": None, "error": f"Failed to create instance '{instance_name}'", "state": None}
            return {"qr": None, "error": str(e), "state": None}

    async def store_thread(self, client_id: str, phone_number: str, thread_id: str, db: AsyncIOMotorDatabase):
        """Store an OpenAI thread for a client and phone number"""
        try:
            thread = Thread(client_id=client_id, phone_number=phone_number, thread_id=thread_id)
            await db["threads"].update_one(
                {"client_id": client_id, "phone_number": phone_number},
                {"$set": thread.dict()},
                upsert=True
            )
            logger.info(f"Stored thread for client {client_id} with phone {phone_number}")
        except Exception as e:
            logger.error(f"Error storing thread for client {client_id}: {str(e)}")

    async def get_thread(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> str | None:
        """Retrieve an OpenAI thread ID for a client and phone number"""
        try:
            thread = await db["threads"].find_one({"client_id": client_id, "phone_number": phone_number})
            if thread:
                return thread["thread_id"]
            return None
        except Exception as e:
            logger.error(f"Error retrieving thread for client {client_id}: {str(e)}")
            return None

    async def send_message(self, message: OutgoingMessage) -> bool:
        try:
            text_message = TextMessage(number=message.phone_number, text=message.message)
            await self.evolution_client.messages.send_text(message.instance_id, text_message, instance_token=None)
            logger.info(f"Message sent to {message.phone_number}")
            return True
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False

    async def generate_ai_response(self, text: str, client_id: str, db: AsyncIOMotorDatabase) -> str:
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found for AI response")
                return "Lo siento, hubo un error procesando tu mensaje."
            openai_api_key = client_data.get("openai_api_key", OPENAI_API_KEY)
            assistant_id = client_data.get("openai_assistant_id")
            phone_number = client_data.get("whatsapp", {}).get("connected_phone", "")
            openai_client = AsyncOpenAI(api_key=openai_api_key)

            # Retrieve or create thread
            thread_id = await self.get_thread(client_id, phone_number, db)
            if not thread_id:
                thread = await openai_client.beta.threads.create()
                thread_id = thread.id
                await self.store_thread(client_id, phone_number, thread_id, db)

            # Add message to thread
            await openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=text
            )

            # Run assistant
            run = await openai_client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=assistant_id
            )

            # Poll for run completion
            while True:
                run_status = await openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run_status.status == "completed":
                    break
                await asyncio.sleep(1)

            # Retrieve messages
            messages = await openai_client.beta.threads.messages.list(thread_id=thread_id)
            response_text = messages.data[0].content[0].text.value.strip()
            logger.info(f"Generated AI response for client {client_id}: {response_text}")
            return response_text
        except Exception as e:
            logger.error(f"Error generating AI response for client {client_id}: {str(e)}")
            return "Lo siento, hubo un error procesando tu mensaje."

    async def store_message(self, client_id: str, phone_number: str, message: str, is_from_ai: bool, db: AsyncIOMotorDatabase):
        try:
            await db["chats"].insert_one({
                "id": str(uuid.uuid4()),
                "client_id": client_id,
                "phone_number": phone_number,
                "message": message,
                "is_from_ai": is_from_ai,
                "timestamp": datetime.utcnow(),
                "created_at": datetime.utcnow()
            })
            logger.info(f"Stored {'AI' if is_from_ai else 'user'} message for client {client_id} from/to {phone_number}")
        except Exception as e:
            logger.error(f"Error storing message for client {client_id}: {str(e)}")

    async def is_pause_command(self, message: str) -> bool:
        return message.lower().strip() in self.commands

    async def process_pause_command(self, message: str, client_id: str, phone_number: str, client_phone: str, db: AsyncIOMotorDatabase) -> str:
        normalized = message.lower().strip()
        if phone_number != client_phone:
            logger.info(f"Ignored pause command from {phone_number} (not client phone {client_phone})")
            return None
        if normalized in self.commands:
            try:
                return await self.commands[normalized](client_id, phone_number, db)
            except ValidationError as e:
                logger.error(f"Invalid input: {e}")
                return "❌ Datos inválidos. Intenta nuevamente."
        return None

    async def is_conversation_paused(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> bool:
        try:
            paused = await db["paused_conversations"].find_one({
                "client_id": client_id,
                "phone_number": {"$in": [phone_number, "ALL"]}
            })
            return bool(paused)
        except Exception as e:
            logger.error(f"Error checking paused status: {e}")
            return False

    async def pause_conversation(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> str:
        try:
            existing = await db["paused_conversations"].find_one({"client_id": client_id, "phone_number": phone_number})
            if existing:
                return "✅ Esta conversación ya estaba pausada."
            pause = PausedConversation(client_id=client_id, phone_number=phone_number, paused_by="client")
            await db["paused_conversations"].update_one(
                {"client_id": client_id, "phone_number": phone_number},
                {"$set": pause.dict()},
                upsert=True
            )
            logger.info(f"Paused conversation {client_id} - {phone_number}")
            client_data = await db["clients"].find_one({"id": client_id})
            if client_data:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                await self.notify_admin_and_client(client, db, "paused", phone_number)
            return "✅ Conversación pausada."
        except Exception as e:
            logger.error(f"Error pausing conversation: {e}")
            return "❌ Error pausando conversación."

    async def reactivate_conversation(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> str:
        try:
            result = await db["paused_conversations"].delete_one({"client_id": client_id, "phone_number": phone_number})
            if result.deleted_count:
                logger.info(f"Reactivated conversation {client_id} - {phone_number}")
                client_data = await db["clients"].find_one({"id": client_id})
                if client_data:
                    client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                    await self.notify_admin_and_client(client, db, "reactivated", phone_number)
                return "✅ Conversación reactivada."
            return "ℹ️ Esta conversación no estaba pausada."
        except Exception as e:
            logger.error(f"Error reactivating conversation: {e}")
            return "❌ Error reactivando conversación."

    async def pause_all_conversations(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> str:
        try:
            pause = PausedConversation(client_id=client_id, phone_number="ALL", paused_by="global")
            await db["paused_conversations"].update_one(
                {"client_id": client_id, "phone_number": "ALL"},
                {"$set": pause.dict()},
                upsert=True
            )
            logger.info(f"Paused all conversations for client {client_id}")
            client_data = await db["clients"].find_one({"id": client_id})
            if client_data:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                await self.notify_admin_and_client(client, db, "paused_all")
            return "✅ Bot completamente pausado."
        except Exception as e:
            logger.error(f"Error pausing all conversations: {e}")
            return "❌ Error pausando bot."

    async def activate_all_conversations(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> str:
        try:
            result = await db["paused_conversations"].delete_many({"client_id": client_id})
            if result.deleted_count:
                logger.info(f"Activated all conversations for client {client_id}")
                client_data = await db["clients"].find_one({"id": client_id})
                if client_data:
                    client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                    await self.notify_admin_and_client(client, db, "reactivated_all")
                return f"✅ Bot reactivado. Se eliminaron {result.deleted_count} pausas."
            return "ℹ️ El bot no tenía conversaciones pausadas."
        except Exception as e:
            logger.error(f"Error activating all conversations: {e}")
            return "❌ Error reactivando bot."

    async def get_conversation_status(self, client_id: str, phone_number: str, db: AsyncIOMotorDatabase) -> str:
        try:
            specific = await db["paused_conversations"].find_one({"client_id": client_id, "phone_number": phone_number})
            global_ = await db["paused_conversations"].find_one({"client_id": client_id, "phone_number": "ALL"})
            total_paused = await db["paused_conversations"].count_documents({"client_id": client_id, "phone_number": {"$ne": "ALL"}})

            msg = "📊 Estado del Bot:\n"
            if global_:
                msg += "🔴 Bot: COMPLETAMENTE PAUSADO\n"
            elif specific:
                msg += "🟡 Esta conversación: PAUSADA\n🟢 Bot: ACTIVO para otras conversaciones\n"
            else:
                msg += "🟢 Esta conversación: ACTIVA\n🟢 Bot: FUNCIONANDO NORMAL\n"
            if total_paused > 0:
                msg += f"📱 Conversaciones pausadas: {total_paused}\n"
            msg += "\nComandos: pausar, reactivar, pausar todo, activar todo"
            return msg
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return "❌ Error obteniendo estado."

    async def pause_service_for_client(self, client_id: str, db: AsyncIOMotorDatabase):
        try:
            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return False
            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
            response = await self.pause_all_conversations(client_id, client_data.get("whatsapp", {}).get("connected_phone", ""), db)
            logger.info(f"Service pause attempt for client {client_id}: {response}")
            return "✅" in response
        except Exception as e:
            logger.error(f"Error pausing service for client {client_id}: {str(e)}")
            return False

    async def handle_webhook(self, client_id: str, payload: dict, db: AsyncIOMotorDatabase, active_websockets: list):
        try:
            event = payload.get('event')
            instance_name = client_id
            logger.info(f"Received webhook for {instance_name}: {event}")

            client_data = await db["clients"].find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return
            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})

            if event == 'qrcode.updated':
                qr_code = payload.get('data', {}).get('base64')
                if qr_code:
                    if client_id not in self.services:
                        self.services[client_id] = {
                            'instance_name': instance_name,
                            'instance_token': client_data.get("instance_token"),
                            'status': 'starting',
                            'client_name': client.name,
                            'qr_code': None,
                            'qr_expiry': None,
                            'connected_phone': None
                        }
                    self.services[client_id]['qr_code'] = qr_code
                    self.services[client_id]['qr_expiry'] = time.time() + 25
                    self.services[client_id]['status'] = ClientStatus.CONNECTING
                    logger.info(f"Updated QR code for {instance_name} with 25-second expiry")
                    await db["clients"].update_one(
                        {"id": client_id},
                        {
                            "$set": {
                                "status": ClientStatus.AWAITING_SCAN,
                                "whatsapp.connected": False,
                                "whatsapp.connected_phone": None,
                                "whatsapp.qr_code": qr_code,
                                "whatsapp.status": ClientStatus.CONNECTING,
                                "last_activity": datetime.utcnow()
                            }
                        }
                    )
                    await self.notify_admin_and_client(client, db, "qr_generated")
                    for ws in active_websockets:
                        await ws.send_json({
                            "clientId": client_id,
                            "connected": False,
                            "phone": None,
                            "status": ClientStatus.CONNECTING,
                            "qrCode": qr_code
                        })
            elif event == 'connection.update':
                status = payload.get('data', {}).get('status')
                if client_id not in self.services:
                    self.services[client_id] = {
                        'instance_name': instance_name,
                        'instance_token': client_data.get("instance_token"),
                        'status': 'starting',
                        'client_name': client.name,
                        'qr_code': None,
                        'qr_expiry': None,
                        'connected_phone': None
                    }
                if status == ClientStatus.OPEN:
                    self.services[client_id]['status'] = 'running'
                    self.services[client_id]['qr_code'] = None
                    self.services[client_id]['qr_expiry'] = None
                    phone = payload.get('data', {}).get('user', {}).get('id', '').split('@')[0]
                    self.services[client_id]['connected_phone'] = phone
                    logger.info(f"Instance {instance_name} connected with phone: +{phone}")
                    await db["clients"].update_one(
                        {"id": client_id},
                        {
                            "$set": {
                                "status": ClientStatus.ACTIVE,
                                "whatsapp.connected": True,
                                "whatsapp.connected_phone": phone,
                                "whatsapp.qr_code": None,
                                "whatsapp.status": ClientStatus.OPEN,
                                "last_activity": datetime.utcnow()
                            }
                        }
                    )
                    await self.notify_admin_and_client(client, db, "connected", phone)
                    for ws in active_websockets:
                        await ws.send_json({
                            "clientId": client_id,
                            "connected": True,
                            "phone": phone,
                            "status": ClientStatus.OPEN
                        })
                elif status in ['close', 'logout']:
                    self.services[client_id]['status'] = 'stopped'
                    self.services[client_id]['qr_code'] = None
                    self.services[client_id]['qr_expiry'] = None
                    self.services[client_id]['connected_phone'] = None
                    logger.info(f"Instance {instance_name} disconnected")
                    await db["clients"].update_one(
                        {"id": client_id},
                        {
                            "$set": {
                                "status": ClientStatus.INACTIVE,
                                "whatsapp.connected": False,
                                "whatsapp.connected_phone": None,
                                "whatsapp.qr_code": None,
                                "whatsapp.status": "close",
                                "last_activity": datetime.utcnow()
                            }
                        }
                    )
                    await db["paused_conversations"].delete_many({"client_id": client_id})
                    await db["threads"].delete_many({"client_id": client_id})
                    await self.notify_admin_and_client(client, db, "disconnected")
                    for ws in active_websockets:
                        await ws.send_json({
                            "clientId": client_id,
                            "connected": False,
                            "phone": None,
                            "status": "close"
                        })
            elif event == 'messages.upsert':
                message_data = payload.get('data', {}).get('messages', [{}])[0]
                text = message_data.get('text', {}).get('body', '')
                phone_number = message_data.get('key', {}).get('remoteJid', '').split('@')[0]
                if text:
                    try:
                        client_phone = client_data.get("whatsapp", {}).get("connected_phone", "")
                        if await self.is_pause_command(text):
                            response = await self.process_pause_command(text, client_id, phone_number, client_phone, db)
                            if response:
                                await self.store_message(client_id, phone_number, text, False, db)
                                await self.send_message(OutgoingMessage(
                                    phone_number=phone_number,
                                    message=response,
                                    instance_id=instance_name
                                ))
                                await self.store_message(client_id, phone_number, response, True, db)
                        elif not await self.is_conversation_paused(client_id, phone_number, db):
                            await self.store_message(client_id, phone_number, text, False, db)
                            ai_response = await self.generate_ai_response(text, client_id, db)
                            if ai_response:
                                await self.send_message(OutgoingMessage(
                                    phone_number=phone_number,
                                    message=ai_response,
                                    instance_id=instance_name
                                ))
                                await self.store_message(client_id, phone_number, ai_response, True, db)
                    except Exception as e:
                        logger.error(f"Error processing message for client {client_id}: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling webhook for client {client_id}: {str(e)}")

service_manager = WhatsAppServiceManager()

# FastAPI Endpoints
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info("WebSocket connected.")
    # Keep the connection open. No receive_text() loop for now.
    # The connection will implicitly close when the client disconnects.
    # We'll rely on the client-side close to remove it from active_connections.
    # This is less robust for server-side cleanup, but good for diagnosis.

@app.on_event("startup")
async def startup_event():
    """Initialize database and start recovery service"""
    db = await get_database()
    await init_db_indexes(db)
    background_tasks = BackgroundTasks()
    background_tasks.add_task(service_manager.monitor_loop, db)
    logger.info("Application started, indexes created, recovery service scheduled")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop recovery service and close database connection"""
    service_manager.stop()
    await close_database()
    logger.info("Application shutdown, recovery service stopped, database closed")

@app.post("/admin/clients", response_model=ClientResponse)
async def create_client(client: ClientCreate, db=Depends(get_database)):
    created_client = await service_manager.create_service_for_client(client, db)
    if not created_client:
        raise HTTPException(status_code=500, detail="Error al crear instancia")
    
    return ClientResponse(
        id=created_client.id,
        name=created_client.name,
        email=created_client.email,
        openai_api_key=created_client.openai_api_key[:4] + "..." if created_client.openai_api_key else "",
        openai_assistant_id=created_client.openai_assistant_id,
        status=created_client.status,
        connected=created_client.whatsapp.get("connected", False),
        connected_phone=created_client.whatsapp.get("connected_phone"),
        unique_url=created_client.unique_url,
        created_at=created_client.created_at,
        last_activity=created_client.last_activity
    )

@app.get("/admin/clients/{client_id}", response_model=ClientResponse)
async def get_client(client_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    client_data = await db["clients"].find_one({"id": client_id})
    if not client_data:
        raise HTTPException(status_code=404, detail="Client not found")
    return ClientResponse(
        id=client_data["id"],
        name=client_data["name"],
        email=client_data["email"],
        openai_api_key=client_data.get("openai_api_key", "")[:4] + "..." if client_data.get("openai_api_key") else "",
        openai_assistant_id=client_data.get("openai_assistant_id", ""),
        status=client_data["status"],
        connected=client_data.get("whatsapp", {}).get("connected", False),
        connected_phone=client_data.get("whatsapp", {}).get("connected_phone"),
        unique_url=client_data["unique_url"],
        created_at=client_data["created_at"],
        last_activity=client_data.get("last_activity")
    )

@app.get("/admin/clients/{client_id}/threads", response_model=List[Thread])
async def get_client_threads(client_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        threads = await db["threads"].find({"client_id": client_id}).to_list(length=100)
        if not threads:
            raise HTTPException(status_code=404, detail="No threads found")
        return [Thread(**thread) for thread in threads]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching threads: {str(e)}")
    
    
@app.put("/admin/clients/{client_id}", response_model=ClientResponse)
async def update_client(client_id: str, client_update: ClientUpdate, db=Depends(get_database)):
    success = await service_manager.update_client(client_id, client_update, db)
    if not success:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    client_data = await db["clients"].find_one({"id": client_id})
    return ClientResponse(
        id=client_data["id"],
        name=client_data["name"],
        email=client_data["email"],
        openai_api_key=client_data["openai_api_key"][:4] + "..." if client_data["openai_api_key"] else "",
        openai_assistant_id=client_data["openai_assistant_id"],
        status=client_data["status"],
        connected=client_data.get("whatsapp", {}).get("connected", False),
        connected_phone=client_data.get("whatsapp", {}).get("connected_phone"),
        unique_url=client_data["unique_url"],
        created_at=client_data["created_at"],
        last_activity=client_data["last_activity"]
    )

@app.put("/admin/clients/{client_id}/email")
async def update_client_email(client_id: str, update_data: UpdateEmailRequest, db=Depends(get_database)):
    success = await service_manager.update_client_email(client_id, update_data, db)
    if not success:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Email actualizado"}

@app.post("/admin/clients/{client_id}/toggle")
async def toggle_client_service(client_id: str, toggle_data: ToggleClientRequest, db=Depends(get_database)):
    success = await service_manager.toggle_client(client_id, toggle_data, db)
    if not success:
        raise HTTPException(status_code=400, detail="Error al cambiar estado del cliente")
    return {"message": f"Cliente {client_id} {'conectado' if toggle_data.action == 'connect' else 'desconectado'}"}

@app.delete("/admin/clients/{client_id}")
async def delete_client(client_id: str, db=Depends(get_database)):
    success = await service_manager.stop_service_for_client(client_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return {"message": "Cliente eliminado"}

@app.get("/admin/clients", response_model=list[ClientResponse])
async def list_clients(db=Depends(get_database)):
    clients = await db["clients"].find().to_list(length=100)
    return [
        ClientResponse(
            id=client["id"],
            name=client["name"],
            email=client["email"],
            openai_api_key=client["openai_api_key"][:4] + "..." if client["openai_api_key"] else "",
            openai_assistant_id=client["openai_assistant_id"],
            status=client["status"],
            connected=client.get("whatsapp", {}).get("connected", False),
            connected_phone=client.get("whatsapp", {}).get("connected_phone"),
            unique_url=client["unique_url"],
            created_at=client["created_at"],
            last_activity=client["last_activity"]
        ) for client in clients
    ]

@app.post("/admin/clients/{client_id}/resend-email")
async def resend_email(client_id: str, db=Depends(get_database)):
    client_data = await db["clients"].find_one({"id": client_id})
    if not client_data:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
    await service_manager.notify_admin_and_client(client, db, "created")
    return {"message": "Email reenviado"}

@app.get("/admin/chats/{instance_id}", response_model=list[ClientMessage])
async def get_chats(instance_id: str, db=Depends(get_database)):
    client = await db["clients"].find_one({"instance_id": instance_id})
    if not client or client["status"] != ClientStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Instancia no encontrada o inactiva")
    chats = await db["chats"].find({"client_id": instance_id}).to_list(length=100)
    return [ClientMessage(**chat) for chat in chats]

@app.get("/admin/clients/{client_id}/status")
async def get_client_status(client_id: str, db=Depends(get_database)):
    status = await service_manager.get_whatsapp_status_for_client(client_id, db)
    if status.get("error"):
        raise HTTPException(status_code=500, detail=status["error"])
    return status

@app.get("/client/{instance_id}/qr")
async def request_qr(instance_id: str, db=Depends(get_database)):
    qr_data = await service_manager.get_qr_code(instance_id, db)
    if qr_data.get("error"):
        raise HTTPException(status_code=500, detail=qr_data["error"])
    return qr_data

@app.get("/client/{instance_id}/status")
async def client_status(instance_id: str, db=Depends(get_database)):
    status = await service_manager.get_whatsapp_status_for_client(instance_id, db)
    if status.get("error"):
        raise HTTPException(status_code=500, detail=status["error"])
    return status


@app.get("/client/{unique_url}/landing")
async def client_landing_page(unique_url: str, db=Depends(get_database)):
    client = await db["clients"].find_one({"unique_url": unique_url})
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    
    instance_id = client["id"]
    status = await service_manager.get_whatsapp_status_for_client(instance_id, db)
    message_count = await db["chats"].count_documents({"client_id": instance_id})
    paused_count = await db["paused_conversations"].count_documents({"client_id": instance_id, "phone_number": {"$ne": "ALL"}})
    global_pause = await db["paused_conversations"].find_one({"client_id": instance_id, "phone_number": "ALL"}) is not None
    
    return ClientResponse(
        id=client["id"],
        name=client["name"],
        email=client["email"],
        openai_api_key=client.get("openai_api_key", "")[:4] + "..." if client.get("openai_api_key") else "",
        openai_assistant_id=client.get("openai_assistant_id", ""),
        status=client["status"],
        connected=client.get("whatsapp", {}).get("connected", False),
        connected_phone=client.get("whatsapp", {}).get("connected_phone"),
        unique_url=client["unique_url"],
        created_at=client["created_at"],
        last_activity=client.get("last_activity"),
        messageCount=message_count,
        pausedCount=paused_count,
        globalPause=global_pause
    )
@app.post("/api/client/{client_id}/webhook")
async def webhook(client_id: str, payload: EvolutionWebhookPayload, db=Depends(get_database)):
    await service_manager.handle_webhook(client_id, payload.dict(), db, active_connections)
    return JSONResponse(content={"status": "received"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)