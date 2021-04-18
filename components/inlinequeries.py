import re
from collections import OrderedDict
from html import escape
from typing import List, cast, Tuple, Optional, no_type_check, Union, Dict
from uuid import uuid4

from telegram import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
    InlineQuery,
    InlineKeyboardMarkup,
)
from telegram.ext import InlineQueryHandler, CallbackContext, Dispatcher

from components import taghints
from components.const import (
    ENCLOSED_REGEX,
    TELEGRAM_SUPERSCRIPT,
    ENCLOSING_REPLACEMENT_CHARACTER,
    GITHUB_PATTERN,
    ARROW_CHARACTER,
    WIKI_URL,
)
from components.search import search
from components.github import CustomCommit, github_issues, Issue, PTBContrib


def article(
    title: str = '',
    description: str = '',
    message_text: str = '',
    key: str = None,
    reply_markup: InlineKeyboardMarkup = None,
) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=key or str(uuid4()),
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(
            message_text=message_text, disable_web_page_preview=True
        ),
        reply_markup=reply_markup,
    )


def fuzzy_replacements_html(
    query: str, threshold: int = 95, official_api_links: bool = True
) -> Tuple[Optional[List[str]], Optional[str]]:
    """Replaces the enclosed characters in the query string with hyperlinks
    to the documentations."""
    symbols = re.findall(ENCLOSED_REGEX, query)

    if not symbols:
        return None, None

    replacements = list()
    for symbol in symbols:
        # Wiki first, cause with docs you can always prepend telegram. for better precision
        wiki = search.wiki(symbol.replace('_', ' '), amount=1, threshold=threshold)
        if wiki:
            name = wiki[0][0].split(ARROW_CHARACTER)[-1].strip()
            text = f'<a href="{wiki[0][1]}">{name}</a>'
            replacements.append((wiki[0][0], symbol, text))
            continue

        doc = search.docs(symbol, threshold=threshold)
        if doc:
            text = f'<a href="{doc.url}">{doc.short_name}</a>'

            if doc.tg_url and official_api_links:
                text += f' <a href="{doc.tg_url}">{TELEGRAM_SUPERSCRIPT}</a>'

            replacements.append((doc.short_name, symbol, text))
            continue

        # not found
        replacements.append((symbol + '❓', symbol, escape(symbol)))

    result = query
    for name, symbol, text in replacements:
        char = ENCLOSING_REPLACEMENT_CHARACTER
        result = result.replace(f'{char}{symbol}{char}', text)

    result_changed = [x[0] for x in replacements]
    return result_changed, result


@no_type_check
def unwrap(things):
    """
    Unwrap and collapse things
    [1,(2,3),4,(5,6),7] into [[1,2,4,5,7], [1,2,4,6,7]]
    Where lists are actually dicts, tuples are actually search results,
    and numbers are Issues/PRs/Commits
    """
    last_search = [None]

    for k, candidate in reversed(things.items()):
        if not isinstance(candidate, (Issue, CustomCommit, PTBContrib)):
            last_search = candidate
            break

    out = [OrderedDict() for _ in last_search]

    for k, elem_merged in things.items():
        if elem_merged is last_search:
            for i, elem_last in enumerate(elem_merged):
                out[i][k] = elem_last
        elif not isinstance(elem_merged, (Issue, CustomCommit, PTBContrib)):
            for i, _ in enumerate(out):
                out[i][k] = elem_merged[0]
        else:
            for i, _ in enumerate(out):
                out[i][k] = elem_merged

    return last_search, out


