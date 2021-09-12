import datetime as dtm
import html
import logging
import time
from queue import Queue
import random
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
)
from components.entrytypes import BaseEntry
from components.taghints import TAG_HINTS, TAG_HINTS_PATTERN
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
    cast(Message, update.message).reply_text(text)


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
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    message.reply_text(
        text,
        parse_mode="Markdown",
        quote=False,
        reply_to_message_id=reply_id,
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
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    message.reply_text(
        text,
        quote=False,
        reply_to_message_id=reply_id,
    )
    try_to_delete(message)


def off_on_topic(update: Update, context: CallbackContext) -> None:
    # Minimal effort LRU cache
    parsed_messages = cast(Dict, context.chat_data).setdefault(
        "redirect_messages", Queue(maxsize=64)
    )

    message = cast(Message, update.effective_message)
    if message.message_id in parsed_messages:
        return
    if parsed_messages.full():
        parsed_messages.get()
        parsed_messages.task_done()

    chat_username = cast(Chat, update.effective_chat).username
    group_one = cast(Match, context.match).group(1)
    if chat_username == ONTOPIC_USERNAME and group_one.lower() == "off":
        reply = message.reply_to_message
        moved_notification = "I moved this discussion to the [off-topic Group]({})."
        if reply and reply.text:
            issued_reply = get_reply_id(update)

            if reply.from_user:
                if reply.from_user.username:
                    name = "@" + reply.from_user.username
                else:
                    name = reply.from_user.first_name
            else:
                name = "Somebody"

            replied_message_text = reply.text_html
            replied_message_id = reply.message_id

            text = (
                f'{name} <a href="t.me/pythontelegrambotgroup/{replied_message_id}">wrote</a>:\n'
                f"{replied_message_text}\n\n"
                f"⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️"
            )

            offtopic_msg = context.bot.send_message(OFFTOPIC_CHAT_ID, text)

            message.reply_text(
                moved_notification.format(
                    "https://telegram.me/pythontelegrambottalk/" + str(offtopic_msg.message_id)
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=issued_reply,
            )

        else:
            message.reply_text(
                "The off-topic group is [here](https://telegram.me/pythontelegrambottalk). "
                "Come join us!",
                parse_mode=ParseMode.MARKDOWN,
            )

        parsed_messages.put(message.message_id)

    elif chat_username == OFFTOPIC_USERNAME and group_one.lower() == "on":
        message.reply_text(
            "The on-topic group is [here](https://telegram.me/pythontelegrambotgroup). "
            "Come join us!",
            parse_mode=ParseMode.MARKDOWN,
        )

        parsed_messages.put(message.message_id)


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


def github(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    last = 0.0
    thing_matches = []
    things: List[BaseEntry] = []

    for match in GITHUB_PATTERN.finditer(get_text_not_in_entities(message.text_html)):
        logging.debug(match.groupdict())
        owner, repo, number, sha, ptbcontrib = [
            match.groupdict()[x] for x in ("owner", "repo", "number", "sha", "ptbcontrib")
        ]
        if number or sha or ptbcontrib:
            thing_matches.append((owner, repo, number, sha, ptbcontrib))

    for thing_match in thing_matches:
        last = keep_typing(last, cast(Chat, update.effective_chat), ChatAction.TYPING)
        owner, repo, number, sha, ptbcontrib = thing_match
        if number:
            issue = github_issues.get_issue(int(number), owner, repo)
            if issue is not None:
                things.append(issue)
        elif sha:
            commit = github_issues.get_commit(sha, owner, repo)
            if commit is not None:
                things.append(commit)
        elif ptbcontrib:
            contrib = github_issues.ptbcontribs.get(ptbcontrib)
            if contrib:
                things.append(contrib)

    if things:
        reply_or_edit(
            update,
            context,
            "\n".join([thing.html_markup() for thing in things]),
        )


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
        f'Welcome {", ".join(users)}! If you haven\'t already, read the rules of this '
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


def tag_hint(update: Update, _: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    reply_to = message.reply_to_message

    messages = []
    keyboard = None
    for match in TAG_HINTS_PATTERN.finditer(cast(str, message.text)):
        hint = TAG_HINTS[match.group(2).lstrip("/")]
        messages.append(hint.html_markup())

        if entry_kb := hint.inline_keyboard:
            if keyboard is None:
                keyboard = entry_kb
            else:
                keyboard.inline_keyboard.extend(entry_kb.inline_keyboard)

    effective_text = "\n➖\n".join(messages)
    message.reply_text(
        effective_text,
        reply_markup=keyboard,
        reply_to_message_id=reply_to.message_id if reply_to else None,
    )

    if reply_to:
        try_to_delete(message)


def say_potato_job(context: CallbackContext) -> None:
    user_id, message, ban_person = cast(Tuple[int, Message, User], cast(Job, context.job).context)
    context.bot.ban_chat_member(chat_id=ONTOPIC_CHAT_ID, user_id=user_id)
    context.bot.ban_chat_member(chat_id=OFFTOPIC_CHAT_ID, user_id=user_id)

    text = (
        "You have been banned for userbot-like behavior. If you are not a userbot and wish to be"
        f"unbanned, please contact {ban_person.mention_html()}."
    )
    message.edit_text(text=text)


def say_potato_button(update: Update, context: CallbackContext) -> None:
    callback_query = cast(CallbackQuery, update.callback_query)
    _, user_id, correct = cast(str, callback_query.data).split()

    if callback_query.from_user.id != user_id:
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
    else:
        callback_query.answer(text="That was wrong. Ciao! 👋", show_alert=True)
        job.run(context.dispatcher)

    job.schedule_removal()


def say_potato_command(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    message.delete()

    if not message.reply_to_message:
        return

    user = cast(User, message.reply_to_message.from_user)
    time_limit = (int(context.args[0]) if context.args else None) or 60
    correct, incorrect_1, incorrect_2 = random.sample(VEGETABLES, 3)

    message_text = (
        f"You display behavior that is common for userbots, i.e. automated Telegram "
        f"accounts that usually produce spam. Please verify that you are not a userbot by "
        f"clicking the button that says {correct}. If you don't press the button within "
        f"{time_limit} minutes, you will be banned from the PTB groups. If you miss the "
        f"time limit but are not a userbot and want to get unbanned, please contact "
        f"{cast(User, message.from_user).mention_html()}."
    )

    answers = random.sample([(correct, True), (incorrect_1, False), (incorrect_2, False)], 3)
    keyboard = InlineKeyboardMarkup.from_row(
        [
            InlineKeyboardButton(text=veg, callback_data=f"POTATO {user.id} {truth}")
            for veg, truth in answers
        ]
    )

    message.reply_to_message.reply_text(message_text, reply_markup=keyboard)
