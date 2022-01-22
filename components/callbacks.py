import datetime as dtm
import html
import logging
import time
from collections import deque
import random
from copy import deepcopy
from typing import cast, Match, List, Dict, Any, Optional, Tuple

from telegram import (
    Update,
    ParseMode,
    ChatAction,
    Message,
    Chat,
    Bot,
    ChatMemberUpdated,
    ChatMember,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    User,
    CallbackQuery,
    MessageEntity,
    MAX_MESSAGE_LENGTH,
)
from telegram.ext import CallbackContext, JobQueue, Job
from telegram.utils.helpers import escape_markdown

from components import const
from components.const import (
    OFFTOPIC_USERNAME,
    ONTOPIC_USERNAME,
    ENCLOSING_REPLACEMENT_CHARACTER,
    ONTOPIC_RULES,
    OFFTOPIC_RULES,
    OFFTOPIC_CHAT_ID,
    GITHUB_PATTERN,
    ONTOPIC_RULES_MESSAGE_LINK,
    OFFTOPIC_RULES_MESSAGE_LINK,
    NEW_CHAT_MEMBERS_LIMIT_SPACING,
    VEGETABLES,
    ONTOPIC_CHAT_ID,
    ENCLOSED_REGEX,
)
from components.entrytypes import BaseEntry
from components.search import search
from components.taghints import TAG_HINTS
from components.util import (
    rate_limit,
    get_reply_id,
    get_text_not_in_entities,
    reply_or_edit,
    try_to_delete,
)
from components.github import github_issues


def start(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.message)
    username = cast(Chat, update.effective_chat)
    args = context.args

    # For deep linking
    if args:
        if args[0] == "inline-help":
            inlinequery_help(update, context)
        if args[0] == "inline-entity-parsing":
            inlinequery_entity_parsing(update, context)
    elif username not in (OFFTOPIC_USERNAME, ONTOPIC_USERNAME):
        message.reply_text(
            "Hi. I'm a bot that will announce the rules of the "
            "python-telegram-bot groups when you type /rules."
        )


def inlinequery_help(update: Update, context: CallbackContext) -> None:
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
        "https://python-telegram-bot.readthedocs.io/en/latest/telegram.html#telegram"
        f".InlineQuery), but you need an [InlineQueryHandler]("
        f"https://python-telegram-bot.readthedocs.io/en"
        f"/latest/telegram.ext.html#telegram.ext.InlineQueryHandler) for it.\n\n"
        f"Some wiki pages have spaces in them. Please replace such spaces with underscores. "
        f"The bot will automatically change them back desired space."
    )
    context.bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN)


def inlinequery_entity_parsing(update: Update, _: CallbackContext) -> None:
    text = (
        "Your inline query produced invalid message entities. If you are trying to combine "
        "custom text with a tag hint or search result, please keep in mind that the text is "
        "is processed with <code>telegram.ParseMode.HTML</code> formatting. You will therefore "
        "have to either use valid HTML-formatted text or escape reserved characters. For a list "
        "of reserved characters, please see the official "
        "<a href='https://core.telegram.org/bots/api#html-style'>Telegram docs</a>."
    )
    cast(Message, update.effective_message).reply_text(text)


@rate_limit
def rules(update: Update, _: CallbackContext) -> None:
    """Load and send the appropriate rules based on which group we're in"""
    message = cast(Message, update.effective_message)
    if message.chat.username == ONTOPIC_USERNAME:
        message.reply_text(ONTOPIC_RULES, quote=False)
        try_to_delete(message)
    elif message.chat.username == OFFTOPIC_USERNAME:
        message.reply_text(OFFTOPIC_RULES, quote=False)
        try_to_delete(message)
    else:
        message.reply_text(
            "Hmm. You're not in a python-telegram-bot group, "
            "and I don't know the rules around here."
        )


@rate_limit
def docs(update: Update, _: CallbackContext) -> None:
    """ Documentation link """
    message = cast(Message, update.effective_message)
    text = (
        "You can find our documentation at "
        "[Read the Docs](https://python-telegram-bot.readthedocs.io/en/stable/)"
    )
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    message.reply_text(
        text,
        parse_mode="Markdown",
        quote=False,
        reply_to_message_id=reply_id,
    )
    try_to_delete(message)


@rate_limit
def wiki(update: Update, _: CallbackContext) -> None:
    """ Wiki link """
    message = cast(Message, update.effective_message)
    text = (
        "You can find our wiki on "
        "[GitHub](https://github.com/python-telegram-bot/python-telegram-bot/wiki)"
    )
    message.reply_text(
        text,
        parse_mode="Markdown",
        quote=False,
        reply_to_message_id=get_reply_id(update),
    )
    try_to_delete(message)


