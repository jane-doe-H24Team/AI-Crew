# avatar_manager/connectors/email_connector.py

import imaplib
import smtplib
import email
from email.mime.text import MIMEText
from email.header import decode_header
from bs4 import BeautifulSoup
from avatar_manager import db
from avatar_manager.connectors.base_connector import BaseConnector

import logging

logger = logging.getLogger(__name__)

class EmailConnector(BaseConnector):
    def __init__(self, avatar_id: str):
        super().__init__(avatar_id)
        self.email_address = None
        self.password = None
        self.imap_server = None
        self.smtp_server = None

    def get_credentials(self):
        self.email_address = self._get_env_var("EMAIL_ADDRESS")
        self.password = self._get_env_var("EMAIL_PASSWORD")
        self.imap_server = self._get_env_var("IMAP_SERVER")
        self.smtp_server = self._get_env_var("SMTP_SERVER")

    async def fetch_updates(self):
        """Connects to the IMAP server and fetches unread emails."""
        try:
            if not all([self.email_address, self.password, self.imap_server]):
                self.logger.error("Email credentials not loaded for avatar %s", self.avatar_id)
                return None, []
            
            mail = imaplib.IMAP4_SSL(self.imap_server)
            mail.login(self.email_address, self.password)
            
            mail.select("inbox")
            
            status, messages = mail.search(None, "UNSEEN")
            
            unread_emails = []
            if status == "OK":
                for num in messages[0].split():
                    status, data = mail.fetch(num, "(RFC822)")
                    if status == "OK":
                        msg = email.message_from_bytes(data[0][1])
                        
                        # Decode subject
                        subject, encoding = decode_header(msg["Subject"])[0]
                        if isinstance(subject, bytes):
                            subject = subject.decode(encoding if encoding else "utf-8")

                        # Decode sender
                        from_address, encoding = decode_header(msg.get("From"))[0]
                        if isinstance(from_address, bytes):
                            from_address = from_address.decode(encoding if encoding else "utf-8")

                        # Extract message body
                        body = _extract_email_body(msg)
                        
                        unread_emails.append({
                            "id": num.decode(), # Add message ID
                            "from": from_address,
                            "subject": subject,
                            "body": body
                        })
                        db.add_email_to_history(self.avatar_id, from_address, self.email_address, subject, body)
            
            # Do not close connection here, pass it to mark as read
            return mail, unread_emails

        except Exception as e:
            self.logger.error("Error fetching emails for %s: %s", self.avatar_id, e)
            return None, []

    async def send_message(self, to_address: str, subject: str, body: str):
        """Connects to the SMTP server and sends an email."""
        try:
            if not all([self.email_address, self.password, self.smtp_server]):
                self.logger.error("Email credentials not loaded for avatar %s", self.avatar_id)
                return False

            # Create message
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = self.email_address
            msg["To"] = to_address

            self.logger.debug(f"Attempting to send email to: {to_address}")
            self.logger.debug(f"Email subject: {subject}")
            self.logger.debug(f"Email body preview: {body[:200]}...") # Log a preview of the body
            self.logger.debug(f"Full email message:\n{msg.as_string()}") # Log the full message

            with smtplib.SMTP_SSL(self.smtp_server, 465) as server:
                server.set_debuglevel(1) # Set debug level to 1 for detailed SMTP conversation
                server.login(self.email_address, self.password)
                server.send_message(msg)
            self.logger.info("[%s] Email sent successfully to %s", self.avatar_id, to_address)
            cleaned_body = BeautifulSoup(body, 'html.parser').get_text().strip()
            # db.add_email_to_history(self.avatar_id, self.email_address, to_address, subject, cleaned_body)
            return True
        except Exception as e:
            self.logger.error("[%s] Error sending email: %s", self.avatar_id, e)
            return False
        
    def mark_emails_as_read(self, mail_connection, message_ids):
        """Marks a list of emails as read (\Seen) using an existing IMAP connection."""
        if not message_ids:
            if mail_connection:
                mail_connection.logout()
            return
        try:
            for msg_id in message_ids:
                mail_connection.store(msg_id.encode(), '+FLAGS', '\Seen')
            self.logger.info("Marked %d emails as read.", len(message_ids))
        except Exception as e:
            self.logger.error("Error flagging emails as read: %s", e)
        finally:
            if mail_connection:
                mail_connection.logout()

def _extract_email_body(msg) -> str:
    """Extracts the plain text body from an email message, handling multipart and HTML."""
    body_plain = ""
    body_html = ""

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            try:
                if "attachment" not in content_disposition:
                    if content_type == "text/plain":
                        body_plain = part.get_payload(decode=True).decode()
                    elif content_type == "text/html":
                        body_html = part.get_payload(decode=True).decode()
            except Exception as e:
                logger.warning(f"Error decoding email part: {e}")
    else:
        body_plain = msg.get_payload(decode=True).decode()

    final_body = ""
    if body_plain:
        final_body = body_plain
    elif body_html:
        final_body = body_html

    # Always strip HTML tags, regardless of whether it was originally plain or HTML
    soup = BeautifulSoup(final_body, 'html.parser')
    return soup.get_text().strip()