import configparser
import logging
import os
import re
from uuid import uuid4

from search import search, WIKI_URL
from telegram import InlineQueryResultArticle, InputTextMessageContent, ParseMode
from telegram.ext import InlineQueryHandler, Updater, CommandHandler, MessageHandler, Filters
from telegram.utils.helpers import escape_markdown
from util import reply_or_edit, get_reply_id

if os.environ.get('ROOLSBOT_DEBUG'):
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.DEBUG)
else:
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)

logger = logging.getLogger(__name__)

SELF_CHAT_ID = '@'  # For now, gets updated in main()
ENCLOSING_REPLACEMENT_CHARACTER = '+'
ENCLOSED_REGEX = rf'\{ENCLOSING_REPLACEMENT_CHARACTER}([a-zA-Z_.0-9]*)\{ENCLOSING_REPLACEMENT_CHARACTER}'
OFFTOPIC_USERNAME = 'pythontelegrambottalk'
ONTOPIC_USERNAME = 'pythontelegrambotgroup'
OFFTOPIC_CHAT_ID = '@' + OFFTOPIC_USERNAME
TELEGRAM_SUPERSCRIPT = 'ᵀᴱᴸᴱᴳᴿᴬᴹ'

ONTOPIC_RULES = """This group is for questions, answers and discussions around the <a href="https://python-telegram-bot.org/">python-telegram-bot library</a> and, to some extent, Telegram bots in general.

<b>Rules:</b>
- The group language is English
- Stay on topic
- No meta questions (eg. <i>"Can I ask something?"</i>)
- Use a pastebin when you have a question about your code, like <a href="https://www.codepile.net">this one</a>.
- Use <code>/wiki</code> and <code>/docs</code> in a private chat if possible.

Before asking, please take a look at our <a href="https://github.com/python-telegram-bot/python-telegram-bot/wiki">wiki</a> and <a href="https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples">example bots</a> or, depending on your question, the <a href="https://core.telegram.org/bots/api">official API docs</a> and <a href="http://pythonhosted.org/python-telegram-bot/py-modindex.html">python-telegram-bot docs</a>).
For off-topic discussions, please use our <a href="https://telegram.me/pythontelegrambottalk">off-topic group</a>."""

OFFTOPIC_RULES = """<b>Topics:</b>
- Discussions about Python in general
- Meta discussions about <code>python-telegram-bot</code>
- Friendly, respectful talking about non-tech topics

<b>Rules:</b>
- The group language is English
- Use a pastebin to share code
- No <a href="https://telegram.me/joinchat/A6kAm0EeUdd0SciQStb9cg">shitposting, flamewars or excessive trolling</a>
- Max. 1 meme per user per day"""


def start(bot, update, args=None):
    if args:
        if args[0] == 'inline-help':
            inlinequery_help(bot, update)
    elif update.message.chat.username not in (OFFTOPIC_USERNAME, ONTOPIC_USERNAME):
        update.message.reply_text("Hi. I'm a bot that will announce the rules of the "
                                  "python-telegram-bot groups when you type /rules.")


