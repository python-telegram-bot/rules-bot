import asyncio
import datetime
import logging
from typing import Dict, Iterable, List, Optional, Tuple, Union, cast

from graphql import GraphQLError
from telegram.ext import ContextTypes, Job, JobQueue

from components.const import DEFAULT_REPO_NAME, DEFAULT_REPO_OWNER, USER_AGENT
from components.entrytypes import Commit, Discussion, Example, Issue, PTBContrib, PullRequest
from components.graphqlclient import GraphQLClient


class GitHub:
    def __init__(self, auth: str, user_agent: str = USER_AGENT) -> None:
        self._gql_client = GraphQLClient(auth=auth, user_agent=user_agent)

        self.logger = logging.getLogger(self.__class__.__qualname__)

        self.issues: Dict[int, Issue] = {}
        self.pull_requests: Dict[int, PullRequest] = {}
        self.discussions: Dict[int, Discussion] = {}
        self.issue_iterator: Optional[Iterable[Issue]] = None
        self.ptb_contribs: Dict[str, PTBContrib] = {}
        self.examples: Dict[str, Example] = {}

    async def initialize(self):
        await self._gql_client.initialize()

    async def shutdown(self):
        await self._gql_client.shutdown()

    @property
    def all_ptbcontribs(self) -> List[PTBContrib]:
        return list(self.ptb_contribs.values())

    @property
    def all_issues(self) -> List[Issue]:
        return list(self.issues.values())

    async def update_examples(self) -> None:
        examples = await self._gql_client.get_examples()
        self.examples.clear()
        for example in examples:
            self.examples[example.short_name] = example

    async def update_ptb_contribs(self) -> None:
        ptb_contribs = await self._gql_client.get_ptb_contribs()
        self.ptb_contribs.clear()
        for ptb_contrib in ptb_contribs:
            self.ptb_contribs[ptb_contrib.short_name.split("/")[1]] = ptb_contrib

    async def update_issues(self, cursor: str = None) -> Optional[str]:
        issues, cursor = await self._gql_client.get_issues(cursor=cursor)
        for issue in issues:
            self.issues[issue.number] = issue
        return cursor

    async def update_pull_requests(self, cursor: str = None) -> Optional[str]:
        pull_requests, cursor = await self._gql_client.get_pull_requests(cursor=cursor)
        for pull_request in pull_requests:
            self.pull_requests[pull_request.number] = pull_request
        return cursor

    async def update_discussions(self, cursor: str = None) -> Optional[str]:
        discussions, cursor = await self._gql_client.get_discussions(cursor=cursor)
        for discussion in discussions:
            self.discussions[discussion.number] = discussion
        return cursor

    async def get_thread(
        self, number: int, owner: str = DEFAULT_REPO_OWNER, repo: str = DEFAULT_REPO_NAME
    ) -> Union[Issue, PullRequest, Discussion, None]:
        if owner != DEFAULT_REPO_OWNER or repo != DEFAULT_REPO_NAME:
            self.logger.info("Getting issue %d for %s/%s", number, owner, repo)
        try:
            thread = await self._gql_client.get_thread(
                number=number, organization=owner, repository=repo
            )

            if owner == DEFAULT_REPO_OWNER and repo == DEFAULT_REPO_NAME:
                if isinstance(thread, Issue):
                    self.issues[thread.number] = thread
                if isinstance(thread, PullRequest):
                    self.pull_requests[thread.number] = thread
                if isinstance(thread, Discussion):
                    self.discussions[thread.number] = thread

            return thread
        except GraphQLError as exc:
            self.logger.exception(
                "Error while getting issue %d for %s/%s", number, owner, repo, exc_info=exc
            )
            return None

    async def get_commit(
        self, sha: str, owner: str = DEFAULT_REPO_OWNER, repo: str = DEFAULT_REPO_NAME
    ) -> Optional[Commit]:
        if owner != DEFAULT_REPO_OWNER or repo != DEFAULT_REPO_NAME:
            self.logger.info("Getting commit %s for %s/%s", sha[:7], owner, repo)
        try:
            return await self._gql_client.get_commit(sha=sha, organization=owner, repository=repo)
        except GraphQLError as exc:
            self.logger.exception(
                "Error while getting commit %s for %s/%s", sha[:7], owner, repo, exc_info=exc
            )
            return None

    async def update_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = cast(Job, context.job)
        cursors = cast(Tuple[Optional[str], Optional[str], Optional[str]], job.data)
        restart = not any(cursors)

        if restart:
            await asyncio.gather(
                context.application.create_task(self.update_examples()),
                context.application.create_task(self.update_ptb_contribs()),
            )

        issue_cursor = (
            await self.update_issues(cursor=cursors[0]) if restart or cursors[0] else None
        )
        pr_cursor = (
            await self.update_pull_requests(cursor=cursors[1]) if restart or cursors[1] else None
        )
        discussion_cursor = (
            await self.update_discussions(cursor=cursors[2]) if restart or cursors[2] else None
        )

        new_cursors = (issue_cursor, pr_cursor, discussion_cursor)
        when = datetime.timedelta(seconds=30) if any(new_cursors) else datetime.timedelta(hours=12)
        cast(JobQueue, context.job_queue).run_once(
            callback=self.update_job, when=when, data=new_cursors
        )
