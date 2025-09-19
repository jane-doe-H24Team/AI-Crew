import yaml
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from avatar_manager.connectors.email_connector import EmailConnector
from avatar_manager.connectors.github_connector import GithubConnector
from avatar_manager.connectors.telegram_connector import TelegramConnector
from avatar_manager.connectors.discord_connector import DiscordConnector
from avatar_manager.connectors.reddit_connector import RedditConnector
from avatar_manager.connectors.slack_connector import SlackConnector
from avatar_manager.core import generator
from avatar_manager import db
from avatar_manager.internal_events import event_bus, InternalMessage
from avatar_manager.config import config
from avatar_manager.tools import tool_manager

import logging

# Configure logging
log_level = config.get('app', {}).get('log_level', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Reduce verbosity of third-party libraries
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Avatar Manager",
    description="An API to manage and orchestrate autonomous avatars.",
    version="0.1.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")

def is_avatar_active(avatar_profile: dict, activity_types: Optional[List[str]] = None) -> bool:
    """Controlla se l'avatar è attivo per un tipo specifico di attività."""
    schedule = avatar_profile.get("schedule")
    if not schedule:
        return True 

    now_utc = datetime.now(timezone.utc)
    current_day = now_utc.weekday() # Monday is 0 and Sunday is 6
    current_hour = now_utc.hour

    # If no specific activity types are requested, check all available schedules.
    if not activity_types:
        activity_types = schedule.keys()

    for activity_type in activity_types:
        if activity_type in schedule:
            details = schedule[activity_type]
            is_day = current_day in details.get("days", [])
            is_hour = details.get("start_hour", 0) <= current_hour < details.get("end_hour", 24)
            if is_day and is_hour:
                return True # Return true if any of the specified schedules are active
            
    return False