def inlinequery_help(bot, update):
    chat_id = update.message.chat_id
    char = ENCLOSING_REPLACEMENT_CHARACTER
    text = (f"Use the `{char}`-character in your inline queries and I will replace "
            f"them with a link to the corresponding article from the documentation or wiki.\n\n"
            f"*Example:*\n"
            f"{SELF_CHAT_ID} I 💙 {char}InlineQueries{char}, but you need an {char}InlineQueryHandler{char} for it.\n\n"
            f"*becomes:*\n"
            f"I 💙 [InlineQueries](https://python-telegram-bot.readthedocs.io/en/latest/telegram.html#telegram"
            f".InlineQuery), but you need an [InlineQueryHandler](https://python-telegram-bot.readthedocs.io/en"
            f"/latest/telegram.ext.html#telegram.ext.InlineQueryHandler) for it.\n\n"
            f"Some wiki pages have spaces in them. Please replace such spaces with underscores. "
            f"The bot will automatically change them back desired space.")
    bot.sendMessage(chat_id, text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


def rules(bot, update):
    """Load and send the appropiate rules based on which group we're in"""
    if update.message.chat.username == ONTOPIC_USERNAME:
        update.message.reply_text(ONTOPIC_RULES, parse_mode=ParseMode.HTML,
                                  disable_web_page_preview=True)
    elif update.message.chat.username == OFFTOPIC_USERNAME:
        update.message.reply_text(OFFTOPIC_RULES, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        update.message.reply_text("Hmm. You're not in a python-telegram-bot group, "
                                  "and I don't know the rules around here.")


def docs(bot, update, args, chat_data):
    """ Documentation search """
    if len(args) > 0:
        doc = search.docs(' '.join(args))
        if doc:
            text = (f'*{doc.short_name}*\n'
                    f'_python-telegram-bot_ documentation for this {doc.type}:\n'
                    f'[{doc.full_name}]({doc.url})')

            if doc.tg_name:
                text += f'\n\nThe official documentation has more info about [{doc.tg_name}]({doc.tg_url}).'
        else:
            text = "Sorry, your search term didn't match anything, please edit your message to search again."

        reply_or_edit(bot, update, chat_data, text)


def wiki(bot, update, args, chat_data, threshold=80):
    """ Wiki search """
    query = ' '.join(args)
    if search != '':
        best = search.wiki(query, amount=1, threshold=threshold)

        if best:
            text = (f'Github wiki for _python-telegram-bot_\n'
                    f'[{best[0][0]}]({best[0][1]})')
        else:
            text = "Sorry, your search term didn't match anything, please edit your message to search again."

        reply_or_edit(bot, update, chat_data, text)


def other_plaintext(bot, update):
    """Easter Eggs and utilities"""

    chat_username = update.message.chat.username

    if chat_username == ONTOPIC_USERNAME:
        if any(ot in update.message.text.lower() for ot in ('off-topic', 'off topic', 'offtopic')):
            if update.message.reply_to_message and update.message.reply_to_message.text:
                issued_reply = get_reply_id(update)

                update.message.reply_text('I moved this discussion to the '
                                          '[off-topic Group](https://telegram.me/pythontelegrambottalk).',
                                          disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN,
                                          reply_to_message_id=issued_reply)

                if update.message.reply_to_message.from_user.username:
                    name = '@' + update.message.reply_to_message.from_user.username
                else:
                    name = update.message.reply_to_message.from_user.first_name

                replied_message_text = update.message.reply_to_message.text

                text = (f'{name} _wrote:_\n'
                        f'{replied_message_text}\n\n'
                        f'⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️')

                bot.sendMessage(OFFTOPIC_CHAT_ID, text, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            else:
                update.message.reply_text('The off-topic group is [here](https://telegram.me/pythontelegrambottalk). '
                                          'Come join us!',
                                          disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    elif chat_username == OFFTOPIC_USERNAME:
        if any(ot in update.message.text.lower() for ot in ('on-topic', 'on topic', 'ontopic')):
            update.message.reply_text('The on-topic group is [here](https://telegram.me/pythontelegrambotgroup). '
                                      'Come join us!',
                                      disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

        # Easteregg
        if "sudo make me a sandwich" in update.message.text:
            update.message.reply_text("Okay.", quote=True)
        elif "make me a sandwich" in update.message.text:
            update.message.reply_text("What? Make it yourself.", quote=True)


def fuzzy_replacements_markdown(query, threshold=95, official_api_links=True):
    """ Replaces the enclosed characters in the query string with hyperlinks to the documentations """
    symbols = re.findall(ENCLOSED_REGEX, query)

    if not symbols:
        return None, None

    replacements = list()
    for s in symbols:
        # Wiki first, cause with docs you can always prepend telegram. for better precision
        wiki = search.wiki(s.replace('_', ' '), amount=1, threshold=threshold)
        if wiki:
            name = wiki[0][0].split('🡺')[-1].strip()
            text = f'[{name}]({wiki[0][1]})'
            replacements.append((wiki[0][0], s, text))
            continue

        doc = search.docs(s, threshold=threshold)
        if doc:
            text = f'[{doc.short_name}]({doc.url})'

            if doc.tg_url and official_api_links:
                text += f' [{TELEGRAM_SUPERSCRIPT}]({doc.tg_url})'

            replacements.append((doc.short_name, s, text))
            continue

        # not found
        replacements.append((s + '❓', s, escape_markdown(s)))

    result = query
    for name, symbol, text in replacements:
        char = ENCLOSING_REPLACEMENT_CHARACTER
        result = result.replace(f'{char}{symbol}{char}', text)

    result_changed = [x[0] for x in replacements]
    return result_changed, result


def article(title='', description='', message_text=''):
    return InlineQueryResultArticle(
        id=uuid4(),
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True)
    )


def inlinequery(bot, update, threshold=60):
    query = update.inline_query.query
    results_list = list()

    if len(query) > 0:
        modified, replaced = fuzzy_replacements_markdown(query, official_api_links=True)
        if modified:
            results_list.append(article(
                title="Replace links and show official Bot API documentation",
                description=', '.join(modified),
                message_text=replaced))

        modified, replaced = fuzzy_replacements_markdown(query, official_api_links=False)
        if modified:
            results_list.append(article(
                title="Replace links",
                description=', '.join(modified),
                message_text=replaced))

        wiki_pages = search.wiki(query, amount=4, threshold=threshold)
        doc = search.docs(query, threshold=threshold)

        if doc:
            text = f'*{doc.short_name}*\n' \
                   f'_python-telegram-bot_ documentation for this {doc.type}:\n' \
                   f'[{doc.full_name}]({doc.url})'
            if doc.tg_name:
                text += f'\n\nThe official documentation has more info about [{doc.tg_name}]({doc.tg_url}).'

            results_list.append(article(
                title=f'{doc.full_name}',
                description="python-telegram-bot documentation",
                message_text=text,
            ))

        if wiki_pages:
            for wiki_page in wiki_pages:
                results_list.append(article(
                    title=f'{wiki_pages[0]}',
                    description="Github wiki for python-telegram-bot",
                    message_text=f'Wiki of _python-telegram-bot_\n'
                                 f'[{wiki_pages[0]}]({wiki_pages[1]})'
                ))

        # "No results" entry
        if len(results_list) == 0:
            results_list.append(article(
                title='❌ No results.',
                description='',
                message_text=f'[GitHub wiki]({WIKI_URL}) of _python-telegram-bot_',
            ))

    else:  # no query input
        # add all wiki pages
        for name, link in search._wiki.items():
            results_list.append(article(
                title=name,
                description="Wiki of python-telegram-bot",
                message_text=f'Wiki of _python-telegram-bot_\n'
                             f'[{escape_markdown(name)}]({link})',
            ))

    bot.answerInlineQuery(update.inline_query.id, results=results_list, switch_pm_text='Help',
                          switch_pm_parameter='inline-help')


def error(bot, update, err):
    """Log all errors"""
    logger.warning(f'Update "{update}" caused error "{err}"')


def main():
    config = configparser.ConfigParser()
    config.read('bot.ini')

    updater = Updater(token=config['KEYS']['bot_api'])
    dispatcher = updater.dispatcher

    global SELF_CHAT_ID
    SELF_CHAT_ID = f'@{updater.bot.get_me().username}'

    start_handler = CommandHandler('start', start, pass_args=True)
    rules_handler = CommandHandler('rules', rules)
    docs_handler = CommandHandler('docs', docs, pass_args=True, allow_edited=True, pass_chat_data=True)
    wiki_handler = CommandHandler('wiki', wiki, pass_args=True, allow_edited=True, pass_chat_data=True)
    other_handler = MessageHandler(Filters.text, other_plaintext)

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(rules_handler)
    dispatcher.add_handler(docs_handler)
    dispatcher.add_handler(wiki_handler)
    dispatcher.add_handler(other_handler)

    dispatcher.add_handler(InlineQueryHandler(inlinequery))
    dispatcher.add_error_handler(error)

    updater.start_polling()
    logger.info("Listening...")
    updater.idle()


if __name__ == '__main__':
    main()
