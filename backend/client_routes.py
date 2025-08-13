from fastapi import FastAPI, APIRouter, Depends, HTTPException, Body
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Dict
import logging
from datetime import datetime
from pydantic import ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import PyMongoError
from evolution_api import EvolutionAPIError

from database import get_database
from models import Client, ClientStatus, EvolutionWebhookPayload, OutgoingMessage
from whatsapp_manager import service_manager, WhatsAppServiceManager
from instance_manager import get_instance_manager, InstanceManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{client_id}/webhook")
async def client_webhook(
    client_id: str,
    payload: EvolutionWebhookPayload,
    db: AsyncIOMotorDatabase = Depends(get_database),
    active_websockets: list = Depends(lambda: []),
):
    try:
        logger.debug(f"Received webhook for client {client_id}: {payload.dict()}")
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found for webhook")
            raise HTTPException(status_code=404, detail="Client not found")
        await service_manager.handle_webhook(client_id, payload.dict(), db, active_websockets)
        logger.info(f"Processed webhook for client {client_id}")
        return {"status": "ok"}
    except PyMongoError as e:
        logger.error(f"Database error processing webhook for client {client_id}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error processing webhook for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error processing webhook for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing webhook: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{unique_url}/instance")
async def create_instance(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
        created = await service_manager.create_service_for_client(client, db)
        if not created:
            logger.error(f"Failed to create instance for client {client.id}")
            raise HTTPException(status_code=500, detail="Error creating instance")
        logger.info(f"Created instance for client {client.id}")
        return {"status": "instance_created", "client_id": client.id}
    except PyMongoError as e:
        logger.error(f"Database error creating instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error creating instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error creating instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error creating instance: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.delete("/client/{unique_url}/instance")
async def delete_instance(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        deleted = await service_manager.stop_service_for_client(client_id, db)
        if not deleted:
            logger.error(f"Failed to delete instance for client {client_id}")
            raise HTTPException(status_code=500, detail="Error deleting instance")
        logger.info(f"Deleted instance for client {client_id}")
        return {"status": "instance_deleted"}
    except PyMongoError as e:
        logger.error(f"Database error deleting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error deleting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error deleting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting instance: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{unique_url}/send")
async def send_message(unique_url: str, body: Dict[str, str] = Body(...), db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        phone_number = body.get("phone_number")
        message = body.get("message")
        if not phone_number or not message:
            logger.error(f"Missing phone_number or message for client {client_id}")
            raise HTTPException(status_code=400, detail="Missing phone_number or message")
        # Validate phone number format
        if not re.match(r"^\+?\d{10,15}$", phone_number):
            logger.error(f"Invalid phone number format: {phone_number}")
            raise HTTPException(status_code=400, detail="Invalid phone number format")
        
        sent = await service_manager.send_message(OutgoingMessage(
            phone_number=phone_number,
            message=message,
            instance_id=f"client-{client_id}"
        ))
        if not sent:
            logger.error(f"Failed to send message for client {client_id}")
            raise HTTPException(status_code=500, detail="Error sending message")
        logger.info(f"Sent message for client {client_id} to {phone_number}")
        return {"status": "message_sent"}
    except PyMongoError as e:
        logger.error(f"Database error sending message for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error sending message for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except ValidationError as e:
        logger.error(f"Invalid message data for unique_url {unique_url}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid message data: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error sending message for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error sending message: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.get("/client/{unique_url}/status")
async def get_instance_status(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database), instance_manager: InstanceManager = Depends(get_instance_manager)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        client = Client(**{k: v for k, v in client_data.items() if k != '_id'})

        status_response = await service_manager.get_whatsapp_status_for_client(client_id, db)
        if status_response["status"] == "unknown":
            logger.warning(f"Status unknown for client {client_id}: {status_response.get('error')}")
            success = await service_manager.create_service_for_client(client, db)
            if success:
                status_response = await service_manager.get_whatsapp_status_for_client(client_id, db)
                if status_response["status"] == "unknown":
                    logger.error(f"Failed to create instance for client {client_id} after unknown status")
                    raise HTTPException(status_code=500, detail="Failed to initialize instance")

        if status_response["status"] == "open" and client_data.get("whatsapp", {}).get("status") != "open":
            logger.info(f"Syncing database for client {client_id} to 'open' state")
            phone_number = status_response.get("instance", {}).get("phoneNumber")
            await db.clients.update_one(
                {"id": client_id},
                {
                    "$set": {
                        "status": ClientStatus.ACTIVE,
                        "whatsapp.connected": True,
                        "whatsapp.connected_phone": phone_number,
                        "whatsapp.qr_code": None,
                        "whatsapp.status": "open",
                        "last_activity": datetime.utcnow()
                    }
                }
            )
            client_data = await db.clients.find_one({"id": client_id})

        logger.info(f"Fetched status for client {client_id}")
        return {
            "status": "ok",
            "data": {
                "client": {
                    "id": client_id,
                    "name": client_data.get("name"),
                    "email": client_data.get("email"),
                    "messageCount": client_data.get("messageCount", 0),
                    "pausedCount": client_data.get("pausedCount", 0),
                    "globalPause": client_data.get("globalPause", False)
                },
                "service": {
                    "status": status_response["status"],
                    "instance": {
                        "user": {
                            "id": f"{status_response.get('instance', {}).get('phoneNumber') or client_data.get('whatsapp', {}).get('connected_phone')}@s.whatsapp.net"
                            if status_response["status"] == "open" else None
                        }
                    },
                    "error": status_response.get("error")
                }
            }
        }
    except PyMongoError as e:
        logger.error(f"Database error fetching status for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error fetching status for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching status for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching instance status: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.get("/client/{unique_url}/qr")
async def get_qr_code(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        qr_response = await service_manager.get_qr_code(client_id, db)
        logger.info(f"Fetched QR code for client {client_id}")
        return {
            "status": "ok",
            "data": {
                "qr": qr_response.get("qr"),
                "base64": qr_response.get("qr"),  # For frontend compatibility
                "state": qr_response.get("state"),
                "error": qr_response.get("error"),
                "connected_phone": qr_response.get("connected_phone"),
                "qr_timeout": qr_response.get("qr_timeout")
            }
        }
    except PyMongoError as e:
        logger.error(f"Database error fetching QR code for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error fetching QR code for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching QR code for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching QR code: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{unique_url}/recreate")
async def recreate_instance(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client = Client(**{k: v for k, v in client_data.items() if k != '_id'})
        await service_manager.stop_service_for_client(client.id, db)
        success = await service_manager.create_service_for_client(client, db)
        if not success:
            logger.error(f"Failed to recreate instance for client {client.id}")
            raise HTTPException(status_code=500, detail="Error recreating instance")
        logger.info(f"Recreated instance for client {client.id}")
        return {"status": "instance_recreated", "client_id": client.id}
    except PyMongoError as e:
        logger.error(f"Database error recreating instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error recreating instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error recreating instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error recreating instance: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.get("/client/{unique_url}/pairing-code")
async def get_pairing_code(unique_url: str, phone_number: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        if not phone_number:
            logger.error(f"Missing phone_number for client {client_id}")
            raise HTTPException(status_code=400, detail="Missing phone_number query parameter")
        if not re.match(r"^\+?\d{10,15}$", phone_number):
            logger.error(f"Invalid phone number format: {phone_number}")
            raise HTTPException(status_code=400, detail="Invalid phone number format")
        
        pairing_response = await service_manager.get_pairing_code_for_client(client_id, phone_number, db)
        logger.info(f"Fetched pairing code for client {client_id}")
        return {
            "status": "ok",
            "data": {
                "code": pairing_response.get("code"),
                "error": pairing_response.get("error")
            }
        }
    except PyMongoError as e:
        logger.error(f"Database error fetching pairing code for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error fetching pairing code for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error fetching pairing code for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching pairing code: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{unique_url}/reconnect")
async def reconnect_instance(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        success = await service_manager.reconnect_instance(f"client-{client_id}")
        if not success:
            logger.error(f"Failed to reconnect instance for client {client_id}")
            raise HTTPException(status_code=500, detail="Error reconnecting instance")
        logger.info(f"Reconnected instance for client {client_id}")
        return {"status": "instance_reconnected"}
    except PyMongoError as e:
        logger.error(f"Database error reconnecting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error reconnecting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error reconnecting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reconnecting instance: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{unique_url}/disconnect")
async def disconnect_instance(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        disconnect_response = await service_manager.disconnect_client_whatsapp(client_id, db)
        if not disconnect_response["success"]:
            logger.error(f"Failed to disconnect instance for client {client_id}: {disconnect_response['error']}")
            raise HTTPException(status_code=500, detail=f"Error disconnecting instance: {disconnect_response['error']}")
        logger.info(f"Disconnected instance for client {client_id}")
        return {"status": "instance_disconnected"}
    except PyMongoError as e:
        logger.error(f"Database error disconnecting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error disconnecting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error disconnecting instance for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error disconnecting instance: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.delete("/client/{client_id}/logout")
async def disconnect_instance_alias(client_id: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client with client_id {client_id} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        disconnect_response = await service_manager.disconnect_client_whatsapp(client_id, db)
        if not disconnect_response["success"]:
            logger.error(f"Failed to disconnect instance for client {client_id}: {disconnect_response['error']}")
            raise HTTPException(status_code=500, detail=f"Error disconnecting instance: {disconnect_response['error']}")
        logger.info(f"Disconnected instance for client {client_id} via logout")
        return {"status": "instance_disconnected"}
    except PyMongoError as e:
        logger.error(f"Database error disconnecting instance for client_id {client_id}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error disconnecting instance for client_id {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error disconnecting instance for client_id {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error disconnecting instance: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/client/{unique_url}/pause")
async def pause_service(unique_url: str, db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"unique_url": unique_url})
        if not client_data:
            logger.error(f"Client with unique_url {unique_url} not found")
            raise HTTPException(status_code=404, detail="Client not found")
        client_id = client_data["id"]
        success = await service_manager.pause_service_for_client(client_id, db)
        if not success:
            logger.error(f"Failed to pause service for client {client_id}")
            raise HTTPException(status_code=500, detail="Error pausing service")
        logger.info(f"Paused service for client {client_id}")
        return {"status": "service_paused"}
    except PyMongoError as e:
        logger.error(f"Database error pausing service for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error pausing service for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error pausing service for unique_url {unique_url}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error pausing service: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.post("/regenerate-all")
async def regenerate_all_services(db: AsyncIOMotorDatabase = Depends(get_database)):
    try:
        result = await service_manager.regenerate_all_services(db)
        logger.info(f"Regenerated services: {result['regenerated']} succeeded, {result['failed']} failed, {result['skipped']} skipped")
        return {
            "status": "ok",
            "data": {
                "regenerated": result["regenerated"],
                "failed": result["failed"],
                "skipped": result["skipped"],
                "details": result["details"]
            }
        }
    except PyMongoError as e:
        logger.error(f"Database error regenerating all services: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error regenerating all services: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error regenerating all services: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error regenerating services: {str(e)}")

# Create the FastAPI app and include the router
app = FastAPI()
app.include_router(router)