async def scheduled_email_check():
    """
    Funzione eseguita dallo scheduler per controllare le email di tutti gli avatar.
    """
    logger.info("--- Email check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile, activity_types=["work"]):
            logger.info("-> %s not in 'work' schedule. Skipping email check.", avatar_profile['name'])
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
                    await event_bus.publish(InternalMessage(
                        sender_avatar_id=avatar_id,
                        message_type="email_ignored",
                        payload={
                            "from": email_data['from'],
                            "subject": email_data['subject'],
                            "body_preview": email_data['body'][:200]
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
        if not is_avatar_active(avatar_profile, activity_types=["work"]):
            logger.info("-> %s not in 'work' schedule. Skipping GitHub check.", avatar_profile['name'])
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
        if not is_avatar_active(avatar_profile, activity_types=["social"]):
            logger.info("-> %s not in 'social' schedule. Skipping Telegram check.", avatar_profile['name'])
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
                reply_text = await generator.generate_telegram_reply(avatar_profile, update_data, avatar_id)
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
        if not is_avatar_active(avatar_profile, activity_types=["social"]):
            logger.info("-> %s not in 'social' schedule. Skipping Discord check.", avatar_profile['name'])
            continue

        discord_connector = avatar_profile['connectors'].get('discord')
        if not discord_connector:
            logger.debug("Discord connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        try:
            updates = await discord_connector.fetch_updates()
            if not updates:
                logger.info("-> No new Discord messages for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d unread Discord messages for %s. Processing.", len(updates), avatar_profile['name'])
            for update_data in updates:
                reply_text = await generator.generate_discord_reply(avatar_profile, update_data, avatar_id)
                await discord_connector.send_message(update_data['channel_id'], reply_text)
                logger.info("-> %s replied to Discord message in channel %s", avatar_profile['name'], update_data['channel_id'])

        except Exception as e:
            logger.error("Error during Discord processing for %s: %s", avatar_id, e)

async def scheduled_reddit_check():
    """
    Funzione eseguita dallo scheduler per controllare i messaggi Reddit.
    """
    logger.info("--- Reddit check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile, activity_types=["social"]):
            logger.info("-> %s not in 'social' schedule. Skipping Reddit check.", avatar_profile['name'])
            continue

        reddit_connector = avatar_profile['connectors'].get('reddit')
        if not reddit_connector:
            logger.debug("Reddit connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        try:
            updates = await reddit_connector.fetch_updates()
            if not updates:
                logger.info("-> No new Reddit messages for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d unread Reddit messages for %s. Processing.", len(updates), avatar_profile['name'])
            for update_data in updates:
                reply_text = await generator.generate_reddit_reply(avatar_profile, update_data, avatar_id)
                await reddit_connector.send_message(update_data['id'], None, reply_text)
                logger.info("-> %s replied to Reddit message from %s", avatar_profile['name'], update_data['author'])

        except Exception as e:
            logger.error("Error during Reddit processing for %s: %s", avatar_id, e)

async def scheduled_slack_check():
    """
    Funzione eseguita dallo scheduler per controllare i messaggi Slack.
    """
    logger.info("--- Slack check at %s ---", datetime.now())
    for avatar_id, avatar_profile in app.state.avatars.items():
        logger.debug("Checking avatar: %s", avatar_profile['name'])
        if not is_avatar_active(avatar_profile, activity_types=["social"]):
            logger.info("-> %s not in 'social' schedule. Skipping Slack check.", avatar_profile['name'])
            continue

        slack_connector = avatar_profile['connectors'].get('slack')
        if not slack_connector:
            logger.debug("Slack connector not configured for %s. Skipping.", avatar_profile['name'])
            continue

        try:
            updates = await slack_connector.fetch_updates()
            if not updates:
                logger.info("-> No new Slack messages for %s.", avatar_profile['name'])
                continue

            logger.info("-> Found %d unread Slack messages for %s. Processing.", len(updates), avatar_profile['name'])
            for update_data in updates:
                reply_text = await generator.generate_slack_reply(avatar_profile, update_data, avatar_id)
                await slack_connector.send_message(update_data['channel'], None, reply_text)
                logger.info("-> %s replied to Slack message in channel %s", avatar_profile['name'], update_data['channel'])

        except Exception as e:
            logger.error("Error during Slack processing for %s: %s", avatar_id, e)

@app.on_event("startup")
async def startup_event():
    # database
    db.create_email_history_table()
    db.create_rag_tables() # This will log a warning if pg_vector is missing
    db.create_chat_history_table()
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
        if profile_file.name.startswith('.'):
            logger.info("Skipping hidden profile file: %s", profile_file.name)
            continue
        logger.debug("Attempting to load file: %s", profile_file.name)
        with open(profile_file, 'r') as f:
            avatar_profile = yaml.safe_load(f)
            avatar_id = profile_file.stem
            avatar_profile['connectors'] = {}
            
            email_conn = EmailConnector(avatar_id)
            try:
                email_conn.get_credentials()
                avatar_profile['connectors']['email'] = email_conn
            except ValueError:
                logger.warning("Email connector not configured for avatar %s", avatar_id)

            github_conn = GithubConnector(avatar_id)
            if github_conn.get_credentials():
                avatar_profile['connectors']['github'] = github_conn
            else:
                logger.warning("GitHub connector not configured for avatar %s", avatar_id)

            telegram_conn = TelegramConnector(avatar_id)
            if await telegram_conn.get_credentials():
                avatar_profile['connectors']['telegram'] = telegram_conn
            else:
                logger.warning("Telegram connector not configured for avatar %s", avatar_id)

            discord_conn = DiscordConnector(avatar_id)
            if await discord_conn.get_credentials():
                avatar_profile['connectors']['discord'] = discord_conn
            else:
                logger.warning("Discord connector not configured for avatar %s", avatar_id)

            reddit_conn = RedditConnector(avatar_id)
            try:
                reddit_conn.get_credentials()
                avatar_profile['connectors']['reddit'] = reddit_conn
            except ValueError:
                logger.warning("Reddit connector not configured for avatar %s", avatar_id)

            slack_conn = SlackConnector(avatar_id)
            try:
                slack_conn.get_credentials()
                avatar_profile['connectors']['slack'] = slack_conn
            except ValueError:
                logger.warning("Slack connector not configured for avatar %s", avatar_id)

            app.state.avatars[avatar_id] = avatar_profile
            logger.info("Loaded avatar: %s", avatar_profile.get('name'))

            async def _handle_avatar_internal_message(message: InternalMessage):
                logger.info("-> Avatar %s received internal message: %s", avatar_id, message.message_type)

            event_bus.subscribe(f"to_{avatar_id}", _handle_avatar_internal_message)

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
    scheduler.add_job(scheduled_reddit_check, 'interval', 
                      minutes=scheduler_config.get('reddit_check_interval_minutes', 5),
                      jitter=scheduler_config.get('reddit_check_jitter_seconds', 90))
    scheduler.add_job(scheduled_slack_check, 'interval', 
                      minutes=scheduler_config.get('slack_check_interval_minutes', 5),
                      jitter=scheduler_config.get('slack_check_jitter_seconds', 90))
    scheduler.start()
    logger.info("Scheduler started.")

@app.on_event("shutdown")
async def shutdown_event():
    event_bus.stop_processing()
    logger.info("Internal event bus stopped.")


@app.get("/")
def root():
    return {"message": "AI-Crew active."}


@app.get("/avatars")
def get_avatars():
    return app.state.avatars


@app.get("/avatars/{avatar_id}")
def get_avatar(avatar_id: str):
    return app.state.avatars.get(avatar_id, {"error": "Avatar not found"})


@app.put("/log_level")
async def set_log_level(level: str):
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        logger.error("Invalid log level: %s", level)
        return {"message": f"Invalid log level: {level}. Valid levels are DEBUG, INFO, WARNING, ERROR, CRITICAL."}
    
    logging.getLogger().setLevel(numeric_level)
    logger.info("Log level set to %s", level.upper())
    return {"message": f"Log level set to {level.upper()}"}

@app.post("/trigger_schedule")
async def trigger_schedule():
    logger.info("Manually triggering all checks.")
    await scheduled_email_check()
    await scheduled_github_check()
    await scheduled_telegram_check()
    await scheduled_discord_check()
    await scheduled_reddit_check()
    await scheduled_slack_check()
    return {"message": "All checks triggered successfully."}