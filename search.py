from collections import OrderedDict, namedtuple
from urllib.parse import urljoin
from urllib.request import urlopen

from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
from sphinx.util.inventory import InventoryFile

from util import ARROW_CHARACTER, DEFAULT_REPO, GITHUB_URL

DOCS_URL = "https://python-telegram-bot.readthedocs.io/en/latest/"
OFFICIAL_URL = "https://core.telegram.org/bots/api"
PROJECT_URL = urljoin(GITHUB_URL, DEFAULT_REPO + '/')
WIKI_URL = urljoin(PROJECT_URL, "wiki/")
WIKI_CODE_SNIPPETS_URL = urljoin(WIKI_URL, "Code-snippets")
EXAMPLES_URL = urljoin(PROJECT_URL, 'tree/master/examples/')

Doc = namedtuple('Doc', 'short_name, full_name, type, url, tg_name, tg_url')


class BestHandler:
    def __init__(self):
        self.items = []

    def add(self, score, item):
        self.items.append((score, item))

    def to_list(self, amount, threshold):
        items = sorted(self.items, key=lambda x: x[0])
        items = [item for score, item in reversed(items[-amount:]) if score > threshold]
        return items if len(items) > 0 else None


class Search:
    def __init__(self):
        self._docs = {}
        self._official = {}
        self._wiki = OrderedDict()  # also examples
        self.parse_docs()
        self.parse_official()
        # Order matters since we use an ordered dict
        self.parse_wiki()
        self.parse_examples()
        self.parse_wiki_code_snippets()

    def parse_docs(self):
        docs_data = urlopen(urljoin(DOCS_URL, "objects.inv"))
        self._docs = InventoryFile.load(docs_data, DOCS_URL, urljoin)

    def parse_official(self):
        official_soup = BeautifulSoup(urlopen(OFFICIAL_URL), "html.parser")
        for anchor in official_soup.select('a.anchor'):
            if '-' not in anchor['href']:
                self._official[anchor['href'][1:]] = anchor.next_sibling

    def parse_wiki(self):
        wiki_soup = BeautifulSoup(urlopen(WIKI_URL), "html.parser")

        # Parse main pages from custom sidebar
        for ol in wiki_soup.select("div.wiki-custom-sidebar > ol"):
            category = ol.find_previous_sibling('h2').text.strip()
            for li in ol.select('li'):
                if li.a['href'] != '#':
                    name = f'{category} {ARROW_CHARACTER} {li.a.text.strip()}'
                    self._wiki[name] = urljoin(WIKI_URL, li.a['href'])

    def parse_wiki_code_snippets(self):
        code_snippet_soup = BeautifulSoup(urlopen(WIKI_CODE_SNIPPETS_URL), 'html.parser')
        for h4 in code_snippet_soup.select('div.wiki-body h4'):
            name = f'Code snippets {ARROW_CHARACTER} {h4.text.strip()}'
            self._wiki[name] = urljoin(WIKI_CODE_SNIPPETS_URL, h4.a['href'])

    def parse_examples(self):
        self._wiki['Examples'] = EXAMPLES_URL

        example_soup = BeautifulSoup(urlopen(EXAMPLES_URL), 'html.parser')

        for a in example_soup.select('.files td.content a'):
            if a.text not in ['LICENSE.txt', 'README.md']:
                name = f'Examples {ARROW_CHARACTER} {a.text.strip()}'
                self._wiki[name] = urljoin(EXAMPLES_URL, a['href'])

    def docs(self, query, threshold=80):
        query = list(reversed(query.split('.')))
        best = (0, None)

        for typ, items in self._docs.items():
            if typ not in ['py:staticmethod', 'py:exception', 'py:method', 'py:module', 'py:class', 'py:attribute',
                           'py:data', 'py:function']:
                continue
            for name, item in items.items():
                name_bits = name.split('.')
                dot_split = zip(query, reversed(name_bits))
                score = 0
                for s, n in dot_split:
                    score += fuzz.ratio(s, n)
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
                    best = (score, Doc('.'.join(short_name), name,
                                       typ[3:], item[2], tg_name, tg_url))
        if best[0] > threshold:
            return best[1]

    def wiki(self, query, amount=5, threshold=50):
        best = BestHandler()
        best.add(0, ('HOME', WIKI_URL))
        if query != '':
            for name, link in self._wiki.items():
                score = fuzz.ratio(query.lower(), name.split(ARROW_CHARACTER)[-1].strip().lower())
                best.add(score, (name, link))

        return best.to_list(amount, threshold)

    def all_wiki_pages(self):
        return list(self._wiki.items())


search = Search()
