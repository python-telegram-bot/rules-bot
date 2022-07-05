import asyncio
import logging
from typing import Dict, Iterable, List, Optional, Union

from graphql import GraphQLError

from components.const import DEFAULT_REPO_NAME, DEFAULT_REPO_OWNER, USER_AGENT
from components.entrytypes import Commit, Discussion, Example, Issue, PTBContrib, PullRequest
from components.graphqlclient import GraphQLClient


class GitHub:
    def __init__(self, auth: str, user_agent: str = USER_AGENT) -> None:
        self._gql_client = GraphQLClient(auth=auth, user_agent=user_agent)

        self._logger = logging.getLogger(self.__class__.__qualname__)

        self.__lock = asyncio.Lock()
        self.issues: Dict[int, Issue] = {}
        self.pull_requests: Dict[int, PullRequest] = {}
        self.discussions: Dict[int, Discussion] = {}
        self.issue_iterator: Optional[Iterable[Issue]] = None
        self.ptb_contribs: Dict[str, PTBContrib] = {}
        self.examples: Dict[str, Example] = {}

    async def initialize(self) -> None:
        await self._gql_client.initialize()

    async def shutdown(self) -> None:
        await self._gql_client.shutdown()

    @property
    def all_ptbcontribs(self) -> List[PTBContrib]:
        return list(self.ptb_contribs.values())

    @property
    def all_issues(self) -> List[Issue]:
        return list(self.issues.values())

    @property
    def all_pull_requests(self) -> List[PullRequest]:
        return list(self.pull_requests.values())

    @property
    def all_discussions(self) -> List[Discussion]:
        return list(self.discussions.values())

    @property
    def all_examples(self) -> List[Example]:
        return list(self.examples.values())

    async def update_examples(self) -> None:
        self._logger.info("Getting examples")
        examples = await self._gql_client.get_examples()
        async with self.__lock:
            self.examples.clear()
            for example in examples:
                self.examples[example.short_name] = example

    async def update_ptb_contribs(self) -> None:
        self._logger.info("Getting ptbcontribs")
        ptb_contribs = await self._gql_client.get_ptb_contribs()
        async with self.__lock:
            self.ptb_contribs.clear()
            for ptb_contrib in ptb_contribs:
                self.ptb_contribs[ptb_contrib.short_name.split("/")[1]] = ptb_contrib

    async def update_issues(self, cursor: str = None) -> Optional[str]:
        self._logger.info("Getting 100 issues before cursor %s", cursor)
        issues, cursor = await self._gql_client.get_issues(cursor=cursor)
        async with self.__lock:
            for issue in issues:
                self.issues[issue.number] = issue
            return cursor

    async def update_pull_requests(self, cursor: str = None) -> Optional[str]:
        self._logger.info("Getting 100 pull requests before cursor %s", cursor)
        pull_requests, cursor = await self._gql_client.get_pull_requests(cursor=cursor)
        async with self.__lock:
            for pull_request in pull_requests:
                self.pull_requests[pull_request.number] = pull_request
            return cursor

    async def update_discussions(self, cursor: str = None) -> Optional[str]:
        self._logger.info("Getting 100 discussions before cursor %s", cursor)
        discussions, cursor = await self._gql_client.get_discussions(cursor=cursor)
        async with self.__lock:
            for discussion in discussions:
                self.discussions[discussion.number] = discussion
            return cursor

    async def get_thread(
        self, number: int, owner: str = DEFAULT_REPO_OWNER, repo: str = DEFAULT_REPO_NAME
    ) -> Union[Issue, PullRequest, Discussion, None]:
        if owner != DEFAULT_REPO_OWNER or repo != DEFAULT_REPO_NAME:
            self._logger.info("Getting issue %d for %s/%s", number, owner, repo)
        try:
            thread = await self._gql_client.get_thread(
                number=number, organization=owner, repository=repo
            )

            if owner == DEFAULT_REPO_OWNER and repo == DEFAULT_REPO_NAME:
                async with self.__lock:
                    if isinstance(thread, Issue):
                        self.issues[thread.number] = thread
                    if isinstance(thread, PullRequest):
                        self.pull_requests[thread.number] = thread
                    if isinstance(thread, Discussion):
                        self.discussions[thread.number] = thread

            return thread
        except GraphQLError as exc:
            self._logger.exception(
                "Error while getting issue %d for %s/%s", number, owner, repo, exc_info=exc
            )
            return None

    async def get_commit(
        self, sha: str, owner: str = DEFAULT_REPO_OWNER, repo: str = DEFAULT_REPO_NAME
    ) -> Optional[Commit]:
        if owner != DEFAULT_REPO_OWNER or repo != DEFAULT_REPO_NAME:
            self._logger.info("Getting commit %s for %s/%s", sha[:7], owner, repo)
        try:
            return await self._gql_client.get_commit(sha=sha, organization=owner, repository=repo)
        except GraphQLError as exc:
            self._logger.exception(
                "Error while getting commit %s for %s/%s", sha[:7], owner, repo, exc_info=exc
            )
            return None
