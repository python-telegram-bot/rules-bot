from pathlib import Path
from typing import Dict, Any, List, Union

from gql import Client, gql
from gql.client import AsyncClientSession
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError

from components.const import USER_AGENT, DEFAULT_REPO_OWNER, DEFAULT_REPO_NAME
from components.entrytypes import Example, Issue, PullRequest, Discussion


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
        return [Example(name=file["name"]) for file in result["repository"]["object"]["entries"]]

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
