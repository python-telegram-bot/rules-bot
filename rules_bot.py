import logging
import urllib.request
import urllib.parse
from collections import namedtuple

from fuzzywuzzy import fuzz
from sphinx.ext.intersphinx import read_inventory_v2
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.DEBUG)
logger = logging.getLogger(__name__)

#updater = Updater(token='123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11')
updater = Updater(token='256806399:AAH8Kko1Xqk-jjwPZxph89osLx3HCenVy70')
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
Doc = namedtuple('Doc', 'last_name, full_name, type url tg_name tg_url')
official = ['sendmessage', 'message', 'file']
official_url = "https://core.telegram.org/bots/api#"


def start(bot, update):
    if update.message.chat.username not in ("pythontelegrambotgroup", "pythontelegrambottalk"):
        bot.sendMessage(chat_id=update.message.chat_id,
                        text="Hi. I'm a bot that will anounce the rules of the python-telegram-bot groups when you type /rules.")


def rules(bot, update):
    """Load and send the appropiate rules based on which group we're in"""
    if update.message.chat.username == "pythontelegrambotgroup":
        bot.sendMessage(chat_id=update.message.chat_id, text=ONTOPIC_RULES, parse_mode="Markdown",
                        disable_web_page_preview=True)
    elif update.message.chat.username == "pythontelegrambottalk":
        bot.sendMessage(chat_id=update.message.chat_id, text=OFFTOPIC_RULES)
    else:
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='Hmm. You\'re not in a python-telegram-bot group, and I don\'t know the rules around here.')


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
            if typ == 'py:module':
                score *= 0.75
            if typ == 'py:class':
                score *= 1.25
            if score > best[0]:
                tg_name = ''
                tg_test = None
                if typ in ['py:class', 'py:method']:
                    tg_test = name_bits[-1].replace('_', '').lower()
                elif typ == 'py:attribute':
                    tg_test = name_bits[-2].replace('_', '').lower()
                if tg_test in official:
                    tg_name = tg_test
                    if typ in ['py:class', 'py:attribute']:
                        tg_name = tg_name.capitalize()
                tg_url = official_url + tg_name
                best = (score, Doc(name_bits[-1], name, typ[3:], item[2], tg_name, tg_url))
    return best[1]


def docs(bot, update, args):
    """Documentation search"""
    doc = get_docs(' '.join(args))
    if doc:
        text = "*Docs for the {type} {last_name}*\n[{full_name}]({url})"
        if doc.tg_name:
            text += "\n\nThe official documentation for [{tg_name}]({tg_url}) might also be helpful."
        text = text.format(**doc._asdict())
        bot.send_message(chat_id=update.message.chat_id,
                         text=text,
                         parse_mode='Markdown',
                         disable_web_page_preview=True)
    else:
        bot.send_message(chat_id=update.message.chat_id,
                         text="No documentation could be found.")


def other(bot, update):
    """Easter Eggs and utilities"""
    if update.message.chat.username == "pythontelegrambotgroup":
        if any(ot in update.message.text for ot in ('off-topic', 'off topic', 'offtopic')):
            bot.sendMessage(chat_id=update.message.chat_id,
                            text="The off-topic group is [here](https://telegram.me/pythontelegrambottalk). Come join us!",
                            disable_web_page_preview=True, parse_mode="Markdown")

    if update.message.chat.username == "pythontelegrambottalk":
        if any(ot in update.message.text for ot in ('on-topic', 'on topic', 'ontopic')):
            bot.sendMessage(chat_id=update.message.chat_id,
                            text="The on-topic group is [here](https://telegram.me/pythontelegrambotgroup). Come join us!",
                            disable_web_page_preview=True, parse_mode="Markdown")

    if update.message.chat.username == "pythontelegrambottalk":
        if "sudo make me a sandwich" in update.message.text:
            bot.sendMessage(chat_id=update.message.chat_id, text="Okay.", reply_to_message_id=update.message.message_id)
        elif "make me a sandwich" in update.message.text:
            bot.sendMessage(chat_id=update.message.chat_id, text="What? Make it yourself.",
                            reply_to_message_id=update.message.message_id)


def error(bot, update, error):
    """Log all errors"""
    logger.warn('Update "%s" caused error "%s"' % (update, error))


start_handler = CommandHandler('start', start)
rules_handler = CommandHandler('rules', rules)
docs_handler = CommandHandler('docs', docs, pass_args=True)
other_handler = MessageHandler([Filters.text], other)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(rules_handler)
dispatcher.add_handler(docs_handler)
dispatcher.add_handler(other_handler)
dispatcher.add_error_handler(error)

updater.start_polling()
updater.idle()
