from collections import namedtuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.error import BadRequest
from telegram.ext import CommandHandler, RegexHandler, run_async, Filters, MessageHandler, CallbackContext

import const
import util

HINTS = {
    '#inline': {
        'message': "Consider using me in inline-mode 😎\n<code>@roolsbot {query}</code>",
        'default': "Your search terms",
        'buttons': [{
            'text': '🔎 Try it out',
            'switch_inline_query': '{query}'
        }],
        'help': 'Give a query that will be used for a switch_to_inline-button'
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
    '#issue': {
        'message': "Hi,\n\nThis is not an issue with the library's code, but a usage question. "
                   'Feel free to ask it in our <a href="https://t.me/pythontelegrambotgroup">telegram group</a>. '
                   'Or (if you can\'t reach our group) our <a href="https://webchat.freenode.net/?channels=##python-telegram-bot">IRC channel</a>.\n{query}',
        'default': '',
        'help': 'Send issue template',
    },
    '#userbot': {
        'message': 'Refer to <a href="http://telegra.ph/How-a-Userbot-superacharges-your-Telegram-Bot-07-09">this article</a> to learn more about <b>Userbots</b>.',
        'help': "@JosXa's article about Userbots"
    },
    '#snippets': {
        'message': '<a href="https://github.com/python-telegram-bot/python-telegram-bot/wiki/Code-snippets">Here</a> '
                   "you can find many useful code snippets for the work with python-telegram-bot",
        'help': "Link to the wiki's snippets section",
    },
    '#pprint': {
        'message': """
            The most convenient way of <b>pretty-printing an update</b> is:
    <pre>from pprint import pprint
    pprint(update.to_dict())</pre>

It shows you what attributes are available in an update. Alternatively, use a json dumping bot like @JsonDumpBot or @JsonDumpBetaBot for a general overview, but keep in mind that this method won't be entirely consistent with your bot's updates (different file\_ids for example).""",
        'help': "Explain how to pretty-print an update"
    },
    '#meta': {
        'message': """No need for meta questions. Just ask! 🤗
<i>"Has anyone done .. before?"</i>
Probably. <b>Just ask your question and somebody will help!</b> 
        """,
        'help': "Show our stance on meta-questions"
    },
    '#tutorial': {
        'message': """Oh, hey! There's someone new joining our awesome community of Python developers ❤️ We have compiled a list of learning resources <i>just for you</i>:
• <a href="https://wiki.python.org/moin/BeginnersGuide/NonProgrammers">As Beginner</a>
• <a href="https://wiki.python.org/moin/BeginnersGuide/Programmers">As Programmer</a>
• <a href="https://docs.python.org/3/tutorial/">Official Tutorial</a>
• <a href="http://www.diveintopython3.net/">Dive into Python</a>
• <a href="https://www.learnpython.org/">Learn Python</a>
• <a href="https://cscircles.cemc.uwaterloo.ca/">Computer Science Circles</a>
• <a href="https://ocw.mit.edu/courses/electrical-engineering-and-computer-science/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/">MIT OpenCourse</a>
• <a href="https://docs.python-guide.org/">Hitchhiker’s Guide to Python</a>
• The @PythonRes Telegram Channel.
• Corey Schafer videos for <a href="https://www.youtube.com/watch?v=YYXdXT2l-Gg&list=PL-osiE80TeTskrapNbzXhwoFUiLCjGgY7">beginners</a> and in <a href="https://www.youtube.com/watch?v=YYXdXT2l-Gg&list=PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU">general</a>
• <a href="http://projectpython.net/chapter00/">Project Python</a>""",
        'help': "How to find a Python tutorial"
    },
    '#wronglib': {
        'message': """Hey, I think you're wrong 🧐
It looks like you're not using the python-telegram-bot library. If you insist on using that other one, please go where you belong:
<a href="https://telegram.me/joinchat/Bn4ixj84FIZVkwhk2jag6A">pyTelegramBotApi</a>
<a href="https://github.com/nickoala/telepot">Telepot</a>
        """,
        'help': "Other Python wrappers for Telegram"
    },
    '#askright': {
        'message': """Hey.
        In order for someone to be able to help you, you must ask a <b>good technical question</b>. Please read <a href="http://telegra.ph/How-not-to-ask-technical-questions-05-10) and try again ;">this short article</a>
        """,
        'help': "@d_Rickyy_b's article about asking technical questions"
    },
    '#broadcast': {
        'message': """Hey. Broadcasting to users is a common use case. This <a href="https://telegra.ph/Sending-notifications-to-all-users-07-17">short article</a> summarizes the most important tips for that.""",
        'help': "@BiboJoshi's article about broadcasting to users."
    },
    '#mwe': {
        'message': """Hey. Please provide a minimal working example (MWE). Have a look at <a href="https://telegra.ph/Minimal-Working-Example-for-PTB-07-18">this short article</a> for information on what a MWE is.""",
        'help': "@BiboJoshi's article about MWEs."
    },
    '#pastebin': {
        'message': """Hey. Please post code using a pastebin rather then as plain text or screenshots. https://pastebin.com/ ist the most popular, but there are many alterantives out there. Of course, for very short snippets, text is fine. Please at least format it as monospace in that case.""",
        'help': "Ask users not to post code as text or images."
    }
}


@run_async
def list_available_hints(update: Update, context: CallbackContext):
    message = "You can use the following hashtags to guide new members:\n\n"
    message += '\n'.join(
        '🗣 {tag} ➖ {help}'.format(
            tag=k, help=v['help']
        ) for k, v in HINTS.items()
    )
    message += "\n\nMake sure to reply to another message, so I know who to refer to."
    update.effective_message.reply_text(message, parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)


Hint = namedtuple('Hint', 'help, msg, reply_markup')


def get_hints(query):
    results = {}
    hashtag, _, query = query.partition(' ')

    for k, v in HINTS.items():
        if k.startswith(hashtag):
            reply_markup = InlineKeyboardMarkup(util.build_menu([InlineKeyboardButton(
                **{k: v.format(query=query) for k, v in b.items()}
            ) for b in v['buttons']], 1)) if 'buttons' in v else None

            msg = v['message'].format(query=query if query else v.get('default', ''))

            results[k] = Hint(help=v.get('help', ''), msg=msg, reply_markup=reply_markup)

    return results


@run_async
def hint_handler(update: Update, context: CallbackContext):
    reply_to = update.message.reply_to_message

    hint = get_hints(update.message.text).popitem()[1]

    if hint is not None:
        update.effective_message.reply_text(hint.msg,
                                            reply_markup=hint.reply_markup,
                                            reply_to_message_id=reply_to.message_id if reply_to else None,
                                            parse_mode=ParseMode.HTML,
                                            disable_web_page_preview=True)
        try:
            update.effective_message.delete()
        except BadRequest:
            pass


def register(dispatcher):
    dispatcher.add_handler(MessageHandler(Filters.regex(rf'{"|".join(HINTS.keys())}.*'), hint_handler))
    dispatcher.add_handler(CommandHandler(('hints', 'listhints'), list_available_hints))
