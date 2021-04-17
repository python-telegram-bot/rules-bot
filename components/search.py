import functools

from datetime import date

from collections import OrderedDict, namedtuple
from typing import TypeVar, Generic, List, Tuple, Optional, Dict, Callable, Any
from urllib.parse import urljoin
from urllib.request import urlopen, Request

from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
from sphinx.util.inventory import InventoryFile

from .const import USER_AGENT, ARROW_CHARACTER, GITHUB_URL, DEFAULT_REPO

DOCS_URL = "https://python-telegram-bot.readthedocs.io/en/stable/"
OFFICIAL_URL = "https://core.telegram.org/bots/api"
PROJECT_URL = urljoin(GITHUB_URL, DEFAULT_REPO + '/')
WIKI_URL = urljoin(PROJECT_URL, "wiki/")
WIKI_CODE_SNIPPETS_URL = urljoin(WIKI_URL, "Code-snippets")
WIKI_FAQ_URL = urljoin(WIKI_URL, "Frequently-Asked-Questions")
EXAMPLES_URL = urljoin(PROJECT_URL, 'tree/master/examples/')

Doc = namedtuple('Doc', 'short_name, full_name, type, url, tg_name, tg_url')


Item = TypeVar('Item')


class BestHandler(Generic[Item]):
    def __init__(self) -> None:
        self.items: List[Tuple[float, Item]] = []

    def add(self, score: float, item: Item) -> None:
        self.items.append((score, item))

    def to_list(self, amount: int, threshold: float) -> Optional[List[Item]]:
        items = sorted(self.items, key=lambda x: x[0])
        effective_items = [item for score, item in reversed(items[-amount:]) if score > threshold]
        return effective_items if len(effective_items) > 0 else None


