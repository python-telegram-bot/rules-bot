from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import CommandHandler, RegexHandler, run_async

import const
import util

HINTS = {
    '#inline': {
        'message': "Consider using me in inline-mode 😎\n`@roolsbot {query}`",
        'default': "Your search terms",
        'buttons': [{
            'text': '🔎 Try it out',
            'switch_inline_query': '{query}'
        }],
        'help': 'Give a query that will be used for a `switch_to_inline`-button'
    },
    '#private': {
        'message': "Please don't spam the group with {query}, and go to a private "
                   "chat with me instead. Thanks a lot, the other members will appreciate it 😊",
        'default': 'searches or commands',
        'buttons': [{
            'text': '🤖 Go to private chat',
            'url': "https://t.me/{}".format(const.SELF_BOT_NAME)
        }],
        'help': 'Tell a member to stop spamming and switch to a private chat',
    },
    '#userbot': {
        'message': "Refer to [this article](http://telegra.ph/How-a-"
                   "Userbot-superacharges-your-Telegram-Bot-07-09) to learn more about *Userbots*.",
        'help': "@JosXa's article about Userbots"
    },
    '#snippets': {
        'message': "[Here](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Code-snippets) "
                   "you can find many useful code snippets for the work with python-telegram-bot",
        'help': "Link to the wiki's *snippets* section",
    },
    '#pprint': {
        'message': """
            The most convenient way of *pretty-printing an update* is:
            
    `from pprint import pprint`
    `pprint(update.to_dict())`

It shows you what attributes are available in an update. Alternatively, use a json dumping bot like @JsonDumpBot or @JsonDumpBetaBot for a general overview, but keep in mind that this method won't be entirely consistent with your bot's updates (different file\_ids for example).""",
        'help': "Explain how to pretty-print an update"
    },
    '#meta': {
        'message': """No need for meta questions. Just ask! 🤗
_"Has anyone done .. before?"_
Probably. *Just ask your question and somebody will help!* 
        """,
        'help': "Show our stance on meta-questions"
    },
    '#tutorial': {
        'message': """Oh, hey! There's a new guy joining our awesome community of Python developers ❤️ We have compiled a list of learning resources _just for you_:
[As Beginner](https://wiki.python.org/moin/BeginnersGuide/NonProgrammers)
[As Programmer](https://wiki.python.org/moin/BeginnersGuide/Programmers)
        """,
        'help': "How to find a Python tutorial"
    },
    '#wronglib':{
        'message':"""Hey, I think you're wrong 🧐
It looks like you're not using the python-telegram-bot library. If you insist on using that other one, please go where you belong:
[pyTelegramBotApi](https://telegram.me/joinchat/Bn4ixj84FIZVkwhk2jag6A)
[Telepot](https://github.com/nickoala/telepot)
        """,
        'help': "Other Python wrappers for Telegram"
    }
}


@run_async
def list_available_hints(bot, update):
    message = "You can use the following hashtags to guide new members:\n\n"
    message += '\n'.join(
        '🗣 {tag} ➖ {help}'.format(
            tag=k, help=v['help']
        ) for k, v in HINTS.items()
    )
    message += "\n\nMake sure to reply to another message, so I know who to refer to."
    update.effective_message.reply_text(message, parse_mode='markdown',
                                        disable_web_page_preview=True)


def get_hint_data(text):
    for k, v in HINTS.items():
        if k not in text:
            continue

        text = text.replace(k, '')
        query = text.strip()

        reply_markup = None
        if v.get('buttons'):
            # Replace 'query' placeholder and expand kwargs
            buttons = [InlineKeyboardButton(
                **{k: v.format(query=query) for k, v in b.items()}
            ) for b in v.get('buttons')]
            reply_markup = InlineKeyboardMarkup(util.build_menu(buttons, 1))

        # Add default value if necessary
        msg = v['message'].format(
            query=query if query else v['default'] if v.get('default') else '')
        return msg, reply_markup, k
    return None, None, None


@run_async
def hint_handler(bot, update):
    text = update.message.text
    reply_to = update.message.reply_to_message

    msg, reply_markup, _ = get_hint_data(text)

    if msg is not None:
        update.effective_message.reply_text(msg,
                                            reply_markup=reply_markup,
                                            reply_to_message_id=reply_to.message_id if reply_to else None,
                                            parse_mode='Markdown',
                                            disable_web_page_preview=True)
        try:
            update.effective_message.delete()
        except BadRequest:
            pass


def register(dispatcher):
    for hashtag in HINTS.keys():
        dispatcher.add_handler(RegexHandler(r'{}.*'.format(hashtag), hint_handler))
    dispatcher.add_handler(CommandHandler(('hints', 'listhints'), list_available_hints))
