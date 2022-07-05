import asyncio
import datetime
import heapq
import itertools
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast
from urllib.parse import urljoin

import httpx
from async_lru import alru_cache
from bs4 import BeautifulSoup
from sphinx.util.inventory import InventoryFile
from telegram.ext import Application, ContextTypes, Job, JobQueue

from .const import (
    DEFAULT_HEADERS,
    DEFAULT_REPO_NAME,
    DEFAULT_REPO_OWNER,
    DOCS_URL,
    EXAMPLES_URL,
    GITHUB_PATTERN,
    OFFICIAL_URL,
    USER_AGENT,
    WIKI_CODE_SNIPPETS_URL,
    WIKI_FAQ_URL,
    WIKI_FRDP_URL,
    WIKI_URL,
)
from .entrytypes import (
    BaseEntry,
    CodeSnippet,
    DocEntry,
    FAQEntry,
    FRDPEntry,
    ParamDocEntry,
    WikiPage,
)
from .github import GitHub
from .taghints import TAG_HINTS


class Search:
    def __init__(self, github_auth: str, github_user_agent: str = USER_AGENT) -> None:
        self.__lock = asyncio.Lock()
        self._docs: List[DocEntry] = []
        self._official: Dict[str, str] = {}
        self._wiki: List[WikiPage] = []
        self._snippets: List[CodeSnippet] = []
        self._faq: List[FAQEntry] = []
        self._design_patterns: List[FRDPEntry] = []
        self.github = GitHub(auth=github_auth, user_agent=github_user_agent)
        self._httpx_client = httpx.AsyncClient()

    async def initialize(
        self, application: Application[Any, Any, Any, Any, Any, JobQueue]
    ) -> None:
        await self.github.initialize()
        application.job_queue.run_once(callback=self.update_job, when=1, data=(None, None, None))

    async def shutdown(self) -> None:
        await self.github.shutdown()
        await self._httpx_client.aclose()
        await self.search.close()  # pylint:disable=no-member
        await self.multi_search_combinations.close()  # pylint:disable=no-member

    async def update_job(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        job = cast(Job, context.job)
        cursors = cast(Tuple[Optional[str], Optional[str], Optional[str]], job.data)
        restart = not any(cursors)

        if restart:
            await asyncio.gather(
                context.application.create_task(self.github.update_examples()),
                context.application.create_task(self.github.update_ptb_contribs()),
            )
            async with self.__lock:
                await asyncio.gather(
                    context.application.create_task(self.update_docs()),
                    context.application.create_task(self.update_wiki()),
                    context.application.create_task(self.update_wiki_code_snippets()),
                    context.application.create_task(self.update_wiki_faq()),
                    context.application.create_task(self.update_wiki_design_patterns()),
                )

        issue_cursor = (
            await self.github.update_issues(cursor=cursors[0]) if restart or cursors[0] else None
        )
        pr_cursor = (
            await self.github.update_pull_requests(cursor=cursors[1])
            if restart or cursors[1]
            else None
        )
        discussion_cursor = (
            await self.github.update_discussions(cursor=cursors[2])
            if restart or cursors[2]
            else None
        )

        new_cursors = (issue_cursor, pr_cursor, discussion_cursor)
        when = datetime.timedelta(seconds=30) if any(new_cursors) else datetime.timedelta(hours=12)
        cast(JobQueue, context.job_queue).run_once(
            callback=self.update_job, when=when, data=new_cursors
        )

        # This is important: If the docs have changed the cache is useless
        self.search.cache_clear()  # pylint:disable=no-member
        self.multi_search_combinations.cache_clear()  # pylint:disable=no-member

    async def _update_official_docs(self) -> None:
        response = await self._httpx_client.get(url=OFFICIAL_URL, headers=DEFAULT_HEADERS)
        official_soup = BeautifulSoup(response.content, "html.parser")
        for anchor in official_soup.select("a.anchor"):
            if "-" not in anchor["href"]:
                self._official[anchor["href"][1:]] = anchor.next_sibling

    async def update_docs(self) -> None:
        await self._update_official_docs()
        response = await self._httpx_client.get(
            url=urljoin(DOCS_URL, "objects.inv"),
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )
        data = InventoryFile.load(BytesIO(response.content), DOCS_URL, urljoin)
        self._docs = []
        for entry_type, items in data.items():
            for name, (_, _, url, display_name) in items.items():
                if "._" in name:
                    # For some reason both `ext._application.Application` and `ext.Application`
                    # are present ...
                    continue

                tg_url, tg_test, tg_name = "", "", ""
                name_bits = name.split(".")

                if entry_type == "py:method" and (
                    "telegram.Bot" in name or "telegram.ext.ExtBot" in name
                ):
                    tg_test = name_bits[-1]
                if entry_type == "py:attribute":
                    tg_test = name_bits[-2]
                if entry_type == "py:class":
                    tg_test = name_bits[-1]
                elif entry_type == "py:parameter":
                    tg_test = name_bits[-4]

                tg_test = tg_test.replace("_", "").lower()

                if tg_test in self._official:
                    tg_name = self._official[tg_test]
                    tg_url = urljoin(OFFICIAL_URL, "#" + tg_name.lower())

                if entry_type == "py:parameter":
                    self._docs.append(
                        ParamDocEntry(
                            name=name,
                            url=url,
                            display_name=display_name if display_name.strip() != "-" else None,
                            entry_type=entry_type,
                            telegram_url=tg_url,
                            telegram_name=tg_name,
                        )
                    )
                else:
                    self._docs.append(
                        DocEntry(
                            name=name,
                            url=url,
                            display_name=display_name if display_name.strip() != "-" else None,
                            entry_type=entry_type,
                            telegram_url=tg_url,
                            telegram_name=tg_name,
                        )
                    )

    async def update_wiki(self) -> None:
        response = await self._httpx_client.get(url=WIKI_URL, headers=DEFAULT_HEADERS)
        wiki_soup = BeautifulSoup(response.content, "html.parser")
        self._wiki = []

        # Parse main pages from custom sidebar
        for tag in ["ol", "ul"]:
            for element in wiki_soup.select(f"div.wiki-custom-sidebar > {tag}"):
                category = element.find_previous_sibling("h2").text.strip()
                for list_item in element.select("li"):
                    if list_item.a["href"] != "#":
                        self._wiki.append(
                            WikiPage(
                                category=category,
                                name=list_item.a.text.strip(),
                                url=urljoin(WIKI_URL, list_item.a["href"]),
                            )
                        )

        self._wiki.append(WikiPage(category="Code Resources", name="Examples", url=EXAMPLES_URL))

    async def update_wiki_code_snippets(self) -> None:
        response = await self._httpx_client.get(
            url=WIKI_CODE_SNIPPETS_URL, headers=DEFAULT_HEADERS
        )
        code_snippet_soup = BeautifulSoup(response.content, "html.parser")
        self._snippets = []
        for headline in code_snippet_soup.select(
            "div#wiki-body h4,div#wiki-body h3,div#wiki-body h2"
        ):
            self._snippets.append(
                CodeSnippet(
                    name=headline.text.strip(),
                    url=urljoin(WIKI_CODE_SNIPPETS_URL, headline.a["href"]),
                )
            )

    async def update_wiki_faq(self) -> None:
        response = await self._httpx_client.get(url=WIKI_FAQ_URL, headers=DEFAULT_HEADERS)
        faq_soup = BeautifulSoup(response.content, "html.parser")
        self._faq = []
        for headline in faq_soup.select("div#wiki-body h3"):
            self._faq.append(
                FAQEntry(name=headline.text.strip(), url=urljoin(WIKI_FAQ_URL, headline.a["href"]))
            )

    async def update_wiki_design_patterns(self) -> None:
        response = await self._httpx_client.get(url=WIKI_FRDP_URL, headers=DEFAULT_HEADERS)
        frdp_soup = BeautifulSoup(response.content, "html.parser")
        self._design_patterns = []
        for headline in frdp_soup.select("div#wiki-body h3,div#wiki-body h2"):
            self._design_patterns.append(
                FRDPEntry(
                    name=headline.text.strip(), url=urljoin(WIKI_FRDP_URL, headline.a["href"])
                )
            )

    @staticmethod
    def _sort_key(entry: BaseEntry, search_query: str) -> float:
        return entry.compare_to_query(search_query)

    @alru_cache(maxsize=64)  # type: ignore[misc]
    async def search(
        self, search_query: Optional[str], amount: int = None
    ) -> Optional[List[BaseEntry]]:
        """Searches all available entries for appropriate results. This includes:

        * wiki pages
        * FAQ entries
        * Design Pattern entries entries
        * Code snippets
        * examples
        * documentation
        * ptbcontrib
        * issues & PRs on GH

        If the query is in one of the following formats, the search will *only* attempt to fand
        one corresponding GitHub result:

        * ((owner)/repo)#<issue number>
        * @<start of sha>

        If the query is in the format `#some search query`, only the issues on
        python-telegram-bot/python-telegram-bot will be searched.

        If the query is in the format `ptbcontrib/<name of contribution>`, only the contributions
        of ptbcontrib will be searched.

        If the query is in the format `/search query`, only the tags hints will be searched.

        Args:
            search_query: The search query. May be None, in which case all available entries
                will be given.
            amount: Optional. If passed, returns the ``amount`` elements with the highest
                comparison score.

        Returns:
            The results sorted by comparison score.
        """
        search_entries: Iterable[BaseEntry] = []

        match = GITHUB_PATTERN.fullmatch(search_query) if search_query else None
        if match:
            owner, repo, number, sha, gh_search_query, ptbcontrib = (
                match.groupdict()[x]
                for x in ("owner", "repo", "number", "sha", "query", "ptbcontrib")
            )
            owner = owner or DEFAULT_REPO_OWNER
            repo = repo or DEFAULT_REPO_NAME

            # If it's an issue
            if number:
                issue = await self.github.get_thread(int(number), owner, repo)
                return [issue] if issue else None
            # If it's a commit
            if sha:
                commit = await self.github.get_commit(sha, owner, repo)
                return [commit] if commit else None
            # If it's a search
            if gh_search_query:
                search_query = gh_search_query
                search_entries = itertools.chain(
                    self.github.all_issues,
                    self.github.all_pull_requests,
                    self.github.all_discussions,
                )
            elif ptbcontrib:
                search_entries = self.github.all_ptbcontribs

        if search_query and search_query.startswith("/"):
            search_entries = TAG_HINTS.values()

        async with self.__lock:
            if not search_entries:
                search_entries = itertools.chain(
                    self._wiki,
                    self.github.all_examples,
                    self._faq,
                    self._design_patterns,
                    self._snippets,
                    self.github.all_ptbcontribs,
                    self._docs,
                    TAG_HINTS.values(),
                )

            if not search_query:
                return search_entries if isinstance(search_entries, list) else list(search_entries)

            if not amount:
                return sorted(
                    search_entries,
                    key=lambda entry: self._sort_key(entry, search_query),  # type: ignore
                    reverse=True,
                )
            return heapq.nlargest(
                amount,
                search_entries,
                key=lambda entry: self._sort_key(entry, search_query),  # type: ignore[arg-type]
            )

    @alru_cache(maxsize=64)  # type: ignore[misc]
    async def multi_search_combinations(
        self, search_queries: Tuple[str], results_per_query: int = 3
    ) -> List[Dict[str, BaseEntry]]:
        """For each query, runs :meth:`search` and fetches the ``results_per_query`` most likely
        results. Then builds all possible combinations.

        Args:
            search_queries: The search queries.
            results_per_query: Optional. Number of results to fetch per query. Defaults to ``3``.

        Returns:
            All possible result combinations. Each list entry is a dictionary mapping each query
                to the corresponding :class:`BaseEntry`.

        """
        # Don't use a page-argument here, as the number of results will usually be relatively small
        # so we can just build the list once and get slices from the cached result if necessary

        results = {}
        # Remove duplicates while maintaining the order
        effective_queries = list(dict.fromkeys(search_queries))
        for query in effective_queries:
            if res := await self.search(search_query=query, amount=results_per_query):
                results[query] = res

        return [
            dict(zip(effective_queries, query_results))
            for query_results in itertools.product(*results.values())
        ]