def cached_parsing(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def checking_cache_time(self: 'Search', *args: Any, **kwargs: Any) -> Any:
        if date.today() > self.last_cache_date:
            self.parse()
            self.last_cache_date = date.today()
        return func(self, *args, **kwargs)

    return checking_cache_time


class Search:
    def __init__(self) -> None:
        self._docs: Dict[str, Dict[str, Tuple[str, str, str, str]]] = {}
        self._official: Dict[str, str] = {}
        self._wiki: Dict[str, str] = OrderedDict()  # also examples
        self._snippets: Dict[str, str] = OrderedDict()
        self._faq: Dict[str, str] = OrderedDict()
        self.last_cache_date = date.today()
        self.parse()

    def parse(self) -> None:
        self.parse_docs()
        self.parse_official()
        # Order matters since we use an ordered dict
        self.parse_wiki()
        self.parse_examples()
        self.parse_wiki_code_snippets()
        self.parse_wiki_faq()

    def parse_docs(self) -> None:
        request = Request(urljoin(DOCS_URL, "objects.inv"), headers={'User-Agent': USER_AGENT})
        docs_data = urlopen(request)
        self._docs = InventoryFile.load(docs_data, DOCS_URL, urljoin)

    def parse_official(self) -> None:
        request = Request(OFFICIAL_URL, headers={'User-Agent': USER_AGENT})
        official_soup = BeautifulSoup(urlopen(request), "html.parser")
        for anchor in official_soup.select('a.anchor'):
            if '-' not in anchor['href']:
                self._official[anchor['href'][1:]] = anchor.next_sibling

    def parse_wiki(self) -> None:
        request = Request(WIKI_URL, headers={'User-Agent': USER_AGENT})
        wiki_soup = BeautifulSoup(urlopen(request), "html.parser")

        # Parse main pages from custom sidebar
        for tag in ['ol', 'ul']:
            for element in wiki_soup.select(f"div.wiki-custom-sidebar > {tag}"):
                category = element.find_previous_sibling('h2').text.strip()
                for list_item in element.select('li'):
                    if list_item.a['href'] != '#':
                        name = f'{category} {ARROW_CHARACTER} {list_item.a.text.strip()}'
                        self._wiki[name] = urljoin(WIKI_URL, list_item.a['href'])

    def parse_wiki_code_snippets(self) -> None:
        request = Request(WIKI_CODE_SNIPPETS_URL, headers={'User-Agent': USER_AGENT})
        code_snippet_soup = BeautifulSoup(urlopen(request), 'html.parser')
        for headline in code_snippet_soup.select('div#wiki-body h4'):
            name = f'Code snippets {ARROW_CHARACTER} {headline.text.strip()}'
            self._wiki[name] = urljoin(WIKI_CODE_SNIPPETS_URL, headline.a['href'])
            self._snippets[name] = self._wiki[name]

    def parse_wiki_faq(self) -> None:
        request = Request(WIKI_FAQ_URL, headers={'User-Agent': USER_AGENT})
        code_snippet_soup = BeautifulSoup(urlopen(request), 'html.parser')
        for headline in code_snippet_soup.select('div#wiki-body h3'):
            name = f'FAQ {ARROW_CHARACTER} {headline.text.strip()}'
            self._wiki[name] = urljoin(WIKI_FAQ_URL, headline.a['href'])
            self._faq[name] = self._wiki[name]

    def parse_examples(self) -> None:
        self._wiki['Examples'] = EXAMPLES_URL

        request = Request(EXAMPLES_URL, headers={'User-Agent': USER_AGENT})
        example_soup = BeautifulSoup(urlopen(request), 'html.parser')

        for div in example_soup.findAll('div', {'role': 'rowheader'}):
            hyperlink = div.a
            if hyperlink.text not in ['LICENSE.txt', 'README.md', '\n. .\n']:
                name = f'Examples {ARROW_CHARACTER} {hyperlink.text.strip()}'
                self._wiki[name] = urljoin(EXAMPLES_URL, hyperlink.href)

    @cached_parsing
    def docs(self, input_query: str, threshold: float = 80) -> Optional[Doc]:
        query = list(reversed(input_query.split('.')))
        best: Tuple[float, Optional[Doc]] = (0.0, None)

        for typ, items in self._docs.items():
            if typ not in [
                'py:staticmethod',
                'py:exception',
                'py:method',
                'py:module',
                'py:class',
                'py:attribute',
                'py:data',
                'py:function',
            ]:
                continue
            for name, item in items.items():
                name_bits = name.split('.')
                dot_split = zip(query, reversed(name_bits))
                score = 0.0
                for target, value in dot_split:
                    score += fuzz.ratio(target, value)
                score += fuzz.ratio(query, name)

                # These values are basically random :/
                if typ == 'py:module':
                    score *= 0.75
                if typ == 'py:class':
                    score *= 1.10
                if typ == 'py:attribute':
                    score *= 0.85

                if score > best[0]:
                    tg_url, tg_test, tg_name = '', '', ''

                    if typ in ['py:class', 'py:method']:
                        tg_test = name_bits[-1].replace('_', '').lower()
                    elif typ == 'py:attribute':
                        tg_test = name_bits[-2].replace('_', '').lower()

                    if tg_test in self._official.keys():
                        tg_name = self._official[tg_test]
                        tg_url = urljoin(OFFICIAL_URL, '#' + tg_name.lower())

                    short_name = name_bits[1:]

                    try:
                        if name_bits[1].lower() == name_bits[2].lower():
                            short_name = name_bits[2:]
                    except IndexError:
                        pass
                    best = (
                        score,
                        Doc('.'.join(short_name), name, typ[3:], item[2], tg_name, tg_url),
                    )
        if best[0] > threshold:
            return best[1]
        return None

    @cached_parsing
    def _get_results(  # pylint: disable=R0201
        self, candidates: Dict[str, str], query: str, amount: int = 5, threshold: int = 50
    ) -> Optional[List[Tuple[str, str]]]:
        best: BestHandler[Tuple[str, str]] = BestHandler()
        best.add(0, ('HOME', WIKI_URL))
        if query != '':
            for name, link in candidates.items():
                score = fuzz.ratio(query.lower(), name.split(ARROW_CHARACTER)[-1].strip().lower())
                best.add(score, (name, link))

        return best.to_list(amount, threshold)

    def faq(self, query: str, amount: int = 5, threshold: int = 50) -> Optional[List[str]]:
        return self._get_results(self._faq, query, amount, threshold)

    def code_snippets(
        self, query: str, amount: int = 5, threshold: int = 50
    ) -> Optional[List[str]]:
        return self._get_results(self._snippets, query, amount, threshold)

    def wiki(self, query: str, amount: int = 5, threshold: int = 50) -> Optional[List[str]]:
        return self._get_results(self._wiki, query, amount, threshold)

    @cached_parsing
    def all_wiki_pages(self) -> List[Tuple[str, str]]:
        return list(self._wiki.items())

    @cached_parsing
    def all_code_snippets(self) -> List[Tuple[str, str]]:
        return list(self._snippets.items())

    @cached_parsing
    def all_faq(self) -> List[Tuple[str, str]]:
        return list(self._faq.items())


search = Search()
