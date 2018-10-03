import logging
from collections import namedtuple

from bs4 import BeautifulSoup
from requests import Session
from telegram import ParseMode

ARROW_CHARACTER = '➜'
GITHUB_URL = "https://github.com/"
DEFAULT_REPO_OWNER = 'python-telegram-bot'
DEFAULT_REPO_NAME = 'python-telegram-bot'
DEFAULT_REPO = f'{DEFAULT_REPO_OWNER}/{DEFAULT_REPO_NAME}'


def get_reply_id(update):
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.message_id
    return None


def reply_or_edit(bot, update, chat_data, text):
    if update.edited_message:
        chat_data[update.edited_message.message_id].edit_text(text,
                                                              parse_mode=ParseMode.MARKDOWN,
                                                              disable_web_page_preview=True)
    else:
        issued_reply = get_reply_id(update)
        if issued_reply:
            chat_data[update.message.message_id] = bot.sendMessage(update.message.chat_id, text,
                                                                   reply_to_message_id=issued_reply,
                                                                   parse_mode=ParseMode.MARKDOWN,
                                                                   disable_web_page_preview=True)
        else:
            chat_data[update.message.message_id] = update.message.reply_text(text,
                                                                             parse_mode=ParseMode.MARKDOWN,
                                                                             disable_web_page_preview=True)


def get_text_not_in_entities(html):
    soup = BeautifulSoup(html, 'html.parser')
    return ' '.join(soup.find_all(text=True, recursive=False))


def build_menu(buttons,
               n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


Issue = namedtuple('Issue', 'type, owner, repo, number, url, title, author')
Commit = namedtuple('Commit', 'owner, repo, sha, url, title, author')


class GitHubIssues:
    def __init__(self, default_owner=DEFAULT_REPO_OWNER, default_repo=DEFAULT_REPO_NAME):
        self.s = Session()
        self.s.headers.update({'user-agent': 'bvanrijn/rules-bot'})
        self.base_url = 'https://api.github.com/'
        self.default_owner = default_owner
        self.default_repo = default_repo

        self.logger = logging.getLogger(self.__class__.__qualname__)

        self.etag = None
        self.issues = {}

    def set_auth(self, client_id, client_secret):
        self.s.params = {
            'client_id': client_id,
            'client_secret': client_secret
        }

    def _get_json(self, url, data=None, headers=None):
        # Add base_url if needed
        url = url if url.startswith('https://') or url.startswith('http') else self.base_url + url
        self.logger.info('Getting %s', url)
        r = self.s.get(url, params=data, headers=headers)
        self.logger.debug('status_code=%d', r.status_code)
        # Only try .json() if we actually got new data
        return r.ok, None if r.status_code == 304 else r.json(), (r.headers, r.links)

    def pretty_format_issue(self, issue):
        # PR OwnerIfNotDefault/RepoIfNotDefault#9999: Title by Author
        return (f'{issue.type} '
                f'{"" if issue.owner == self.default_owner else issue.owner+"/"}'
                f'{"" if issue.repo == self.default_repo else issue.repo}'
                f'#{issue.number}: '
                f'{issue.title} by {issue.author}')

    def pretty_format_commit(self, commit):
        # Commit OwnerIfNotDefault/RepoIfNotDefault@abcdf123456789: Title by Author
        return (f'Commit '
                f'{"" if commit.owner == self.default_owner else commit.owner+"/"}'
                f'{"" if commit.repo == self.default_repo else commit.repo}'
                f'@{commit.sha}: '
                f'{commit.title} by {commit.author}')

    def get_issue(self,
                  number: int,
                  owner=None,
                  repo=None):
        # Other owner or repo than default?
        if owner is not None or repo is not None:
            owner = owner or self.default_owner
            repo = repo or self.default_repo
            ok, data, _ = self._get_json(f'repos/{owner}/{repo}/issues/{number}')
            # Return issue directly, or unknown if not found
            return Issue(type=('PR' if 'pull_request' in data else 'Issue') if ok else '',
                         owner=owner,
                         repo=repo,
                         number=number,
                         url=data['html_url'] if ok else f'https://github.com/{owner}/{repo}/issues/{number}',
                         title=data['title'] if ok else 'Unknown',
                         author=data['user']['login'] if ok else 'Unknown')

        # Look the issue up, or if not found, fall back on above code
        return self.issues.get(number, self.get_issue(number, owner=self.default_owner, repo=self.default_repo))

    def get_commit(self,
                   sha: int,
                   owner=None,
                   repo=None):
        owner = owner or self.default_owner
        repo = repo or self.default_repo
        ok, data, _ = self._get_json(f'repos/{owner}/{repo}/commits/{sha}')
        return Commit(owner=owner,
                      repo=repo,
                      sha=sha,
                      url=data['html_url'] if ok else f'https://github.com/{owner}/{repo}/commits/{sha}',
                      title=data['commit']['message'].partition('\n')[0] if ok else 'Unknown',
                      author=data['commit']['author']['name'] if ok else 'Unknown')

    def _job(self, url, job_queue, first=True):
        logging.debug('Getting issues from %s', url)

        # Load 100 issues
        # We pass the ETag if we have one (not called from init_issues)
        ok, data, (modified, headers, links) = self._get_json(url, {
            'per_page': 100,
            'state': 'all'
        }, {'If-None-Match': self.etag} if self.etag else None)

        # If we got status_code 304 not modified
        if not data:
            return

        if not ok:
            logging.error('Something went broke :(')
            return

        # Add to issue cache
        for issue in data:
            self.issues[issue['number']] = Issue(type='PR' if 'pull_request' in issue else 'Issue',
                                                 owner=self.default_owner,
                                                 repo=self.default_repo,
                                                 url=issue['html_url'],
                                                 number=issue['number'],
                                                 title=issue['title'],
                                                 author=issue['user']['login'])

        # If more issues
        if 'next' in links:
            # Process next page after 5 sec to not get rate-limited
            job_queue.run_once(lambda: self._job(links['next']['url'], job_queue), 5)
        # No more issues
        else:
            # Add a job that every 10 min checks if the 100 first issues changed, and update them in our cache if needed
            job_queue.run_repeating(lambda: self._job(links['first']['url'], job_queue, first=True), interval=10 * 60)

        # If this is on page one (first) then we wanna save the header
        if first:
            self.etag = headers['etag']

    def init_issues(self, job_queue):
        self._job(f'repos/{self.default_owner}/{self.default_repo}/issues', job_queue, first=True)


github_issues = GitHubIssues()
