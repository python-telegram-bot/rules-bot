import datetime as dtm
import html
import logging
import time

from telegram import Update, ParseMode, MessageEntity, ChatAction
from telegram.ext import CallbackContext
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
    github_issues,
    reply_or_edit,
)


def start(update: Update, context: CallbackContext):
    args = context.args
    if args:
        if args[0] == 'inline-help':
            inlinequery_help(update, context)
    elif update.message.chat.username not in (OFFTOPIC_USERNAME, ONTOPIC_USERNAME):
        update.message.reply_text(
            "Hi. I'm a bot that will announce the rules of the "
            "python-telegram-bot groups when you type /rules."
        )


def inlinequery_help(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
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
    context.bot.sendMessage(
        chat_id, text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True
    )


@rate_limit
def rules(update: Update, _: CallbackContext):
    """Load and send the appropriate rules based on which group we're in"""
    if update.message.chat.username == ONTOPIC_USERNAME:
        update.message.reply_text(ONTOPIC_RULES, disable_web_page_preview=True, quote=False)
        update.message.delete()
    elif update.message.chat.username == OFFTOPIC_USERNAME:
        update.message.reply_text(OFFTOPIC_RULES, disable_web_page_preview=True, quote=False)
        update.message.delete()
    else:
        update.message.reply_text(
            "Hmm. You're not in a python-telegram-bot group, "
            "and I don't know the rules around here."
        )


@rate_limit
def docs(update: Update, _: CallbackContext):
    """ Documentation link """
    text = (
        "You can find our documentation at "
        "[Read the Docs](https://python-telegram-bot.readthedocs.io/en/stable/)"
    )
    if update.message.reply_to_message:
        reply_id = update.message.reply_to_message.message_id
    else:
        reply_id = None
    update.message.reply_text(
        text,
        parse_mode='Markdown',
        quote=False,
        disable_web_page_preview=True,
        reply_to_message_id=reply_id,
    )
    update.message.delete()


@rate_limit
def wiki(update: Update, _: CallbackContext):
    """ Wiki link """
    text = (
        "You can find our wiki on "
        "[GitHub](https://github.com/python-telegram-bot/python-telegram-bot/wiki)"
    )
    if update.message.reply_to_message:
        reply_id = update.message.reply_to_message.message_id
    else:
        reply_id = None
    update.message.reply_text(
        text,
        parse_mode='Markdown',
        quote=False,
        disable_web_page_preview=True,
        reply_to_message_id=reply_id,
    )
    update.message.delete()


@rate_limit
def help_callback(update: Update, context: CallbackContext):
    """ Link to rules readme """
    text = (
        f'You can find an explanation of @{html.escape(context.bot.username)}\'s functionality '
        'wiki on <a href="https://github.com/python-telegram-bot/rules-bot/blob/master/README.md">'
        'GitHub</a>.'
    )
    if update.message.reply_to_message:
        reply_id = update.message.reply_to_message.message_id
    else:
        reply_id = None
    update.message.reply_text(
        text,
        quote=False,
        disable_web_page_preview=True,
        reply_to_message_id=reply_id,
    )
    update.message.delete()


def off_on_topic(update: Update, context: CallbackContext):
    chat_username = update.message.chat.username
    group_one = context.match.group(1)
    if chat_username == ONTOPIC_USERNAME and group_one.lower() == 'off':
        reply = update.message.reply_to_message
        moved_notification = 'I moved this discussion to the [off-topic Group]({}).'
        if reply and reply.text:
            issued_reply = get_reply_id(update)

            if reply.from_user.username:
                name = '@' + reply.from_user.username
            else:
                name = reply.from_user.first_name

            replied_message_text = reply.text_html
            replied_message_id = reply.message_id

            text = (
                f'{name} <a href="t.me/pythontelegrambotgroup/{replied_message_id}">wrote</a>:\n'
                f'{replied_message_text}\n\n'
                f'⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️'
            )

            offtopic_msg = context.bot.send_message(
                OFFTOPIC_CHAT_ID, text, disable_web_page_preview=True
            )

            update.message.reply_text(
                moved_notification.format(
                    'https://telegram.me/pythontelegrambottalk/' + str(offtopic_msg.message_id)
                ),
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=issued_reply,
            )

        else:
            update.message.reply_text(
                'The off-topic group is [here](https://telegram.me/pythontelegrambottalk). '
                'Come join us!',
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN,
            )

    elif chat_username == OFFTOPIC_USERNAME and group_one.lower() == 'on':
        update.message.reply_text(
            'The on-topic group is [here](https://telegram.me/pythontelegrambotgroup). '
            'Come join us!',
            disable_web_page_preview=True,
            parse_mode=ParseMode.MARKDOWN,
        )


def sandwich(update: Update, context: CallbackContext):
    if update.message.chat.username == OFFTOPIC_USERNAME:
        if 'sudo' in context.match.group(0):
            update.message.reply_text("Okay.", quote=True)
        else:
            update.message.reply_text("What? Make it yourself.", quote=True)


def keep_typing(last, chat, action):
    now = time.time()
    if (now - last) > 1:
        chat.send_action(action)
    return now


def github(update: Update, context: CallbackContext):
    message = update.effective_message
    last = 0
    thing_matches = []
    things = {}

    # Due to bug in ptb we need to convert entities of type URL to TEXT_LINK
    # for them to be converted to html
    for entity in message.entities:
        if entity.type == MessageEntity.URL:
            entity.type = MessageEntity.TEXT_LINK
            entity.url = message.parse_entity(entity)

    for match in GITHUB_PATTERN.finditer(get_text_not_in_entities(message.text_html)):
        logging.debug(match.groupdict())
        owner, repo, number, sha = [
            match.groupdict()[x] for x in ('owner', 'repo', 'number', 'sha')
        ]
        if number or sha:
            thing_matches.append((owner, repo, number, sha))

    for thing_match in thing_matches:
        last = keep_typing(last, update.effective_chat, ChatAction.TYPING)
        owner, repo, number, sha = thing_match
        if number:
            issue = github_issues.get_issue(int(number), owner, repo)
            things[issue.url] = github_issues.pretty_format_issue(issue)
        elif sha:
            commit = github_issues.get_commit(sha, owner, repo)
            things[commit.url] = github_issues.pretty_format_commit(commit)

    if things:
        reply_or_edit(
            update,
            context,
            '\n'.join([f'<a href="{url}">{name}</a>' for url, name in things.items()]),
        )


def delete_new_chat_members_message(update: Update, _: CallbackContext):
    update.message.delete()


def greet_new_chat_members(update: Update, context: CallbackContext):
    group_user_name = update.effective_chat.username
    # Get saved users
    user_lists = context.chat_data.setdefault('new_chat_members', {})
    users = user_lists.setdefault(group_user_name, [])

    # save new users
    new_chat_members = update.message.new_chat_members
    for user in new_chat_members:
        users.append(user.mention_html())

    # check rate limit
    last_message_date = context.chat_data.setdefault(
        'new_chat_members_timeout',
        dtm.datetime.now() - dtm.timedelta(minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING + 1),
    )
    if dtm.datetime.now() < last_message_date + dtm.timedelta(
        minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING
    ):
        logging.debug('Waiting a bit longer before greeting new members.')
        return

    # save new timestamp
    context.chat_data['new_chat_members_timeout'] = dtm.datetime.now()

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

    # send message
    update.message.reply_text(text, disable_web_page_preview=True, quote=False)
