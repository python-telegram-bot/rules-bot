import logging
import threading
from typing import Dict, NamedTuple, Union, Optional, no_type_check, List

from fuzzywuzzy import process, fuzz
from github import Github, GithubException
from github.Commit import Commit
from github.Issue import Issue
from github.Organization import Organization
from github.Repository import Repository
from telegram.ext import JobQueue

from components.const import DEFAULT_REPO_OWNER, DEFAULT_REPO_NAME, USER_AGENT
from components.util import truncate_str


class RepoDict(Dict[str, Repository]):
    def __init__(self, org: Organization):
        super().__init__()
        self.org = org

    def __missing__(self, key: str) -> Repository:
        return self.org.get_repo(key)


class CustomCommit(NamedTuple):
    commit: Commit
    owner: str
    repo: str


class GitHubIssues:
    def __init__(
        self, default_owner: str = DEFAULT_REPO_OWNER, default_repo: str = DEFAULT_REPO_NAME
    ) -> None:
        self.session = Github(user_agent=USER_AGENT, per_page=100)
        self.default_owner = default_owner
        self.default_repo = default_repo
        self.default_org = self.session.get_organization(self.default_owner)

        self.logger = logging.getLogger(self.__class__.__qualname__)

        self.repos = RepoDict(self.default_org)
        self.issues: Dict[int, Issue] = {}
        self.issues_lock = threading.Lock()

    def set_auth(self, client_id: str, client_secret: str) -> None:
        self.session = Github(client_id, client_secret, user_agent=USER_AGENT, per_page=100)

    def pretty_format(
        self,
        thing: Union[Issue, CustomCommit],
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
        owner_name = issue.repository.owner.name or issue.repository.owner.login
        user_name = issue.user.name or issue.user.login
        issue_type = 'Issue' if not issue.pull_request else 'PR'
        short_text = (
            f'{"" if owner_name == self.default_owner else owner_name + "/"}'
            f'{"" if issue.repository.name == self.default_repo else issue.repository.name}'
            f'#{issue.number}'
        )
        if short:
            return short_text
        if short_with_title:
            return f'{short_text}: {truncate_str(issue.title, title_max_length)}'
        return f'{issue_type} {short_text}: {issue.title} by {user_name}'

    def pretty_format_commit(
        self,
        commit: CustomCommit,
        short: bool = False,
        short_with_title: bool = False,
        title_max_length: int = 15,
    ) -> str:
        # Commit OwnerIfNotDefault/RepoIfNotDefault@abcdf123456789: Title by Author
        # OwnerIfNotDefault/RepoIfNotDefault@abcdf123456789 if short=True
        author = commit.commit.author.name or commit.commit.author.login
        short_text = (
            f'{"" if commit.owner == self.default_owner else commit.owner + "/"}'
            f'{"" if commit.repo == self.default_repo else commit.repo}'
            f'@{commit.commit.sha[:7]}'
        )
        if short:
            return short_text
        if short_with_title:
            return f'{short_text}: {truncate_str(commit.commit.commit.message, title_max_length)}'
        return f'Commit {short_text}: {commit.commit.commit.message} by {author}'

    def get_issue(self, number: int, owner: str = None, repo: str = None) -> Optional[Issue]:
        try:
            if owner is not None:
                repository = self.session.get_repo(f'{owner}/{repo or self.default_repo}')
                return repository.get_issue(number)

            repository = self.repos[repo or self.default_repo]
            if repo is None:
                return self.issues.setdefault(number, repository.get_issue(number))
            return repository.get_issue(number)
        except GithubException:
            return None

    @no_type_check
    def get_commit(
        self, sha: Union[int, str], owner: str = None, repo: str = None
    ) -> Optional[CustomCommit]:
        try:
            if owner is None:
                repository = self.repos[repo or self.default_repo]
            else:
                repository = self.session.get_repo(f'{owner}/{repo or self.default_repo}')
            return CustomCommit(
                repository.get_commit(sha), owner or self.default_owner, repo or self.default_repo
            )
        except GithubException:
            return None

    @no_type_check
    def _job(self, job_queue: JobQueue, page: int = 0) -> None:
        logging.info('Getting issues for page %d', page)

        # Load 100 issues
        # We pass the ETag if we have one (not called from init_issues)
        try:
            issue_paginator = self.repos[self.default_repo].get_issues(state='all')
            issues = issue_paginator.get_page(page)

            # Add to issue cache
            # Acquire lock so we don't add while a func (like self.search) is iterating over it
            with self.issues_lock:
                for issue in issues:
                    self.issues[issue.number] = issue
        except GithubException:
            # Retry in 5 sec
            job_queue.run_once(lambda _: self._job(job_queue, page), 5)
            return

        # If more issues
        if issue_paginator.totalCount > page * 100:
            # Process next page after 5 sec to not get rate-limited
            job_queue.run_once(lambda _: self._job(job_queue, page + 1), 5)
        # No more issues
        else:
            # In 10 min check if the 100 first issues changed,
            # and update them in our cache if needed
            job_queue.run_once(lambda _: self._job(job_queue), 10 * 60)

    def init_issues(self, job_queue: JobQueue) -> None:
        self._job(job_queue)

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


github_issues = GitHubIssues()