@rate_limit
def help_callback(update: Update, context: CallbackContext) -> None:
    """ Link to rules readme """
    message = cast(Message, update.effective_message)
    text = (
        f"You can find an explanation of @{html.escape(context.bot.username)}'s functionality "
        'wiki on <a href="https://github.com/python-telegram-bot/rules-bot/blob/master/README.md">'
        "GitHub</a>."
    )
    message.reply_text(
        text,
        quote=False,
        reply_to_message_id=get_reply_id(update),
    )
    try_to_delete(message)


def off_on_topic(update: Update, context: CallbackContext) -> None:
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
                try_to_delete(message)
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

            offtopic_msg = context.bot.send_message(OFFTOPIC_CHAT_ID, text)

            message.reply_text(
                text=(
                    'I moved this discussion to the <a href="https://t.me/'
                    f'{OFFTOPIC_USERNAME}/{offtopic_msg.message_id}">off-topic group</a>.'
                ),
                reply_to_message_id=issued_reply,
            )

        else:
            message.reply_text(
                f'The off-topic group is <a href="https://t.me/{OFFTOPIC_USERNAME}">here</a>. '
                "Come join us!",
            )

    elif chat_username == OFFTOPIC_USERNAME and group_one.lower() == "on":
        message.reply_text(
            f'The on-topic group is <a href="https://t.me/{ONTOPIC_USERNAME}">here</a>. '
            "Come join us!",
        )

    parsed_messages.append(message.message_id)


