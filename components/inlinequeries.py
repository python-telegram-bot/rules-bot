import re
from collections import OrderedDict
from uuid import uuid4

from telegram import InlineQueryResultArticle, InputTextMessageContent, ParseMode, Update
from telegram.ext import InlineQueryHandler, CallbackContext
from telegram.utils.helpers import escape_markdown

from components import taghints
from const import ENCLOSED_REGEX, TELEGRAM_SUPERSCRIPT, ENCLOSING_REPLACEMENT_CHARACTER, GITHUB_PATTERN
from search import WIKI_URL, search
from util import ARROW_CHARACTER, github_issues, Issue, Commit


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


def unwrap(things):
    """
    Unwrap and collapse things
    [1,(2,3),4,(5,6),7] into [[1,2,4,5,7], [1,2,4,6,7]]
    Where lists are actually dicts, tuples are actually search results,
    and numbers are Issues/PRs/Commits
    """
    last_search = [None]

    for k, candidate in reversed(things.items()):
        if not isinstance(candidate, (Issue, Commit)):
            last_search = candidate
            break

    out = [OrderedDict() for _ in last_search]

    for k, elem_merged in things.items():
        if elem_merged is last_search:
            for i, elem_last in enumerate(elem_merged):
                out[i][k] = elem_last
        elif not isinstance(elem_merged, (Issue, Commit)):
            for i in range(len(out)):
                out[i][k] = elem_merged[0]
        else:
            for i in range(len(out)):
                out[i][k] = elem_merged

    return last_search, out


def inline_github(query):
    """
    Parse query for issues, PRs and commits SHA
    Returns a list of `articles`.

    Examples:
        `#10` - [(title=Replace via GitHub,
                 description=#10: tenth issue title)]
        `#10 #9` - [(title=Replace via GitHub,
                    description=#10: tenth issue title, #9: ninth issue)]
        `@d6d0dec6e0e8b647d140dfb74db66ecb1d00a61d` - [(title=Replace via GitHub,
                                                        description=@d6d0dec: commit title)]
        `#search` - [(title= 🔍 An issue with search in it's issue,
                      description=#3: that issue),
                     (title= 🔍 Another issue with search in it's issue,
                      description=#2: that issue),
                     ... (3 more)]
        `#10 #search` - [(title=An issue with search in it's issue,
                          description=#10: tenth issue, #3: that issue),
                         (title=Another issue with search in it's issue,
                          description=#10: tenth issue, #2: that issue),
                         ... (3 more)]
        `#search #10` - [(title= 🔍 An issue with search in it's issue,
                          description=#3: that issue, #10: tenth issue),
                         (title= 🔍 Another issue with search in it's issue,
                          description=#2: that issue, #10, tenth issue),
                         ... (3 more)]
        `#search1 #10 #search2` - [(title= 🔍 An issue with search2 in it's issue,
                                    description=#3: search1 result, #10: tenth issue, #5: search2 result1),
                                   (title= 🔍 Another issue with search2 in it's issue,
                                    description=#3: search1 result, #10, tenth issue, #6: search2 result2),
                                   ... (3 more)]
    """
    # Issues/PRs/Commits
    things = OrderedDict()
    results = []

    # Search for Issues, PRs and commits in the query and add them to things
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
        # If it's a search
        elif search_query:
            search_results = github_issues.search(search_query)
            things['#' + search_query] = search_results

    if not things:
        # We didn't find anything
        return []

    # Unwrap and collapse things
    last_search, choices = unwrap(things)

    # Loop over all the choices we should send to the client
    # Each choice (things) is a dict of things (issues/PRs/commits) to show in that choice
    # If not searching there will only be a single choice
    # If searching we have 5 different possibilities we wanna send
    for i, things in enumerate(choices):
        # If we did a search
        if last_search and last_search[i]:
            # Show the search title as the title
            title = '🔍' + github_issues.pretty_format(last_search[i],
                                                       short_with_title=True,
                                                       title_max_length=50)
        else:
            # Otherwise just use generic title
            title = 'Resolve via GitHub'

        # Description is the short formats combined with ', '
        description = (', '.join(github_issues.pretty_format(thing, short_with_title=True)
                                 for thing in things.values()))

        # Truncate the description to 100 chars, from the left side.
        # So the last thing will always be shown.
        if len(description) > 100:
            description = '⟻' + description[-99:].partition(',')[2]

        # The text that will be sent when user clicks the choice/result
        text = ''
        pattern = r'|'.join(re.escape(thing) for thing in sorted(things.keys(), key=len, reverse=True))
        # Check if there's other stuff than issues/PRs etc. in the query by
        # removing issues/PRs etc. and seeing if there's anything left
        if re.sub(pattern, '', query).strip():
            # Replace every 'thing' with a link to said thing *all at once*
            # Needs to all at once because otherwise 'blah/blah#2 #2'
            # would break would turn into something like
            # [blah/blah[#2](LinkFor#2)](LinkForblah/blah[#2](LinkFor#2))
            # which isn't even valid markdown
            text = re.sub(pattern,
                          lambda x: f'[{github_issues.pretty_format(things[x.group(0)], short=True)}]'
                          f'({things[x.group(0)].url})', query)

        # Add full format to bottom of message
        text += '\n\n' + '\n'.join(f'[{github_issues.pretty_format(thing)}]({thing.url})'
                                   for thing in things.values())

        results.append(article(title=title, description=description, message_text=text))

    return results


def inline_query(update: Update, context: CallbackContext, threshold=20):
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

        if '#' in query or '@' in query:
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

    update.inline_query.answer(results=results_list, switch_pm_text='Help',
                               switch_pm_parameter='inline-help', cache_time=0)


def register(dispatcher):
    dispatcher.add_handler(InlineQueryHandler(inline_query))
