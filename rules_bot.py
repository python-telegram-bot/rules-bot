import configparser
import html
import logging
import os
import time
import datetime as dtm

from telegram import ParseMode, MessageEntity, ChatAction, Update, Bot
from telegram.error import BadRequest, Unauthorized
from telegram.ext import CommandHandler, Updater, MessageHandler, Filters, CallbackContext
from telegram.utils.helpers import escape_markdown

import const
from components import inlinequeries, taghints
from const import (ENCLOSING_REPLACEMENT_CHARACTER, GITHUB_PATTERN, OFFTOPIC_CHAT_ID, OFFTOPIC_RULES,
                   OFFTOPIC_USERNAME, ONTOPIC_RULES, ONTOPIC_USERNAME, ONTOPIC_RULES_MESSAGE_LINK,
                   OFFTOPIC_RULES_MESSAGE_LINK, ONTOPIC_RULES_MESSAGE_ID,
                   OFFTOPIC_RULES_MESSAGE_ID)
from util import get_reply_id, reply_or_edit, get_text_not_in_entities, github_issues, rate_limit, rate_limit_tracker

if os.environ.get('ROOLSBOT_DEBUG'):
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.DEBUG)
else:
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)
    aps_logger = logging.getLogger('apscheduler')
    aps_logger.setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

self_chat_id = '@'  # Updated in main()

# Welcome new chat members at most ever X minutes
NEW_CHAT_MEMBERS_LIMIT_SPACING = 60


def start(update: Update, context: CallbackContext):
    args = context.args
    if args:
        if args[0] == 'inline-help':
            inlinequery_help(update, context)
    elif update.message.chat.username not in (OFFTOPIC_USERNAME, ONTOPIC_USERNAME):
        update.message.reply_text("Hi. I'm a bot that will announce the rules of the "
                                  "python-telegram-bot groups when you type /rules.")


