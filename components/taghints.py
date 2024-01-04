import re
from typing import Any, Dict, List, Match, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, MessageEntity
from telegram.ext.filters import MessageFilter

from components import const
from components.const import DOCS_URL, PTBCONTRIB_LINK
from components.entrytypes import TagHint

# Tag hints should be used for "meta" hints, i.e. pointing out how to use the PTB groups
# Explaining functionality should be done in the wiki instead.
#
# Note that wiki pages are available through the search directly, but the Ask-Right and MWE pages
# are needed so frequently that we provide tag hints for them ...
_TAG_HINTS: Dict[str, Dict[str, Any]] = {
    "askright": {
        "message": (
            '{query} Please read <a href="https://github.com/python-telegram-bot/'
            'python-telegram-bot/wiki/Ask-Right">this short article</a> and try again ;)'
        ),
        "help": "The wiki page about asking technical questions",
        "default": (
            "Hey. In order for someone to be able to help you, you must ask a <b>good "
            "technical question</b>."
        ),
    },
    "mwe": {
        "message": (
            '{query} Have a look at <a href="https://github.com/python-telegram-bot/python-'
            'telegram-bot/wiki/MWE">Minimal Working Example (MWE)</a> if you need help.'
        ),
        "help": "How to build an MWE for PTB.",
        "default": "Hey. Please provide a minimal working example (MWE).",
    },
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
            "{query} If you are using a different package/language, we are sure you can "
            "find some kind of community help on their homepage. Here are a few links for other "
            "popular libraries: "
            '<a href="https://t.me/joinchat/Bn4ixj84FIZVkwhk2jag6A">pyTelegramBotApi</a>, '
            '<a href="https://github.com/nickoala/telepot">Telepot</a>, '
            '<a href="https://t.me/pyrogramchat">pyrogram</a>, '
            '<a href="https://t.me/TelethonChat">Telethon</a>, '
            '<a href="https://t.me/aiogram">aiogram</a>, '
            '<a href="https://t.me/botogram_users">botogram</a>.'
        ),
        "help": "Other Python wrappers for Telegram",
        "default": (
            "Hey, I think you're wrong 🧐\nThis is the support group of the "
            "<code>python-telegram-bot</code> library."
        ),
    },
    "pastebin": {
        "message": (
            "{query} Please post code or tracebacks using a pastebin rather than via plain text "
            "or a picture. https://pastebin.com/ is quite popular, but there are "
            "<a href='https://github.com/lorien/awesome-pastebin'>many alternatives</a> "
            "out there. Of course, for very short snippets, text is fine. Please at "
            "least format it as monospace in that case."
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
        "buttons": [[InlineKeyboardButton(text="🔗 Take me there!", url=PTBCONTRIB_LINK)]],
        "help": "Display a short info text about ptbcontrib",
    },
    "botlists": {
        "message": (
            "{query} This group is for technical questions that come up while you code your own "
            "Telegram bot. If you are looking for ready-to-use bots, please have a look at "
            "channels like @BotsArchive or @BotList/@BotlistBot. There are also a number of "
            "websites that list existing bots."
        ),
        "default": "Hey.",
        "help": "Redirect users to lists of existing bots.",
    },
    "coc": {
        "message": (
            f'{{query}} Please read our <a href="{DOCS_URL}coc.html">Code of Conduct</a> and '
            "stick to it. Note that violation of the CoC can lead to temporary or permanent "
            "banishment from this group."
        ),
        "default": "Hey.",
        "help": "Remind the users of the Code of Conduct.",
    },
    "docs": {
        "message": (
            f"{{query}} You can find our documentation at <a href='{const.DOCS_URL}'>Read the "
            f"Docs</a>. "
        ),
        "default": "Hey.",
        "help": "Point users to the documentation",
        "group_command": True,
    },
    "wiki": {
        "message": f"{{query}} You can find our wiki on <a href='{const.WIKI_URL}'>Github</a>.",
        "default": "Hey.",
        "help": "Point users to the wiki",
        "group_command": True,
    },
    "help": {
        "message": (
            "{query} You can find an explanation of @roolsbot's functionality on '"
            '<a href="https://github.com/python-telegram-bot/rules-bot/blob/master/README.md">'
            "GitHub</a>."
        ),
        "default": "Hey.",
        "help": "Point users to the bots readme",
        "group_command": True,
    },
    "upgrade": {
        "message": (
            "{query} You seem to be using a version &lt;=13.15 of "
            "<code>python-telegram-bot</code>. "
            "Please note that we only provide support for the latest stable version and that the "
            "library has undergone significant changes in v20. Please consider upgrading to v20 "
            "by reading the release notes and the transition guide linked below."
        ),
        "buttons": [
            [
                InlineKeyboardButton(
                    text="🔗 Release Notes",
                    url="https://telegra.ph/Release-notes-for-python-telegram-bot-v200a0-05-06",
                ),
                InlineKeyboardButton(
                    text="🔗 Transition Guide",
                    url="https://github.com/python-telegram-bot/python-telegram-bot/wiki"
                    "/Transition-guide-to-Version-20.0",
                ),
            ]
        ],
        "default": "Hey.",
        "help": "Ask users to upgrade to the latest version of PTB",
        "group_command": True,
    },
    "compat": {
        "message": (
            "{query} You seem to be using the new version (&gt;=20.0) of"
            "<code>python-telegram-bot</code> but your code is written for an older and "
            "deprecated version (&lt;=13.15).\nPlease update your code to the new v20 by reading"
            " the release notes and the transition guide linked below.\nYou can also install a "
            "version of PTB that is compatible with your code base, but please note that the "
            "library has undergone significant changes in v20 and the older version is not "
            "supported anymore and may be broken."
        ),
        "buttons": [
            [
                InlineKeyboardButton(
                    text="🔗 Release Notes",
                    url="https://telegra.ph/Release-notes-for-python-telegram-bot-v200a0-05-06",
                ),
                InlineKeyboardButton(
                    text="🔗 Transition Guide",
                    url="https://github.com/python-telegram-bot/python-telegram-bot/wiki"
                    "/Transition-guide-to-Version-20.0",
                ),
            ]
        ],
        "default": "Hey.",
        "help": "Point out compatibility issues of code and PTB version to users",
        "group_command": True,
    },
    "llm": {
        "message": (
            "{query} This text reads like an AI/LLM was used to generate this. We found their "
            "answers to be unfitting for this group. We are all about providing fine tuned help "
            "for technical questions. These generated texts are often long winded, very "
            "explanatory answers for steps which didn't need explaining, and then happen to miss "
            "the actual underlying question completely or are outright false in the worst case."
            "\n\n"
            "Please refrain from this in the future. If you can answer a question yourself, we "
            "are glad to see a precise, technical answer. If you can not answer a question, it's "
            "better to just not reply instead of copy-pasting an autogenerated answer 😉."
        ),
        "default": "Hey.",
        "help": "Tell users not to use AI/LLM generated answers",
        "group_command": True,
    },
    "traceback": {
        "message": (
            "{query} Please show the <i>full</i> traceback via a pastebin. Make sure to include "
            "everything from the first <code>Traceback (most recent call last):</code> until the "
            "last error message. https://pastebin.com/ is a popular pastebin service, but there "
            "are <a href='https://github.com/lorien/awesome-pastebin'>many alternatives</a> out "
            "there."
        ),
        "default": "Hey.",
        "help": "Ask for the full traceback",
        "group_command": True,
    },
}


