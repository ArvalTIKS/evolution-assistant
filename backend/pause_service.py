from datetime import datetime
from database import get_database_direct
from models import PausedConversation
import logging
from pydantic import ValidationError
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

class ConversationPauseService:
    def __init__(self):
        self.commands = {
            'pausar': self.pause_conversation,
            'reactivar': self.reactivate_conversation,
            'pausar todo': self.pause_all_conversations,
            'activar todo': self.activate_all_conversations,
            'estado': self.get_conversation_status
        }
        self.db = None
    
    async def initialize(self, db):
        """Initialize the service with a database connection"""
        if not db:
            logger.error("Invalid database connection provided")
            raise ValueError("Database connection is required")
        self.db = db
        try:
            await self.db.command("ping")
            logger.info("ConversationPauseService initialized with database")
        except PyMongoError as e:
            logger.error(f"Failed to initialize database connection: {str(e)}")
            raise

    def is_pause_command(self, message: str) -> bool:
        """Check if message is a pause control command"""
        if not message:
            return False
        # Normalize command: remove extra spaces, convert to lowercase
        normalized = re.sub(r'\s+', ' ', message.lower().strip())
        return normalized in self.commands

    async def process_pause_command(self, message: str, client_id: str, phone_number: str, client_phone: str) -> str:
        """Process pause control commands"""
        if phone_number != client_phone:
            logger.info(f"Ignoring pause command from {phone_number}: not client phone {client_phone}")
            return None
        normalized_message = re.sub(r'\s+', ' ', message.lower().strip())
        if normalized_message in self.commands:
            try:
                return await self.commands[normalized_message](client_id, phone_number)
            except ValidationError as e:
                logger.error(f"Invalid input for pause command: {str(e)}")
                return "❌ Datos inválidos. Intenta nuevamente."
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def is_conversation_paused(self, client_id: str, phone_number: str) -> bool:
        """Check if a specific conversation is paused"""
        try:
            paused_conversations = self.db.paused_conversations
            paused = await paused_conversations.find_one({
                "client_id": client_id,
                "phone_number": {"$in": [phone_number, "ALL"]}
            })
            return bool(paused)
        except PyMongoError as e:
            logger.error(f"Error checking if conversation is paused: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def pause_conversation(self, client_id: str, phone_number: str) -> str:
        """Pause specific conversation"""
        try:
            paused_conversations = self.db.paused_conversations
            existing = await paused_conversations.find_one({
                "client_id": client_id,
                "phone_number": phone_number
            })
            if existing:
                return "✅ Esta conversación ya estaba pausada."
            
            pause_data = PausedConversation(
                client_id=client_id,
                phone_number=phone_number,
                paused_at=datetime.utcnow()
            )
            await paused_conversations.update_one(
                {"client_id": client_id, "phone_number": phone_number},
                {"$set": pause_data.dict()},
                upsert=True
            )
            logger.info(f"Conversation paused for client {client_id}, phone {phone_number}")
            return "✅ Conversación pausada."
        except PyMongoError as e:
            logger.error(f"Error pausing conversation: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def reactivate_conversation(self, client_id: str, phone_number: str) -> str:
        """Reactivate specific conversation"""
        try:
            paused_conversations = self.db.paused_conversations
            result = await paused_conversations.delete_one({
                "client_id": client_id,
                "phone_number": phone_number
            })
            if result.deleted_count > 0:
                logger.info(f"Conversation reactivated for client {client_id}, phone {phone_number}")
                return "✅ Conversación reactivada."
            return "ℹ️ Esta conversación no estaba pausada."
        except PyMongoError as e:
            logger.error(f"Error reactivating conversation: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def pause_all_conversations(self, client_id: str, phone_number: str) -> str:
        """Pause all conversations for this client"""
        try:
            paused_conversations = self.db.paused_conversations
            pause_data = PausedConversation(
                client_id=client_id,
                phone_number="ALL",
                paused_at=datetime.utcnow()
            )
            await paused_conversations.update_one(
                {"client_id": client_id, "phone_number": "ALL"},
                {"$set": pause_data.dict()},
                upsert=True
            )
            logger.info(f"All conversations paused for client {client_id}")
            return "✅ Bot completamente pausado."
        except PyMongoError as e:
            logger.error(f"Error pausing all conversations: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def activate_all_conversations(self, client_id: str, phone_number: str) -> str:
        """Activate all conversations for this client"""
        try:
            paused_conversations = self.db.paused_conversations
            result = await paused_conversations.delete_many({"client_id": client_id})
            if result.deleted_count > 0:
                logger.info(f"All conversations activated for client {client_id}")
                return f"✅ Bot reactivado. Se eliminaron {result.deleted_count} pausas."
            return "ℹ️ El bot no tenía conversaciones pausadas."
        except PyMongoError as e:
            logger.error(f"Error activating all conversations: {str(e)}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
    async def get_conversation_status(self, client_id: str, phone_number: str) -> str:
        """Get status of current conversation and bot"""
        try:
            paused_conversations = self.db.paused_conversations
            specific_pause = await paused_conversations.find_one({
                "client_id": client_id,
                "phone_number": phone_number
            })
            global_pause = await paused_conversations.find_one({
                "client_id": client_id,
                "phone_number": "ALL"
            })
            total_paused = await paused_conversations.count_documents({
                "client_id": client_id,
                "phone_number": {"$ne": "ALL"}
            })
            
            status_msg = "📊 Estado del Bot:\n"
            if global_pause:
                status_msg += "🔴 Bot: COMPLETAMENTE PAUSADO\n"
            elif specific_pause:
                status_msg += "🟡 Esta conversación: PAUSADA\n"
                status_msg += "🟢 Bot: ACTIVO para otras conversaciones\n"
            else:
                status_msg += "🟢 Esta conversación: ACTIVA\n"
                status_msg += "🟢 Bot: FUNCIONANDO NORMAL\n"
            if total_paused > 0:
                status_msg += f"📱 Conversaciones pausadas: {total_paused}\n"
            status_msg += "\nComandos: pausar, reactivar, pausar todo, activar todo"
            
            return status_msg
        except PyMongoError as e:
            logger.error(f"Error getting conversation status: {str(e)}")
            raise

# Global pause service instance
pause_service = ConversationPauseService()