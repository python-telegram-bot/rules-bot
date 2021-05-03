import logging
import re
import threading
import time
from typing import (
    Dict,
    NamedTuple,
    Union,
    Optional,
    no_type_check,
    List,
    Pattern,
    Tuple,
    Any,
    cast,
    Iterable,
)

from fuzzywuzzy import process, fuzz
from github3.repos.contents import Contents
from github3 import login, GitHub
from github3.exceptions import GitHubException
from github3.git import Commit as GHCommit
from github3.repos import Repository as GHRepo
from github3.issues import Issue as GHIssue
from github3.structs import GitHubIterator
from telegram.ext import JobQueue

from components.const import (
    DEFAULT_REPO_OWNER,
    DEFAULT_REPO_NAME,
    PTBCONTRIB_REPO_NAME,
    EXAMPLES_URL,
)
from components.util import truncate_str


class RepoDict(Dict[str, GHRepo]):
    def __init__(self, owner: str, session: GitHub):
        super().__init__()
        self._owner = owner
        self._session = session

    def __missing__(self, key: str) -> GHRepo:
        if key not in self:
            self[key] = self._session.repository(self._owner, key)
        return self[key]

    def update_session(self, session: GitHub) -> None:
        self._session = session


class Commit:
    def __init__(self, commit: GHCommit, repository: GHRepo) -> None:
        self._commit = commit
        self._repository = repository

    @property
    def owner(self) -> str:
        return self._repository.owner.login

    @property
    def repo(self) -> str:
        return self._repository.name

    @property
    def sha(self) -> str:
        return self._commit.sha

    @property
    def url(self) -> str:
        return self._commit.html_url

    @property
    def title(self) -> str:
        return self._commit.message

    @property
    def author(self) -> str:
        return self._commit.author.login


class Issue:
    def __init__(self, issue: GHIssue, repository: GHRepo) -> None:
        self._issue = issue
        self._repository = repository

    @property
    def type(self) -> str:
        return 'Issue' if not self._issue.pull_request_urls else 'PR'

    @property
    def owner(self) -> str:
        return self._repository.owner.login

    @property
    def repo(self) -> str:
        return self._repository.name

    @property
    def number(self) -> int:
        return self._issue.number

    @property
    def url(self) -> str:
        return self._issue.html_url

    @property
    def title(self) -> str:
        return self._issue.title

    @property
    def author(self) -> str:
        return self._issue.user.login


class PTBContrib(NamedTuple):
    name: str
    url: str


