import logging
import urllib.request
import urllib.parse
from collections import namedtuple

import configparser
from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
from sphinx.ext.intersphinx import read_inventory_v2
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read('bot.ini')

updater = Updater(token=config['KEYS']['bot_api'])
dispatcher = updater.dispatcher

ONTOPIC_RULES = """This group is for questions, answers and discussions around the [python-telegram-bot library](https://python-telegram-bot.org/) and, to some extent, Telegram bots in general.

*Rules:*
- The group language is English
- Stay on topic
- No meta questions (eg. _"Can I ask something?"_)
- Use a pastebin when you have a question about your code, like [this one](https://www.codepile.net)

Before asking, please take a look at our [wiki](https://github.com/python-telegram-bot/python-telegram-bot/wiki) and [example bots](https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples) or, depending on your question, the [official API docs](https://core.telegram.org/bots/api) and [python-telegram-bot docs](http://pythonhosted.org/python-telegram-bot/py-modindex.html).
For off-topic discussions, please use our [off-topic group](https://telegram.me/pythontelegrambottalk)"""

OFFTOPIC_RULES = """- No pornography
- No advertising
- No spam"""

docs_url = "https://pythonhosted.org/python-telegram-bot/"
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
        update.message.reply_text(ONTOPIC_RULES, parse_mode="Markdown",
                                  disable_web_page_preview=True)
    elif update.message.chat.username == "pythontelegrambottalk":
        update.message.reply_text(OFFTOPIC_RULES)
    else:
        update.message.reply_text('Hmm. You\'re not in a python-telegram-bot group, '
                                  'and I don\'t know the rules around here.')


def get_docs(search):
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
    return best[1]


def docs(bot, update, args):
    """Documentation search"""
    doc = get_docs(' '.join(args))

    if doc:
        text = "*{short_name}*\n_python-telegram-bot_ documentation for this {type}:\n[{full_name}]({url})"

        if doc.tg_name:
            text += "\n\nThe official documentation has more info about [{tg_name}]({tg_url})."

        text = text.format(**doc._asdict())
        update.message.reply_text(text,
                                  parse_mode='Markdown',
                                  disable_web_page_preview=True)


def wiki(bot, update, args):
    search = ' '.join(args)
    best = (0, ('HOME', wiki_url))
    if search != '':
        for name, link in wiki_pages.items():
            score = fuzz.partial_ratio(search, name)
            if score > best[0]:
                best = (score, (name, link))
    update.message.reply_text('Github wiki for _python-telegram-bot_\n[{b[0]}]({b[1]})'.format(b=best[1]),
                              disable_web_page_preview=True, parse_mode='Markdown')


def other(bot, update):
    """Easter Eggs and utilities"""
    if update.message.chat.username == "pythontelegrambotgroup":
        if any(ot in update.message.text for ot in ('off-topic', 'off topic', 'offtopic')):
            update.message.reply_text("The off-topic group is [here](https://telegram.me/pythontelegrambottalk)."
                                      "Come join us!",
                                      disable_web_page_preview=True, parse_mode="Markdown")

    if update.message.chat.username == "pythontelegrambottalk":
        if any(ot in update.message.text for ot in ('on-topic', 'on topic', 'ontopic')):
            update.message.reply_text("The on-topic group is [here](https://telegram.me/pythontelegrambotgroup)."
                                      "Come join us!",
                                      disable_web_page_preview=True, parse_mode="Markdown")

    if update.message.chat.username == "pythontelegrambottalk":
        if "sudo make me a sandwich" in update.message.text:
            update.message.reply_text("Okay.", quote=True)
        elif "make me a sandwich" in update.message.text:
            update.message.reply_text("What? Make it yourself.", quote=True)


def error(bot, update, error):
    """Log all errors"""
    logger.warn('Update "%s" caused error "%s"' % (update, error))


start_handler = CommandHandler('start', start)
rules_handler = CommandHandler('rules', rules)
docs_handler = CommandHandler('docs', docs, pass_args=True)
wiki_handler = CommandHandler('wiki', wiki, pass_args=True)
other_handler = MessageHandler([Filters.text], other)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(rules_handler)
dispatcher.add_handler(docs_handler)
dispatcher.add_handler(wiki_handler)
dispatcher.add_handler(other_handler)
dispatcher.add_error_handler(error)

updater.start_polling()
updater.idle()
