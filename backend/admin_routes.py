from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, ValidationError
from typing import List
from datetime import datetime
import logging
import json
from jsonschema import validate, ValidationError as JSONSchemaValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import PyMongoError
from evolution_api import EvolutionAPIError

from models import Client, ClientCreate, ClientResponse, ClientStatus, ToggleClientRequest, UpdateEmailRequest
from database import get_database
from email_service import email_service
from whatsapp_manager import service_manager
from instance_manager import get_instance_manager, InstanceManager
from url_detection import get_frontend_base_url

logger = logging.getLogger(__name__)

# Load JSON schema with fallback
try:
    with open("instance_schema.json", "r") as f:
        instance_schema = json.load(f)
except Exception as e:
    logger.warning(f"Failed to load instance_schema.json: {str(e)}. Using empty schema.")
    instance_schema = {}

router = APIRouter(prefix="/api/admin", tags=["admin"])

@router.post("/instances/configure")
async def configure_instance(instance_config: dict):
    try:
        if not instance_schema:
            logger.warning("No instance schema available. Skipping validation.")
            return {"message": "Instance configuration accepted (no schema validation)."}
        validate(instance_config, instance_schema)
        logger.info("Instance configuration validated successfully")
        return {"message": "Instance configuration data is valid."}
    except JSONSchemaValidationError as e:
        logger.error(f"Validation error in instance configuration: {e.message}")
        raise HTTPException(400, detail=f"Validation error: {e.message}")
    except Exception as e:
        logger.error(f"Unexpected error in configure_instance: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=f"Unexpected error: {str(e)}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.post("/clients", response_model=ClientResponse)
async def create_client(client_data: ClientCreate, background_tasks: BackgroundTasks, db=Depends(get_database)):
    try:
        client = Client(
            name=client_data.name,
            email=client_data.email,
            openai_api_key=client_data.openai_api_key,
            openai_assistant_id=client_data.openai_assistant_id,
            whatsapp_port=None,
            status=ClientStatus.PENDING
        )
        await db.clients.insert_one(client.dict())
        landing_url = f"{get_frontend_base_url()}/client/{client.unique_url}"
        background_tasks.add_task(email_service.send_client_invitation, client.email, client.name, landing_url)
        logger.info(f"Created client {client.name} with ID {client.id}")
        return ClientResponse(**client.dict())
    except PyMongoError as e:
        logger.error(f"Database error creating client: {str(e)}", exc_info=True)
        raise
    except ValidationError as e:
        logger.error(f"Invalid client data: {str(e)}")
        raise HTTPException(400, detail=f"Invalid client data: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error creating client: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.get("/clients", response_model=List[ClientResponse])
async def get_all_clients(db=Depends(get_database)):
    try:
        clients = await db.clients.find().to_list(None)
        result = []
        for c in clients:
            client_id = c["id"]
            status = await service_manager.get_whatsapp_status_for_client(f"client-{client_id}", db)
            if status.get("status") == "open" and c.get("status") != ClientStatus.ACTIVE:
                phone = status.get("instance", {}).get("owner", "").split("@")[0]
                update = {
                    "status": ClientStatus.ACTIVE,
                    "connected_phone": phone,
                    "last_activity": datetime.utcnow()
                }
                await db.clients.update_one({"id": client_id}, {"$set": update})
                c.update(update)
            c.pop("_id", None)
            c["connected"] = c["status"] in [ClientStatus.ACTIVE, ClientStatus.OPEN]
            result.append(ClientResponse(**c))
        logger.info(f"Fetched {len(result)} clients")
        return result
    except PyMongoError as e:
        logger.error(f"Database error fetching clients: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching clients: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.put("/clients/{client_id}/disconnect")
async def disconnect_client_whatsapp(client_id: str, db=Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        result = await service_manager.disconnect_client_whatsapp(client_id)
        if result.get("success"):
            await db.clients.update_one(
                {"id": client_id},
                {"$set": {"status": ClientStatus.INACTIVE, "connected_phone": None, "last_activity": datetime.utcnow()}}
            )
            logger.info(f"Disconnected WhatsApp for client {client_data['name']}")
            return {"success": True, "message": f"WhatsApp disconnected for client {client_data['name']}"}
        logger.error(f"Failed to disconnect WhatsApp for client {client_id}: {result.get('error')}")
        raise HTTPException(500, result.get("error", "Failed to disconnect WhatsApp"))
    except PyMongoError as e:
        logger.error(f"Database error disconnecting client {client_id}: {str(e)}", exc_info=True)
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error disconnecting client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type((PyMongoError, EvolutionAPIError)))
@router.put("/clients/{client_id}/toggle")
async def toggle_client_service(client_id: str, toggle_request: ToggleClientRequest, db=Depends(get_database), instance_manager: InstanceManager = Depends(get_instance_manager)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        client = Client(**{k: v for k, v in client_data.items() if k != "_id"})

        if toggle_request.action == "connect":
            status = await service_manager.get_whatsapp_status_for_client(client_id, db)
            if status.get("error", "").startswith("The") and "instance does not exist" in status.get("error", ""):
                created = await service_manager.create_service_for_client(client, db)
                if not created:
                    logger.error(f"Failed to create WhatsApp instance for client {client_id}")
                    raise HTTPException(500, "Failed to create WhatsApp instance")
            
            client_instance = await instance_manager.get_client(client_id)
            instance_data = await client_instance.fetch_instance(f"client-{client_id}")
            if instance_data.get("instance", {}).get("state") == "connected":
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"status": ClientStatus.ACTIVE, "connected_phone": instance_data.get("instance", {}).get("phoneNumber"), "last_activity": datetime.utcnow()}}
                )
                logger.info(f"Client {client.name} is already connected")
                return {"message": f"Client {client.name} is already connected.", "status": "active"}
            
            await db.clients.update_one(
                {"id": client_id},
                {"$set": {"status": ClientStatus.CONNECTING, "last_activity": datetime.utcnow()}}
            )
            logger.info(f"Initiated connection for client {client.name}")
            return {"message": f"Client {client.name} connection initiated.", "status": "initiated"}

        elif toggle_request.action == "disconnect":
            result = await service_manager.disconnect_client_whatsapp(client_id, db)
            if result.get("success"):
                await db.clients.update_one(
                    {"id": client_id},
                    {"$set": {"status": ClientStatus.INACTIVE, "connected_phone": None, "last_activity": datetime.utcnow()}}
                )
                logger.info(f"Disconnected service for client {client.name}")
                return {"message": f"Client {client.name} service stopped", "status": "inactive"}
            err = result.get("error", "Unknown error")
            if "instance is not connected" in err:
                logger.warning(f"Cannot disconnect client {client_id}: WhatsApp instance not connected")
                raise HTTPException(409, "Cannot disconnect: WhatsApp instance not connected.")
            logger.error(f"Failed to disconnect client {client_id}: {err}")
            raise HTTPException(500, f"Failed to stop WhatsApp service: {err}")

        else:
            logger.error(f"Invalid action for client {client_id}: {toggle_request.action}")
            raise HTTPException(400, "Invalid action. Use 'connect' or 'disconnect'")

    except PyMongoError as e:
        logger.error(f"Database error toggling service for client {client_id}: {str(e)}", exc_info=True)
        raise
    except EvolutionAPIError as e:
        logger.error(f"Evolution API error toggling service for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=f"Evolution API error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error toggling service for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, db=Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        await service_manager.stop_service_for_client(client_id, db)
        await db.clients.delete_one({"id": client_id})
        await db.client_messages.delete_many({"client_id": client_id})
        await db.paused_conversations.delete_many({"client_id": client_id})
        await db.openai_threads.delete_many({"client_id": client_id})
        logger.info(f"Deleted client {client_data['name']}")
        return {"message": f"Client {client_data['name']} deleted successfully"}
    except PyMongoError as e:
        logger.error(f"Database error deleting client {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error deleting client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.get("/clients/{client_id}/status")
async def get_client_status(client_id: str, db=Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        client_response_data = {k: v for k, v in client_data.items() if k != "_id"}
        client_response_data["connected"] = client_response_data["status"] in [ClientStatus.ACTIVE, ClientStatus.OPEN]
        service_status = await service_manager.get_whatsapp_status_for_client(client_id, db)
        coll = db.client_messages
        total_msgs = await coll.count_documents({"client_id": client_id})
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        msgs_today = await coll.count_documents({"client_id": client_id, "created_at": {"$gte": today_start}})
        unique_users = len(await coll.distinct("phone_number", {"client_id": client_id}))
        logger.info(f"Fetched status for client {client_id}")
        return {
            "client": ClientResponse(**client_response_data),
            "service": service_status,
            "stats": {"total_messages": total_msgs, "messages_today": msgs_today, "unique_users": unique_users}
        }
    except PyMongoError as e:
        logger.error(f"Database error fetching status for client {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching status for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@router.post("/cleanup/force")
async def force_cleanup():
    try:
        from cleanup_service import cleanup_service
        await cleanup_service.force_cleanup()
        logger.info("Force cleanup executed successfully")
        return {"message": "Cleanup executed successfully"}
    except Exception as e:
        logger.error(f"Error during force cleanup: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.put("/clients/{client_id}/update-openai")
async def update_client_openai(client_id: str, openai_data: dict, db=Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        update_fields = {}
        if "api_key" in openai_data:
            update_fields["openai_api_key"] = openai_data["api_key"]
        if "assistant_id" in openai_data:
            update_fields["openai_assistant_id"] = openai_data["assistant_id"]
        if not update_fields:
            logger.error(f"No OpenAI data provided for client {client_id}")
            raise HTTPException(400, "No OpenAI data provided")
        update_fields["last_activity"] = datetime.utcnow()
        await db.clients.update_one({"id": client_id}, {"$set": update_fields})
        logger.info(f"Updated OpenAI config for client {client_id}")
        return {"message": "OpenAI config updated", "success": True}
    except PyMongoError as e:
        logger.error(f"Database error updating OpenAI for client {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating OpenAI for client {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.get("/clients/{client_id}/paused-conversations")
async def get_paused_conversations(client_id: str, db=Depends(get_database)):
    try:
        paused = await db.paused_conversations.find({"client_id": client_id}).to_list(None)
        for p in paused:
            p.pop("_id", None)
        logger.info(f"Fetched {len(paused)} paused conversations for client {client_id}")
        return {"paused_conversations": paused, "count": len(paused)}
    except PyMongoError as e:
        logger.error(f"Database error fetching paused conversations for {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching paused conversations for {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.post("/clients/{client_id}/clear-paused")
async def clear_all_paused_conversations(client_id: str, db=Depends(get_database)):
    try:
        result = await db.paused_conversations.delete_many({"client_id": client_id})
        logger.info(f"Cleared {result.deleted_count} paused conversations for client {client_id}")
        return {"message": f"Cleared {result.deleted_count} paused conversations", "success": True, "cleared_count": result.deleted_count}
    except PyMongoError as e:
        logger.error(f"Database error clearing paused conversations for {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error clearing paused conversations for {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.put("/clients/{client_id}/update-email")
async def update_client_email(client_id: str, email_request: UpdateEmailRequest, db=Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"email": email_request.new_email, "last_activity": datetime.utcnow()}}
        )
        logger.info(f"Updated email for client {client_id} to {email_request.new_email}")
        return {"message": f"Email updated to {email_request.new_email}", "success": True}
    except PyMongoError as e:
        logger.error(f"Database error updating email for {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating email for {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), retry=retry_if_exception_type(PyMongoError))
@router.post("/clients/{client_id}/resend-email")
async def resend_client_email(client_id: str, background_tasks: BackgroundTasks, db=Depends(get_database)):
    try:
        client_data = await db.clients.find_one({"id": client_id})
        if not client_data:
            logger.error(f"Client {client_id} not found")
            raise HTTPException(404, "Client not found")
        client = Client(**{k: v for k, v in client_data.items() if k != "_id"})
        landing_url = f"{get_frontend_base_url()}/client/{client.unique_url}"
        background_tasks.add_task(email_service.send_client_invitation, client.email, client.name, landing_url)
        await db.clients.update_one(
            {"id": client_id},
            {"$set": {"last_activity": datetime.utcnow()}}
        )
        logger.info(f"Resent email to {client.email} for client {client_id}")
        return {"message": f"Email resent to {client.email}", "success": True}
    except PyMongoError as e:
        logger.error(f"Database error resending email for {client_id}: {str(e)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error resending email for {client_id}: {str(e)}", exc_info=True)
        raise HTTPException(500, detail=str(e))