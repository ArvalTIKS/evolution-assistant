from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum
import uuid
import re

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
    email: Optional[EmailStr] = None
    openai_api_key: Optional[str] = None
    openai_assistant_id: Optional[str] = None
    unique_url: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    whatsapp_port: Optional[int] = None
    status: ClientStatus = ClientStatus.PENDING
    connected_phone: Optional[str] = Field(None, pattern=r"^\+?\d{10,15}$", description="Phone number in international format")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: Optional[datetime] = None
    whatsapp: Optional[dict] = {}  # Supports whatsapp.connected, whatsapp.qr_code, etc.

class ClientResponse(BaseModel):
    id: str
    name: str
    email: Optional[EmailStr] = None
    openai_api_key: Optional[str] = None
    openai_assistant_id: Optional[str] = None
    status: ClientStatus
    connected: bool
    connected_phone: Optional[str] = Field(None, pattern=r"^\+?\d{10,15}$")
    whatsapp_port: Optional[int] = None
    unique_url: str
    created_at: datetime
    last_activity: Optional[datetime] = None

class ClientMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    phone_number: str = Field(..., pattern=r"^\+?\d{10,15}$", description="Phone number in international format")
    message: str
    timestamp: datetime
    is_from_ai: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

class EmailTemplate(BaseModel):
    to_email: EmailStr
    client_name: str
    landing_url: str

class ToggleClientRequest(BaseModel):
    action: str  # "connect" or "disconnect"

class UpdateEmailRequest(BaseModel):
    new_email: EmailStr

class PausedConversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str
    phone_number: str = Field(..., pattern=r"^(?:\d{10,15}|ALL)$", description="Phone number or 'ALL' for global pause")
    paused_at: datetime = Field(default_factory=datetime.utcnow)
    paused_by: str = Field("client", description="'client' or 'global'")