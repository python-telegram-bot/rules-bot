# rules-bot

The Telegram bot @roolsbot serves the python-telegram-bot [group](https://telegram.me/pythontelegrambotgroup) [chats](https://t.me/pythontelegrambottalk) by announcing the rules and searching the [docs](https://python-telegram-bot.readthedocs.io/) & [wiki](https://github.com/python-telegram-bot/python-telegram-bot/wiki) of [python-telegram-bot](https://python-telegram-bot.org)

So what exactly can this bot do?

## Inline Mode

rules-bot has an extensive inline functionality. It has basically two components:

### Direct Search

Typing `@roolsbot <search query>` will present you with a list of search results, from which you can select. Things than can be searched for:

* [Wiki](https://github.com/python-telegram-bot/python-telegram-bot/wiki) pages
* entries on the [FAQ](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Frequently-Asked-Questions) and [code snippets](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Code-snippets) pages
* Entries in the [documentation](https://python-telegram-bot.readthedocs.io/en/stable/)
* Examples from the [examples directory](https://github.com/python-telegram-bot/python-telegram-bot/tree/master/examples#examples)
* Tag hints as described [in this section](#short-replies)

rules-bot tries really hard to provide you with the closest match to your query. This is not always easy, so you might need to scroll a bit.

Also, special prefixes restrict the search results:

* Prepending the query with `/` will search *only* for [tag hints](#short-replies)
* Prepending the query with `#`/`PR-`/`GH-` will search *only* for entries on GitHub as described [in this section](#link-to-github-threads). This also allows you to search issues & pull request titles on the [GitHub repository](https://github.com/python-telegram-bot/python-telegram-bot).

### Insertion Search

Instead of searching for just one result, you can also insert links into a message by wrapping search queries in `+<search query>+`. The syntax for the search queries is exactly as described above. For example

```
@roolsbot I 💙 +InlineQueries+, but you need an +InlineQueryHandler+ for it.
```
becomes

> I 💙 [InlineQueries](https://python-telegram-bot.readthedocs.io/en/stable/telegram.inlinequery.html#telegram.InlineQuery), but you need an [InlineQueryHandler](https://python-telegram-bot.readthedocs.io/en/stable/telegram.ext.inlinequeryhandler.html#telegram.ext.InlineQueryHandler) for it.

For each inserted search query, rules-bot will search for the three best matches and will offer you all possible combinations of the corresponding results.

Please note that Telegram will only parse the first 256 characters of your inline query. Everything else will be cut off.

# Texting Mode

## Short-Replies

rules-bot provides a number of predefined messages that are frequently needed. A list of available tag hints is available in the command menu. Simply send `/<taghint>` and rules-bot will delete your message and send the corresponding text instead. Reply to a message with `/<taghint>` to make rules-bot send the message as reply to that message. Type `/<taghint> <a personal message>`, to insert the personal message at a meaningful spot within the message. For most tag hints this will just prepend the personal message. You can even send multiple short messages at once by typing `/<taghint 1> <message 1> /<taghint 2> <message 2> ...`

## Redirect to On- & Off-Topic

To redirect a user to the on-/off-topic group simply reply with `/on_topic` or `/off_topic` to their message. The hint may also be part of a longer message.

## Link To GitHub Threads

When mentioning issues, pull requests, commit SHAs or `ptbcontrib` contributions in the same manner, rules-bot will automatically reply to your message with the corresponding links to the [GitHub repository](https://github.com/python-telegram-bot/python-telegram-bot) of python-telegram-bot. If your message is a reply to another message, the links will be sent as reply to that message.

Mentioning those works in the following forms:

* `ptbcontrib/name` with the (directory) name of a contribution of [ptbcontrib](https://github.com/python-telegram-bot/ptbcontrib/tree/main/ptbcontrib)
* `#number` with the number of an issue/pull request
* `#phrase` with a phrase to search for in issue/pull request titles
* `@sha` with a commit SHA

In the last three cases, `#` may be replaced by `GH-` or `PR-` or you can prepend

* `repo` to search in the repo `https://github.com/python-telegram-bot/repo`
* `owner/` to search in the repo `https://github.com/owner/repo`

## Link to search results

The searching functionality described [above](#inline-mode) is also available outside of the inline mode. In a message, mark your search queries as `+<search query>+` put `!search` at the very start or end of your message. Then rules-bot will automatically reply with the best match for each of the queries. If your message is a reply to another message, the message will sent as reply to that message.
The search results are combined with links to GitHub threads, if applicable.

## Welcome Members

rules-bot will automatically delete the service messages announcing new members. Instead, it will welcome new members by mentioning them in a short message that links to a message stating the rules of the group. New members are welcomed in batches. Currently, there will be at most one welcoming message per hour. The linked rules messages are updated with the current rules on start-up.

## Fixed Commands

* `/docs`: Sends the link to the docs.
* `/wiki`: Sends the link to the wiki.
* `/help`: Links to this readme.
* `/say_potato`: Asks a user to verify that they are not a userbot. Only available to group admins.

## Other

rules-bot can make sandwiches. You can ask it to do so by typing `make me a sandwich`. We'll see if it actually does 😉

# Setting up the bot for development and testing

Copy the [example INI file `bot_example.ini`](bot_example.ini) to `bot.ini` and fill in your credentials:
- `bot_api`: your Bot API you [got from Botfather](https://core.telegram.org/bots/features#botfather);
- `github_auth`: your GitHub personal access token (see [instructions](https://docs.github.com/en/graphql/guides/forming-calls-with-graphql#authenticating-with-graphql)).
GraphQL will need this token to be prepended with `Bearer `, but it will be done automatically if you don't.

**Be sure not to commit `bot.ini`.** 

# Token Detection

rules-bot will detect **valid** bot tokens on messages and warn users about the leak, posting the name(s) of the affected bot(s) and telling them to go revoke at @BotFather
