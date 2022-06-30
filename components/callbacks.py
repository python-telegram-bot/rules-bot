import datetime
import html
import logging
import random
import time
from collections import deque
from copy import deepcopy
from typing import Dict, List, Match, Optional, Tuple, cast

from telegram import (
    CallbackQuery,
    Chat,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageEntity,
    Update,
    User,
)
from telegram.constants import ChatAction, MessageLimit, ParseMode
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes, Job, JobQueue
from telegram.helpers import escape_markdown

from components import const
from components.const import (
    ENCLOSED_REGEX,
    ENCLOSING_REPLACEMENT_CHARACTER,
    GITHUB_PATTERN,
    OFFTOPIC_CHAT_ID,
    OFFTOPIC_RULES,
    OFFTOPIC_USERNAME,
    ONTOPIC_CHAT_ID,
    ONTOPIC_RULES,
    ONTOPIC_USERNAME,
    VEGETABLES,
)
from components.entrytypes import BaseEntry
from components.github import github_issues
from components.search import search
from components.taghints import TAG_HINTS
from components.util import (
    get_reply_id,
    get_text_not_in_entities,
    rate_limit,
    reply_or_edit,
    try_to_delete,
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = cast(Message, update.message)
    username = cast(Chat, update.effective_chat)
    args = context.args

    # For deep linking
    if args:
        if args[0] == "inline-help":
            await inlinequery_help(update, context)
        if args[0] == "inline-entity-parsing":
            await inlinequery_entity_parsing(update, context)
    elif username not in (OFFTOPIC_USERNAME, ONTOPIC_USERNAME):
        await message.reply_text(
            "Hi. I'm a bot that will announce the rules of the "
            "python-telegram-bot groups when you type /rules."
        )


async def inlinequery_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = cast(Message, update.message).chat_id
    char = ENCLOSING_REPLACEMENT_CHARACTER
    self_chat_id = f"@{context.bot.username}"
    text = (
        f"Use the `{char}`-character in your inline queries and I will replace "
        f"them with a link to the corresponding article from the documentation or wiki.\n\n"
        f"*Example:*\n"
        f"{escape_markdown(self_chat_id)} I 💙 {char}InlineQueries{char}, "
        f"but you need an {char}InlineQueryHandler{char} for it.\n\n"
        f"*becomes:*\n"
        f"I 💙 [InlineQueries]("
        f"{const.DOCS_URL}en/latest/telegram.html#telegram"
        f".InlineQuery), but you need an [InlineQueryHandler]({const.DOCS_URL}en"
        f"/latest/telegram.ext.html#telegram.ext.InlineQueryHandler) for it.\n\n"
        f"Some wiki pages have spaces in them. Please replace such spaces with underscores. "
        f"The bot will automatically change them back desired space."
    )
    await context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)


async def inlinequery_entity_parsing(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Your inline query produced invalid message entities. If you are trying to combine "
        "custom text with a tag hint or search result, please keep in mind that the text is "
        "is processed with <code>telegram.ParseMode.HTML</code> formatting. You will therefore "
        "have to either use valid HTML-formatted text or escape reserved characters. For a list "
        "of reserved characters, please see the official "
        f"<a href='{const.OFFICIAL_URL}#html-style'>Telegram docs</a>."
    )
    await cast(Message, update.effective_message).reply_text(text)


@rate_limit
async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Load and send the appropriate rules based on which group we're in"""
    message = cast(Message, update.effective_message)
    if message.chat.username == ONTOPIC_USERNAME:
        await message.reply_text(ONTOPIC_RULES, quote=False)
        context.application.create_task(try_to_delete(message), update=update)
    elif message.chat.username == OFFTOPIC_USERNAME:
        await message.reply_text(OFFTOPIC_RULES, quote=False)
        context.application.create_task(try_to_delete(message), update=update)
    else:
        await message.reply_text(
            "Hmm. You're not in a python-telegram-bot group, "
            "and I don't know the rules around here."
        )


@rate_limit
async def docs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Documentation link"""
    message = cast(Message, update.effective_message)
    text = f"You can find our documentation at [Read the Docs]({const.DOCS_URL})"
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    await message.reply_markdown(
        text,
        quote=False,
        reply_to_message_id=reply_id,
    )
    context.application.create_task(try_to_delete(message), update=update)


@rate_limit
async def wiki(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Wiki link"""
    message = cast(Message, update.effective_message)
    text = f"You can find our wiki on [GitHub]({const.WIKI_URL})"
    await message.reply_markdown(
        text,
        quote=False,
        reply_to_message_id=get_reply_id(update),
    )
    context.application.create_task(try_to_delete(message), update=update)


