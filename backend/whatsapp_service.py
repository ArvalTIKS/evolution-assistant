import logging
import asyncio
import os
from typing import Dict, Any
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from evolution_api import Client as EvolutionClient, EvolutionAPIError  # Hypothetical package
from pause_service import pause_service
from models import Client, ClientStatus
import openai

logger = logging.getLogger(__name__)

class EvolutionWebhookPayload(BaseModel):
    event: str
    instance: str
    data: Any

class OutgoingMessage(BaseModel):
    phone_number: str
    message: str
    instance_id: str

class WhatsAppServiceManager:
    def __init__(self):
        self.services: Dict[str, dict] = {}
        self.evolution_api_url = os.environ.get('EVOLUTION_API_URL')
        self.evolution_api_key = os.environ.get('EVOLUTION_API_KEY')
        self.base_url = os.environ.get('BASE_URL', 'https://assistant-evolution.onrender.com')
        self.admin_email = os.environ.get('ADMIN_EMAIL')
        if not self.evolution_api_key or not self.evolution_api_url:
            logger.error("EVOLUTION_API_URL or EVOLUTION_API_KEY environment variable not set")
            raise ValueError("EVOLUTION_API_URL and EVOLUTION_API_KEY are required")
        self.api_client = EvolutionClient(api_key=self.evolution_api_key, base_url=self.evolution_api_url)
        logger.info("Initialized WhatsAppServiceManager with Evolution API client")

    async def _assign_available_port(self, db) -> int:
        used_ports = [c["whatsapp_port"] for c in await db.clients.find({"whatsapp_port": {"$ne": None}}).to_list(length=None)]
        for port in range(3000, 4000):
            if port not in used_ports:
                return port
        logger.error("No available ports in range 3000-4000")
        return None

    async def notify_admin_and_client(self, client: Client, db, event_type: str, phone: str = None):
        logger.info(f"Notification for {event_type} for client {client.name} would be sent here if enabled")
        pass

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def update_webhook_settings(self, instance_name: str, client_id: str) -> bool:
        try:
            webhook_url = f"{self.base_url.rstrip('/')}/api/client/{client_id}/webhook"
            webhook_config = {
                "url": webhook_url,
                "enabled": True,
                "webhook_by_events": True,
                "events": ["QRCODE_UPDATED", "CONNECTION_UPDATE", "MESSAGES_UPSERT"]
            }
            logger.debug(f"Updating webhook settings for {instance_name}: {webhook_config}")
            await self.api_client.set_webhook(instance_name, webhook_config)
            logger.info(f"Webhook settings updated successfully for {instance_name}")
            return True
        except EvolutionAPIError as e:
            logger.error(f"Error updating webhook settings for {instance_name}: {str(e)}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def create_service_for_client(self, client: Client, db) -> bool:
        instance_name = f"client-{client.id}"
        try:
            webhook_url = f"{self.base_url.rstrip('/')}/api/client/{client.id}/webhook"
            logger.debug(f"Creating instance {instance_name}")
            await self.api_client.create_instance(
                instance_name=instance_name,
                qrcode=True,
                webhook_url=webhook_url,
                webhook_events=["QRCODE_UPDATED", "CONNECTION_UPDATE", "MESSAGES_UPSERT"],
                webhook_by_events=True
            )
            logger.info(f"Instance {instance_name} created successfully for client {client.name}")
            await self.update_webhook_settings(instance_name, client.id)
            return True
        except EvolutionAPIError as e:
            if "already in use" in str(e).lower():
                logger.info(f"Instance {instance_name} already exists for client {client.name}")
                await self.update_webhook_settings(instance_name, client.id)
                return True
            elif "authentication failed" in str(e).lower():
                logger.error(f"Authentication failed for instance creation: {instance_name}")
                return False
            elif "token already exists" in str(e).lower():
                logger.warning(f"Instance {instance_name} token already exists. Attempting to reset and recreate.")
                if await self.reset_instance(instance_name):
                    logger.info(f"Instance {instance_name} successfully reset. Retrying creation.")
                    return await self.create_service_for_client(client, db)
                logger.error(f"Failed to reset instance {instance_name}. Cannot recreate.")
                return False
            logger.error(f"Error creating instance {instance_name}: {str(e)}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def reconnect_instance(self, instance_name: str) -> bool:
        try:
            logger.debug(f"Reconnecting instance {instance_name}")
            await self.api_client.connect(instance_name, qrcode=True)
            logger.info(f"Instance {instance_name} reconnected successfully")
            return True
        except EvolutionAPIError as e:
            logger.error(f"Error reconnecting instance {instance_name}: {str(e)}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def reset_instance(self, instance_name: str) -> bool:
        try:
            logger.debug(f"Deleting instance {instance_name}")
            await self.api_client.delete_instance(instance_name)
            logger.info(f"Instance {instance_name} deleted successfully")
            return True
        except EvolutionAPIError as e:
            logger.error(f"Error deleting instance {instance_name}: {str(e)}", exc_info=True)
            raise

    async def get_pairing_code_for_client(self, client_id: str, phone_number: str, db) -> dict:
        instance_name = client_id
        try:
            client_data = await db.clients.find_one({"id": client_id})
            if not client_data:
                return {"code": None, "error": "Client not found"}

            if client_id not in self.services:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                success = await self.create_service_for_client(client, db)
                if not success:
                    return {"code": None, "error": "Failed to create WhatsApp instance"}

            response = await self.api_client.connect(instance_name, pairing_code=True, number=phone_number)
            if response.get('code'):
                return {"code": response['code'], "error": None}
            if response.get('instance', {}).get('state') == 'open':
                logger.warning(f"Attempted to get pairing code for {instance_name}, but it's already open.")
                return {"code": None, "error": "This client is already connected."}
            if response.get('base64'):
                logger.warning(f"API could not generate a pairing code for {instance_name} and fell back to QR code.")
                return {"code": None, "error": "Could not get a pairing code. Please use the QR code method instead."}
            return {"code": None, "error": "Failed to retrieve pairing code"}
        except EvolutionAPIError as e:
            if "instance does not exist" in str(e).lower():
                logger.warning(f"Instance {instance_name} does not exist. Attempting to recreate.")
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                success = await self.create_service_for_client(client, db)
                if not success:
                    return {"code": None, "error": "Failed to recreate WhatsApp instance"}
                return await self.get_pairing_code_for_client(client_id, phone_number, db)
            logger.error(f"Error getting pairing code for client {client_id}: {str(e)}", exc_info=True)
            return {"code": None, "error": f"A server error occurred: {str(e)}"}

    async def stop_service_for_client(self, client_id: str, db) -> bool:
        instance_name = client_id
        try:
            await self.api_client.delete_instance(instance_name)
            logger.info(f"Deleted instance {instance_name} for client {client_id}")
            if client_id in self.services:
                del self.services[client_id]
            client_data = await db.clients.find_one({"id": client_id})
            if client_data:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                await self.notify_admin_and_client(client, db, "disconnected")
            return True
        except EvolutionAPIError as e:
            if "instance not found" in str(e).lower():
                logger.warning(f"Instance {instance_name} not found, treating as stopped")
                if client_id in self.services:
                    del self.services[client_id]
                client_data = await db.clients.find_one({"id": client_id})
                if client_data:
                    client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                    await self.notify_admin_and_client(client, db, "disconnected")
                return True
            logger.error(f"Error stopping service for client {client_id}: {str(e)}", exc_info=True)
            return False

    async def get_whatsapp_status_for_client(self, client_id: str, db=None):
        instance_name = client_id
        try:
            instance_data = await self.api_client.fetch_instance(instance_name)
            return {"status": instance_data.get("status", "unknown"), "instance": instance_data}
        except EvolutionAPIError as e:
            if "instance not found" in str(e).lower():
                return {"status": "unknown", "error": f"Instance '{instance_name}' not found"}
            logger.error(f"Error fetching status for client {client_id}: {str(e)}", exc_info=True)
            return {"status": "unknown", "error": str(e)}

    async def get_qr_code(self, client_id: str):
        instance_name = client_id
        try:
            response = await self.api_client.connect(instance_name, qrcode=True)
            instance_data = await self.api_client.fetch_instance(instance_name)
            if instance_data.get("status") == "connected":
                return {
                    "qr": None,
                    "error": None,
                    "state": "connected",
                    "connected_phone": instance_data.get("phoneNumber") or instance_data.get("owner")
                }
            if response.get("instance", {}).get("state") == "open":
                logger.info(f"Instance {instance_name} is already in 'open' state, indicating WhatsApp is linked.")
                return {"qr": None, "error": None, "state": "connected"}
            qr_code = response.get("base64") or response.get("qr") or response.get("qrcode")
            if not qr_code:
                logger.error(f"No QR code in response for {instance_name}: {response}")
                return {"qr": None, "error": "No QR code provided by Evolution API", "state": "open"}
            if not isinstance(qr_code, str):
                logger.error(f"QR code is not a string: {qr_code}")
                return {"qr": None, "error": "Invalid QR code format", "state": "open"}
            if not qr_code.startswith("data:image"):
                qr_code = f"data:image/png;base64,{qr_code}"
            return {"qr": qr_code, "error": None, "state": "qr", "qr_timeout": 25000}
        except EvolutionAPIError as e:
            if "instance does not exist" in str(e).lower():
                return {"qr": None, "error": f"Instance '{instance_name}' does not exist", "state": None}
            logger.error(f"Error fetching QR code for {instance_name}: {str(e)}", exc_info=True)
            return {"qr": None, "error": str(e), "state": None}

    async def disconnect_client_whatsapp(self, client_id: str, db) -> dict:
        instance_name = client_id
        try:
            await self.api_client.logout(instance_name)
            logger.info(f"WhatsApp logout successful for client {client_id}")
            if client_id in self.services:
                self.services[client_id]['status'] = 'stopped'
                self.services[client_id]['qr_code'] = None
                self.services[client_id]['qr_expiry'] = None
                self.services[client_id]['connected_phone'] = None
            client_data = await db.clients.find_one({"id": client_id})
            if client_data:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                await self.notify_admin_and_client(client, db, "disconnected")
            return {"success": True, "error": None}
        except EvolutionAPIError as e:
            if "instance not found" in str(e).lower():
                logger.warning(f"Instance {instance_name} not found, treating as disconnected")
                if client_id in self.services:
                    del self.services[client_id]
                client_data = await db.clients.find_one({"id": client_id})
                if client_data:
                    client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                    await self.notify_admin_and_client(client, db, "disconnected")
                return {"success": True, "error": None}
            logger.error(f"Error disconnecting client {client_id}: {str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def regenerate_all_services(self, db) -> dict:
        try:
            clients_collection = db.clients
            clients = await clients_collection.find({"status": ClientStatus.ACTIVE}).to_list(length=None)
            result = {"regenerated": 0, "failed": 0, "skipped": 0, "details": []}

            for client_data in clients:
                client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
                instance_name = client.id
                if client.id in self.services:
                    await self.stop_service_for_client(client.id, db)
                try:
                    instance_data = await self.api_client.fetch_instance(instance_name)
                    if instance_data:
                        await self.stop_service_for_client(client.id, db)
                except EvolutionAPIError:
                    pass  # Instance doesn't exist, proceed to create
                success = await self.create_service_for_client(client, db)
                if success:
                    result["regenerated"] += 1
                    result["details"].append(f"Regenerated instance for {client.name}")
                else:
                    result["failed"] += 1
                    result["details"].append(f"Failed to regenerate instance for {client.name}")
            logger.info(f"Service regeneration complete: {result['regenerated']} success, {result['failed']} failed, {result['skipped']} skipped")
            return result
        except Exception as e:
            logger.error(f"Error regenerating services: {str(e)}", exc_info=True)
            return {"regenerated": 0, "failed": len(clients) if 'clients' in locals() else 0, "skipped": 0, "details": [str(e)]}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(EvolutionAPIError))
    async def send_whatsapp_message(self, message: OutgoingMessage):
        try:
            instance_id = message.instance_id if message.instance_id.startswith("client-") else f"client-{message.instance_id}"
            logger.debug(f"Sending WhatsApp message to {message.phone_number} for instance {instance_id}: {message.message[:50]}...")
            response = await self.api_client.send_text_message(
                instance_id=instance_id,
                number=message.phone_number,
                message=message.message,
                options={"delay": 1200, "presence": "composing"}
            )
            logger.info(f"Message sent successfully to {message.phone_number} for instance {instance_id}")
            return response
        except EvolutionAPIError as e:
            logger.error(f"Error sending WhatsApp message to {message.phone_number} for instance {instance_id}: {str(e)}", exc_info=True)
            if "unauthorized" in str(e).lower():
                raise HTTPException(status_code=401, detail="Unauthorized access to Evolution API")
            raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")

    async def generate_ai_response(self, message: str, phone_number: str, openai_api_key: str, openai_assistant_id: str, db) -> str:
        try:
            start_time = datetime.utcnow()
            logger.info(f"[OpenAI] Starting response generation for phone {phone_number}, message: {message[:50]}...")
            client = openai.AsyncOpenAI(api_key=openai_api_key)
            if not openai_assistant_id:
                logger.error("Assistant ID not provided for this client.")
                return "Lo siento, hay un problema de configuración del asistente. Por favor intenta más tarde."

            thread = await client.beta.threads.create()
            logger.debug(f"[OpenAI] Thread created for {phone_number}: {thread.id}")
            await client.beta.threads.messages.create(thread_id=thread.id, role="user", content=message)
            run = await client.beta.threads.runs.create(thread_id=thread.id, assistant_id=openai_assistant_id)
            logger.debug(f"[OpenAI] Run started: {run.id}, initial status: {run.status}")

            max_attempts = 60
            attempts = 0
            while run.status in ['queued', 'in_progress'] and attempts < max_attempts:
                await asyncio.sleep(0.5)
                run = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
                attempts += 1
                logger.debug(f"[OpenAI] Attempt {attempts}, current status: {run.status}")

            if run.status == 'completed':
                messages = await client.beta.threads.messages.list(thread_id=thread.id, order="desc", limit=1)
                if messages.data and messages.data[0].role == 'assistant':
                    elapsed = (datetime.utcnow() - start_time).total_seconds()
                    logger.info(f"✅ OpenAI responded to {phone_number} in {elapsed:.2f}s")
                    return messages.data[0].content[0].text.value.strip()
                else:
                    logger.warning(f"[OpenAI] No assistant response found for {phone_number}")
                    return "Lo siento, no pude procesar tu mensaje correctamente."
            else:
                logger.error(f"❌ Assistant run failed or timed out with status: {run.status}")
                return "Lo siento, hubo un error procesando tu mensaje. Por favor intenta nuevamente."
        except Exception as e:
            logger.error(f"[OpenAI] Error generating response for phone {phone_number}: {str(e)}", exc_info=True)
            return "¡Hola! Gracias por tu mensaje. En este momento estoy procesando tu consulta. ¿En qué puedo ayudarte?"

    async def get_or_create_thread(self, db, phone_number: str, openai_api_key: str) -> str:
        threads_collection = db.whatsapp_threads
        thread_doc = await threads_collection.find_one({"phone_number": phone_number})
        client = openai.OpenAI(api_key=openai_api_key)
        if thread_doc and thread_doc.get('thread_id'):
            try:
                client.beta.threads.retrieve(thread_doc['thread_id'])
                return thread_doc['thread_id']
            except Exception as e:
                logger.warning(f"Thread {thread_doc['thread_id']} no longer exists in OpenAI: {e}")
                await threads_collection.delete_one({"phone_number": phone_number})
        thread = client.beta.threads.create()
        await threads_collection.update_one(
            {"phone_number": phone_number},
            {"$set": {"thread_id": thread.id, "created_at": datetime.utcnow()}},
            upsert=True
        )
        return thread.id

    async def store_message(self, db, phone_number: str, message: str, timestamp: int, is_from_ai: bool = False):
        try:
            messages_collection = db.whatsapp_messages
            await messages_collection.insert_one({
                "phone_number": phone_number,
                "message": message,
                "timestamp": timestamp,
                "is_from_ai": is_from_ai,
                "created_at": datetime.utcnow()
            })
        except Exception as e:
            logger.error(f"Error storing message: {str(e)}")

    async def handle_webhook(self, client_id: str, payload: dict, db, active_websockets: list):
        try:
            logger.debug(f"Webhook payload for {client_id}: {json.dumps(payload, indent=2)}")
            event = payload.get('event')
            instance_name = client_id
            logger.info(f"Received webhook for {instance_name}: {event}")

            client_data = await db.clients.find_one({"id": client_id})
            if not client_data:
                logger.error(f"Client {client_id} not found")
                return
            client = Client(**{k: v for k, v in client_data.items() if k != '_id'})

            if not hasattr(pause_service, 'db'):
                await pause_service.initialize(db)

            if event == 'qrcode.updated':
                qr_code = payload.get('data', {}).get('base64')
                if qr_code:
                    if client_id not in self.services:
                        self.services[client_id] = {
                            'instance_name': instance_name,
                            'status': 'starting',
                            'client_name': client.name,
                            'qr_code': None,
                            'qr_expiry': None,
                            'connected_phone': None
                        }
                    self.services[client_id]['qr_code'] = qr_code
                    self.services[client_id]['qr_expiry'] = time.time() + 25
                    logger.info(f"Updated QR code for {instance_name} with 25-second expiry.")
                    await db.clients.update_one(
                        {"id": client_id},
                        {
                            "$set": {
                                "status": ClientStatus.AWAITING_SCAN,
                                "whatsapp.connected": False,
                                "whatsapp.connected_phone": None,
                                "whatsapp.qr_code": qr_code,
                                "last_activity": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                    await self.notify_admin_and_client(client, db, "qr_generated")
            elif event == 'connection.update':
                status = payload.get('data', {}).get('status')
                if client_id not in self.services:
                    self.services[client_id] = {
                        'instance_name': instance_name,
                        'status': 'starting',
                        'client_name': client.name,
                        'qr_code': None,
                        'qr_expiry': None,
                        'connected_phone': None
                    }
                if status == 'open':
                    self.services[client_id]['status'] = 'running'
                    self.services[client_id]['qr_code'] = None
                    self.services[client_id]['qr_expiry'] = None
                    phone = payload.get('data', {}).get('user', {}).get('id', '').split('@')[0]
                    self.services[client_id]['connected_phone'] = phone
                    logger.info(f"Instance {instance_name} connected with phone: +{phone}")
                    await db.clients.update_one(
                        {"id": client_id},
                        {
                            "$set": {
                                "status": ClientStatus.ACTIVE,
                                "connected_phone": phone,
                                "whatsapp.connected": True,
                                "whatsapp.qr_code": None,
                                "last_activity": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                    await self.notify_admin_and_client(client, db, "connected", phone)
                    for ws in active_websockets:
                        await ws.send_json({
                            "clientId": client_id,
                            "connected": True,
                            "phone": phone,
                            "status": "active"
                        })
                elif status in ['close', 'logout']:
                    self.services[client_id]['status'] = 'stopped'
                    self.services[client_id]['qr_code'] = None
                    self.services[client_id]['qr_expiry'] = None
                    self.services[client_id]['connected_phone'] = None
                    logger.info(f"Instance {instance_name} disconnected.")
                    await db.clients.update_one(
                        {"id": client_id},
                        {
                            "$set": {
                                "status": ClientStatus.INACTIVE,
                                "whatsapp.connected": False,
                                "whatsapp.connected_phone": None,
                                "whatsapp.qr_code": None,
                                "last_activity": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                    await self.notify_admin_and_client(client, db, "disconnected")
                    for ws in active_websockets:
                        await ws.send_json({
                            "clientId": client_id,
                            "connected": False,
                            "phone": None,
                            "status": "inactive"
                        })
            else:
                logger.info(f"Handling {event} for client {client_id}")
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {f"whatsapp.{event}": payload.get('data', {}), "last_activity": datetime.utcnow()}},
                    upsert=True
                )
        except Exception as e:
            logger.error(f"Error handling webhook for client {client_id}: {str(e)}", exc_info=True)

service_manager = WhatsAppServiceManager()