# pylint:disable=cyclic-import
# because we import truncate_str in entrytypes.Issue.short_description
import logging
import sys
import warnings
from functools import wraps
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union, cast

from bs4 import MarkupResemblesLocatorWarning
from telegram import InlineKeyboardButton, Message, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import CallbackContext, ContextTypes

from .const import OFFTOPIC_CHAT_ID, ONTOPIC_CHAT_ID, RATE_LIMIT_SPACING
from .taghints import TAG_HINTS

# Messages may contain links that we don't care about - so let's ignore the warnings
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning, module="bs4")


def get_reply_id(update: Update) -> Optional[int]:
    if update.effective_message and update.effective_message.reply_to_message:
        return update.effective_message.reply_to_message.message_id
    return None


async def reply_or_edit(update: Update, context: CallbackContext, text: str) -> None:
    chat_data = cast(Dict, context.chat_data)
    if update.edited_message and update.edited_message.message_id in chat_data:
        try:
            chat_data[update.edited_message.message_id].edit_text(text)
        except BadRequest as exc:
            if "not modified" not in str(exc):
                raise exc
    else:
        message = cast(Message, update.effective_message)
        issued_reply = get_reply_id(update)
        if issued_reply:
            chat_data[message.message_id] = await context.bot.send_message(
                message.chat_id,
                text,
                reply_to_message_id=issued_reply,
            )
        else:
            chat_data[message.message_id] = await message.reply_text(text)


def get_text_not_in_entities(message: Message) -> str:
    if message.text is None:
        raise ValueError("Message has no text!")

    if sys.maxunicode != 0xFFFF:
        text: Union[str, bytes] = message.text.encode("utf-16-le")
    else:
        text = message.text

    removed_chars = 0
    for entity in message.entities:
        start = entity.offset - removed_chars
        end = entity.offset + entity.length - removed_chars
        removed_chars += entity.length

        if sys.maxunicode != 0xFFFF:
            start = 2 * start
            end = 2 * end

        text = text[:start] + text[end:]  # type: ignore

    if isinstance(text, str):
        return text
    return text.decode("utf-16-le")


def build_menu(
    buttons: List[InlineKeyboardButton],
    n_cols: int,
    header_buttons: List[InlineKeyboardButton] = None,
    footer_buttons: List[InlineKeyboardButton] = None,
) -> List[List[InlineKeyboardButton]]:
    menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


async def try_to_delete(message: Message) -> bool:
    try:
        return await message.delete()
    except (BadRequest, Forbidden):
        return False


async def rate_limit_tracker(_: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = cast(Dict, context.chat_data).setdefault("rate_limit", {})

    for key in data.keys():
        data[key] += 1


def rate_limit(
    func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]]:
    """
    Rate limit command so that RATE_LIMIT_SPACING non-command messages are
    required between invocations. Private chats are not rate limited.
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if chat := update.effective_chat:
            if chat.type == chat.PRIVATE:
                return await func(update, context)

        # Get rate limit data
        data = cast(Dict, context.chat_data).setdefault("rate_limit", {})

        # If we have not seen two non-command messages since last of type `func`
        if data.get(func, RATE_LIMIT_SPACING) < RATE_LIMIT_SPACING:
            logging.debug("Ignoring due to rate limit!")
            context.application.create_task(
                try_to_delete(cast(Message, update.effective_message)), update=update
            )
            return None

        data[func] = 0
        return await func(update, context)

    return wrapper


def truncate_str(string: str, max_length: int) -> str:
    return (string[:max_length] + "…") if len(string) > max_length else string


def build_command_list(
    private: bool = False, group_name: str = None, admins: bool = False
) -> List[Tuple[str, str]]:

    base_commands = [
        ("docs", "Send the link to the docs."),
        ("wiki", "Send the link to the wiki."),
        ("help", "Send the link to this bots README."),
    ]
    hint_commands = [(hint.tag, hint.description) for hint in TAG_HINTS.values()]

    if private:
        return base_commands + hint_commands

    base_commands += [("rules", "Show the rules for this group.")]

    if group_name is None:
        return base_commands + hint_commands

    on_off_topic = [
        {
            ONTOPIC_CHAT_ID: ("off_topic", "Redirect to the off-topic group"),
            OFFTOPIC_CHAT_ID: ("on_topic", "Redirect to the on-topic group"),
        }[group_name],
    ]

    if not admins:
        return base_commands + on_off_topic + hint_commands

    say_potato = [("say_potato", "Send captcha to a potential userbot")]

    return base_commands + on_off_topic + say_potato + hint_commands
