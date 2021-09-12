import logging
from functools import wraps
from typing import (
    Optional,
    List,
    Callable,
    TypeVar,
    Dict,
    cast,
    Tuple,
)

from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, Message
from telegram.error import BadRequest, Unauthorized
from telegram.ext import CallbackContext

from .const import RATE_LIMIT_SPACING, ONTOPIC_CHAT_ID, OFFTOPIC_CHAT_ID
from .taghints import TAG_HINTS


def get_reply_id(update: Update) -> Optional[int]:
    if update.effective_message and update.effective_message.reply_to_message:
        return update.effective_message.reply_to_message.message_id
    return None


def reply_or_edit(update: Update, context: CallbackContext, text: str) -> None:
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
            chat_data[message.message_id] = context.bot.send_message(
                message.chat_id,
                text,
                reply_to_message_id=issued_reply,
            )
        else:
            chat_data[message.message_id] = message.reply_text(text)


def get_text_not_in_entities(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.find_all(text=True, recursive=False))


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


def rate_limit_tracker(_: Update, context: CallbackContext) -> None:
    data = cast(Dict, context.chat_data).setdefault("rate_limit", {})

    for key in data.keys():
        data[key] += 1


Func = TypeVar("Func", bound=Callable[[Update, CallbackContext], None])


def rate_limit(
    func: Callable[[Update, CallbackContext], None]
) -> Callable[[Update, CallbackContext], None]:
    """
    Rate limit command so that RATE_LIMIT_SPACING non-command messages are
    required between invocations. Private chats are not rate limited.
    """

    @wraps(func)
    def wrapper(update: Update, context: CallbackContext) -> None:
        if chat := update.effective_chat:
            if chat.type == chat.PRIVATE:
                return func(update, context)

        # Get rate limit data
        data = cast(Dict, context.chat_data).setdefault("rate_limit", {})

        # If we have not seen two non-command messages since last of type `f`
        if data.get(func, RATE_LIMIT_SPACING) < RATE_LIMIT_SPACING:
            logging.debug("Ignoring due to rate limit!")
            cast(Message, update.effective_message).delete()
            return None

        data[func] = 0
        return func(update, context)

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

    if not group_name:
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


def try_to_delete(message: Message) -> bool:
    try:
        return message.delete()
    except (BadRequest, Unauthorized):
        return False
