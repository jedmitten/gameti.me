import logging

from .config import settings

logger = logging.getLogger(__name__)


async def send_recovery_email(to_email: str, username: str, recovery_url: str) -> None:
    if not settings.smtp_host:
        print(f"[DEV] Password recovery for {username}: {recovery_url}")
        return

    try:
        import aiosmtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "OurTime password recovery"
        msg["From"] = settings.smtp_from
        msg["To"] = to_email

        html_body = f"""<!DOCTYPE html>
<html>
<body>
<p>Hi {username},</p>
<p>You requested a password reset for your OurTime account.</p>
<p><a href="{recovery_url}">Click here to reset your password</a></p>
<p>This link expires in 15 minutes.</p>
<p>If you did not request this, you can ignore this email.</p>
</body>
</html>"""

        text_body = (
            f"Hi {username},\n\n"
            f"You requested a password reset for your OurTime account.\n\n"
            f"Reset your password here: {recovery_url}\n\n"
            f"This link expires in 15 minutes.\n\n"
            f"If you did not request this, you can ignore this email."
        )

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_tls,
        )
    except Exception as exc:
        logger.error("Failed to send recovery email to %s: %s", to_email, exc)
