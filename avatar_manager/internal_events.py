import asyncio
from collections import defaultdict
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class InternalMessage:
    def __init__(
        self, 
        sender_avatar_id: str, 
        message_type: str, 
        payload: Dict[str, Any], 
        recipient_avatar_id: Optional[str] = None
    ):
        self.sender_avatar_id = sender_avatar_id
        self.recipient_avatar_id = recipient_avatar_id
        self.message_type = message_type
        self.payload = payload

    def __repr__(self):
        return f"InternalMessage(sender={self.sender_avatar_id}, type={self.message_type}, recipient={self.recipient_avatar_id}, payload={self.payload})"

class InternalEventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)
        self._queue = asyncio.Queue()
        self._processing_task = None

    def subscribe(self, message_type: str, callback):
        self._subscribers[message_type].append(callback)
        logger.debug(f"Subscribed {callback.__name__} to message type '{message_type}'")

    def unsubscribe(self, message_type: str, callback):
        if callback in self._subscribers[message_type]:
            self._subscribers[message_type].remove(callback)
            logger.debug(f"Unsubscribed {callback.__name__} from message type '{message_type}'")

    async def publish(self, message: InternalMessage):
        await self._queue.put(message)
        logger.info(f"Published message of type '{message.message_type}' from '{message.sender_avatar_id}' (to {message.recipient_avatar_id if message.recipient_avatar_id else 'all'})")

    async def _process_single_message(self, message: InternalMessage):
        # Notify specific recipient if specified
        if message.recipient_avatar_id:
            recipient_key = f"to_{message.recipient_avatar_id}"
            if recipient_key in self._subscribers:
                for callback in self._subscribers[recipient_key]:
                    try:
                        await callback(message)
                    except Exception as e:
                        logger.error(f"Error in recipient-specific callback for {recipient_key}: {e}")
        
        # Notify general subscribers for message type
        if message.message_type in self._subscribers:
            for callback in self._subscribers[message.message_type]:
                try:
                    await callback(message)
                except Exception as e:
                    logger.error(f"Error in general callback for {message.message_type}: {e}")

    async def process_messages(self):
        logger.info("InternalEventBus: Starting message processing loop.")
        while True:
            message = await self._queue.get()
            logger.debug(f"InternalEventBus: Dequeued message {message}")
            await self._process_single_message(message)
            self._queue.task_done()

    def start_processing(self):
        if not self._processing_task:
            self._processing_task = asyncio.create_task(self.process_messages())
            logger.info("InternalEventBus: Processing task started.")

    def stop_processing(self):
        if self._processing_task:
            self._processing_task.cancel()
            self._processing_task = None
            logger.info("InternalEventBus: Processing task stopped.")

# Global instance
event_bus = InternalEventBus()
