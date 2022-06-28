import logging
import re
import threading
from typing import Any, Dict, Iterable, List, Optional, Pattern, Tuple, Union, cast, no_type_check

from github3 import GitHub, login
from github3.exceptions import GitHubException
from github3.repos import Repository as GHRepo
from github3.repos.contents import Contents
from telegram.ext import JobQueue

from components.const import (
    DEFAULT_REPO_NAME,
    DEFAULT_REPO_OWNER,
    EXAMPLES_URL,
    PTBCONTRIB_REPO_NAME,
)
from components.entrytypes import Commit, Issue, PTBContrib


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

    @property
    def all_ptbcontribs(self) -> List[PTBContrib]:
        with self.ptbcontrib_lock:
            return list(self.ptbcontribs.values())

    @property
    def all_issues(self) -> List[Issue]:
        with self.issues_lock:
            return list(self.issues.values())

    def get_issue(self, number: int, owner: str = None, repo: str = None) -> Optional[Issue]:
        if owner or repo:
            self.logger.info(
                "Getting issue %d for %s/%s",
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
                "Getting commit %s for %s/%s",
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

    def _ptbcontrib_job(self, _: JobQueue) -> None:
        self.logger.info("Getting ptbcontrib data.")

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
                        if content.type == "dir"
                    }
                )

            # Rerun in two hours minutes
            # job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 2 * 60 * 60)
        except GitHubException as exc:
            if "rate limit" in str(exc):
                self.logger.warning("GH API rate limit exceeded. Retrying in 70 minutes.")
                # job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 60 * 70)
            else:
                self.logger.exception(
                    "Something went wrong fetching issues. Retrying in 10s.", exc_info=exc
                )
                # job_queue.run_once(lambda _: self._ptbcontrib_job(job_queue), 10)

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
            self.repos[self.default_repo].directory_contents("examples"),
        )
        if effective_pattern is None:
            return [(name, self._build_example_url(name)) for name, _ in files]
        return [
            (name, self._build_example_url(name))
            for name, _ in files
            if effective_pattern.search(name)
        ]


github_issues = GitHubIssues()
