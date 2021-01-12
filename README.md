# rules-bot

The Telegram bot @roolsbot serves the python-telegram-bot [group](https://telegram.me/pythontelegrambotgroup) [chats](https://t.me/pythontelegrambottalk) by announcing the rules and searching the [docs](https://python-telegram-bot.readthedocs.io/) & [wiki](https://github.com/python-telegram-bot/python-telegram-bot/wiki) of [python-telegram-bot](https://python-telegram-bot.org)

So what exactly can this bot do?

## Search docs & wiki

You can use the inline mode to search for entries in the documentation or the wiki. Simply type `@roolsbot <your search keywords>` and select one of the results. To search exclusively within the [code snippets](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Code-snippets) or [FAQ](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-Asked-Questions), type `@roolsbot snippets/faq <your search keywords>`.

To nicely insert those links directly into your message, you can enclose the search keywords by `+`, e.g.
```
@roolsbot I 💙 +InlineQueries+, but you need an +InlineQueryHandler+ for it.
```
becomes

> I 💙 [InlineQueries](https://python-telegram-bot.readthedocs.io/en/stable/telegram.inlinequery.html#telegram.InlineQuery), but you need an [InlineQueryHandler](https://python-telegram-bot.readthedocs.io/en/stable/telegram.ext.inlinequeryhandler.html#telegram.ext.InlineQueryHandler) for it.

You can also choose to include links to the official Bot API docs, where available.

All search is fuzzy, i.e. a few typos won't matter.

## Search GitHub

The inline mode can also be used to search for threads and commits in the [GitHub repository](https://github.com/python-telegram-bot/python-telegram-bot) of python-telegram-bot. Simply type `@roolsbot #<your search keyword>` and select the result. The search keyword may be either

* the number of an issue/pull request
* a phrase to search for in issue/pull request titles
* a commit SHA

Optionally you may prepend the name of a repository within the [python-telegram-bot GitHub organization](https://github.com/python-telegram-bot) (`@roolsbot repo#<your search keyword>`) to search in that repo instead of the default repository.

Of course, you can also insert those links directly into your message, e.g.

```
@roolsbot Pull Request #1920 is about #TypeHinting.
```

## Short-Replies

rules-bot provides a number of predefined messages that are frequently needed. A list of available tag hints is available via the `/hints` command. Simply send `#<taghint>` and rules-bot will delete your message and send the corresponding text instead. Reply to a message with `#<taghint>` to make rules-bot send the message as reply to that message.

Tag hints are also available via the inline mode. Typing `@roolsbot #taghint` allows you to send the message yourself instead of having rules-bot send it. You can even type `@roolsbot #taghint <a personal message>`, to insert the personal message at a meaningful spot within the message. For most tag hints this will just prepend the personal message.

## Things it does automatically

rules-bot does a number of things without explicitly requesting it. This includes: 

## Redirect to On- & Off-Topic

To redirect a user to the on-/off-topic group simply reply with `on-topic` or `off-topic` to their message. rules-bot accepts different variants of this (e.g. `#off-topic`, `offtopic`, `off topic` are valid) and the hint may also be part of a longer message. 

### Link to GitHub Threads

When mentioning issues, pull requests or commit SHAs in the same manner as described above in [Search GitHub](#search-github), rules-bot will automatically reply to your message with the corresponding links. If your message is a reply to another message, the links will be sent as reply to that message.

### Welcome members

rules-bot will automatically delete the service messages announcing new members. Instead, it will welcome new members by mentioning them in a short message that links to a message stating the rules of the group. New members are welcomed in batches. Currently, there will be at most one welcoming message per hour. The linked rules messages are updated with the current rules on start-up.

## Fixed commands

* `/docs`: Sends the link to the docs.
* `/wiki`: Sends the link to the wiki.
* `/hints` & `/listhints`: Sends a list of available tag hints (see [here](#short---replies))
* `/help`: Links to this readme.

## Other

rules-bot can make sandwiches. You can ask it to do so by typing `make me a sandwich`. We'll see, if it actually does 😉