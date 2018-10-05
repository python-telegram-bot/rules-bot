import re

ENCLOSING_REPLACEMENT_CHARACTER = '+'
ENCLOSED_REGEX = rf'\{ENCLOSING_REPLACEMENT_CHARACTER}([a-zA-Z_.0-9]*)\{ENCLOSING_REPLACEMENT_CHARACTER}'
OFFTOPIC_USERNAME = 'pythontelegrambottalk'
ONTOPIC_USERNAME = 'pythontelegrambotgroup'
OFFTOPIC_CHAT_ID = '@' + OFFTOPIC_USERNAME
TELEGRAM_SUPERSCRIPT = 'ᵀᴱᴸᴱᴳᴿᴬᴹ'
FAQ_CHANNEL_ID = '@ptbfaq'
SELF_BOT_NAME = 'roolsbot'
ONTOPIC_RULES = """This group is for questions, answers and discussions around the <a href="https://python-telegram-bot.org/">python-telegram-bot library</a> and, to some extent, Telegram bots in general.

<b>Rules:</b>
- The group language is English
- Stay on topic
- No meta questions (eg. <i>"Can I ask something?"</i>)
- Use a pastebin when you have a question about your code, like <a href="https://www.codepile.net">this one</a>.
- Use <code>/wiki</code> and <code>/docs</code> in a private chat if possible.

Before asking, please take a look at our <a href="https://github.com/python-telegram-bot/python-telegram-bot/wiki">wiki</a> and <a href="https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples">example bots</a> or, depending on your question, the <a href="https://core.telegram.org/bots/api">official API docs</a> and <a href="https://python-telegram-bot.readthedocs.io">python-telegram-bot docs</a>).
For off-topic discussions, please use our <a href="https://telegram.me/pythontelegrambottalk">off-topic group</a>."""

OFFTOPIC_RULES = """<b>Topics:</b>
- Discussions about Python in general
- Meta discussions about <code>python-telegram-bot</code>
- Friendly, respectful talking about non-tech topics

<b>Rules:</b>
- The group language is English
- Use a pastebin to share code
- No <a href="https://telegram.me/joinchat/A6kAm0EeUdd0SciQStb9cg">shitposting, flamewars or excessive trolling</a>
- Max. 1 meme per user per day"""

GITHUB_PATTERN = re.compile(r'''
    (?i)                                # Case insensitivity
    [\s\S]*?                            # Any characters
    (?P<full>                           # Capture for the the whole thing
        (?:                                 # Optional non-capture group for username/repo
            (?:(?P<owner>[^\s/\#@]+)/)?     # Matches username/org - only if ends with slash
            (?P<repo>[^\s/\#@]+)?           # Optionally matches repo
        )?                                  # End optional non-capture group
        (?:                                 # Match either
            (
                (?P<number_type>\#|GH-|PR-)     # Hashtag or "GH-" or "PR-"
                (?:                             # Followed by either
                    (?P<number>\d+)                 # Numbers
                    |                           # Or
                    (?P<query>\S+)                  # A search query (without spaces) (only works inline)
                )
            )
        |                                   # Or
            (?:@?(?P<sha>[0-9a-f]{40}))         # at sign followed by 40 hexadecimal characters
        )
    )
''', re.VERBOSE)

