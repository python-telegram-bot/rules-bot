import configparser
import logging
import os
import re
import urllib.parse
from collections import namedtuple
from uuid import uuid4

from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
from sphinx.ext.intersphinx import read_inventory_v2
from telegram import InlineQueryResultArticle
from telegram import InputTextMessageContent
from telegram import ParseMode
from telegram.ext import InlineQueryHandler
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

import util
from custemoji import Emoji

if os.environ.get('ROOLSBOT_DEBUG'):
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.DEBUG)
else:
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read('bot.ini')

updater = Updater(token=config['KEYS']['bot_api'])
dispatcher = updater.dispatcher

ENCLOSING_REPLACEMENT_CHARACTER = '$'
OFFTOPIC_CHAT_ID = '@pythontelegrambottalk'

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

docs_url = "https://python-telegram-bot.readthedocs.io/en/latest/"
docs_data = urllib.request.urlopen(docs_url + "objects.inv")
docs_data.readline()  # Need to remove first line for some reason
docs_inv = read_inventory_v2(docs_data, docs_url, urllib.parse.urljoin)

Doc = namedtuple('Doc', 'short_name, full_name, type url tg_name tg_url')

official_url = "https://core.telegram.org/bots/api#"
official_soup = BeautifulSoup(
    urllib.request.urlopen(official_url), "html.parser")
official = {}
for anchor in official_soup.select('a.anchor'):
    if '-' not in anchor['href']:
        official[anchor['href'][1:]] = anchor.next_sibling

wiki_url = "https://github.com/python-telegram-bot/python-telegram-bot/wiki"
wiki_soup = BeautifulSoup(urllib.request.urlopen(wiki_url), "html.parser")
wiki_pages = {}
for li in wiki_soup.select("ul.wiki-pages > li"):
    if li.a['href'] != '#':
        wiki_pages[li.strong.a.string] = "https://github.com" + li.strong.a['href']


def start(bot, update, args=None):
    if args:
        if args[0] == 'inline-help':
            inlinequery_help(bot, update)
    elif update.message.chat.username not in ("pythontelegrambotgroup", "pythontelegrambottalk"):
        update.message.reply_text("Hi. I'm a bot that will anounce the rules of the "
                                  "python-telegram-bot groups when you type /rules.")


