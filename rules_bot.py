"""
Rules bot of python-telegram-bot chat
"""
import configparser
import logging
import os
import urllib.parse
from collections import namedtuple
from uuid import uuid4

from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
from sphinx.ext.intersphinx import read_inventory_v2
from telegram import InlineQueryResultArticle
from telegram import InputTextMessageContent
from telegram import ParseMode, TelegramError
from telegram.ext import InlineQueryHandler
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, Job
import requests

import util

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
JOBQ = updater.job_queue

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


def start(bot, update):
    if update.message.chat.username not in ("pythontelegrambotgroup", "pythontelegrambottalk"):
        update.message.reply_text("Hi. I'm a bot that will anounce the rules of the "
                                  "python-telegram-bot groups when you type /rules.")


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


def other(bot, update):
    """
    Easter Eggs, utilities and antispam
    """
    if update.message.chat.username == "pythontelegrambotgroup":
        if any(ot in update.message.text for ot in ('off-topic', 'off topic', 'offtopic')):
            update.message.reply_text("The off-topic group is [here](https://telegram.me/pythontelegrambottalk)."
                                      " Come join us!",
                                      disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    if update.message.chat.username == "pythontelegrambottalk":
        if any(ot in update.message.text for ot in ('on-topic', 'on topic', 'ontopic')):
            update.message.reply_text("The on-topic group is [here](https://telegram.me/pythontelegrambotgroup)."
                                      " Come join us!",
                                      disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)

    if update.message.chat.username == "pythontelegrambottalk":
        if "sudo make me a sandwich" in update.message.text:
            update.message.reply_text("Okay.", quote=True)
        elif "make me a sandwich" in update.message.text:
            update.message.reply_text("What? Make it yourself.", quote=True)
    if update.message.chat.username == "pythontelegrambotgroup" or update.message.chat.username == "pythontelegrambottalk":
        if update.message.forward_from_chat is not None:
            if update.message.forward_from_chat.title in SPAMCHANS:
                try:
                    update.message.reply_text("Spam detected⚠")
                    update.message.chat.kick_member(update.message.from_user.id)
                except TelegramError:
                    update.message.reply_text("I tried to ban this spammer, but it seems like " +
                                              "I am not an admin!")
                else:
                    update.message.reply_text("Banned!🔨")

def inlinequery(bot, update, threshold=60):
    query = update.inline_query.query
    results_list = list()

    wiki = search_wiki(query)
    doc = get_docs(query)

    if len(query) > 0:

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
            print('abc')
            print(util.escape_markdown(wiki[1][0]))
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

    bot.answerInlineQuery(update.inline_query.id, results=results_list)


def error(bot, update, error):
    """Log all errors"""
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def update_spam_list(*_):
    """
    Updates a spam list
    """
    global SPAMCHANS
    req = requests.get("https://raw.githubusercontent.com/OctoNezd/octonezd.github.io/master/telespam.json")
    SPAMCHANS = req.json()


start_handler = CommandHandler('start', start)
rules_handler = CommandHandler('rules', rules)
docs_handler = CommandHandler('docs', docs, pass_args=True, allow_edited=True, pass_chat_data=True)
wiki_handler = CommandHandler('wiki', wiki, pass_args=True, allow_edited=True, pass_chat_data=True)
other_handler = MessageHandler(Filters.text, other)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(rules_handler)
dispatcher.add_handler(docs_handler)
dispatcher.add_handler(wiki_handler)
dispatcher.add_handler(other_handler)

dispatcher.add_handler(InlineQueryHandler(inlinequery))
dispatcher.add_error_handler(error)
UPDJOB = Job(update_spam_list, 60.0)
JOBQ.put(UPDJOB, next_t=0.0)
updater.start_polling()
logger.info("Listening...")
updater.idle()
