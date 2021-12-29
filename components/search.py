import functools
import heapq
import itertools

from datetime import date

from threading import Lock
from typing import List, Tuple, Dict, Callable, Any, Optional, Iterable
from urllib.parse import urljoin
from urllib.request import urlopen, Request

from bs4 import BeautifulSoup
from sphinx.util.inventory import InventoryFile

from .const import (
    USER_AGENT,
    DOCS_URL,
    OFFICIAL_URL,
    WIKI_URL,
    WIKI_CODE_SNIPPETS_URL,
    WIKI_FAQ_URL,
    EXAMPLES_URL,
    GITHUB_PATTERN,
    WIKI_FRDP_URL,
)
from .entrytypes import WikiPage, Example, CodeSnippet, FAQEntry, DocEntry, BaseEntry, FRDPEntry
from .github import github_issues
from .taghints import TAG_HINTS


def cached_parsing(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def checking_cache_time(self: "Search", *args: Any, **kwargs: Any) -> Any:
        if date.today() > self.last_cache_date:
            self.fetch_entries()
            self.last_cache_date = date.today()
        return func(self, *args, **kwargs)

    return checking_cache_time


class Search:
    def __init__(self) -> None:
        self.__lock = Lock()
        self._docs: List[DocEntry] = []
        self._official: Dict[str, str] = {}
        self._wiki: List[WikiPage] = []
        self._examples: List[Example] = []
        self._snippets: List[CodeSnippet] = []
        self._faq: List[FAQEntry] = []
        self._design_patterns: List[FRDPEntry] = []
        self.last_cache_date = date.today()
        self.github_session = github_issues
        self.fetch_entries()

    def fetch_entries(self) -> None:
        with self.__lock:
            self.fetch_docs()
            self.fetch_wiki()
            self.fetch_examples()
            self.fetch_wiki_code_snippets()
            self.fetch_wiki_faq()
            self.fetch_wiki_design_patterns()

            # This is important: If the docs have changed the cache is useless
            self.search.cache_clear()
            self.multi_search_combinations.cache_clear()

    def fetch_official_docs(self) -> None:
        request = Request(OFFICIAL_URL, headers={"User-Agent": USER_AGENT})
        official_soup = BeautifulSoup(urlopen(request), "html.parser")
        for anchor in official_soup.select("a.anchor"):
            if "-" not in anchor["href"]:
                self._official[anchor["href"][1:]] = anchor.next_sibling

    def fetch_docs(self) -> None:
        self.fetch_official_docs()
        request = Request(urljoin(DOCS_URL, "objects.inv"), headers={"User-Agent": USER_AGENT})
        docs_data = urlopen(request)
        data = InventoryFile.load(docs_data, DOCS_URL, urljoin)
        for entry_type, items in data.items():
            for name, (_, _, url, display_name) in items.items():
                tg_url, tg_test, tg_name = "", "", ""
                name_bits = name.split(".")

                if entry_type in ["py:class", "py:method"]:
                    tg_test = name_bits[-1].replace("_", "").lower()
                elif entry_type == "py:attribute":
                    tg_test = name_bits[-2].replace("_", "").lower()

                if tg_test in self._official.keys():
                    tg_name = self._official[tg_test]
                    tg_url = urljoin(OFFICIAL_URL, "#" + tg_name.lower())

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

    def fetch_wiki(self) -> None:
        self._wiki = []
        request = Request(WIKI_URL, headers={"User-Agent": USER_AGENT})
        wiki_soup = BeautifulSoup(urlopen(request), "html.parser")

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

    def fetch_wiki_code_snippets(self) -> None:
        self._snippets = []
        request = Request(WIKI_CODE_SNIPPETS_URL, headers={"User-Agent": USER_AGENT})
        code_snippet_soup = BeautifulSoup(urlopen(request), "html.parser")
        for headline in code_snippet_soup.select(
            "div#wiki-body h4,div#wiki-body h3,div#wiki-body h2"
        ):
            self._snippets.append(
                CodeSnippet(
                    name=headline.text.strip(),
                    url=urljoin(WIKI_CODE_SNIPPETS_URL, headline.a["href"]),
                )
            )

    def fetch_wiki_faq(self) -> None:
        self._faq = []
        request = Request(WIKI_FAQ_URL, headers={"User-Agent": USER_AGENT})
        faq_soup = BeautifulSoup(urlopen(request), "html.parser")
        for headline in faq_soup.select("div#wiki-body h3"):
            self._faq.append(
                FAQEntry(name=headline.text.strip(), url=urljoin(WIKI_FAQ_URL, headline.a["href"]))
            )

    def fetch_wiki_design_patterns(self) -> None:
        self._design_patterns = []
        request = Request(WIKI_FRDP_URL, headers={"User-Agent": USER_AGENT})
        frdp_soup = BeautifulSoup(urlopen(request), "html.parser")
        for headline in frdp_soup.select("div#wiki-body h3,div#wiki-body h2"):
            self._design_patterns.append(
                FRDPEntry(
                    name=headline.text.strip(), url=urljoin(WIKI_FRDP_URL, headline.a["href"])
                )
            )

    def fetch_examples(self) -> None:
        self._examples = []
        for name, link in self.github_session.get_examples_directory(r"^.*\.py"):
            self._examples.append(Example(name=name, url=link))

    @staticmethod
    def _sort_key(entry: BaseEntry, search_query: str) -> float:
        return entry.compare_to_query(search_query)

    @functools.lru_cache(maxsize=64)
    @cached_parsing
    def search(self, search_query: Optional[str], amount: int = None) -> Optional[List[BaseEntry]]:
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
            owner, repo, number, sha, gh_search_query, ptbcontrib = [
                match.groupdict()[x]
                for x in ("owner", "repo", "number", "sha", "query", "ptbcontrib")
            ]

            # If it's an issue
            if number:
                issue = github_issues.get_issue(int(number), owner, repo)
                return [issue] if issue else None
            # If it's a commit
            if sha:
                commit = github_issues.get_commit(sha, owner, repo)
                return [commit] if commit else None
            # If it's a search
            if gh_search_query:
                search_query = gh_search_query
                search_entries = github_issues.all_issues
            elif ptbcontrib:
                search_entries = github_issues.all_ptbcontribs

        if search_query and search_query.startswith("/"):
            search_entries = TAG_HINTS.values()

        with self.__lock:
            if not search_entries:
                search_entries = itertools.chain(
                    self._wiki,
                    self._examples,
                    self._faq,
                    self._design_patterns,
                    self._snippets,
                    github_issues.all_ptbcontribs,
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

    @functools.lru_cache(64)
    @cached_parsing
    def multi_search_combinations(
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
            if res := self.search(search_query=query, amount=results_per_query):
                results[query] = res

        return [
            dict(zip(effective_queries, query_results))
            for query_results in itertools.product(*results.values())
        ]


search = Search()
