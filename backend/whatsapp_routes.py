import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from database import get_database
from evolution_client import EvolutionClient  # Hypothetical Evolution API client

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

class MessageResponse(BaseModel):
    reply: Optional[str] = None
    success: bool = True

# Utility function to clean instance_id
def clean_instance_id(instance_id: str) -> str:
    return instance_id.replace("client-", "") if instance_id.startswith("client-") else instance_id

# Initialize Evolution API client (assuming it needs an API key)
evolution_client = EvolutionClient(api_key="YOUR_API_KEY")  # Replace with actual API key

@router.post("/webhook", response_model=MessageResponse)
async def process_evolution_webhook(request: Request, db=Depends(get_database)):
    try:
        payload_raw = await request.json()
        logger.info(f"Received raw webhook payload: {payload_raw}")
        instance_id = payload_raw.get('instance')
        if not instance_id:
            logger.error("No instance ID provided in webhook payload")
            return MessageResponse(success=False, reply="No instance ID provided")

        client_id = clean_instance_id(instance_id)
        # Delegate webhook processing to Evolution API client
        await evolution_client.handle_webhook(client_id, payload_raw)
        return MessageResponse(success=True)
    except ValueError as ve:
        logger.error(f"Invalid payload format: {str(ve)}")
        return MessageResponse(success=False, reply=str(ve))
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return MessageResponse(success=False, reply=str(e))

@router.get("/logout/{instance_id}")
async def logout_whatsapp(instance_id: str, db=Depends(get_database)):
    try:
        client_id = clean_instance_id(instance_id)
        # Use Evolution API client to disconnect
        result = await evolution_client.disconnect_instance(client_id)
        if result.get('success'):
            await db.clients.update_one(
                {"id": client_id},
                {"$set": {
                    "whatsapp.connected": False,
                    "whatsapp.status": "inactive",
                    "whatsapp.connected_phone": None,
                    "last_activity": datetime.utcnow()
                }}
            )
            return result
        raise HTTPException(status_code=500, detail=result.get('error', 'Unknown error'))
    except Exception as e:
        logger.error(f"Error during WhatsApp logout for instance {instance_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/qr/{instance_id}")
async def get_qr_code(instance_id: str, db=Depends(get_database)):
    try:
        client_id = clean_instance_id(instance_id)
        # Use Evolution API client to get QR code
        result = await evolution_client.get_qr_code(client_id)
        if result.get('qr'):
            return {"qr": result['qr'], "success": True}
        raise HTTPException(status_code=500, detail=result.get('error', 'Failed to obtain QR code'))
    except Exception as e:
        logger.error(f"Error obtaining QR for instance {instance_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")

@router.get("/status/{instance_id}")
async def get_whatsapp_status(instance_id: str, db=Depends(get_database)):
    try:
        client_id = clean_instance_id(instance_id)
        # Use Evolution API client to check status
        result = await evolution_client.get_instance_status(client_id)
        return result
    except Exception as e:
        logger.error(f"Error obtaining WhatsApp status for instance {instance_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Evolution API error: {str(e)}")

@router.get("/messages/{phone_number}")
async def get_messages(phone_number: str, db=Depends(get_database)):
    try:
        messages_collection = db.whatsapp_messages
        messages_cursor = messages_collection.find({"phone_number": phone_number}).sort("timestamp", -1).limit(50)
        messages = await messages_cursor.to_list(length=50)
        for message in messages:
            if '_id' in message:
                message['_id'] = str(message['_id'])
        return {"messages": list(reversed(messages))}
    except Exception as e:
        logger.error(f"Error fetching messages for {phone_number}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats(db=Depends(get_database)):
    try:
        messages_collection = db.whatsapp_messages
        total_messages = await messages_collection.count_documents({})
        utc_now = datetime.utcnow()
        utc_today_start = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
        messages_today = await messages_collection.count_documents({
            "created_at": {"$gte": utc_today_start}
        })
        unique_users = await messages_collection.distinct("phone_number")
        unique_users_count = len(unique_users)
        return {
            "total_messages": total_messages,
            "messages_today": messages_today,
            "unique_users": unique_users_count
        }
    except Exception as e:
        logger.error(f"Error fetching stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")