import datetime as dtm
import html
import logging
import time
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
)
from telegram.error import BadRequest
from telegram.ext import CallbackContext, JobQueue
from telegram.utils.helpers import escape_markdown

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
)
from components.util import (
    rate_limit,
    get_reply_id,
    get_text_not_in_entities,
    reply_or_edit,
)
from components.github import github_issues


def start(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.message)
    username = cast(Chat, update.effective_chat)
    args = context.args
    if args:
        if args[0] == 'inline-help':
            inlinequery_help(update, context)
        if args[0] == 'inline-entity-parsing':
            inlinequery_entity_parsing(update, context)
    elif username not in (OFFTOPIC_USERNAME, ONTOPIC_USERNAME):
        message.reply_text(
            "Hi. I'm a bot that will announce the rules of the "
            "python-telegram-bot groups when you type /rules."
        )


def inlinequery_help(update: Update, context: CallbackContext) -> None:
    chat_id = cast(Message, update.message).chat_id
    char = ENCLOSING_REPLACEMENT_CHARACTER
    self_chat_id = f'@{context.bot.username}'
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
        message.delete()
    elif message.chat.username == OFFTOPIC_USERNAME:
        message.reply_text(OFFTOPIC_RULES, quote=False)
        message.delete()
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
        parse_mode='Markdown',
        quote=False,
        reply_to_message_id=reply_id,
    )
    message.delete()


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
        parse_mode='Markdown',
        quote=False,
        reply_to_message_id=reply_id,
    )
    message.delete()


@rate_limit
def help_callback(update: Update, context: CallbackContext) -> None:
    """ Link to rules readme """
    message = cast(Message, update.effective_message)
    text = (
        f'You can find an explanation of @{html.escape(context.bot.username)}\'s functionality '
        'wiki on <a href="https://github.com/python-telegram-bot/rules-bot/blob/master/README.md">'
        'GitHub</a>.'
    )
    reply_id = message.reply_to_message.message_id if message.reply_to_message else None
    message.reply_text(
        text,
        quote=False,
        reply_to_message_id=reply_id,
    )
    message.delete()


def off_on_topic(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    chat_username = cast(Chat, update.effective_chat).username
    group_one = cast(Match, context.match).group(1)
    if chat_username == ONTOPIC_USERNAME and group_one.lower() == 'off':
        reply = message.reply_to_message
        moved_notification = 'I moved this discussion to the [off-topic Group]({}).'
        if reply and reply.text:
            issued_reply = get_reply_id(update)

            if reply.from_user:
                if reply.from_user.username:
                    name = '@' + reply.from_user.username
                else:
                    name = reply.from_user.first_name
            else:
                name = 'Somebody'

            replied_message_text = reply.text_html
            replied_message_id = reply.message_id

            text = (
                f'{name} <a href="t.me/pythontelegrambotgroup/{replied_message_id}">wrote</a>:\n'
                f'{replied_message_text}\n\n'
                f'⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️'
            )

            offtopic_msg = context.bot.send_message(OFFTOPIC_CHAT_ID, text)

            message.reply_text(
                moved_notification.format(
                    'https://telegram.me/pythontelegrambottalk/' + str(offtopic_msg.message_id)
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=issued_reply,
            )

        else:
            message.reply_text(
                'The off-topic group is [here](https://telegram.me/pythontelegrambottalk). '
                'Come join us!',
                parse_mode=ParseMode.MARKDOWN,
            )

    elif chat_username == OFFTOPIC_USERNAME and group_one.lower() == 'on':
        message.reply_text(
            'The on-topic group is [here](https://telegram.me/pythontelegrambotgroup). '
            'Come join us!',
            parse_mode=ParseMode.MARKDOWN,
        )


def sandwich(update: Update, context: CallbackContext) -> None:
    message = cast(Message, update.effective_message)
    username = cast(Chat, update.effective_chat).username
    if username == OFFTOPIC_USERNAME:
        if 'sudo' in cast(Match, context.match).group(0):
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
    things = {}

    for match in GITHUB_PATTERN.finditer(get_text_not_in_entities(message.text_html)):
        logging.debug(match.groupdict())
        owner, repo, number, sha, ptbcontrib = [
            match.groupdict()[x] for x in ('owner', 'repo', 'number', 'sha', 'ptbcontrib')
        ]
        if number or sha or ptbcontrib:
            thing_matches.append((owner, repo, number, sha, ptbcontrib))

    for thing_match in thing_matches:
        last = keep_typing(last, cast(Chat, update.effective_chat), ChatAction.TYPING)
        owner, repo, number, sha, ptbcontrib = thing_match
        if number:
            issue = github_issues.get_issue(int(number), owner, repo)
            if issue is not None:
                things[issue.url] = github_issues.pretty_format_issue(issue)
        elif sha:
            commit = github_issues.get_commit(sha, owner, repo)
            if commit is not None:
                things[commit.url] = github_issues.pretty_format_commit(commit)
        elif ptbcontrib:
            contrib = github_issues.ptbcontribs.get(ptbcontrib)
            if contrib:
                things[contrib.url] = f'ptbcontrib/{contrib.name}'

    if things:
        reply_or_edit(
            update,
            context,
            '\n'.join([f'<a href="{url}">{name}</a>' for url, name in things.items()]),
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
    chat_data['new_chat_members_timeout'] = dtm.datetime.now()

    # Send message
    bot.send_message(chat_id=f'@{group_user_name}', text=text)


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
    user_lists = chat_data.setdefault('new_chat_members', {})
    users = user_lists.setdefault(group_user_name, [])

    # save new user
    users.append(chat_member.new_chat_member.user.mention_html())

    # check rate limit
    last_message_date = chat_data.setdefault(
        'new_chat_members_timeout',
        dtm.datetime.now() - dtm.timedelta(minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING + 1),
    )
    next_possible_greeting_time = last_message_date + dtm.timedelta(
        minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING
    )
    if dtm.datetime.now() < next_possible_greeting_time:
        # We schedule a job to the next possible greeting time so that people are greeted
        # and presented with the rules as early as possible while not exceeding the rate limit
        logging.debug('Scheduling job to greet new members after greetings-cool down.')
        job_queue = cast(JobQueue, context.job_queue)
        jobs = job_queue.get_jobs_by_name('greetings_job')
        if not jobs:
            job_queue.run_once(
                callback=lambda _: do_greeting(
                    bot=context.bot,
                    chat_data=chat_data,
                    group_user_name=group_user_name,
                    users=users,
                ),
                when=(next_possible_greeting_time - dtm.datetime.now()).seconds,
                name='greetings_job',
            )
    else:
        do_greeting(
            bot=context.bot, chat_data=chat_data, group_user_name=group_user_name, users=users
        )


def leave_group(update: Update, _: CallbackContext) -> None:
    """Leaves a group chat. Make sure to not call this for our groups"""
    try:
        cast(Message, update.effective_message).reply_text(
            f'Sorry, I exclusively work for @{ONTOPIC_USERNAME} and @{OFFTOPIC_USERNAME}'
        )
    except BadRequest:
        pass

    cast(Chat, update.effective_chat).leave()