class GitHubIssues:
    def __init__(
        self, default_owner: str = DEFAULT_REPO_OWNER, default_repo: str = DEFAULT_REPO_NAME
    ) -> None:
        self.session = GitHub()
        self.default_owner = default_owner
        self.default_repo = default_repo

        self.logger = logging.getLogger(self.__class__.__qualname__)

        self.repos = RepoDict(self.default_owner, self.session)
        self.issues: Dict[int, Issue] = {}
        self.issue_iterator: Optional[Iterable[Issue]] = None
        self.ptbcontribs: Dict[str, PTBContrib] = {}
        self.issues_lock = threading.Lock()
        self.ptbcontrib_lock = threading.Lock()

    def set_auth(self, client_id: str, client_secret: str) -> None:
        self.session = login(client_id, client_secret)
        self.repos.update_session(self.session)

    def pretty_format(
        self,
        thing: Union[Issue, Commit, PTBContrib],
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
        if isinstance(thing, PTBContrib):
            return f'ptbcontrib/{thing.name}'
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

    def get_issue(self, number: int, owner: str = None, repo: str = None) -> Optional[Issue]:
        if owner or repo:
            self.logger.info(
                'Getting issue %d for %s/%s',
                number,
                owner or self.default_owner,
                repo or self.default_repo,
            )
        try:
            if owner is not None:
                repository = self.session.repository(owner, repo or self.default_repo)
                gh_issue = repository.issue(number)
            else:
                repository = self.repos[repo or self.default_repo]
                if repo is None:
                    if issue := self.issues.get(number):
                        return issue
                    gh_issue = repository.issue(number)
                else:
                    gh_issue = repository.issue(number)
            issue = Issue(gh_issue, repository)

            if repo is None:
                self.issues[number] = issue

            return issue
        except GitHubException:
            return None

    @no_type_check
    def get_commit(
        self, sha: Union[int, str], owner: str = None, repo: str = None
    ) -> Optional[Commit]:
        if owner or repo:
            self.logger.info(
                'Getting commit %s for %s/%s',
                sha[:7],
                owner or self.default_owner,
                repo or self.default_repo,
            )
        try:
            if owner is not None:
                repository = self.session.repository(owner, repo or self.default_repo)
                gh_commit = repository.commit(sha)
            else:
                repository = self.repos[repo or self.default_repo]
                if repo is None:
                    if commit := self.issues.get(sha):
                        return commit
                    gh_commit = sha, repository.commit(sha)
                else:
                    gh_commit = repository.commit(sha)
            return Commit(gh_commit, repository)
        except GitHubException:
            return None

    def _job(self, job_queue: JobQueue) -> None:
        self.logger.info('Getting issues for default repo.')

        try:
            repo = self.repos[self.default_repo]
            if self.issue_iterator is None:
                self.issue_iterator = self.repos[self.default_repo].issues(state='all')
            else:
                # The GitHubIterator automatically takes care of passing the ETag
                # which reduces the number of API requests that count towards the rate limit
                cast(GitHubIterator, self.issue_iterator).refresh(True)

            for i, gh_issue in enumerate(self.issue_iterator):
                # Acquire lock so we don't add while a func (like self.search) is iterating over it
                # We do this for ever single issue instead of before the for-loop, because that
                # would block self.search during the loop which takes a while
                with self.issues_lock:
                    self.issues[gh_issue.number] = Issue(gh_issue, repo)
                # Sleeping a moment after 100 issues to give the API some rest - we're not in a
                # hurry. The 100 is the max. per page number and as of 2.0.0 what github3.py
                # uses. sleeping doesn't block the bot, as jobs run in their own thread.
                # This is outside the lock! (see above commit)
                if (i + 1) % 100 == 0:
                    self.logger.info('Done with %d issues. Sleeping a moment.', i + 1)
                    time.sleep(10)

            # Rerun in 20 minutes
            job_queue.run_once(lambda _: self._job(job_queue), 60 * 20)
        except GitHubException as exc:
            if 'rate limit' in str(exc):
                self.logger.warning('GH API rate limit exceeded. Retrying in 70 minutes.')
                job_queue.run_once(lambda _: self._job(job_queue), 60 * 70)
            else:
                self.logger.exception(
                    'Something went wrong fetching issues. Retrying in 10s.', exc_info=exc
                )
                job_queue.run_once(lambda _: self._job(job_queue), 10)

    def init_issues(self, job_queue: JobQueue) -> None:
        job_queue.run_once(lambda _: self._job(job_queue), 10)

    def _ptbcontrib_job(self, job_queue: JobQueue) -> None:
        self.logger.info('Getting ptbcontrib data.')

        try:
            files = cast(
                List[Tuple[str, Contents]],
                self.repos[PTBCONTRIB_REPO_NAME].directory_contents(PTBCONTRIB_REPO_NAME),
            )
            with self.ptbcontrib_lock:
                self.ptbcontribs.clear()
                self.ptbcontribs.update(
                    {
                        name: PTBContrib(name, content.html_url)
                        for name, content in files
                        if content.type == 'dir'
                    }
                )

            # Rerun in two hours minutes
            job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 2 * 60 * 60)
        except GitHubException as exc:
            if 'rate limit' in str(exc):
                self.logger.warning('GH API rate limit exceeded. Retrying in 70 minutes.')
                job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 60 * 70)
            else:
                self.logger.exception(
                    'Something went wrong fetching issues. Retrying in 10s.', exc_info=exc
                )
                job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 10)

    def init_ptb_contribs(self, job_queue: JobQueue) -> None:
        job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 5)

    def search(self, query: str) -> List[Issue]:
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

    def search_ptbcontrib(self, query: str) -> List[PTBContrib]:
        def processor(str_or_contrib: PTBContrib) -> str:
            string = (
                str_or_contrib.name if isinstance(str_or_contrib, PTBContrib) else str_or_contrib
            )
            return string.strip().lower().replace('_', '')

        # We don't care about the score, so return first element
        # This must not happen while updating the self.issues dict so acquire the lock
        with self.ptbcontrib_lock:
            return [
                result[0]
                for result in process.extract(
                    query,
                    self.ptbcontribs,
                    scorer=fuzz.partial_ratio,
                    processor=processor,
                    limit=1000,
                )
            ]

    @staticmethod
    def _build_example_url(example_file_name: str) -> str:
        return f'{EXAMPLES_URL}#{example_file_name.replace(".", "")}'

    def get_examples_directory(self, pattern: Union[str, Pattern] = None) -> List[Tuple[str, str]]:
        if isinstance(pattern, str):
            effective_pattern: Optional[Pattern[Any]] = re.compile(pattern)
        else:
            effective_pattern = pattern

        files = cast(
            List[Tuple[str, Contents]],
            self.repos[self.default_repo].directory_contents('examples'),
        )
        if effective_pattern is None:
            return [(name, self._build_example_url(name)) for name, _ in files]
        return [
            (name, self._build_example_url(name))
            for name, _ in files
            if effective_pattern.search(name)
        ]


github_issues = GitHubIssues()
