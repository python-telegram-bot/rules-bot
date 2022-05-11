import re
from urllib.parse import urljoin

ARROW_CHARACTER = "➜"
GITHUB_URL = "https://github.com/"
DEFAULT_REPO_OWNER = "python-telegram-bot"
DEFAULT_REPO_NAME = "python-telegram-bot"
PTBCONTRIB_REPO_NAME = "ptbcontrib"
DEFAULT_REPO = f"{DEFAULT_REPO_OWNER}/{DEFAULT_REPO_NAME}"
# Require x non-command messages between each /rules etc.
RATE_LIMIT_SPACING = 2
# Welcome new chat members at most ever X minutes
NEW_CHAT_MEMBERS_LIMIT_SPACING = 60
USER_AGENT = "Github: python-telegram-bot/rules-bot"
ENCLOSING_REPLACEMENT_CHARACTER = "+"
_ERC = ENCLOSING_REPLACEMENT_CHARACTER
ENCLOSED_REGEX = re.compile(rf"\{_ERC}([^{_ERC}]*)\{_ERC}")
OFFTOPIC_USERNAME = "pythontelegrambottalk"
ONTOPIC_USERNAME = "pythontelegrambotgroup"
OFFTOPIC_CHAT_ID = "@" + OFFTOPIC_USERNAME
ONTOPIC_CHAT_ID = "@" + ONTOPIC_USERNAME
ERROR_CHANNEL_CHAT_ID = -1001397960657
TELEGRAM_SUPERSCRIPT = "ᵀᴱᴸᴱᴳᴿᴬᴹ"
FAQ_CHANNEL_ID = "@ptbfaq"
SELF_BOT_NAME = "roolsbot"
ONTOPIC_RULES_MESSAGE_ID = 419903
ONTOPIC_RULES_MESSAGE_LINK = "https://t.me/pythontelegrambotgroup/419903"
OFFTOPIC_RULES_MESSAGE_ID = 161133
OFFTOPIC_RULES_MESSAGE_LINK = "https://t.me/pythontelegrambottalk/161133"
PTBCONTRIB_LINK = "https://github.com/python-telegram-bot/ptbcontrib/"
DOCS_URL = "https://python-telegram-bot.readthedocs.io/"
OFFICIAL_URL = "https://core.telegram.org/bots/api"
PROJECT_URL = urljoin(GITHUB_URL, DEFAULT_REPO + "/")
WIKI_URL = urljoin(PROJECT_URL, "wiki/")
WIKI_CODE_SNIPPETS_URL = urljoin(WIKI_URL, "Code-snippets")
WIKI_FAQ_URL = urljoin(WIKI_URL, "Frequently-Asked-Questions")
WIKI_FRDP_URL = urljoin(WIKI_URL, "Frequently-requested-design-patterns")
EXAMPLES_URL = urljoin(PROJECT_URL, "tree/master/examples/")
ONTOPIC_RULES = """
This group is for questions, answers and discussions around the \
<a href="https://python-telegram-bot.org/">python-telegram-bot library</a> and, to some extent, \
Telegram bots in general.

<b>Rules:</b>
- The group language is English
- Stay on topic
- Advertisement or posting as channels is disallowed
- No meta questions (eg. <i>"Can I ask something?"</i>)
- Use a pastebin when you have a question about your code, like <a href="https://www.codepile.net"\
>this one</a>. If you <i>really</i> can't explain your problem without showing a picture, upload\
 it somewhere and share a link.
- Use <code>/wiki</code> and <code>/docs</code> in a private chat if possible.
- Only mention or reply to users directly if you're answering their question or following up on a \
conversation with them.
- Please abide by our <a href="python-telegram-bot.readthedocs.io/coc.html">Code of Conduct</a>
- Use <code>@admin</code> to report spam or abuse and <i>only</i> for that.
- If you have a userbot, deactivate it in here. Otherwise you'll get banned at least temporarily.

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
- Advertisement or posting as channels is disallowed
- Use a pastebin to share code. If you <i>really</i> can't explain your problem without showing a\
 picture, upload it somewhere and share a link.
- No shitposting, flamewars or excessive trolling
- Max. 1 meme per user per day
- Only mention or reply to users directly if you're answering their question or following up on a \
conversation with them.
- Please abide by our <a href="python-telegram-bot.readthedocs.io/coc.html">Code of Conduct</a>
- Use <code>@admin</code> to report spam or abuse and <i>only</i> for that.
- If you have a userbot, deactivate it in here. Otherwise you'll get banned at least temporarily.
"""