def inlinequery_help(bot, update):
    chat_id = update.message.chat_id
    text = "Use the `{char}`-character in your inline queries and I will replace them with a link to the corresponding " \
           "article from the documentation or wiki.\n\n" \
           "*Example:*\n" \
           "@roolsbot I 💙 {char}InlineQueries{char}, but you need an {char}InlineQueryHandler{char} for it." \
           "\n\n*becomes:*\n" \
           "I 💙 [InlineQueries](https://python-telegram-bot.readthedocs.io/en/latest/telegram.html#telegram" \
           ".InlineQuery), but you need an [InlineQueryHandler](https://python-telegram-bot.readthedocs.io/en" \
           "/latest/telegram.ext.html#telegram.ext.InlineQueryHandler) for it.".format(
        char=ENCLOSING_REPLACEMENT_CHARACTER)
    bot.sendMessage(chat_id, text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


def rules(bot, update):
    """Load and send the appropiate rules based on which group we're in"""
    if update.message.chat.username == "pythontelegrambotgroup":
        update.message.reply_text(ONTOPIC_RULES, parse_mode=ParseMode.HTML,
                                  disable_web_page_preview=True)
    elif update.message.chat.username == "pythontelegrambottalk":
        update.message.reply_text(OFFTOPIC_RULES, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        update.message.reply_text('Hmm. You\'re not in a python-telegram-bot group, '
                                  'and I don\'t know the rules around here.')


def get_docs(search, threshold=80):
    search = list(reversed(search.split('.')))
    best = (0, None)

    for typ, items in docs_inv.items():
        if typ not in ['py:staticmethod', 'py:exception', 'py:method', 'py:module', 'py:class', 'py:attribute',
                       'py:data', 'py:function']:
            continue
        for name, item in items.items():
            name_bits = name.split('.')
            dot_split = zip(search, reversed(name_bits))
            score = 0
            for s, n in dot_split:
                score += fuzz.ratio(s, n)
            score += fuzz.ratio(search, name)

            # These values are basically random :/
            if typ == 'py:module':
                score *= 0.75
            if typ == 'py:class':
                score *= 1.10
            if typ == 'py:attribute':
                score *= 0.85

            if score > best[0]:
                tg_name = ''
                tg_test = ''

                if typ in ['py:class', 'py:method']:
                    tg_test = name_bits[-1].replace('_', '').lower()
                elif typ == 'py:attribute':
                    tg_test = name_bits[-2].replace('_', '').lower()

                if tg_test in official.keys():
                    tg_name = official[tg_test]

                tg_url = official_url + tg_test
                short_name = name_bits[1:]

                try:
                    if name_bits[1].lower() == name_bits[2].lower():
                        short_name = name_bits[2:]
                except IndexError:
                    pass
                best = (score, Doc('.'.join(short_name), name,
                                   typ[3:], item[2], tg_name, tg_url))
    if best[0] > threshold:
        return best[1]
    else:
        return None


def search_wiki(query):
    best = (0, ('HOME', wiki_url))
    if query != '':
        for name, link in wiki_pages.items():
            score = fuzz.partial_ratio(query, name)
            if score > best[0]:
                best = (score, (name, link))

        return best


def _get_reply_id(update):
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.message_id

    return None


def reply_or_edit(bot, update, chat_data, text):
    if update.edited_message:
        chat_data[update.edited_message.message_id].edit_text(text, parse_mode=ParseMode.MARKDOWN)
    else:
        issued_reply = _get_reply_id(update)
        if issued_reply:
            chat_data[update.message.message_id] = bot.sendMessage(update.message.chat_id, text,
                                                                   reply_to_message_id=issued_reply,
                                                                   parse_mode=ParseMode.MARKDOWN,
                                                                   disable_web_page_preview=True)
        else:
            chat_data[update.message.message_id] = update.message.reply_text(text,
                                                                             parse_mode=ParseMode.MARKDOWN,
                                                                             disable_web_page_preview=True)


def docs(bot, update, args, chat_data):
    """ Documentation search """
    if len(args) > 0:
        doc = get_docs(' '.join(args))
        if doc:
            text = "*{short_name}*\n_python-telegram-bot_ documentation for this {type}:\n[{full_name}]({url})"

            if doc.tg_name:
                text += "\n\nThe official documentation has more info about [{tg_name}]({tg_url})."

            text = text.format(**doc._asdict())
        else:
            text = "Sorry, your search term didn't match anything, please edit your message to search again."

        reply_or_edit(bot, update, chat_data, text)


def wiki(bot, update, args, chat_data, threshold=80):
    """ Wiki search """
    search = ' '.join(args)
    if search != '':
        best = search_wiki(search)

        if best[0] > threshold:
            text = 'Github wiki for _python-telegram-bot_\n[{b[0]}]({b[1]})'.format(b=best[1])
        else:
            text = "Sorry, your search term didn't match anything, please edit your message to search again."

        reply_or_edit(bot, update, chat_data, text)


def other_plaintext(bot, update):
    """Easter Eggs and utilities"""

    chat_username = update.message.chat.username

    if chat_username == "pythontelegrambotgroup":
        if any(ot in update.message.text.lower() for ot in ('off-topic', 'off topic', 'offtopic')):
            if update.message.reply_to_message and update.message.reply_to_message.text:
                issued_reply = _get_reply_id(update)

                update.message.reply_text("I moved this discussion to the "
                                          "[off-topic Group](https://telegram.me/pythontelegrambottalk).",
                                          disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN,
                                          reply_to_message_id=issued_reply)

                if update.message.reply_to_message.from_user.username:
                    name = '@' + update.message.reply_to_message.from_user.username
                else:
                    name = update.message.reply_to_message.from_user.first_name

                replied_message_text = update.message.reply_to_message.text

                text = '{} _wrote:_\n{}\n\n⬇️ ᴘʟᴇᴀsᴇ ᴄᴏɴᴛɪɴᴜᴇ ʜᴇʀᴇ ⬇️'.format(name, replied_message_text)

                bot.sendMessage(OFFTOPIC_CHAT_ID, text, disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)
            else:
                update.message.reply_text("The off-topic group is [here](https://telegram.me/pythontelegrambottalk)."
                                          " Come join us!",
                                          disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    elif chat_username == "pythontelegrambottalk":
        if any(ot in update.message.text.lower() for ot in ('on-topic', 'on topic', 'ontopic')):
            update.message.reply_text("The on-topic group is [here](https://telegram.me/pythontelegrambotgroup)."
                                      " Come join us!",
                                      disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

        # Easteregg
        if "sudo make me a sandwich" in update.message.text:
            update.message.reply_text("Okay.", quote=True)
        elif "make me a sandwich" in update.message.text:
            update.message.reply_text("What? Make it yourself.", quote=True)


def fuzzy_replacements_markdown(query, threshold=95):
    enclosed_regex = r'\{char}([a-zA-Z_.0-9]*)\{char}'.format(
        char=ENCLOSING_REPLACEMENT_CHARACTER)  # match names enclosed in {char}...{char}
    symbols = re.findall(enclosed_regex, query)

    if not symbols:
        return None, None

    replacements = list()
    for s in symbols:
        doc = get_docs(s, threshold=threshold)

        if doc:
            # replace only once in the query
            if doc.short_name in replacements:
                continue

            text = "[{}]({})"
            text = text.format(s, doc.url)

            replacements.append((True, doc.short_name, s, text))
            continue

        wiki = search_wiki(s)
        if wiki and wiki[0] > threshold:
            text = "[{}]({})".format(s, wiki[1][1])
            replacements.append((True, wiki[1][0], s, text))
            continue

        # not found
        replacements.append((False, '{}{}'.format(Emoji.BLACK_QUESTION_MARK_ORNAMENT, s), s, s))

    result = query
    for found, name, symbol, text in replacements:
        result = result.replace('{char}{symbol}{char}'.format(
            symbol=symbol,
            char=ENCLOSING_REPLACEMENT_CHARACTER
        ), text)

    result_changed = [x[1] for x in replacements]

    # # TODO sort the list by errors first
    # pprint(list(enumerate([x[1] for x in replacements])))
    # result_changed = sorted(enumerate([x[1] for x in replacements]), key=lambda k: k[1][0])

    return result_changed, result


def inlinequery(bot, update, threshold=60):
    query = update.inline_query.query
    results_list = list()

    modified, replaced = fuzzy_replacements_markdown(query, threshold=threshold)

    if len(query) > 0:

        if modified:
            results_list.append(InlineQueryResultArticle(
                id=uuid4(),
                title="Replace Links",
                description=', '.join(modified),
                input_message_content=InputTextMessageContent(
                    message_text=replaced,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True)
            ))

        wiki = search_wiki(query)
        doc = get_docs(query)

        # add the doc if found
        if doc:
            text = "*{short_name}*\n_python-telegram-bot_ documentation for this {type}:\n[{full_name}]({url})"
            if doc.tg_name:
                text += "\n\nThe official documentation has more info about [{tg_name}]({tg_url})."
            text = text.format(**doc._asdict())

            results_list.append(InlineQueryResultArticle(
                id=uuid4(),
                title="{full_name}".format(**doc._asdict()),
                description="python-telegram-bot documentation",
                input_message_content=InputTextMessageContent(
                    message_text=text,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True)
            ))

        # add the best wiki page if weight is over threshold
        if wiki and wiki[0] > threshold:
            results_list.append(InlineQueryResultArticle(
                id=uuid4(),
                title="{w[0]}".format(w=wiki[1]),
                description="Github wiki for python-telegram-bot",
                input_message_content=InputTextMessageContent(
                    message_text='Wiki of <i>python-telegram-bot</i>\n<a href="{}">{}</a>'.format(
                        wiki[1][1],
                        wiki[1][0]
                    ),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )))

        # "No results" entry
        if len(results_list) == 0:
            results_list.append(InlineQueryResultArticle(
                id=uuid4(),
                title=util.failure("No results."),
                description="",
                input_message_content=InputTextMessageContent(
                    message_text="[GitHub wiki]({}) of _python-telegram-bot_".format(wiki_url),
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True)
            ))

    else:  # no query input
        # add all wiki pages
        for name, link in wiki_pages.items():
            results_list.append(InlineQueryResultArticle(
                id=uuid4(),
                title=name,
                description="Wiki of python-telegram-bot",
                input_message_content=InputTextMessageContent(
                    message_text="Wiki of _python-telegram-bot_\n[{}]({})".format(util.escape_markdown(name), link),
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )))

    bot.answerInlineQuery(update.inline_query.id, results=results_list, switch_pm_text='Help',
                          switch_pm_parameter='inline-help')


def error(bot, update, error):
    """Log all errors"""
    logger.warn('Update "%s" caused error "%s"' % (update, error))


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
