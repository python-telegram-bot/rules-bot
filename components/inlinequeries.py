import re
from collections import OrderedDict
from uuid import uuid4

from telegram import InlineQueryResultArticle, InputTextMessageContent, ParseMode
from telegram.ext import InlineQueryHandler
from telegram.utils.helpers import escape_markdown

from components import taghints
from const import ENCLOSED_REGEX, TELEGRAM_SUPERSCRIPT, ENCLOSING_REPLACEMENT_CHARACTER, GITHUB_PATTERN
from search import WIKI_URL, search
from util import ARROW_CHARACTER, github_issues


def article(title='', description='', message_text='', key=None, reply_markup=None):
    return InlineQueryResultArticle(
        id=key or uuid4(),
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True),
        reply_markup=reply_markup
    )


def fuzzy_replacements_markdown(query, threshold=95, official_api_links=True):
    """ Replaces the enclosed characters in the query string with hyperlinks to the documentations """
    symbols = re.findall(ENCLOSED_REGEX, query)

    if not symbols:
        return None, None

    replacements = list()
    for s in symbols:
        # Wiki first, cause with docs you can always prepend telegram. for better precision
        wiki = search.wiki(s.replace('_', ' '), amount=1, threshold=threshold)
        if wiki:
            name = wiki[0][0].split(ARROW_CHARACTER)[-1].strip()
            text = f'[{name}]({wiki[0][1]})'
            replacements.append((wiki[0][0], s, text))
            continue

        doc = search.docs(s, threshold=threshold)
        if doc:
            text = f'[{doc.short_name}]({doc.url})'

            if doc.tg_url and official_api_links:
                text += f' [{TELEGRAM_SUPERSCRIPT}]({doc.tg_url})'

            replacements.append((doc.short_name, s, text))
            continue

        # not found
        replacements.append((s + '❓', s, escape_markdown(s)))

    result = query
    for name, symbol, text in replacements:
        char = ENCLOSING_REPLACEMENT_CHARACTER
        result = result.replace(f'{char}{symbol}{char}', text)

    result_changed = [x[0] for x in replacements]
    return result_changed, result


def inline_github(query):
    # Issues/PRs/Commits
    things = OrderedDict()
    search_query = None
    results = []

    for match in GITHUB_PATTERN.finditer(query):
        owner, repo, number, sha, search_query, full = [match.groupdict()[x] for x in ('owner', 'repo', 'number',
                                                                                       'sha', 'query', 'full')]
        # If it's an issue
        if number:
            issue = github_issues.get_issue(int(number), owner, repo)
            things[full] = issue
        # If it's a commit
        elif sha:
            commit = github_issues.get_commit(sha, owner, repo)
            things[full] = commit

    # If the last thing from the for loop above was a search
    if search_query:
        choices = []
        # Output a separate choice for each search result
        for search_result in github_issues.search(search_query):
            tmp = things.copy()
            tmp['#' + search_query] = search_result[0]
            choices.append(tmp)
    else:
        choices = [things]

    # Loop over all the choices we should send to the client
    # Each choice (things) is a dict of things (issues/PRs/commits) to show in that choice
    for things in choices:
        # For the title we wanna add the title of the last 'thing'
        title = things[next(reversed(things))].title
        # If longer than 30 cut it off
        if len(title) > 30:
            title = title[:29] + '…'
        # Add ' & others' if multiple
        if len(things) > 1:
            title += ' & others'

        # Description is the short formats combined with ', '
        description = ', '.join(github_issues.pretty_format(thing, short=True) for thing in things.values())

        text = ''

        # Check if there's other stuff than issues/PRs etc. in the query
        if re.sub(r'|'.join(re.escape(thing) for thing in things.keys()), '', query).strip():
            # Replace every 'thing' with a link to said thing *all at once*
            # Needs to all at once because otherwise 'blah/blah#2 #2' would break
            text = re.sub(r'|'.join(re.escape(thing) for thing in things.keys()),
                          lambda x: f'[{github_issues.pretty_format(things[x.group(0)], short=True)}]'
                                    f'({things[x.group(0)].url})', query)

        # Add full format to bottom of message
        text += '\n\n' + '\n'.join(f'[{github_issues.pretty_format(thing)}]({thing.url})' for thing in things.values())

        results.append(article(title=title, description=description, message_text=text))

    return results


def inline_query(bot, update, threshold=20):
    query = update.inline_query.query
    results_list = list()

    if len(query) > 0:
        if query.startswith('#'):
            hints = taghints.get_hints(query)
            results_list.extend([article(f'Send hint on {key.capitalize()}',
                                         hint.help,
                                         hint.msg,
                                         key=key,
                                         reply_markup=hint.reply_markup) for key, hint in hints.items()])

        if '#' in query:
            results_list.extend(inline_github(query))

        if ENCLOSING_REPLACEMENT_CHARACTER in query:
            modified, replaced = fuzzy_replacements_markdown(query, official_api_links=True)
            if modified:
                results_list.append(article(
                    title="Replace links and show official Bot API documentation",
                    description=', '.join(modified),
                    message_text=replaced))

            modified, replaced = fuzzy_replacements_markdown(query, official_api_links=False)
            if modified:
                results_list.append(article(
                    title="Replace links",
                    description=', '.join(modified),
                    message_text=replaced))

        # If no results so far then search wiki and docs
        if not results_list:
            doc = search.docs(query, threshold=threshold)
            if doc:
                text = f'*{doc.short_name}*\n' \
                       f'_python-telegram-bot_ documentation for this {doc.type}:\n' \
                       f'[{doc.full_name}]({doc.url})'
                if doc.tg_name:
                    text += f'\n\nThe official documentation has more info about [{doc.tg_name}]({doc.tg_url}).'

                results_list.append(article(
                    title=f'{doc.full_name}',
                    description="python-telegram-bot documentation",
                    message_text=text,
                ))

            wiki_pages = search.wiki(query, amount=4, threshold=threshold)
            if wiki_pages:
                # Limit number of search results to maximum (-1 cause we might have added a doc above)
                wiki_pages = wiki_pages[:49]
                for wiki_page in wiki_pages:
                    results_list.append(article(
                        title=f'{wiki_page[0]}',
                        description="Github wiki for python-telegram-bot",
                        message_text=f'Wiki of _python-telegram-bot_\n'
                                     f'[{wiki_page[0]}]({wiki_page[1]})'
                    ))

        # If no results even after searching wiki and docs
        if not results_list:
            results_list.append(article(
                title='❌ No results.',
                description='',
                message_text=f'[GitHub wiki]({WIKI_URL}) of _python-telegram-bot_',
            ))

    else:
        # If no query then add all wiki pages (max 50)
        for name, link in search.all_wiki_pages()[:50]:
            results_list.append(article(
                title=name,
                description='Wiki of python-telegram-bot',
                message_text=f'Wiki of _python-telegram-bot_\n'
                             f'[{escape_markdown(name)}]({link})',
            ))

    bot.answer_inline_query(update.inline_query.id, results=results_list, switch_pm_text='Help',
                            switch_pm_parameter='inline-help')


def register(dispatcher):
    dispatcher.add_handler(InlineQueryHandler(inline_query))
