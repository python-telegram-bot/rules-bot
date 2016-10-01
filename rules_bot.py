import logging
from telegram import ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

updater = Updater(token='123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11')
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


def docs(bot, update, args):
    """Documentation search"""
    try:
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='This feature is under construction.\n\n`args[0]` or search term: `{}`'.format(args[0]),
                        parse_mode="Markdown")
    except IndexError:
        # Not enough arguments
        bot.sendMessage(chat_id=update.message.chat_id,
                        text='This feature is under construction.\n\nPlease use this command like `/docs <something>`',
                        parse_mode="Markdown")


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
