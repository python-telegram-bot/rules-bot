import re

ARROW_CHARACTER = '➜'
GITHUB_URL = "https://github.com/"
DEFAULT_REPO_OWNER = 'python-telegram-bot'
DEFAULT_REPO_NAME = 'python-telegram-bot'
DEFAULT_REPO = f'{DEFAULT_REPO_OWNER}/{DEFAULT_REPO_NAME}'
# Require x non-command messages between each /rules etc.
RATE_LIMIT_SPACING = 2
# Welcome new chat members at most ever X minutes
NEW_CHAT_MEMBERS_LIMIT_SPACING = 60
USER_AGENT = 'Github: python-telegram-bot/rules-bot'
ENCLOSING_REPLACEMENT_CHARACTER = '+'
ENCLOSED_REGEX = (
    rf'\{ENCLOSING_REPLACEMENT_CHARACTER}([a-zA-Z_.0-9]*)\{ENCLOSING_REPLACEMENT_CHARACTER}'
)
OFFTOPIC_USERNAME = 'pythontelegrambottalk'
ONTOPIC_USERNAME = 'pythontelegrambotgroup'
OFFTOPIC_CHAT_ID = '@' + OFFTOPIC_USERNAME
ERROR_CHANNEL_CHAT_ID = -1001397960657
TELEGRAM_SUPERSCRIPT = 'ᵀᴱᴸᴱᴳᴿᴬᴹ'
FAQ_CHANNEL_ID = '@ptbfaq'
SELF_BOT_NAME = 'roolsbot'
ONTOPIC_RULES_MESSAGE_ID = 419903
ONTOPIC_RULES_MESSAGE_LINK = 'https://t.me/pythontelegrambotgroup/419903'
OFFTOPIC_RULES_MESSAGE_ID = 161133
OFFTOPIC_RULES_MESSAGE_LINK = 'https://t.me/pythontelegrambottalk/161133'
PTBCONTRIB_LINK = 'https://github.com/python-telegram-bot/ptbcontrib/'
ONTOPIC_RULES = """
This group is for questions, answers and discussions around the \
<a href="https://python-telegram-bot.org/">python-telegram-bot library</a> and, to some extent, \
Telegram bots in general.

<b>Rules:</b>
- The group language is English
- Stay on topic
- No meta questions (eg. <i>"Can I ask something?"</i>)
- Use a pastebin when you have a question about your code, like <a href="https://www.codepile.net"\
>this one</a>.
- Use <code>/wiki</code> and <code>/docs</code> in a private chat if possible.
- Only mention or reply to users directly if you're answering their question or following up on a \
conversation with them.
- Please abide by our <a href="https://github.com/python-telegram-bot/python-telegram-bot/blob/\
master/CODE_OF_CONDUCT.md">Code of Conduct</a>
- Use <code>@admin</code> to report spam or abuse and <i>only</i> for that.

Before asking, please take a look at our <a href="https://github.com/python-telegram-bot/\
python-telegram-bot/wiki">wiki</a> and <a href="https://github.com/python-telegram-bot/\
python-telegram-bot/tree/master/examples">example bots</a> or, depending on your question, the \
<a href="https://core.telegram.org/bots/api">official API docs</a> and <a href="https://\
python-telegram-bot.readthedocs.io">python-telegram-bot docs</a>).
For off-topic discussions, please use our <a href="https://telegram.me/pythontelegrambottalk">\
off-topic group</a>.
"""

OFFTOPIC_RULES = """
<b>Topics:</b>
- Discussions about Python in general
- Meta discussions about <code>python-telegram-bot</code>
- Friendly, respectful talking about non-tech topics

<b>Rules:</b>
- The group language is English
- Use a pastebin to share code
- No shitposting, flamewars or excessive trolling
- Max. 1 meme per user per day
- Only mention or reply to users directly if you're answering their question or following up on a \
conversation with them.
- Please abide by our <a href="https://github.com/python-telegram-bot/python-telegram-bot/blob/\
master/CODE_OF_CONDUCT.md">Code of Conduct</a>
- Use <code>@admin</code> to report spam or abuse and <i>only</i> for that.
"""

# Github username
# Per https://github.com/join
# Github username may only contain alphanumeric characters or hyphens.
# Github username cannot have multiple consecutive hyphens.
# Github username cannot begin or end with a hyphen.
# Maximum is 39 characters.
# Therefore we use:
# [a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38}

# Repo names seem to allow alphanumeric, -, . and _
# And the form at https://github.com/new has a maxlength of 100
# Therefore we use
# [A-Za-z0-9-._]{0,100}

GITHUB_PATTERN = re.compile(
    r"""
    (?i)  # Case insensitivity
    [\s\S]*?  # Any characters
    (?P<full>  # Capture for the the whole thing
        (?:  # Optional non-capture group for username/repo
  # Matches username or org - only if ends with slash
            (?:(?P<owner>[a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38})/)?
            (?P<repo>[A-Za-z0-9-._]{0,100})?  # Optionally matches repo
        )?  # End optional non-capture group
        (?:  # Match either
            (
                (?P<number_type>\#|GH-|PR-)  # Hashtag or "GH-" or "PR-"
                (?:  # Followed by either
                    (?P<number>\d+)  # Numbers
                    |  # Or
                    (?P<query>\S+)  # A search query (without spaces) (only works inline)
                )
            )
        |  # Or
            (?:@?(?P<sha>[0-9a-f]{40}))  # at sign followed by 40 hexadecimal characters
        )
    )
""",
    re.VERBOSE,
)