def inline_github(query: str) -> List[InlineQueryResultArticle]:
    """
    Parse query for issues, PRs and commits SHA
    Returns a list of `articles`.

    Examples:
        `ptbcontrib/search` - [(title=🔍 A contrib with search in its description,
                                description=ptbcontrib/that contrib), …]
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
                                    description=#3: search1 result, #10: tenth issue,
                                    #5: search2 result1),
                                   (title= 🔍 Another issue with search2 in it's issue,
                                    description=#3: search1 result, #10, tenth issue,
                                    #6: search2 result2), ... (3 more)]
    """
    # Issues/PRs/Commits
    things: Dict[
        str, Union[Issue, CustomCommit, List[Issue], PTBContrib, List[PTBContrib]]
    ] = OrderedDict()
    results = []

    # Search for Issues, PRs and commits in the query and add them to things
    for match in GITHUB_PATTERN.finditer(query):
        owner, repo, number, sha, search_query, full, ptbcontrib = [
            match.groupdict()[x]
            for x in ('owner', 'repo', 'number', 'sha', 'query', 'full', 'ptbcontrib')
        ]
        # If it's an issue
        if number:
            issue = github_issues.get_issue(int(number), owner, repo)
            if issue:
                things[full] = issue
        # If it's a commit
        elif sha:
            commit = github_issues.get_commit(sha, owner, repo)
            if commit:
                things[full] = commit
        # If it's a search
        elif search_query:
            search_results = github_issues.search(search_query)
            things['#' + search_query] = search_results
        elif ptbcontrib:
            contrib = github_issues.ptbcontribs.get(ptbcontrib)
            if contrib is not None:
                things[full] = contrib
            else:
                contrib_search_results = github_issues.search_ptbcontrib(ptbcontrib)
                things[full] = contrib_search_results

    if not things:
        # We didn't find anything
        return []

    # Unwrap and collapse things
    last_search, choices = unwrap(things)

    # Loop over all the choices we should send to the client
    # Each choice (items) is a dict of things (issues/PRs/commits) to show in that choice
    # If not searching there will only be a single choice
    # If searching we have 5 different possibilities we wanna send
    for i, items in enumerate(choices):
        # If we did a search
        if last_search and last_search[i]:
            # Show the search title as the title
            title = '🔍' + github_issues.pretty_format(
                last_search[i], short_with_title=True, title_max_length=50
            )
        else:
            # Otherwise just use generic title
            title = 'Resolve via GitHub'

        # Description is the short formats combined with ', '
        description = ', '.join(
            github_issues.pretty_format(thing, short_with_title=True) for thing in items.values()
        )

        # Truncate the description to 100 chars, from the left side.
        # So the last thing will always be shown.
        if len(description) > 100:
            description = '⟻' + description[-99:].partition(',')[2]

        # The text that will be sent when user clicks the choice/result
        text = ''
        pattern = r'|'.join(
            re.escape(thing) for thing in sorted(items.keys(), key=len, reverse=True)
        )
        # Check if there's other stuff than issues/PRs etc. in the query by
        # removing issues/PRs etc. and seeing if there's anything left
        if re.sub(pattern, '', query).strip():
            # Replace every 'thing' with a link to said thing *all at once*
            # Needs to all at once because otherwise 'blah/blah#2 #2'
            # would break would turn into something like
            # [blah/blah[#2](LinkFor#2)](LinkForblah/blah[#2](LinkFor#2))
            # which isn't even valid markdown
            text = re.sub(
                pattern,
                lambda x: f'<a href="{items[x.group(0)].html_url}">'  # pylint: disable=W0640
                f'{github_issues.pretty_format(items[x.group(0)], short=True)}</a>',
                query,
            )

        # Add full format to bottom of message
        text += '\n\n' + '\n'.join(
            f'<a href="{thing.html_url}">{github_issues.pretty_format(thing)}</a>'
            for thing in items.values()
        )

        results.append(article(title=title, description=description, message_text=text))

    return results