# Sort the hints by key
_TAG_HINTS = dict(sorted(_TAG_HINTS.items()))
# convert into proper objects
TAG_HINTS: Dict[str, TagHint] = {
    key: TagHint(
        tag=key,
        message=value["message"],
        description=value["help"],
        default_query=value.get("default"),
        inline_keyboard=InlineKeyboardMarkup(value["buttons"]) if "buttons" in value else None,
        group_command=value.get("group_command", False),
    )
    for key, value in _TAG_HINTS.items()
}
TAG_HINTS_PATTERN = re.compile(
    # case insensitive
    r"(?i)"
    # join the /tags
    r"((?P<tag_hint_with_username>(?P<tag_hint>"
    rf'{"|".join(hint.short_name for hint in TAG_HINTS.values())})'
    # don't allow the tag to be followed by '/' - That could be the start of the next tag
    r"(?!/)"
    # Optionally the bots username
    rf"(@{re.escape(const.SELF_BOT_NAME)})?)"
    # match everything that comes next as long as it's separated by a whitespace - important for
    # inserting a custom query in inline mode
    r"($| (?P<query>[^\/.]*)))"
)


class TagHintFilter(MessageFilter):
    """Custom filter class for filtering for tag hint messages"""

    def __init__(self) -> None:
        super().__init__(name="TageHintFilter", data_filter=True)

    def filter(self, message: Message) -> Optional[Dict[str, List[Match]]]:
        """Does the filtering. Applies the regex and makes sure that only those tag hints are
        handled, that are also marked as bot command.
        """
        if not message.text:
            return None

        matches = []
        command_texts = message.parse_entities([MessageEntity.BOT_COMMAND]).values()
        for match in TAG_HINTS_PATTERN.finditer(message.text):
            if match.groupdict()["tag_hint_with_username"] in command_texts:
                matches.append(match)

        if not matches:
            return None

        return {"matches": matches}
