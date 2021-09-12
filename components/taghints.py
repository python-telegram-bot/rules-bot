import re
from typing import Dict, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from components import const
from components.const import PTBCONTRIB_LINK
from components.entrytypes import TagHint

_TAG_HINTS: Dict[str, Dict[str, Any]] = {
    "inline": {
        "message": (
            f"Consider using me in inline-mode 😎 <code>@{const.SELF_BOT_NAME} " + "{query}</code>"
        ),
        "default": "Your search terms",
        "buttons": [[InlineKeyboardButton(text="🔎 Try it out", switch_inline_query="")]],
        "help": "Give a query that will be used for a switch_to_inline-button",
    },
    "private": {
        "message": "Please don't spam the group with {query}, and go to a private "
        "chat with me instead. Thanks a lot, the other members will appreciate it 😊",
        "default": "searches or commands",
        "buttons": [
            [
                InlineKeyboardButton(
                    text="🤖 Go to private chat", url=f"https://t.me/{const.SELF_BOT_NAME}"
                )
            ]
        ],
        "help": "Tell a member to stop spamming and switch to a private chat",
    },
    "userbot": {
        "message": (
            '{query} Refer to <a href="https://telegra.ph/How-a-Userbot-superacharges-your-'
            'Telegram-Bot-07-09">this article</a> to learn more about <b>Userbots</b>.'
        ),
        "help": "What are Userbots?",
        "default": "",
    },
    "snippets": {
        "message": (
            '<a href="https://github.com/python-telegram-bot/python-telegram-bot/wiki/'
            'Code-snippets">Here</a> '
            "you can find many useful code snippets for the work with python-telegram-bot"
        ),
        "help": "Link to the wiki's snippets section",
    },
    "pprint": {
        "message": (
            "The most convenient way of <b>pretty-printing an update</b> is:\n\n"
            "<pre>from pprint import pprint\npprint(update.to_dict())</pre>\n\n"
            "It shows you what attributes are available in an update. Alternatively, use a json "
            "dumping bot like @JsonDumpBot or @JsonDumpBetaBot for a general overview, but keep "
            "in mind that this method won't be entirely consistent with your bots updates "
            "(different file_ids for example)."
        ),
        "help": "Explain how to pretty-print an update",
    },
    "meta": {
        "message": (
            'No need for meta questions. <a href="https://dontasktoask.com">Just ask</a>! 🤗'
            '<i>"Has anyone done .. before?" </i>'
            "Probably. <b>Just ask your question and somebody will help!</b>"
        ),
        "help": "Show our stance on meta-questions",
    },
    "tutorial": {
        "message": (
            "{query}"
            "We have compiled a list of learning resources <i>just for you</i>:\n\n"
            '• <a href="https://wiki.python.org/moin/BeginnersGuide/NonProgrammers">As Beginner'
            "</a>\n"
            '• <a href="https://wiki.python.org/moin/BeginnersGuide/Programmers">As Programmer'
            "</a>\n"
            '• <a href="https://docs.python.org/3/tutorial/">Official Tutorial</a>\n'
            '• <a href="http://www.diveintopython3.net/">Dive into Python</a>\n'
            '• <a href="https://www.learnpython.org/">Learn Python</a>\n'
            '• <a href="https://cscircles.cemc.uwaterloo.ca/">Computer Science Circles</a>\n'
            '• <a href="https://ocw.mit.edu/courses/electrical-engineering-and-computer-science/'
            '6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/">MIT '
            "OpenCourse</a>\n"
            '• <a href="https://docs.python-guide.org/">Hitchhiker’s Guide to Python</a>\n'
            "• The @PythonRes Telegram Channel.\n"
            '• Corey Schafer videos for <a href="https://www.youtube.com/watch?v=YYXdXT2l-Gg&list'
            '=PL-osiE80TeTskrapNbzXhwoFUiLCjGgY7">beginners</a> and in <a href="https://www.'
            'youtube.com/watch?v=YYXdXT2l-Gg&list=PL-osiE80TeTt2d9bfVyTiXJA-UTHn6WwU">general'
            "</a>\n"
            '• <a href="http://projectpython.net/chapter00/">Project Python</a>\n'
        ),
        "help": "How to find a Python tutorial",
        "default": (
            "Oh, hey! There's someone new joining our awesome community of Python developers "
            "❤️ "
        ),
    },
    "wronglib": {
        "message": (
            "{query} If you insist on using that other one, please go where you belong: "
            '<a href="https://telegram.me/joinchat/Bn4ixj84FIZVkwhk2jag6A">pyTelegramBotApi</a>, '
            '<a href="https://github.com/nickoala/telepot">Telepot</a>, '
            '<a href="https://t.me/Pyrogram">pyrogram</a>, '
            '<a href="https://t.me/TelethonChat">Telethon</a>, '
            '<a href="https://t.me/aiogram">aiogram</a>, '
            '<a href="https://t.me/botogram_users">botogram</a>.'
        ),
        "help": "Other Python wrappers for Telegram",
        "default": (
            "Hey, I think you're wrong 🧐\nIt looks like you're not using the python-telegram-bot "
            "library."
        ),
    },
    "askright": {
        "message": (
            "{query} In order for someone to be able to help you, you must ask a <b>good "
            'technical question</b>. Please read <a href="https://github.com/python-telegram-bot/'
            'python-telegram-bot/wiki/Ask-Right">this short article</a> and try again ;)'
        ),
        "help": "The wiki page about asking technical questions",
        "default": "Hey.",
    },
    "broadcast": {
        "message": (
            '{query} Broadcasting to users is a common use case. This <a href="https://telegra.ph/'
            'Sending-notifications-to-all-users-07-17">short article</a> summarizes the most '
            "important tips for that."
        ),
        "help": "FAQ for broadcasting to users.",
        "default": "Hey.",
    },
    "mwe": {
        "message": (
            '{query} Have a look at <a href="https://telegra.ph/Minimal-Working-Example-for-PTB-'
            '07-18">this short article</a> for information on what a MWE is.'
        ),
        "help": "How to build an MWE for PTB.",
        "default": "Hey. Please provide a minimal working example (MWE).",
    },
    "pastebin": {
        "message": (
            "{query} Please post code using a pastebin rather then as plain text or screenshots. "
            "https://pastebin.com/ is quite popular, but there are many alternatives out there."
            " Of course, for very short snippets, text is fine. Please at least format it as "
            "monospace in that case."
        ),
        "help": "Ask users not to post code as text or images.",
        "default": "Hey.",
    },
    "doublepost": {
        "message": (
            "{query} Please don't double post. Questions usually are on-topic only in one of the "
            "two groups anyway."
        ),
        "help": "Ask users not to post the same question in both on- and off-topic.",
        "default": "Hey.",
    },
    "formatting": {
        "message": (
            "{query} Telegram supports some formatting options for text. All the details about "
            'what is supported can be found <a href="https://core.telegram.org/bots/api#formatting'
            '-options">here</a>. You can format text with every API method/type that has a '
            "<code>parse_mode</code> parameter. In addition to editing your text as described in "
            "the link above, pass one of the parse modes available through "
            '<a href="https://python-telegram-bot.readthedocs.io/en/stable/telegram.parsemode.html'
            '">telegram.ParseMode</a> to the <code>parse_mode</code> parameter. Since the '
            "<code>5.0</code> update of the Bot API (version <code>13.1+</code> of our library), "
            'you can alternatively pass a list of <a href="https://python-telegram-bot.'
            'readthedocs.io/en/stable/telegram.messageentity.html">telegram.MessageEntities</a> '
            "to the <code>entities</code> parameter."
        ),
        "default": "Hey.",
        "help": "How to use text formatting.",
    },
    "xy": {
        "message": (
            '{query} This seems like an <a href="https://xyproblem.info">xy-problem</a> to me.'
        ),
        "default": "Hey. What exactly do you want this for?",
        "help": "Ask users for the actual use case.",
    },
    "dontping": {
        "message": (
            "{query} Please only mention or reply to users directly if you're following up on a "
            "conversation with them. Otherwise just ask your question and wait if someone has a "
            "solution for you - that's how this group works 😉 Also note that the "
            "<code>@admin</code> tag is only to be used to report spam or abuse!"
        ),
        "default": "Hey.",
        "help": "Tell users not to ping randomly ping you.",
    },
    "read": {
        "message": (
            "I just pointed you to {query} and I have the strong feeling that <i>you did not "
            "actually read it</i>. Please do so. If you don't understand everything and have "
            "follow up questions, that's fine, but you can't expect me to repeat everything "
            "<i>just for you</i> because you didn't feel like reading on your own. 😉"
        ),
        "default": "a resource in the wiki, the docs or the examples",
        "help": "Tell users to actually read the resources they were linked to",
    },
    "ptbcontrib": {
        "message": (
            "{query} <code>ptbcontrib</code> is a library that provides extensions for the "
            "<code>python-telegram-bot</code> library that written and maintained by the "
            "community of PTB users."
        ),
        "default": "Hey.",
        "buttons": [[InlineKeyboardButton(text="🔗 Take me there!", url=f"{PTBCONTRIB_LINK}")]],
        "help": "Display a short info text about ptbcontrib",
    },
    "botlists": {
        "message": (
            "{query} This group is for technical questions that come up while you code your own "
            "Telegram bot. If you are looking for ready-to-use bots, please have a look at "
            "channels like @BotsArchive or @BotList. There are also a number of websites that "
            "list existing bots."
        ),
        "default": "Hey.",
        "help": "Redirect users to lists of existing bots.",
    },
    "coc": {
        "message": (
            '{query} Please read our <a href="https://github.com/python-telegram-bot/'
            'python-telegram-bot/blob/master/CODE_OF_CONDUCT.md">Code of Conduct</a> and stick to '
            "it. Note that violation of the CoC can lead to temporary or permanent banishment from"
            " this group."
        ),
        "default": "Hey",
        "help": "Remind the users of the Code of Conduct.",
    },
}


# Sort the hints by hey
_TAG_HINTS = dict(sorted(_TAG_HINTS.items()))
# convert into proper objects
TAG_HINTS: Dict[str, TagHint] = {
    key: TagHint(
        tag=key,
        message=value["message"],
        description=value["help"],
        default_query=value.get("default"),
        inline_keyboard=InlineKeyboardMarkup(value["buttons"]) if "buttons" in value else None,
    )
    for key, value in _TAG_HINTS.items()
}
TAG_HINTS_PATTERN = re.compile(
    rf'(?i)(({"|".join(hint.short_name for hint in TAG_HINTS.values())})[^\/]*)'
)
