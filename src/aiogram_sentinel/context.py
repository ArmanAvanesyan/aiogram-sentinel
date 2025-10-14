"""Context extractors for aiogram events."""

from __future__ import annotations

from typing import Any

from aiogram.types import TelegramObject


def extract_user_id(event: TelegramObject, data: dict[str, Any]) -> int | None:
    """Extract user ID from event with fallbacks.

    Args:
        event: Telegram event object
        data: Middleware data dictionary

    Returns:
        User ID if found, None otherwise
    """
    # Try from_user attribute (most common)
    if hasattr(event, "from_user") and getattr(event, "from_user", None):
        return getattr(event.from_user, "id", None)

    # Try user attribute (some event types)
    if hasattr(event, "user") and getattr(event, "user", None):
        return getattr(event.user, "id", None)

    # Try chat attribute as fallback (for anonymous events)
    if hasattr(event, "chat") and getattr(event, "chat", None):
        chat_id = getattr(event.chat, "id", None)
        # Only return chat ID if it's a private chat (user ID == chat ID)
        # and it's positive (not a group/supergroup)
        if chat_id and chat_id > 0 and getattr(event.chat, "type", None) == "private":
            return chat_id

    return None


def extract_chat_id(event: TelegramObject, data: dict[str, Any]) -> int | None:
    """Extract chat ID from event.

    Args:
        event: Telegram event object
        data: Middleware data dictionary

    Returns:
        Chat ID if found, None otherwise
    """
    # Try chat attribute
    if hasattr(event, "chat") and getattr(event, "chat", None):
        return getattr(event.chat, "id", None)

    # Try message attribute (for some event types)
    if hasattr(event, "message") and getattr(event, "message", None):
        message = getattr(event, "message", None)
        if message and hasattr(message, "chat") and getattr(message, "chat", None):
            return getattr(message.chat, "id", None)

    return None


def extract_group_ids(
    event: TelegramObject, data: dict[str, Any]
) -> tuple[int | None, int | None]:
    """Extract both user and chat IDs for group scope.

    Args:
        event: Telegram event object
        data: Middleware data dictionary

    Returns:
        Tuple of (user_id, chat_id)
    """
    user_id = extract_user_id(event, data)
    chat_id = extract_chat_id(event, data)
    return user_id, chat_id


def extract_event_type(event: TelegramObject, data: dict[str, Any]) -> str:
    """Extract event type for classification.

    Args:
        event: Telegram event object
        data: Middleware data dictionary

    Returns:
        Event type string
    """
    # Get class name and convert to lowercase
    event_type = event.__class__.__name__.lower()

    # Map specific event types to more readable names
    type_mapping = {
        "message": "message",
        "callbackquery": "callback",
        "inlinequery": "inline",
        "choseninlineresult": "inline",
        "chatmemberupdated": "chat_member",
        "mycommand": "command",
        "chatjoinrequest": "join_request",
        "chatboostupdated": "boost",
        "chatboostremoved": "boost",
        "messageautodeletetimerchanged": "auto_delete",
        "forumtopiccreated": "forum_topic",
        "forumtopicclosed": "forum_topic",
        "forumtopicreopened": "forum_topic",
        "forumtopicedited": "forum_topic",
        "generalforumtopichidden": "forum_topic",
        "generalforumtopicunhidden": "forum_topic",
        "forumtopicpinned": "forum_topic",
        "forumtopicunpinned": "forum_topic",
        "writeaccessallowed": "write_access",
        "userprofilephotos": "profile_photos",
        "usershared": "user_shared",
        "chatshared": "chat_shared",
        "story": "story",
        "storydeleted": "story",
        "videonote": "video_note",
        "voice": "voice",
        "video": "video",
        "photo": "photo",
        "document": "document",
        "animation": "animation",
        "sticker": "sticker",
        "contact": "contact",
        "location": "location",
        "venue": "venue",
        "poll": "poll",
        "dice": "dice",
        "game": "game",
        "invoice": "invoice",
        "successfulpayment": "payment",
        "passportdata": "passport",
        "proximityalerttriggered": "proximity",
        "webappdata": "webapp",
        "videochatstarted": "video_chat",
        "videochatended": "video_chat",
        "videochatparticipantsinvited": "video_chat",
        "videochatscheduled": "video_chat",
        "webapp": "webapp",
        "giveawaycreated": "giveaway",
        "giveaway": "giveaway",
        "giveawaywinners": "giveaway",
        "giveawaycompleted": "giveaway",
        "businessconnection": "business",
        "businessmessagesdeleted": "business",
        "businessintro": "business",
        "businesslocation": "business",
        "businessopeninghours": "business",
        "businessawaymessage": "business",
        "businessgreetingmessage": "business",
        "businesschat": "business",
    }

    return type_mapping.get(event_type, event_type)


def extract_handler_bucket(
    event: TelegramObject, data: dict[str, Any]
) -> str | None:
    """Extract handler bucket from event and data.

    Args:
        event: Telegram event object
        data: Middleware data dictionary

    Returns:
        Handler bucket string if found, None otherwise
    """
    # Try to get handler name from data
    if "handler" in data:
        handler = data["handler"]
        if hasattr(handler, "__name__"):
            return handler.__name__

    # Try to get handler from event attributes
    if hasattr(event, "handler") and getattr(event, "handler", None):
        handler = getattr(event, "handler", None)
        if handler and hasattr(handler, "__name__"):
            return handler.__name__

    return None


def extract_callback_bucket(
    event: TelegramObject, data: dict[str, Any]
) -> str | None:
    """Extract callback bucket from callback query events.

    Args:
        event: Telegram event object
        data: Middleware data dictionary

    Returns:
        Callback bucket string if found, None otherwise
    """
    # Only process callback query events
    if not hasattr(event, "data"):
        return None

    callback_data = getattr(event, "data", None)
    if callback_data is None:
        return None

    # Convert to string if not already
    callback_data = str(callback_data)

    # Handle empty string case
    if not callback_data:
        return ""

    # Parse callback data to extract action
    # Common patterns: "action:param", "action_param", "action"
    if ":" in callback_data:
        return callback_data.split(":", 1)[0]
    elif "_" in callback_data and len(callback_data.split("_")) > 2:
        # Only split on underscore if there are multiple parts
        return callback_data.split("_", 1)[0]
    else:
        return callback_data