def inline_query(update: Update, _: CallbackContext, threshold: int = 15) -> None:
    query = cast(InlineQuery, update.inline_query).query
    results_list = list()

    if len(query) > 0:
        if query.startswith('#'):
            hints = taghints.get_hints(query)
            results_list.extend(
                [
                    article(
                        f'Send hint on {key.capitalize()}',
                        hint.help,
                        hint.msg,
                        key=key,
                        reply_markup=hint.reply_markup,
                    )
                    for key, hint in hints.items()
                ]
            )

        if '#' in query or '@' in query or 'ptbcontrib/' in query:
            results_list.extend(inline_github(query))

        if ENCLOSING_REPLACEMENT_CHARACTER in query:
            modified, replaced = fuzzy_replacements_html(query, official_api_links=True)
            assert modified and replaced
            if modified:
                results_list.append(
                    article(
                        title="Replace links and show official Bot API documentation",
                        description=', '.join(modified),
                        message_text=replaced,
                    )
                )

            modified, replaced = fuzzy_replacements_html(query, official_api_links=False)
            assert modified and replaced
            if modified:
                results_list.append(
                    article(
                        title="Replace links",
                        description=', '.join(modified),
                        message_text=replaced,
                    )
                )

        if query.lower() == 'faq':
            for name, link in search.all_faq():
                results_list.append(
                    article(
                        title=name,
                        description='Wiki of python-telegram-bot',
                        message_text=f'Wiki of <i>python-telegram-bot</i>\n'
                        f'<a href="{link}">{escape(name)}</a>',
                    )
                )
        if query.lower().startswith('faq') and len(query.split(' ')) > 1:
            faq = search.faq(query.split(' ', 1)[1], amount=20, threshold=threshold)
            if faq:
                for question in faq:
                    results_list.append(
                        article(
                            title=f'{question[0]}',
                            description="Github wiki for python-telegram-bot",
                            message_text=f'Wiki of <i>python-telegram-bot</i>\n'
                            f'<a href="{question[1]}">{question[0]}</a>',
                        )
                    )

        if query.lower() == 'snippets':
            for name, link in search.all_code_snippets():
                results_list.append(
                    article(
                        title=name,
                        description='Wiki of python-telegram-bot',
                        message_text=f'Wiki of <i>python-telegram-bot</i>\n'
                        f'<a href="{link}">{escape(name)}</a>',
                    )
                )
        if query.lower().startswith('snippets') and len(query.split(' ')) > 1:
            snippets = search.code_snippets(query.split(' ', 1)[1], amount=20, threshold=threshold)
            if snippets:
                for snippet in snippets:
                    results_list.append(
                        article(
                            title=f'{snippet[0]}',
                            description="Github wiki for python-telegram-bot",
                            message_text=f'Wiki of <i>python-telegram-bot</i>\n'
                            f'<a href="{snippet[1]}">{snippet[0]}</a>',
                        )
                    )

        # If no results so far then search wiki and docs
        if not results_list:
            doc = search.docs(query, threshold=threshold)
            if doc:
                text = (
                    f'<b>{doc.short_name}</b>\n'
                    f'<i>python-telegram-bot</i> documentation for this {doc.type}:\n'
                    f'<a href="{doc.url}">{doc.full_name}</a>'
                )
                if doc.tg_name:
                    text += (
                        f'\n\nThe official documentation has more info about '
                        f'<a href="{doc.tg_url}">{doc.tg_name}</a>. '
                    )

                results_list.append(
                    article(
                        title=f'{doc.full_name}',
                        description="python-telegram-bot documentation",
                        message_text=text,
                    )
                )

            wiki_pages = search.wiki(query, amount=4, threshold=threshold)
            if wiki_pages:
                for wiki_page in wiki_pages:
                    results_list.append(
                        article(
                            title=f'{wiki_page[0]}',
                            description="Github wiki for python-telegram-bot",
                            message_text=f'Wiki of <i>python-telegram-bot</i>\n'
                            f'<a href="{wiki_page[1]}">{wiki_page[0]}</a>',
                        )
                    )

        # If no results even after searching wiki and docs
        if not results_list:
            results_list.append(
                article(
                    title='❌ No results.',
                    description='',
                    message_text=f'<a href="{WIKI_URL}">GitHub wiki</a> of '
                    f'<i>python-telegram-bot</i>',
                )
            )

    else:
        for name, link in search.all_wiki_pages():
            results_list.append(
                article(
                    title=name,
                    description='Wiki of python-telegram-bot',
                    message_text=f'Wiki of <i>python-telegram-bot</i>\n'
                    f'<a href="{link}">{escape(name)}</a>',
                )
            )

    cast(InlineQuery, update.inline_query).answer(
        results=results_list,
        switch_pm_text='Help',
        switch_pm_parameter='inline-help',
        cache_time=0,
        auto_pagination=True,
    )


def register(dispatcher: Dispatcher) -> None:
    dispatcher.add_handler(InlineQueryHandler(inline_query))