# Github Pattern
# This matches two different kinds of things:
# 1. ptbcontrib/description
# 2. owner/repo(#|GH-|PR-|@)number/query, where both owner/ and repo are optional
#
# Per https://github.com/join
# Github username may only contain alphanumeric characters or hyphens.
# Github username cannot have multiple consecutive hyphens.
# Github username cannot begin or end with a hyphen.
# Maximum is 39 characters.
# Therefore we use:
# [a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38}
#
# Repo names seem to allow alphanumeric, -, . and _
# And the form at https://github.com/new has a maxlength of 100
# Therefore we use
# [A-Za-z0-9-._]{0,100}

GITHUB_PATTERN = re.compile(
    r"""
    (?i)  # Case insensitivity
    [\s\S]*?  # Any characters
    (?P<full>  # Capture for the the whole thing
        (?:  # Optional non-capture group for owner/repo#number/sha/query matches
            (?:  # Optional non-capture group for username/repo
                # Matches username or org - only if ends with slash
                (?:(?P<owner>[a-z\d](?:[a-z\d]|-(?=[a-z\d])){0,38})/)?
                (?P<repo>[A-Za-z0-9-._]{0,100})?  # Optionally matches repo
            )?  # End optional non-capture group
            (?:  # Match either
                (
                    # "#" or "GH-" or "PR-" or "/issues/" or "/pull"
                    (?P<number_type>\#|GH-|PR-|/issues/|/pull/)
                    (?:  # Followed by either
                        (?P<number>\d+)  # Numbers
                        |  # Or
                        (?P<query>.+)  # A search query (only works inline)
                    )
                )
            |  # Or
                (?:(/commit/|@)? # Optionall /commit/ or @
                (?P<sha>[0-9a-f]{7,40})) # sha: 7-40 hexadecimal chars
            )
        )
        |  # Or ptbcontrib match
        ptbcontrib/(?P<ptbcontrib>[\w_]+)
    )
""",
    re.VERBOSE,
)
VEGETABLES = [
    "amaranth",
    "anise",
    "artichoke",
    "arugula",
    "asparagus",
    "aubergine",
    "basil",
    "beet",
    "broccoflower",
    "broccoli",
    "cabbage",
    "calabrese",
    "caraway",
    "carrot",
    "cauliflower",
    "celeriac",
    "celery",
    "chamomile",
    "chard",
    "chayote",
    "chickpea",
    "chives",
    "cilantro",
    "corn",
    "corn salad",
    "courgette",
    "cucumber",
    "daikon",
    "delicata",
    "dill",
    "eggplant",
    "endive",
    "fennel",
    "fiddlehead",
    "frisee",
    "garlic",
    "ginger",
    "habanero",
    "horseradish",
    "jalapeno",
    "jicama",
    "kale",
    "kohlrabi",
    "lavender",
    "leek ",
    "legume",
    "lentils",
    "lettuce",
    "mamey",
    "mangetout",
    "marjoram",
    "mushroom",
    "nopale",
    "okra",
    "onion",
    "oregano",
    "paprika",
    "parsley",
    "parsnip",
    "pea",
    "potato",
    "pumpkin",
    "radicchio",
    "radish",
    "rhubarb",
    "rosemary",
    "rutabaga",
    "sage",
    "scallion",
    "shallot",
    "skirret",
    "spinach",
    "squash",
    "taro",
    "thyme",
    "topinambur",
    "tubers",
    "turnip",
    "wasabi",
    "watercress",
    "yam",
    "zucchini",
]
