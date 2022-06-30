from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from gql import Client, gql
from gql.client import AsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError

from components.const import DEFAULT_REPO_NAME, DEFAULT_REPO_OWNER, PTBCONTRIB_LINK, USER_AGENT
from components.entrytypes import Commit, Discussion, Example, Issue, PTBContrib, PullRequest


class GraphQLClient:
    def __int__(self, auth: str, user_agent: str = USER_AGENT) -> None:
        self._transport = AIOHTTPTransport(
            url="https://api.github.com/graphql",
            headers={
                "Authorization": auth,
                "user-agent": user_agent,
            },
        )
        self._session = AsyncClientSession(Client(transport=self._transport))

    async def initialize(self) -> None:
        await self._transport.connect()

    async def shutdown(self) -> None:
        await self._transport.close()

    async def _do_request(
        self, query_name: str, variable_values: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        return await self._session.execute(
            gql(Path(f"components/graphql_queries/{query_name}").read_text(encoding="utf-8")),
            variable_values=variable_values,
        )

    async def get_examples(self) -> List[Example]:
        """The all examples on the master branch"""
        result = await self._do_request("getExamples")
        return [
            Example(name=file["name"])
            for file in result["repository"]["object"]["entries"]
            if file["name"].endswith(".py")
        ]

    async def get_ptb_contribs(self) -> List[PTBContrib]:
        """The all ptb_contribs on the main branch"""
        result = await self._do_request("getPTBContribs")
        return [
            PTBContrib(name=contrib["name"], url=f"{PTBCONTRIB_LINK}tree/main/{contrib['name']}")
            for contrib in result["repository"]["object"]["entries"]
            if contrib["type"] == "tree"
        ]

    async def get_thread(
        self,
        number: int,
        organization: str = DEFAULT_REPO_OWNER,
        repository: str = DEFAULT_REPO_NAME,
    ) -> Union[Issue, PullRequest, Discussion]:
        """Get a specific thread (issue/pr/discussion) on any repository. By default, ptb/ptb
        will be searched"""
        # The try-except is needed because we query for both issueOrPR & discussion at the same
        # time, but it will only ever be one of them. Unfortunately we don't know which one …
        try:
            result = await self._do_request(
                "getThread",
                variable_values={
                    "number": number,
                    "organization": organization,
                    "repository": repository,
                },
            )
        except TransportQueryError as exc:
            if not exc.data:
                raise exc
            result = exc.data

        data = result["repository"]
        if data["issueOrPullRequest"]:
            thread_data = data["issueOrPullRequest"]
        else:
            thread_data = data["discussion"]

        entry_type_data = dict(
            owner=organization,
            repo=repository,
            number=number,
            title=thread_data["title"],
            url=thread_data["url"],
            author=thread_data["author"]["login"],
        )

        if thread_data.get("__typename") == "Issue":
            return Issue(**entry_type_data)
        if thread_data.get("__typename") == "PullRequest":
            return PullRequest(**entry_type_data)
        return Discussion(**entry_type_data)

    async def get_commit(
        self,
        sha: str,
        organization: str = DEFAULT_REPO_OWNER,
        repository: str = DEFAULT_REPO_NAME,
    ) -> Commit:
        """Get a specific commit on any repository. By default, ptb/ptb
        will be searched"""
        result = await self._do_request(
            "getCommit",
            variable_values={
                "sha": sha,
                "organization": organization,
                "repository": repository,
            },
        )
        data = result["repository"]["object"]
        return Commit(
            owner=organization,
            repo=repository,
            sha=data["oid"],
            url=data["ulr"],
            title=data["message"],
            author=data["author"]["user"]["login"],
        )

    async def get_issues(self, cursor: str = None) -> Tuple[List[Issue], Optional[str]]:
        """Last 100 issues before cursor"""
        result = await self._do_request("getIssues", variable_values={"cursor": cursor})
        return [
            Issue(
                owner=DEFAULT_REPO_OWNER,
                repo=DEFAULT_REPO_NAME,
                number=issue["number"],
                title=issue["title"],
                url=issue["url"],
                author=issue["author"]["login"],
            )
            for issue in result["repository"]["issues"]["nodes"]
        ], result["repository"]["issues"]["page_info"]["startCursor"]

    async def get_pull_requests(
        self, cursor: str = None
    ) -> Tuple[List[PullRequest], Optional[str]]:
        """Last 100 pull requests before cursor"""
        result = await self._do_request("getPullRequests", variable_values={"cursor": cursor})
        return [
            PullRequest(
                owner=DEFAULT_REPO_OWNER,
                repo=DEFAULT_REPO_NAME,
                number=pull_request["number"],
                title=pull_request["title"],
                url=pull_request["url"],
                author=pull_request["author"]["login"],
            )
            for pull_request in result["repository"]["pullRequests"]["nodes"]
        ], result["repository"]["pullRequests"]["page_info"]["startCursor"]

    async def get_discussions(self, cursor: str = None) -> Tuple[List[Discussion], Optional[str]]:
        """Last 100 discussions before cursor"""
        result = await self._do_request("getDiscussions", variable_values={"cursor": cursor})
        return [
            Discussion(
                owner=DEFAULT_REPO_OWNER,
                repo=DEFAULT_REPO_NAME,
                number=discussion["number"],
                title=discussion["title"],
                url=discussion["url"],
                author=discussion["author"]["login"],
            )
            for discussion in result["repository"]["discussions"]["nodes"]
        ], result["repository"]["discussions"]["page_info"]["startCursor"]