@rate_limit
async def help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Link to rules readme"""
    message = cast(Message, update.effective_message)
    text = (
        f"You can find an explanation of @{html.escape(context.bot.username)}'s functionality "
        'wiki on <a href="https://github.com/python-telegram-bot/rules-bot/blob/master/README.md">'
        "GitHub</a>."
    )
    await message.reply_html(
        text,
        quote=False,
        reply_to_message_id=get_reply_id(update),
    )
    context.application.create_task(try_to_delete(message), update=update)


async def off_on_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Minimal effort LRU cache
    # We store the newest 64 messages that lead to redirection to minimize the chance that
    # editing a message falsely triggers the redirect again
    parsed_messages = cast(Dict, context.chat_data).setdefault(
        "redirect_messages", deque(maxlen=64)
    )

    message = cast(Message, update.effective_message)
    if message.message_id in parsed_messages:
        return

    # Standalone on/off-topic commands don't make any sense
    # But we only delete them if they contain nothing but the command
    if not message.reply_to_message:
        entities = message.parse_entities()
        if len(entities) == 1:
            entity, text = entities.popitem()
            if entity.type == MessageEntity.BOT_COMMAND and text == message.text:
                context.application.create_task(try_to_delete(message), update=update)
        return

    chat_username = cast(Chat, update.effective_chat).username
    group_one = cast(Match, context.match).group(1)
    if chat_username == ONTOPIC_USERNAME and group_one.lower() == "off":
        reply = message.reply_to_message
        if reply.text:
            issued_reply = get_reply_id(update)

            if reply.from_user:
                if reply.from_user.username:
                    name = "@" + reply.from_user.username
                else:
                    name = reply.from_user.first_name
            else:
                # Probably never happens anyway ...
                name = "Somebody"

            replied_message_text = reply.text_html
            replied_message_id = reply.message_id

            text = (
                f'{name} <a href="t.me/{ONTOPIC_USERNAME}/{replied_message_id}">wrote</a>:\n'
                f"{replied_message_text}\n\n"
                f"⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️"
            )

            offtopic_msg = await context.bot.send_message(OFFTOPIC_CHAT_ID, text)

            await message.reply_text(
                text=(
                    'I moved this discussion to the <a href="https://t.me/'
                    f'{OFFTOPIC_USERNAME}/{offtopic_msg.message_id}">off-topic group</a>.'
                ),
                reply_to_message_id=issued_reply,
            )

        else:
            await message.reply_text(
                f'The off-topic group is <a href="https://t.me/{OFFTOPIC_USERNAME}">here</a>. '
                "Come join us!",
            )

    elif chat_username == OFFTOPIC_USERNAME and group_one.lower() == "on":
        await message.reply_text(
            f'The on-topic group is <a href="https://t.me/{ONTOPIC_USERNAME}">here</a>. '
            "Come join us!",
        )

    parsed_messages.append(message.message_id)


async def sandwich(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = cast(Message, update.effective_message)
    username = cast(Chat, update.effective_chat).username
    if username == OFFTOPIC_USERNAME:
        if "sudo" in cast(Match, context.match).group(0):
            await message.reply_text("Okay.", quote=True)
        else:
            await message.reply_text("What? Make it yourself.", quote=True)


def keep_typing(last: float, chat: Chat, action: str, application: Application) -> float:
    now = time.time()
    if (now - last) > 1:
        application.create_task(chat.send_action(action))
    return now


async def reply_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = cast(Message, update.effective_message)
    last = 0.0
    thing_matches: List[Tuple[int, Tuple[str, str, str, str, str]]] = []
    things: List[Tuple[int, BaseEntry]] = []

    no_entity_text = get_text_not_in_entities(message).strip()

    # Parse exact matches for GitHub threads & ptbcontrib things first
    for match in GITHUB_PATTERN.finditer(no_entity_text):
        logging.debug(match.groupdict())
        owner, repo, number, sha, ptbcontrib = (
            cast(str, match.groupdict()[x])
            for x in ("owner", "repo", "number", "sha", "ptbcontrib")
        )
        if number or sha or ptbcontrib:
            thing_matches.append((match.start(), (owner, repo, number, sha, ptbcontrib)))

    for thing_match in thing_matches:
        last = keep_typing(
            last,
            cast(Chat, update.effective_chat),
            ChatAction.TYPING,
            application=context.application,
        )
        owner, repo, number, sha, ptbcontrib = thing_match[1]
        if number:
            issue = github_issues.get_issue(int(number), owner, repo)
            if issue is not None:
                things.append((thing_match[0], issue))
        elif sha:
            commit = github_issues.get_commit(sha, owner, repo)
            if commit is not None:
                things.append((thing_match[0], commit))
        elif ptbcontrib:
            contrib = github_issues.ptb_contribs.get(ptbcontrib)
            if contrib:
                things.append((thing_match[0], contrib))

    # Parse fuzzy search next
    if no_entity_text.startswith("!search") or no_entity_text.endswith("!search"):
        for match in ENCLOSED_REGEX.finditer(no_entity_text):
            last = keep_typing(
                last,
                cast(Chat, update.effective_chat),
                ChatAction.TYPING,
                application=context.application,
            )
            things.append((match.start(), search.search(match.group(0), amount=1)[0]))

        # Sort the things - only necessary if we appended something here
        things.sort(key=lambda thing: thing[0])

    if things:
        await reply_or_edit(
            update, context, "\n".join(thing[1].html_reply_markup() for thing in things)
        )


async def delete_new_chat_members_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await cast(Message, update.effective_message).delete()


async def leave_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.create_task(cast(Chat, update.effective_chat).leave(), update=update)
    raise ApplicationHandlerStop


async def raise_app_handler_stop(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    raise ApplicationHandlerStop


async def list_available_hints(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    private = False
    if cast(Chat, update.effective_chat).type != Chat.PRIVATE:
        text = "Please use this command in private chat with me."
        reply_markup: Optional[InlineKeyboardMarkup] = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Take me there!", url=f"https://t.me/{const.SELF_BOT_NAME}")
        )
        private = True
    else:
        text = "You can use the following tags to guide new members:\n\n"
        text += "\n".join(
            f"🗣 {hint.display_name} ➖ {hint.description}" for hint in TAG_HINTS.values()
        )
        text += "\n\nMake sure to reply to another message, so I know who to refer to."
        reply_markup = None

    message = cast(Message, update.effective_message)
    await message.reply_text(
        text,
        reply_markup=reply_markup,
    )
    if private:
        await message.delete()


async def tag_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = cast(Message, update.effective_message)
    reply_to = message.reply_to_message
    first_match = cast(int, MessageLimit.TEXT_LENGTH)

    messages = []
    keyboard = None
    for match in cast(List[Match], context.matches):
        first_match = min(first_match, match.start(0))

        hint = TAG_HINTS[match.groupdict()["tag_hint"].lstrip("/")]
        messages.append(hint.html_markup(None or match.group(0)))

        # Merge keyboards into one
        if entry_kb := hint.inline_keyboard:
            if keyboard is None:
                keyboard = deepcopy(entry_kb)
            else:
                keyboard.inline_keyboard.extend(entry_kb.inline_keyboard)

    effective_text = "\n➖\n".join(messages)
    await message.reply_text(
        effective_text,
        reply_markup=keyboard,
        reply_to_message_id=reply_to.message_id if reply_to else None,
    )

    if reply_to and first_match == 0:
        await try_to_delete(message)


async def ban_sender_channels(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    message = cast(Message, update.effective_message)
    await cast(Chat, update.effective_chat).ban_sender_chat(cast(Chat, message.sender_chat).id)
    await try_to_delete(message)


async def say_potato_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, message, who_banned = cast(Tuple[int, Message, User], cast(Job, context.job).context)
    await context.bot.ban_chat_member(chat_id=ONTOPIC_CHAT_ID, user_id=user_id)
    await context.bot.ban_chat_member(chat_id=OFFTOPIC_CHAT_ID, user_id=user_id)

    text = (
        "You have been banned for userbot-like behavior. If you are not a userbot and wish to be "
        f"unbanned, please contact {who_banned.mention_html()}."
    )
    await message.edit_text(text=text)


async def say_potato_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    callback_query = cast(CallbackQuery, update.callback_query)
    _, user_id, correct = cast(str, callback_query.data).split()

    if str(callback_query.from_user.id) != user_id:
        await callback_query.answer(
            text="This button is obviously not meant for you. 😉", show_alert=True
        )
        return

    jobs = cast(JobQueue, context.job_queue).get_jobs_by_name(f"POTATO {user_id}")
    if not jobs:
        return
    job = jobs[0]

    if correct == "True":
        await callback_query.answer(
            text="Thanks for the verification! Have fun in the group 🙂", show_alert=True
        )
        await cast(Message, callback_query.message).delete()
    else:
        await callback_query.answer(text="That was wrong. Ciao! 👋", show_alert=True)
        await job.run(context.application)

    job.schedule_removal()


async def say_potato_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = cast(Message, update.effective_message)
    who_banned = cast(User, message.from_user)
    chat = cast(Chat, update.effective_chat)

    # This check will fail if we add or remove admins at runtime but that is so rare that
    # we can just restart the bot in that case ...
    admins = cast(Dict, context.chat_data).setdefault("admins", await chat.get_administrators())
    if who_banned not in [admin.user for admin in admins]:
        await message.reply_text(
            "This command is only available for admins. You are not an admin."
        )
        return

    await message.delete()

    if not message.reply_to_message:
        return

    user = cast(User, message.reply_to_message.from_user)

    if context.args:
        try:
            time_limit = int(context.args[0])
        except ValueError:
            time_limit = 60
    else:
        time_limit = 60

    correct, incorrect_1, incorrect_2 = random.sample(VEGETABLES, 3)

    message_text = (
        f"You display behavior that is common for userbots, i.e. automated Telegram "
        f"accounts that usually produce spam. Please verify that you are not a userbot by "
        f"clicking the button that says »<code>{correct}</code>«.\nIf you don't press the button "
        f"within {time_limit} minutes, you will be banned from the PTB groups. If you miss the "
        f"time limit but are not a userbot and want to get unbanned, please contact "
        f"{who_banned.mention_html()}."
    )

    answers = random.sample([(correct, True), (incorrect_1, False), (incorrect_2, False)], 3)
    keyboard = InlineKeyboardMarkup.from_row(
        [
            InlineKeyboardButton(text=veg, callback_data=f"POTATO {user.id} {truth}")
            for veg, truth in answers
        ]
    )

    potato_message = await message.reply_to_message.reply_text(message_text, reply_markup=keyboard)
    cast(JobQueue, context.job_queue).run_once(
        say_potato_job,
        time_limit * 60,
        data=(
            user.id,
            potato_message,
            message.from_user,
        ),
        name=f"POTATO {user.id}",
    )


async def join_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_request = cast(ChatJoinRequest, update.chat_join_request)
    on_topic = join_request.chat.username == ONTOPIC_USERNAME
    group_mention = ONTOPIC_CHAT_ID if on_topic else OFFTOPIC_CHAT_ID
    text = (
        f"Hi, {join_request.from_user.mention_html()}! I'm {context.bot.bot.mention_html()}, the "
        f"guardian of the group {group_mention}, that you requested to join.\n\nBefore you can "
        "join the group, please carefully read the below rules of the group. Confirm that you "
        "have read them by double-tapping the button at the bottom of the message - that's it 🙃"
        f"\n\n{ONTOPIC_RULES if on_topic else OFFTOPIC_RULES}"
    )
    reply_markup = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton(
            text="I have read the rules 📖",
            callback_data=f"JOIN 1 {join_request.from_user.id} {join_request.chat.id}",
        )
    )
    message = await join_request.from_user.send_message(text=text, reply_markup=reply_markup)
    cast(JobQueue, context.job_queue).run_once(
        callback=join_request_timeout_job,
        when=datetime.timedelta(hours=12),
        data=(join_request.from_user.id, join_request.chat.id, message, group_mention),
    )


async def join_request_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    callback_query = cast(CallbackQuery, update.callback_query)
    _, press, user, chat = cast(str, callback_query.data).split()
    if press == "2":
        await context.bot.approve_chat_join_request(chat_id=int(chat), user_id=int(user))
        context.application.create_task(
            callback_query.from_user.send_message("Nice! Have fun in the group 🙂"), update=update
        )
        reply_markup = None
    else:
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton(
                text="⚠️ Tap again to confirm",
                callback_data=f"JOIN 2 {user} {chat}",
            )
        )

    context.application.create_task(
        callback_query.edit_message_reply_markup(reply_markup=reply_markup), update=update
    )


async def join_request_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = cast(Job, context.job)
    user, chat, message, group = cast(Tuple[int, int, Message, str], job.data)
    text = (
        f"Your request to join the group {group} has timed out. Please send a new request to join."
    )
    await context.bot.decline_chat_join_request(chat_id=int(chat), user_id=int(user))
    context.application.create_task(message.edit_text(text=text))
