import logging
import threading
from collections import namedtuple
from functools import wraps
from typing import Optional, List, Union, Callable, Any, TypeVar, Dict, no_type_check, cast

import requests
from bs4 import BeautifulSoup
from fuzzywuzzy import process, fuzz
from requests import Session
from telegram import Update, InlineKeyboardButton, Message
from telegram.ext import CallbackContext, JobQueue

from .const import USER_AGENT, DEFAULT_REPO_OWNER, DEFAULT_REPO_NAME, RATE_LIMIT_SPACING


def get_reply_id(update: Update) -> Optional[int]:
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.message_id
    return None


def reply_or_edit(update: Update, context: CallbackContext, text: str) -> None:
    chat_data = cast(Dict, context.chat_data)
    if update.edited_message:
        chat_data[update.edited_message.message_id].edit_text(text, disable_web_page_preview=True)
    else:
        message = cast(Message, update.message)
        issued_reply = get_reply_id(update)
        if issued_reply:
            chat_data[message.message_id] = context.bot.send_message(
                message.chat_id,
                text,
                reply_to_message_id=issued_reply,
                disable_web_page_preview=True,
            )
        else:
            chat_data[message.message_id] = message.reply_text(text, disable_web_page_preview=True)


def get_text_not_in_entities(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    return ' '.join(soup.find_all(text=True, recursive=False))


def build_menu(
    buttons: List[InlineKeyboardButton],
    n_cols: int,
    header_buttons: List[InlineKeyboardButton] = None,
    footer_buttons: List[InlineKeyboardButton] = None,
) -> List[List[InlineKeyboardButton]]:
    menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


def rate_limit_tracker(_: Update, context: CallbackContext) -> None:
    data = cast(Dict, context.chat_data).setdefault('rate_limit', {})

    for key in data.keys():
        data[key] += 1


Func = TypeVar('Func', bound=Callable[[Update, CallbackContext], None])


def rate_limit(
    func: Callable[[Update, CallbackContext], None]
) -> Callable[[Update, CallbackContext], None]:
    """
    Rate limit command so that RATE_LIMIT_SPACING non-command messages are
    required between invocations.
    """

    @wraps(func)
    def wrapper(update: Update, context: CallbackContext) -> None:
        # Get rate limit data
        try:
            data = cast(Dict, context.chat_data)['rate_limit']
        except KeyError:
            data = cast(Dict, context.chat_data)['rate_limit'] = {}

        # If we have not seen two non-command messages since last of type `f`
        if data.get(func, RATE_LIMIT_SPACING) < RATE_LIMIT_SPACING:
            logging.debug('Ignoring due to rate limit!')
            return None

        data[func] = 0

        return func(update, context)

    return wrapper


def truncate_str(string: str, max_length: int) -> str:
    return (string[:max_length] + '…') if len(string) > max_length else string


Issue = namedtuple('Issue', 'type, owner, repo, number, url, title, author')
Commit = namedtuple('Commit', 'owner, repo, sha, url, title, author')


class GitHubIssues:
    def __init__(
        self, default_owner: str = DEFAULT_REPO_OWNER, default_repo: str = DEFAULT_REPO_NAME
    ) -> None:
        self.session = Session()
        self.session.headers.update({'user-agent': USER_AGENT})
        self.base_url = 'https://api.github.com/'
        self.default_owner = default_owner
        self.default_repo = default_repo

        self.logger = logging.getLogger(self.__class__.__qualname__)

        self.etag = None
        self.issues: Dict[int, Issue] = {}
        self.issues_lock = threading.Lock()

    def set_auth(self, client_id: str, client_secret: str) -> None:
        self.session.auth = (client_id, client_secret)

    @no_type_check
    def _get_json(self, url: str, data: Dict[str, Any] = None, headers: str = None):
        # Add base_url if needed
        url = url if url.startswith('https://') else self.base_url + url
        self.logger.info('Getting %s', url)
        try:
            result = self.session.get(url, params=data, headers=headers)
        except requests.exceptions.RequestException as exc:
            self.logger.exception('While getting %s with data %s', url, data, exec_info=exc)
            return False, None, (None, None)
        self.logger.debug('status_code=%d', result.status_code)
        if not result.ok:
            self.logger.error('Not OK: %s', result.text)
        # Only try .json() if we actually got new data
        return (
            result.ok,
            None if result.status_code == 304 else result.json(),
            (result.headers, result.links),
        )

    def pretty_format(
        self,
        thing: Union[Issue, Commit],
        short: bool = False,
        short_with_title: bool = False,
        title_max_length: int = 15,
    ) -> str:
        if isinstance(thing, Issue):
            return self.pretty_format_issue(
                thing,
                short=short,
                short_with_title=short_with_title,
                title_max_length=title_max_length,
            )
        return self.pretty_format_commit(
            thing,
            short=short,
            short_with_title=short_with_title,
            title_max_length=title_max_length,
        )

    def pretty_format_issue(
        self,
        issue: Issue,
        short: bool = False,
        short_with_title: bool = False,
        title_max_length: int = 15,
    ) -> str:
        # PR OwnerIfNotDefault/RepoIfNotDefault#9999: Title by Author
        # OwnerIfNotDefault/RepoIfNotDefault#9999 if short=True
        short_text = (
            f'{"" if issue.owner == self.default_owner else issue.owner + "/"}'
            f'{"" if issue.repo == self.default_repo else issue.repo}'
            f'#{issue.number}'
        )
        if short:
            return short_text
        if short_with_title:
            return f'{short_text}: {truncate_str(issue.title, title_max_length)}'
        return f'{issue.type} {short_text}: {issue.title} by {issue.author}'

    def pretty_format_commit(
        self,
        commit: Commit,
        short: bool = False,
        short_with_title: bool = False,
        title_max_length: int = 15,
    ) -> str:
        # Commit OwnerIfNotDefault/RepoIfNotDefault@abcdf123456789: Title by Author
        # OwnerIfNotDefault/RepoIfNotDefault@abcdf123456789 if short=True
        short_text = (
            f'{"" if commit.owner == self.default_owner else commit.owner + "/"}'
            f'{"" if commit.repo == self.default_repo else commit.repo}'
            f'@{commit.sha[:7]}'
        )
        if short:
            return short_text
        if short_with_title:
            return f'{short_text}: {truncate_str(commit.title, title_max_length)}'
        return f'Commit {short_text}: {commit.title} by {commit.author}'

    @no_type_check
    def get_issue(self, number: int, owner: str = None, repo: str = None) -> Issue:
        # Other owner or repo than default?
        if owner is not None or repo is not None:
            owner = owner or self.default_owner
            repo = repo or self.default_repo
            status, data, _ = self._get_json(f'repos/{owner}/{repo}/issues/{number}')
            # Return issue directly, or unknown if not found
            return Issue(
                type=('PR' if 'pull_request' in data else 'Issue') if status else '',
                owner=owner,
                repo=repo,
                number=number,
                url=data['html_url']
                if status
                else f'https://github.com/{owner}/{repo}/issues/{number}',
                title=data['title'] if status else 'Unknown',
                author=data['user']['login'] if status else 'Unknown',
            )

        # Look the issue up, or if not found, fall back on above code
        try:
            return self.issues[number]
        except KeyError:
            return self.get_issue(number, owner=self.default_owner, repo=self.default_repo)

    @no_type_check
    def get_commit(self, sha: Union[int, str], owner: str = None, repo: str = None) -> Commit:
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        status, data, _ = self._get_json(f'repos/{owner}/{repo}/commits/{sha}')
        return Commit(
            owner=owner,
            repo=repo,
            sha=sha,
            url=data['html_url'] if status else f'https://github.com/{owner}/{repo}/commits/{sha}',
            title=data['commit']['message'].partition('\n')[0] if status else 'Unknown',
            author=data['commit']['author']['name'] if status else 'Unknown',
        )

    @no_type_check
    def _job(self, url: str, job_queue: JobQueue, first: bool = True) -> None:
        logging.debug('Getting issues from %s', url)

        # Load 100 issues
        # We pass the ETag if we have one (not called from init_issues)
        status, data, (headers, links) = self._get_json(
            url,
            {'per_page': 100, 'state': 'all'},
            {'If-None-Match': self.etag} if self.etag else None,
        )

        if status and data:
            # Add to issue cache
            # Acquire lock so we don't add while a func (like self.search) is iterating over it
            with self.issues_lock:
                for issue in data:
                    self.issues[issue['number']] = Issue(
                        type='PR' if 'pull_request' in issue else 'Issue',
                        owner=self.default_owner,
                        repo=self.default_repo,
                        url=issue['html_url'],
                        number=issue['number'],
                        title=issue['title'],
                        author=issue['user']['login'],
                    )
        elif not status:
            # Retry in 5 sec
            job_queue.run_once(lambda _: self._job(url, job_queue), 5)
            return

        # If more issues
        if 'next' in links:
            # Process next page after 5 sec to not get rate-limited
            job_queue.run_once(lambda _: self._job(links['next']['url'], job_queue), 5)
        # No more issues
        else:
            # In 10 min check if the 100 first issues changed,
            # and update them in our cache if needed
            job_queue.run_once(
                lambda _: self._job(links['first']['url'], job_queue, first=True), 10 * 60
            )

        # If this is on page one (first) then we wanna save the header
        if first:
            self.etag = headers['etag']

    def init_issues(self, job_queue: JobQueue) -> None:
        self._job(f'repos/{self.default_owner}/{self.default_repo}/issues', job_queue, first=True)

    def search(self, query: str) -> List[str]:
        def processor(str_or_issue: Union[str, Issue]) -> str:
            string = str_or_issue.title if isinstance(str_or_issue, Issue) else str_or_issue
            return string.strip().lower()

        # We don't care about the score, so return first element
        # This must not happen while updating the self.issues dict so acquire the lock
        with self.issues_lock:
            return [
                result[0]
                for result in process.extract(
                    query, self.issues, scorer=fuzz.partial_ratio, processor=processor, limit=1000
                )
            ]


github_issues = GitHubIssues()
