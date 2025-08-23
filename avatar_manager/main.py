import yaml
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from avatar_manager.connectors.email_connector import EmailConnector
from avatar_manager.connectors.github_connector import GithubConnector
from avatar_manager.connectors.telegram_connector import TelegramConnector
from avatar_manager.connectors.discord_connector import DiscordConnector
from avatar_manager.core import generator
from avatar_manager import db
from avatar_manager.internal_events import event_bus, InternalMessage
from avatar_manager.config import config

import logging

# Configure logging
log_level = config.get('app', {}).get('log_level', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Avatar Manager",
    description="An API to manage and orchestrate autonomous avatars.",
    version="0.1.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

def is_avatar_active(avatar_profile: dict) -> bool:
    """Controlla se l'avatar è attivo in base al suo schedule."""
    schedule = avatar_profile.get("schedule")
    if not schedule:
        return True 

    now_utc = datetime.now(timezone.utc)
    current_day = now_utc.weekday() # Monday is 0 and Sunday is 6
    current_hour = now_utc.hour

    for activity_type, details in schedule.items():
        is_day = current_day in details.get("days", [])
        is_hour = details.get("start_hour", 0) <= current_hour < details.get("end_hour", 24)
        if is_day and is_hour:
            return True
            
    return False

async def scheduled_email_check():
    """
    Funzione eseguita dallo scheduler per controllare le email di tutti gli avatar.
    """
    logger.info("--- Email check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile):
            logger.info("-> %s not active. Skipping.", avatar_profile['name'])
            continue
        
        email_connector = avatar_profile['connectors'].get('email')
        if not email_connector:
            logger.debug("Email connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        logger.info("-> %s active. Email checking...", avatar_profile['name'])
        try:
            mail_conn, unread_emails = await email_connector.fetch_updates()
            if mail_conn is None: # Check if an error occurred during fetching
                logger.info("-> Skipping email processing for %s due to previous error.", avatar_profile['name'])
                continue
            if not unread_emails:
                if mail_conn: email_connector.mark_emails_as_read(mail_conn, []) # Logout if no emails
                logger.info("-> No unread emails for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d emails for %s. Processing.", len(unread_emails), avatar_profile['name'])
            processed_ids, ignored_ids = [], []

            for email_data in unread_emails:
                if generator.should_reply_to_email(email_data):
                    reply_body = await generator.generate_reply(avatar_profile, email_data, avatar_id)
                    reply_subject = f"Re: {email_data['subject']}"
                    success = await email_connector.send_message(email_data['from'], reply_subject, reply_body)
                    if success:
                        processed_ids.append(email_data['id'])
                else:
                    logger.info("Email from %s ignored.", email_data['from'])
                    ignored_ids.append(email_data['id'])
                    # Publish internal message for ignored email
                    await event_bus.publish(InternalMessage(
                        sender_avatar_id=avatar_id,
                        message_type="email_ignored",
                        payload={
                            "from": email_data['from'],
                            "subject": email_data['subject'],
                            "body_preview": email_data['body'][:200] # Send a preview
                        }
                    ))
            
            all_processed_ids = processed_ids + ignored_ids
            email_connector.mark_emails_as_read(mail_conn, all_processed_ids)

        except Exception as e:
            logger.error("Error during email processing for %s: %s", avatar_id, e)

async def scheduled_github_check():
    """
    Funzione eseguita dallo scheduler per controllare le notifiche GitHub.
    """
    logger.info("--- GitHub check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile):
            logger.info("-> %s not active. Skipping.", avatar_profile['name'])
            continue

        github_connector = avatar_profile['connectors'].get('github')
        if not github_connector:
            logger.debug("GitHub connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        try:
            notifications = await github_connector.fetch_updates()
            if not notifications:
                logger.info("-> No new mention for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d unread mentions for %s.", len(notifications), avatar_profile['name'])
            for notif in notifications:
                thread_details = github_connector.get_thread_details(notif['subject']['url'])
                comment_body = await generator.generate_github_comment(avatar_profile, thread_details)
                
                comments_url = thread_details.get('comments_url')
                if comments_url:
                    await github_connector.send_message(comments_url, comment_body)
                    logger.info("-> %s commented on: %s", avatar_profile['name'], thread_details['title'])
                
                github_connector.mark_thread_as_read(notif['id'])

        except Exception as e:
            logger.error("Error during GitHub processing for %s: %s", avatar_id, e)

async def scheduled_telegram_check():
    """
    Funzione eseguita dallo scheduler per controllare i messaggi Telegram.
    """
    logger.info("--- Telegram check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile):
            logger.info("-> %s not active. Skipping.", avatar_profile['name'])
            continue

        telegram_connector = avatar_profile['connectors'].get('telegram')
        if not telegram_connector:
            logger.debug("Telegram connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        try:
            updates = await telegram_connector.fetch_updates()
            if not updates:
                logger.info("-> No new Telegram messages for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d unread Telegram messages for %s. Processing.", len(updates), avatar_profile['name'])
            for update_data in updates:
                # For now, we'll just reply to all messages
                reply_text = await generator.generate_telegram_reply(avatar_profile, update_data)
                await telegram_connector.send_message(update_data['chat_id'], reply_text)
                logger.info("-> %s replied to Telegram message from %s", avatar_profile['name'], update_data['username'])

        except Exception as e:
            logger.error("Error during Telegram processing for %s: %s", avatar_id, e)

async def scheduled_discord_check():
    """
    Funzione eseguita dallo scheduler per controllare i messaggi Discord.
    """
    logger.info("--- Discord check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile):
            logger.info("-> %s not active. Skipping.", avatar_profile['name'])
            continue

        discord_connector = avatar_profile['connectors'].get('discord')
        if not discord_connector:
            logger.debug("Discord connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        try:
            # Discord polling is highly inefficient and not fully implemented for scheduled checks.
            # Consider running discord.Client in a separate task for proper event handling.
            updates = await discord_connector.fetch_updates()
            if not updates:
                logger.info("-> No new Discord messages for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d unread Discord messages for %s. Processing.", len(updates), avatar_profile['name'])
            for update_data in updates:
                # For now, we'll just reply to all messages
                reply_text = await generator.generate_discord_reply(avatar_profile, update_data)
                await discord_connector.send_message(update_data['channel_id'], reply_text)
                logger.info("-> %s replied to Discord message in channel %s", avatar_profile['name'], update_data['channel_id'])

        except Exception as e:
            logger.error("Error during Discord processing for %s: %s", avatar_id, e)

@app.on_event("startup")
def startup_event():
    # database
    db.create_email_history_table()
    db.create_rag_tables() # This will log a warning if pg_vector is missing
    if db._db_connection_failed:
        logger.warning("Database connection failed. Database functionality will be disabled.")
    else:
        logger.info("Database tables created/verified successfully.")

    # Start internal event bus
    event_bus.start_processing()

    # avatar
    app.state.avatars = {}
    profiles_path = Path("profiles")
    for profile_file in profiles_path.glob("*.yaml"):
        if profile_file.name.startswith('.'): # Exclude dotfiles
            logger.info("Skipping hidden profile file: %s", profile_file.name)
            continue
        logger.debug("Attempting to load file: %s", profile_file.name)
        with open(profile_file, 'r') as f:
            avatar_profile = yaml.safe_load(f)
            avatar_id = profile_file.stem
            avatar_profile['connectors'] = {}
            
            # Initialize Email Connector
            email_conn = EmailConnector(avatar_id)
            try:
                email_conn.get_credentials()
                avatar_profile['connectors']['email'] = email_conn
            except ValueError:
                logger.warning("Email connector not configured for avatar %s", avatar_id)

            # Initialize GitHub Connector
            github_conn = GithubConnector(avatar_id)
            if github_conn.get_credentials(): # get_credentials returns False if token is missing
                avatar_profile['connectors']['github'] = github_conn
            else:
                logger.warning("GitHub connector not configured for avatar %s", avatar_id)

            # Initialize Telegram Connector
            telegram_conn = TelegramConnector(avatar_id)
            if telegram_conn.get_credentials(): # get_credentials returns False if token is missing
                avatar_profile['connectors']['telegram'] = telegram_conn
            else:
                logger.warning("Telegram connector not configured for avatar %s", avatar_id)

            # Initialize Discord Connector
            discord_conn = DiscordConnector(avatar_id)
            if discord_conn.get_credentials(): # get_credentials returns False if token is missing
                avatar_profile['connectors']['discord'] = discord_conn
            else:
                logger.warning("Discord connector not configured for avatar %s", avatar_id)

            app.state.avatars[avatar_id] = avatar_profile
            logger.info("Loaded avatar: %s", avatar_profile.get('name'))

            # Subscribe avatar to its own internal message queue
            async def _handle_avatar_internal_message(message: InternalMessage):
                logger.info("-> Avatar %s received internal message: %s", avatar_id, message.message_type)
                # Here, you would dispatch the message to the avatar's specific handler
                # For now, just log it. In a real scenario, avatar_profile would have a method
                # like avatar_profile.process_internal_message(message)

            event_bus.subscribe(f"to_{avatar_id}", _handle_avatar_internal_message)

    # scheduler
    scheduler_config = config.get('scheduler', {})
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_email_check, 'interval', 
                      minutes=scheduler_config.get('email_check_interval_minutes', 4),
                      jitter=scheduler_config.get('email_check_jitter_seconds', 120))
    scheduler.add_job(scheduled_github_check, 'interval', 
                      minutes=scheduler_config.get('github_check_interval_minutes', 8),
                      jitter=scheduler_config.get('github_check_jitter_seconds', 180))
    scheduler.add_job(scheduled_telegram_check, 'interval', 
                      minutes=scheduler_config.get('telegram_check_interval_minutes', 2),
                      jitter=scheduler_config.get('telegram_check_jitter_seconds', 60))
    scheduler.add_job(scheduled_discord_check, 'interval', 
                      minutes=scheduler_config.get('discord_check_interval_minutes', 5),
                      jitter=scheduler_config.get('discord_check_jitter_seconds', 90))
    scheduler.start()
    logger.info("Scheduler started.")

@app.on_event("shutdown")
async def shutdown_event():
    event_bus.stop_processing()
    logger.info("Internal event bus stopped.")


@app.get("/")
def root():
    """
    Root endpoint that returns a welcome message.
    """
    return {"message": "AI-Crew active."}


@app.get("/avatars")
def get_avatars():
    """
    Returns the loaded avatar profiles.
    """
    return app.state.avatars


@app.get("/avatars/{avatar_id}")
def get_avatar(avatar_id: str):
    """
    Returns the profile of a specific avatar.
    """
    return app.state.avatars.get(avatar_id, {"error": "Avatar not found"})


@app.put("/log_level")
async def set_log_level(level: str):
    """
    Sets the logging level for the application.
    Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        logger.error("Invalid log level: %s", level)
        return {"message": f"Invalid log level: {level}. Valid levels are DEBUG, INFO, WARNING, ERROR, CRITICAL."}
    
    logging.getLogger().setLevel(numeric_level)
    logger.info("Log level set to %s", level.upper())
    return {"message": f"Log level set to {level.upper()}"}

@app.post("/trigger_schedule")
async def trigger_schedule():
    """
    Triggers an immediate run of the email and GitHub checks.
    """
    logger.info("Manually triggering email, GitHub, Telegram and Discord checks.")
    await scheduled_email_check()
    await scheduled_github_check()
    await scheduled_telegram_check()
    await scheduled_discord_check()
    return {"message": "Email, GitHub, Telegram and Discord checks triggered successfully."}