def sandwich(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    username = cast(Chat, update.effective_chat).username
    if username == OFFTOPIC_USERNAME:
        if "sudo" in cast(Match, context.match).group(0):
            message.reply_text("Okay.", quote=True)
        else:
            message.reply_text("What? Make it yourself.", quote=True)


def keep_typing(last: float, chat: Chat, action: str) -> float:
    now = time.time()
    if (now - last) > 1:
        chat.send_action(action)
    return now


def reply_search(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    last = 0.0
    thing_matches: List[Tuple[int, Tuple[str, str, str, str, str]]] = []
    things: List[Tuple[int, BaseEntry]] = []

    no_entity_text = get_text_not_in_entities(message.text_html).strip()

    # Parse exact matches for GitHub threads & ptbcontrib things first
    for match in GITHUB_PATTERN.finditer(no_entity_text):
        logging.debug(match.groupdict())
        owner, repo, number, sha, ptbcontrib = [
            cast(str, match.groupdict()[x])
            for x in ("owner", "repo", "number", "sha", "ptbcontrib")
        ]
        if number or sha or ptbcontrib:
            thing_matches.append((match.start(), (owner, repo, number, sha, ptbcontrib)))

    for thing_match in thing_matches:
        last = keep_typing(last, cast(Chat, update.effective_chat), ChatAction.TYPING)
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
            contrib = github_issues.ptbcontribs.get(ptbcontrib)
            if contrib:
                things.append((thing_match[0], contrib))

    # Parse fuzzy search next
    if no_entity_text.startswith("!search") or no_entity_text.endswith("!search"):
        for match in ENCLOSED_REGEX.finditer(no_entity_text):
            last = keep_typing(last, cast(Chat, update.effective_chat), ChatAction.TYPING)
            things.append((match.start(), search.search(match.group(0), amount=1)[0]))

        # Sort the things - only necessary if we appended something here
        things.sort(key=lambda thing: thing[0])

    if things:
        reply_or_edit(update, context, "\n".join(thing[1].html_reply_markup() for thing in things))


def delete_new_chat_members_message(update: Update, _: CallbackContext) -> None:
    cast(Message, update.effective_message).delete()


def extract_status_change(
    chat_member_update: ChatMemberUpdated,
) -> Optional[Tuple[bool, bool]]:
    """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
    of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
    the status didn't change."""
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = (
        old_status
        in [
            ChatMember.MEMBER,
            ChatMember.CREATOR,
            ChatMember.ADMINISTRATOR,
        ]
        or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    )
    is_member = (
        new_status
        in [
            ChatMember.MEMBER,
            ChatMember.CREATOR,
            ChatMember.ADMINISTRATOR,
        ]
        or (new_status == ChatMember.RESTRICTED and new_is_member is True)
    )

    return was_member, is_member


def do_greeting(
    bot: Bot, chat_data: Dict[str, Any], group_user_name: str, users: List[str]
) -> None:
    link = (
        ONTOPIC_RULES_MESSAGE_LINK
        if group_user_name == ONTOPIC_USERNAME
        else OFFTOPIC_RULES_MESSAGE_LINK
    )
    text = (
        f"Welcome {', '.join(users)}! If you haven't already, read the rules of this "
        f'group and be sure to follow them. You can find them <a href="{link}">here 🔗</a>.'
    )

    # Clear users list
    users.clear()

    # save new timestamp
    chat_data["new_chat_members_timeout"] = dtm.datetime.now()

    # Send message
    bot.send_message(chat_id=f"@{group_user_name}", text=text)


def greet_new_chat_members(update: Update, context: CallbackContext) -> None:
    chat_member = cast(ChatMemberUpdated, update.chat_member)
    result = extract_status_change(chat_member)
    if result is None:
        return

    # Only greet members how newly joined the group
    was_member, is_member = result
    if not (was_member is False and is_member is True):
        return

    # Get groups name
    group_user_name = cast(str, cast(Chat, update.effective_chat).username)

    # Just a precaution in case the bot was added to a different group
    if group_user_name not in [ONTOPIC_USERNAME, OFFTOPIC_USERNAME]:
        return

    # Get saved users
    chat_data = cast(dict, context.chat_data)
    user_lists = chat_data.setdefault("new_chat_members", {})
    users = user_lists.setdefault(group_user_name, [])

    # save new user
    users.append(chat_member.new_chat_member.user.mention_html())

    # check rate limit
    last_message_date = chat_data.setdefault(
        "new_chat_members_timeout",
        dtm.datetime.now() - dtm.timedelta(minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING + 1),
    )
    next_possible_greeting_time = last_message_date + dtm.timedelta(
        minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING
    )
    if dtm.datetime.now() < next_possible_greeting_time:
        # We schedule a job to the next possible greeting time so that people are greeted
        # and presented with the rules as early as possible while not exceeding the rate limit
        logging.debug("Scheduling job to greet new members after greetings-cool down.")
        job_queue = cast(JobQueue, context.job_queue)
        jobs = job_queue.get_jobs_by_name("greetings_job")
        if not jobs:
            job_queue.run_once(
                callback=lambda _: do_greeting(
                    bot=context.bot,
                    chat_data=chat_data,
                    group_user_name=group_user_name,
                    users=users,
                ),
                when=(next_possible_greeting_time - dtm.datetime.now()).seconds,
                name="greetings_job",
            )
    else:
        do_greeting(
            bot=context.bot, chat_data=chat_data, group_user_name=group_user_name, users=users
        )


def list_available_hints(update: Update, _: CallbackContext) -> None:
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
    message.reply_text(
        text,
        reply_markup=reply_markup,
    )
    if private:
        message.delete()


def tag_hint(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    reply_to = message.reply_to_message
    first_match = MAX_MESSAGE_LENGTH

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
    message.reply_text(
        effective_text,
        reply_markup=keyboard,
        reply_to_message_id=reply_to.message_id if reply_to else None,
    )

    if reply_to and first_match == 0:
        try_to_delete(message)


def ban_sender_channels(update: Update, _: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    cast(Chat, update.effective_chat).ban_sender_chat(cast(Chat, message.sender_chat).id)
    try_to_delete(message)


def say_potato_job(context: CallbackContext) -> None:
    user_id, message, who_banned = cast(Tuple[int, Message, User], cast(Job, context.job).context)
    context.bot.ban_chat_member(chat_id=ONTOPIC_CHAT_ID, user_id=user_id)
    context.bot.ban_chat_member(chat_id=OFFTOPIC_CHAT_ID, user_id=user_id)

    text = (
        "You have been banned for userbot-like behavior. If you are not a userbot and wish to be "
        f"unbanned, please contact {who_banned.mention_html()}."
    )
    message.edit_text(text=text)


def say_potato_button(update: Update, context: CallbackContext) -> None:
    callback_query = cast(CallbackQuery, update.callback_query)
    _, user_id, correct = cast(str, callback_query.data).split()

    if str(callback_query.from_user.id) != user_id:
        callback_query.answer(
            text="This button is obviously not meant for you. 😉", show_alert=True
        )
        return

    jobs = cast(JobQueue, context.job_queue).get_jobs_by_name(f"POTATO {user_id}")
    if not jobs:
        return
    job = jobs[0]

    if correct == "True":
        callback_query.answer(
            text="Thanks for the verification! Have fun in the group 🙂", show_alert=True
        )
        cast(Message, callback_query.message).delete()
    else:
        callback_query.answer(text="That was wrong. Ciao! 👋", show_alert=True)
        job.run(context.dispatcher)

    job.schedule_removal()


def say_potato_command(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    who_banned = cast(User, message.from_user)
    chat = cast(Chat, update.effective_chat)

    # This check will fail if we add or remove admins at runtime but that is so rare that
    # we can just restart the bot in that case ...
    admins = cast(Dict, context.chat_data).setdefault("admins", chat.get_administrators())
    if who_banned not in [admin.user for admin in admins]:
        message.reply_text("This command is only available for admins. You are not an admin.")
        return

    message.delete()

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

    potato_message = message.reply_to_message.reply_text(message_text, reply_markup=keyboard)
    cast(JobQueue, context.job_queue).run_once(
        say_potato_job,
        time_limit * 60,
        context=(
            user.id,
            potato_message,
            message.from_user,
        ),
        name=f"POTATO {user.id}",
    )
