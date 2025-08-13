import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from aiosmtplib import SMTP, SMTPException, SMTPAuthenticationError, SMTPConnectError
from pydantic import EmailStr, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from url_detection import get_environment_info

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = os.environ.get('EMAIL_SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('EMAIL_SMTP_PORT', 587))
        self.sender_email = os.environ.get('EMAIL_USERNAME', 'tikschile@gmail.com')
        self.email_password = os.environ.get('EMAIL_PASSWORD')
        
        # Validate environment variables
        if not all([self.smtp_server, self.sender_email, self.email_password]):
            logger.error("Missing required email environment variables: EMAIL_SMTP_SERVER, EMAIL_USERNAME, or EMAIL_PASSWORD")
            raise ValueError("EMAIL_SMTP_SERVER, EMAIL_USERNAME, and EMAIL_PASSWORD are required")
        try:
            if self.smtp_port <= 0 or self.smtp_port > 65535:
                raise ValueError(f"Invalid EMAIL_SMTP_PORT: {self.smtp_port}")
        except ValueError as e:
            logger.error(f"Invalid SMTP port configuration: {str(e)}")
            raise
        
        try:
            EmailStr.validate(self.sender_email)
        except ValidationError as e:
            logger.error(f"Invalid sender email format: {str(e)}")
            raise ValueError(f"Invalid EMAIL_USERNAME format: {self.sender_email}")

        self.smtp = SMTP(hostname=self.smtp_server, port=self.smtp_port, use_tls=False, start_tls=True)
        logger.info(f"Email service configured for {self.sender_email}")

    async def _connect_smtp(self):
        """Connect to the SMTP server with retry logic."""
        try:
            await self.smtp.connect()
            await self.smtp.starttls()
            await self.smtp.login(self.sender_email, self.email_password)
            logger.debug("SMTP connection established")
        except SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {str(e)}")
            raise
        except SMTPConnectError as e:
            logger.error(f"Failed to connect to SMTP server: {str(e)}")
            raise
        except SMTPException as e:
            logger.error(f"SMTP connection error: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((SMTPConnectError, SMTPException))
    )
    async def send_client_invitation(self, client_email: str, client_name: str, landing_url: str) -> bool:
        """Send invitation email to client with their landing page URL."""
        try:
            EmailStr.validate(client_email)
        except ValidationError as e:
            logger.error(f"Invalid client email format: {client_email}, error: {str(e)}")
            return False

        if not self.email_password:
            logger.error("Cannot send email - EMAIL_PASSWORD not configured")
            return False

        env_info = get_environment_info()
        logger.info(f"EMAIL: Environment: {env_info['environment']}, Frontend URL: {env_info['frontend_url']}, Landing URL: {landing_url}")

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
                    <div class="greeting">¡Hola <strong>{client_name}</strong>! 👋</div>
                    <div class="message">Tu asistente inteligente de WhatsApp ha sido configurado exitosamente.</div>
                    <div style="text-align: center;">
                        <a href="{landing_url}" class="cta-button"><span class="emoji">📱</span> Activar mi Asistente</a>
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
                            Contáctanos: <a href="mailto:{self.sender_email}" style="color: #25D366;">{self.sender_email}</a>
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
            msg['From'] = self.sender_email
            msg['To'] = client_email
            msg['Subject'] = f"🤖 Tu Asistente WhatsApp está listo - {client_name}"
            msg.attach(MIMEText(html_content, 'html'))

            await self._connect_smtp()
            await self.smtp.send_message(msg)
            logger.info(f"Email sent successfully to {client_email}")
            return True
        except (SMTPException, ValidationError) as e:
            logger.error(f"Error sending invitation email to {client_email}: {str(e)}")
            return False
        finally:
            if self.smtp.is_connected:
                await self.smtp.quit()
                logger.debug("SMTP connection closed")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((SMTPConnectError, SMTPException))
    )
    async def send_email(self, to_email: str, subject: str, message: str) -> bool:
        """Send a generic plain-text email."""
        try:
            EmailStr.validate(to_email)
        except ValidationError as e:
            logger.error(f"Invalid email format: {to_email}, error: {str(e)}")
            return False

        if not self.email_password:
            logger.error("Cannot send email - EMAIL_PASSWORD not configured")
            return False

        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))

            await self._connect_smtp()
            await self.smtp.send_message(msg)
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except (SMTPException, ValidationError) as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False
        finally:
            if self.smtp.is_connected:
                await self.smtp.quit()
                logger.debug("SMTP connection closed")

email_service = EmailService()