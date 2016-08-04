import logging
from telegram import ParseMode
from telegram.ext import Updater, CommandHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

updater = Updater(token='123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11')
dispatcher = updater.dispatcher

def start(bot, update):
    if update.message.chat.username not in ("pythontelegrambotgroup", "pythontelegrambottalk"):
        bot.sendMessage(chat_id=update.message.chat_id, text="Hi. I'm a bot that will anounce the rules of the python-telegram-bot groups when you type /rules.")

def rules(bot, update):
    # Load the appropiate rules based on which group we're in
    if update.message.chat.username == "pythontelegrambotgroup":
        bot.sendMessage(chat_id=update.message.chat_id, text='This group is for questions, answers and discussions around the <a href="https://python-telegram-bot.org/">python-telegram-bot library</a> and, to some extent, Telegram bots in general.\n\n<b>Rules:</b>\n- The group language is English\n- Stay on topic\n- No meta questions (eg. <i>"Can I ask something?"</i>)\n- Use a pastebin when you have a question about your code, like <a href="https://www.codepile.net">this one</a>\n\nFor bot examples, <a href="https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples">click here</a>\nFor off-topic discussions, please use our <a href="https://telegram.me/pythontelegrambottalk">off-topic group</a>', parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    elif update.message.chat.username == "pythontelegrambottalk":
        bot.sendMessage(chat_id=update.message.chat_id, text='- No pornography\n- No advertising\n- No spam')
    else:
        bot.sendMessage(chat_id=update.message.chat_id, text='Hmm. You\'re not in a python-telegram-bot group, and I don\'t know the rules around here.')

def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))
    # Do `touch rules_bot.log` first!
    with open('rules_bot.log', 'a') as logfile:
        logfile.write('Update "%s" caused error "%s"' % (update, error))
        logfile.close()

start_handler = CommandHandler('start', start)
rules_handler = CommandHandler('rules', rules)

dispatcher.add_handler(start_handler)
dispatcher.add_handler(rules_handler)
dispatcher.add_error_handler(error)

updater.start_polling()
updater.idle()
