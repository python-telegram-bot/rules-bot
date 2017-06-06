import urllib.request
from urllib.parse import urljoin
from collections import namedtuple

from bs4 import BeautifulSoup
from fuzzywuzzy import fuzz
from sphinx.ext.intersphinx import read_inventory_v2

DOCS_URL = "https://python-telegram-bot.readthedocs.io/en/latest/"
OFFICIAL_URL = "https://core.telegram.org/bots/api#"
GITHUB_URL = "https://github.com/"
WIKI_URL = urljoin(GITHUB_URL, "python-telegram-bot/python-telegram-bot/wiki/")
WIKI_CODE_SNIPPETS_URL = urljoin(WIKI_URL, "Code-snippets")

Doc = namedtuple('Doc', 'short_name, full_name, type, url, tg_name, tg_url')


class Search:
    def __init__(self):
        self._docs = {}
        self._official = {}
        self._wiki = {}
        self.parse_docs()
        self.parse_official()
        self.parse_wiki()

    def parse_docs(self):
        docs_data = urllib.request.urlopen(urljoin(DOCS_URL, "objects.inv"))
        docs_data.readline()  # Need to remove first line for some reason
        self._docs = read_inventory_v2(docs_data, DOCS_URL, urljoin)

    def parse_official(self):
        official_soup = BeautifulSoup(urllib.request.urlopen(OFFICIAL_URL), "html.parser")
        for anchor in official_soup.select('a.anchor'):
            if '-' not in anchor['href']:
                self._official[anchor['href'][1:]] = anchor.next_sibling

    def parse_wiki(self):
        wiki_soup = BeautifulSoup(urllib.request.urlopen(WIKI_URL), "html.parser")

        # Parse main pages from custom sidebar
        for ol in wiki_soup.select("div.wiki-custom-sidebar > ol"):
            category = ol.find_previous_sibling('h2').text
            for li in ol.select('li'):
                if li.a['href'] != '#':
                    name = '{} 🡺 {}'.format(category, li.a.text)
                    self._wiki[name] = urljoin(WIKI_URL, li.a['href'])

        # Parse code snippets
        code_snippet_soup = BeautifulSoup(urllib.request.urlopen(WIKI_CODE_SNIPPETS_URL), 'html.parser')
        for h4 in code_snippet_soup.select('div.wiki-body h4'):
            name = 'Code snippets 🡺 ' + h4.text
            self._wiki[name] = urljoin(WIKI_CODE_SNIPPETS_URL, h4.a['href'])

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
                    tg_name = ''
                    tg_test = ''

                    if typ in ['py:class', 'py:method']:
                        tg_test = name_bits[-1].replace('_', '').lower()
                    elif typ == 'py:attribute':
                        tg_test = name_bits[-2].replace('_', '').lower()

                    if tg_test in self._official.keys():
                        tg_name = self._official[tg_test]

                    tg_url = OFFICIAL_URL + tg_test
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

    def wiki(self, query):
        best = (0, ('HOME', WIKI_URL))
        if query != '':
            for name, link in self._wiki.items():
                score = fuzz.partial_ratio(query, name)
                if score > best[0]:
                    best = (score, (name, link))

            return best

search = Search()