def inlinequery_help(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    char = ENCLOSING_REPLACEMENT_CHARACTER
    text = (f"Use the `{char}`-character in your inline queries and I will replace "
            f"them with a link to the corresponding article from the documentation or wiki.\n\n"
            f"*Example:*\n"
            f"{escape_markdown(SELF_CHAT_ID)} I 💙 {char}InlineQueries{char}, "
            f"but you need an {char}InlineQueryHandler{char} for it.\n\n"
            f"*becomes:*\n"
            f"I 💙 [InlineQueries](https://python-telegram-bot.readthedocs.io/en/latest/telegram.html#telegram"
            f".InlineQuery), but you need an [InlineQueryHandler](https://python-telegram-bot.readthedocs.io/en"
            f"/latest/telegram.ext.html#telegram.ext.InlineQueryHandler) for it.\n\n"
            f"Some wiki pages have spaces in them. Please replace such spaces with underscores. "
            f"The bot will automatically change them back desired space.")
    context.bot.sendMessage(chat_id, text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


@rate_limit
def rules(update: Update, context: CallbackContext):
    """Load and send the appropriate rules based on which group we're in"""
    if update.message.chat.username == ONTOPIC_USERNAME:
        update.message.reply_text(ONTOPIC_RULES, parse_mode=ParseMode.HTML,
                                  disable_web_page_preview=True, quote=False)
        update.message.delete()
    elif update.message.chat.username == OFFTOPIC_USERNAME:
        update.message.reply_text(OFFTOPIC_RULES, parse_mode=ParseMode.HTML,
                                  disable_web_page_preview=True, quote=False)
        update.message.delete()
    else:
        update.message.reply_text("Hmm. You're not in a python-telegram-bot group, "
                                  "and I don't know the rules around here.")


@rate_limit
def docs(update: Update, context: CallbackContext):
    """ Documentation link """
    text = "You can find our documentation at [Read the Docs](https://python-telegram-bot.readthedocs.io/en/stable/)"
    if update.message.reply_to_message:
        reply_id = update.message.reply_to_message.message_id
    else:
        reply_id = None
    update.message.reply_text(text, parse_mode='Markdown', quote=False,
                              disable_web_page_preview=True, reply_to_message_id=reply_id)
    update.message.delete()


@rate_limit
def wiki(update: Update, context: CallbackContext):
    """ Wiki link """
    text = "You can find our wiki on [GitHub](https://github.com/python-telegram-bot/python-telegram-bot/wiki)"
    if update.message.reply_to_message:
        reply_id = update.message.reply_to_message.message_id
    else:
        reply_id = None
    update.message.reply_text(text, parse_mode='Markdown', quote=False,
                              disable_web_page_preview=True, reply_to_message_id=reply_id)
    update.message.delete()


@rate_limit
def help(update: Update, context: CallbackContext):
    """ Link to rules readme """
    text = f'You can find an explanation of @{html.escape(context.bot.username)}\'s functionality wiki on <a href="https://github.com/python-telegram-bot/rules-bot/blob/master/README.md">GitHub</a>.'
    if update.message.reply_to_message:
        reply_id = update.message.reply_to_message.message_id
    else:
        reply_id = None
    update.message.reply_text(text, parse_mode=ParseMode.HTML, quote=False,
                              disable_web_page_preview=True, reply_to_message_id=reply_id)
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

            text = (f'{name} <a href="t.me/pythontelegrambotgroup/{replied_message_id}">wrote</a>:\n'
                    f'{replied_message_text}\n\n'
                    f'⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️')

            offtopic_msg = context.bot.send_message(OFFTOPIC_CHAT_ID, text, disable_web_page_preview=True,
                                                    parse_mode=ParseMode.HTML)

            update.message.reply_text(
                moved_notification.format('https://telegram.me/pythontelegrambottalk/' +
                                          str(offtopic_msg.message_id)),
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN,
                reply_to_message_id=issued_reply
            )

        else:
            update.message.reply_text(
                'The off-topic group is [here](https://telegram.me/pythontelegrambottalk). '
                'Come join us!',
                disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    elif chat_username == OFFTOPIC_USERNAME and group_one.lower() == 'on':
        update.message.reply_text(
            'The on-topic group is [here](https://telegram.me/pythontelegrambotgroup). '
            'Come join us!',
            disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


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
    message = update.message or update.edited_message
    last = 0
    thing_matches = []
    things = {}

    # Due to bug in ptb we need to convert entities of type URL to TEXT_LINK for them to be converted to html
    for entity in message.entities:
        if entity.type == MessageEntity.URL:
            entity.type = MessageEntity.TEXT_LINK
            entity.url = message.parse_entity(entity)

    for match in GITHUB_PATTERN.finditer(get_text_not_in_entities(message.text_html)):
        logging.debug(match.groupdict())
        owner, repo, number, sha = [match.groupdict()[x] for x in ('owner', 'repo', 'number', 'sha')]
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
        reply_or_edit(update, context, '\n'.join([f'<a href="{url}">{name}</a>' for url, name in things.items()]))


def delete_new_chat_members_message(update: Update, context: CallbackContext):
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
        dtm.datetime.now() - dtm.timedelta(minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING + 1)
    )
    if dtm.datetime.now() < last_message_date + dtm.timedelta(minutes=NEW_CHAT_MEMBERS_LIMIT_SPACING):
        logging.debug('Waiting a bit longer before greeting new members.')
        return

    # save new timestamp
    context.chat_data['new_chat_members_timeout'] = dtm.datetime.now()


    link = ONTOPIC_RULES_MESSAGE_LINK if group_user_name == ONTOPIC_USERNAME else OFFTOPIC_RULES_MESSAGE_LINK
    text = (f'Welcome {", ".join(users)}! If you haven't already, read the rules of this '
            f'group and make sure to follow them. You can find them <a href="{link}">here 🔗</a>.')

    # Clear users list
    users.clear()

    # send message
    update.message.reply_text(text, disable_web_page_preview=True, quote=False,
                              parse_mode=ParseMode.HTML)


def error(update: Update, context: CallbackContext):
    """Log all errors"""
    logger.warning(f'Update "{update}" caused error "{context.error}"')


def update_rules_messages(bot: Bot):
    try:
        bot.edit_message_text(
            chat_id='@' + ONTOPIC_USERNAME,
            message_id=ONTOPIC_RULES_MESSAGE_ID,
            text=ONTOPIC_RULES,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except (BadRequest, Unauthorized) as exc:
        logger.warning(f'Updating on-topic rules failed: {exc}')
    try:
        bot.edit_message_text(
            chat_id='@' + OFFTOPIC_USERNAME,
            message_id=OFFTOPIC_RULES_MESSAGE_ID,
            text=OFFTOPIC_RULES,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except (BadRequest, Unauthorized) as exc:
        logger.warning(f'Updating off-topic rules failed: {exc}')



def main():
    config = configparser.ConfigParser()
    config.read('bot.ini')

    updater = Updater(token=config['KEYS']['bot_api'], use_context=True)
    dispatcher = updater.dispatcher
    update_rules_messages(updater.bot)

    global SELF_CHAT_ID
    SELF_CHAT_ID = f'@{updater.bot.get_me().username}'

    rate_limit_tracker_handler = MessageHandler(~Filters.command, rate_limit_tracker)

    start_handler = CommandHandler('start', start)
    rules_handler = CommandHandler('rules', rules)
    rules_handler_hashtag = MessageHandler(Filters.regex(r'.*#rules.*'), rules)
    docs_handler = CommandHandler('docs', docs)
    wiki_handler = CommandHandler('wiki', wiki)
    help_handler = CommandHandler('help', help)
    sandwich_handler = MessageHandler(Filters.regex(r'(?i)[\s\S]*?((sudo )?make me a sandwich)[\s\S]*?'),
                                      sandwich)
    off_on_topic_handler = MessageHandler(Filters.regex(r'(?i)[\s\S]*?\b(?<!["\\])(off|on)[- _]?topic\b'),
                                          off_on_topic)
    delete_new_chat_members_handler = MessageHandler(Filters.status_update.new_chat_members,
                                                     delete_new_chat_members_message)
    greet_new_chat_members_handler = MessageHandler(Filters.status_update.new_chat_members,
                                                    greet_new_chat_members)

    # We need several matches so Filters.regex is basically useless
    # therefore we catch everything and do regex ourselves
    # This should probably be in another dispatcher group
    # but I kept getting SystemErrors...
    github_handler = MessageHandler(Filters.text & ~Filters.command, github)

    dispatcher.add_handler(rate_limit_tracker_handler, group=-1)

    # Note: Order matters!
    taghints.register(dispatcher)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(rules_handler)
    dispatcher.add_handler(rules_handler_hashtag)
    dispatcher.add_handler(docs_handler)
    dispatcher.add_handler(wiki_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(sandwich_handler)
    dispatcher.add_handler(off_on_topic_handler)
    dispatcher.add_handler(github_handler)
    dispatcher.add_handler(greet_new_chat_members_handler)
    dispatcher.add_handler(delete_new_chat_members_handler, group=1)

    inlinequeries.register(dispatcher)
    dispatcher.add_error_handler(error)

    updater.start_polling()
    logger.info('Listening...')

    try:
        github_issues.set_auth(config['KEYS']['github_client_id'], config['KEYS']['github_client_secret'])
    except KeyError:
        logging.info('No github auth set. Rate-limit is 60 requests/hour without auth.')

    github_issues.init_issues(dispatcher.job_queue)

    # set commands
    updater.bot.set_my_commands([
        ('docs', 'Send the link to the docs. Use in PM.'),
        ('wiki', 'Send the link to the wiki. Use in PM.'),
        ('hints', 'List available tag hints. Use in PM.'),
        ('help', 'Send the link to this bots README. Use in PM.'),
    ])

    updater.idle()


if __name__ == '__main__':
    main()
