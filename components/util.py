# pylint:disable=cyclic-import
# because we import truncate_str in entrytypes.Issue.short_description
import logging
import re
import sys
import warnings
from functools import wraps
from typing import Any, Callable, Coroutine, Dict, List, Optional, Pattern, Tuple, Union, cast

from bs4 import MarkupResemblesLocatorWarning
from telegram import Bot, Chat, InlineKeyboardButton, Message, Update, User
from telegram.error import BadRequest, Forbidden, InvalidToken
from telegram.ext import CallbackContext, ContextTypes, filters

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
            await chat_data[update.edited_message.message_id].edit_text(text)
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
        (hint.tag, hint.description) for hint in TAG_HINTS.values() if hint.group_command
    ]
    hint_commands = [
        (hint.tag, hint.description) for hint in TAG_HINTS.values() if not hint.group_command
    ]

    if private:
        return base_commands + hint_commands

    base_commands += [
        ("privacy", "Show the privacy policy of this bot"),
        ("rules", "Show the rules for this group."),
        ("buy", "Tell people to not do job offers."),
        ("token", "Warn people if they share a token."),
    ]

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


async def admin_check(chat_data: Dict, chat: Chat, who_banned: User) -> bool:
    # This check will fail if we add or remove admins at runtime but that is so rare that
    # we can just restart the bot in that case ...
    admins = chat_data.setdefault("admins", await chat.get_administrators())
    if who_banned not in [admin.user for admin in admins]:
        return False
    return True


async def get_bot_from_token(token: str) -> Optional[User]:
    bot = Bot(token)

    try:
        user = await bot.get_me()
        return user

    # raised when the token isn't valid
    except InvalidToken:
        return None


def update_shared_token_timestamp(message: Message, context: ContextTypes.DEFAULT_TYPE) -> str:
    chat_data = cast(Dict, context.chat_data)
    key = "shared_token_timestamp"

    last_time = chat_data.get(key)
    current_time = message.date
    chat_data[key] = current_time

    if last_time is None:
        return (
            "... Error... No time found....\n"
            "Oh my god. Where is the time. Has someone seen the time?"
        )

    time_diff = current_time - last_time
    # We do a day counter for now
    return f"{time_diff.days}"


class FindAllFilter(filters.MessageFilter):
    __slots__ = ("pattern",)

    def __init__(self, pattern: Union[str, Pattern]):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)
        self.pattern: Pattern = pattern
        super().__init__(data_filter=True)

    def filter(self, message: Message) -> Optional[Dict[str, List[str]]]:
        if message.text:
            matches = re.findall(self.pattern, message.text)
            if matches:
                return {"matches": matches}
        return {}
