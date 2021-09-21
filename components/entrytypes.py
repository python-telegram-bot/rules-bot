import re
from abc import ABC, abstractmethod
from typing import List, Optional

from github3.repos.commit import RepoCommit as GHCommit
from github3.repos import Repository as GHRepo
from github3.issues import Issue as GHIssue
from thefuzz import fuzz
from telegram import InlineKeyboardMarkup

from components.const import (
    ARROW_CHARACTER,
    TELEGRAM_SUPERSCRIPT,
    DEFAULT_REPO_OWNER,
    DEFAULT_REPO_NAME,
)


class BaseEntry(ABC):
    """Base class for all searchable entries."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Name to display in the search results"""

    @property
    def short_name(self) -> str:
        """Potentially shorter name to display. Defaults to :attr:`display_name`"""
        return self.display_name

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the entry to display in the search results"""

    @property
    def short_description(self) -> str:
        """Short description of the entry to display in the search results. Useful when displaying
        multiple search results in one entry. Defaults to :attr:`short_name` if not overridden."""
        return self.short_name

    @abstractmethod
    def html_markup(self, search_query: str = None) -> str:
        """HTML markup to be used if this entry is selected in the search. May depend on the search
        query."""

    @abstractmethod
    def html_insertion_markup(self, search_query: str = None) -> str:
        """HTML markup to be used for insertion search. May depend on the search query."""

    @abstractmethod
    def compare_to_query(self, search_query: str) -> float:
        """Gives a number ∈[0,100] describing how similar the search query is to this entry."""

    @property
    def inline_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        """Inline Keyboard markup that can be attached to this entry. Returns :obj:`None`, if
        not overridden."""
        return None


class Example(BaseEntry):
    """An example in the examples directory.

    Args:
        name: The name of the example
        url: URL of the example
    """

    def __init__(self, name: str, url: str):
        if name.endswith(".py"):
            self._name = name[:-3]
        else:
            self._name = name
        self._search_name = f"example {self._name}".lower()
        self.url = url

    @property
    def display_name(self) -> str:
        return f"Examples {ARROW_CHARACTER} {self._name}"

    @property
    def short_name(self) -> str:
        return f"{self._name}.py"

    @property
    def description(self) -> str:
        return "Examples directory of python-telegram-bot"

    def html_markup(self, search_query: str = None) -> str:
        return (
            "Examples directory of <i>python-telegram-bot</i>:"
            f"\n{self.html_insertion_markup(search_query)}"
        )

    def html_insertion_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def compare_to_query(self, search_query: str) -> float:
        if search_query.endswith(".py"):
            search_query = search_query[:-3]

        return fuzz.partial_token_set_ratio(self._search_name, search_query.lower())


class WikiPage(BaseEntry):
    """A wiki page.

    Args:
        category: The .py of the page, as listed in the sidebar
        name: The name of the page
        url: URL of the page
    """

    def __init__(self, category: str, name: str, url: str):
        self.category = category
        self.name = name
        self.url = url
        self._compare_name = f"{self.category} {self.name}".lower()

    @property
    def display_name(self) -> str:
        return f"{self.category} {ARROW_CHARACTER} {self.name}"

    @property
    def short_name(self) -> str:
        return self.name

    @property
    def description(self) -> str:
        return "Wiki of python-telegram-bot"

    def html_markup(self, search_query: str = None) -> str:
        return (
            f"Wiki of <i>python-telegram-bot</i> - Category <i>{self.category}</i>\n"
            f"{self.html_insertion_markup(search_query)}"
        )

    def html_insertion_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def compare_to_query(self, search_query: str) -> float:
        return fuzz.token_set_ratio(self._compare_name, search_query.lower())


class CodeSnippet(WikiPage):
    """A code snippet

    Args:
        name: The name of the snippet
        url: URL of the snippet
    """

    def __init__(self, name: str, url: str):
        super().__init__(category="Code Snippets", name=name, url=url)


class FAQEntry(WikiPage):
    """An FAQ entry

    Args:
        name: The name of the entry
        url: URL of the entry
    """

    def __init__(self, name: str, url: str):
        super().__init__(category="FAQ", name=name, url=url)


class DocEntry(BaseEntry):
    """An entry to the PTB docs.

    Args:
        url: URL to the online documentation of the entry.
        entry_type: Which type of entry this is.
        name: Name of the entry.
        display_name: Optional. Display name for the entry.
        telegram_name: Optional: Name of the corresponding Telegram documentation entry.
        telegram_url: Optional. Link to the corresponding Telegram documentation.
    """

    def __init__(
        self,
        url: str,
        entry_type: str,
        name: str,
        display_name: str = None,
        telegram_name: str = None,
        telegram_url: str = None,
    ):
        self.url = url
        self.entry_type = entry_type
        self.effective_type = self.entry_type.split(":")[-1]
        self.name = name
        self._display_name = display_name
        self.telegram_url = telegram_url
        self.telegram_name = telegram_name
        self._parsed_name: List[str] = self.parse_search_query(self.name)

    @staticmethod
    def parse_search_query(search_query: str) -> List[str]:
        """
        Does some preprocessing of the query needed for comparison with the entries in the docs.

        Args:
            search_query: The search query.

        Returns:
            The query, split on ``.``, ``-`` and ``/``, in reversed order.
        """
        # reversed, so that 'class' matches the 'class' part of 'module.class' exactly instead of
        # not matching the 'module' part
        return list(reversed(re.split(r"\.|/|-", search_query.strip())))

    @property
    def display_name(self) -> str:
        name = self._display_name or self.name
        return name.replace("filters.", "")

    @property
    def short_name(self) -> str:
        name = self._display_name or self.name

        if name.startswith("telegram.ext.filters."):
            return f"ext.{name[len('telegram.ext.filters.') :]}"
        if name.startswith("telegram."):
            return name[len("telegram.") :]
        return name

    @property
    def description(self) -> str:
        return "Documentation of python-telegram-bot"

    def html_markup(self, _: str = None) -> str:
        base = (
            f"<code>{self.short_name}</code>\n"
            f"<i>python-telegram-bot</i> documentation for this {self.effective_type}:\n"
            f"{self.html_markup_no_telegram}"
        )
        if not self.telegram_url and not self.telegram_name:
            tg_text = ""
        else:
            tg_text = (
                "\n\nTelegram's official Bot API documentation has more info about "
                f'<a href="{self.telegram_url}">{self.telegram_name}</a>.'
            )
        return base + tg_text

    @property
    def html_markup_no_telegram(self) -> str:
        return f'<a href="{self.url}">{self.name}</a>'

    def html_insertion_markup(self, _: str = None) -> str:
        if not self.telegram_name and not self.telegram_url:
            return self.html_markup_no_telegram
        return (
            f'{self.html_markup_no_telegram} <a href="{self.telegram_url}">'
            f"{TELEGRAM_SUPERSCRIPT}</a>"
        )

    def compare_to_query(self, search_query: str) -> float:
        score = 0.0
        processed_query = self.parse_search_query(search_query)

        # We compare all the single parts of the query …
        for target, value in zip(processed_query, self._parsed_name):
            score += fuzz.ratio(target.lower(), value.lower())
        # ... and the full name because we're generous
        score += fuzz.ratio(search_query.lower(), self.name.lower())
        # To stay <= 100 as not to overrule other results
        score = score / 2

        # IISC std: is the domain for general stuff like headlines and chapters.
        # we'll wanna give those a little less weight
        if self.entry_type.startswith("std:"):
            score *= 0.8
        return score


class Commit(BaseEntry):
    """A commit on Github

    Args:
        commit: The github3 commit object
        repository: The github3 repository object
    """

    def __init__(self, commit: GHCommit, repository: GHRepo) -> None:
        self._commit = commit
        self._repository = repository

    @property
    def owner(self) -> str:
        return self._repository.owner.login

    @property
    def repo(self) -> str:
        return self._repository.name

    @property
    def sha(self) -> str:
        return self._commit.sha

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @property
    def url(self) -> str:
        return self._commit.html_url

    @property
    def title(self) -> str:
        return self._commit.commit["message"]

    @property
    def author(self) -> str:
        return self._commit.author["login"]

    @property
    def short_name(self) -> str:
        return (
            f'{"" if self.owner == DEFAULT_REPO_OWNER else self.owner + "/"}'
            f'{"" if self.repo == DEFAULT_REPO_NAME else self.repo}'
            f"@{self.short_sha}"
        )

    @property
    def display_name(self) -> str:
        return f"Commit {self.short_name}: {self.title} by {self.author}"

    @property
    def description(self) -> str:
        return "Search on GitHub"

    def html_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.display_name}</a>'

    def html_insertion_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def compare_to_query(self, search_query: str) -> float:
        search_query = search_query.lstrip("@ ")
        if self.sha.startswith(search_query):
            return 100
        return 0


class Issue(BaseEntry):
    """An issue/PR on Github

    Args:
        issue: The github3 issue object
        repository: The github3 repository object
    """

    def __init__(self, issue: GHIssue, repository: GHRepo) -> None:
        self._issue = issue
        self._repository = repository

    @property
    def type(self) -> str:
        return "Issue" if not self._issue.pull_request_urls else "PR"

    @property
    def owner(self) -> str:
        return self._repository.owner.login

    @property
    def repo(self) -> str:
        return self._repository.name

    @property
    def number(self) -> int:
        return self._issue.number

    @property
    def url(self) -> str:
        return self._issue.html_url

    @property
    def title(self) -> str:
        return self._issue.title

    @property
    def author(self) -> str:
        return self._issue.user.login

    @property
    def short_name(self) -> str:
        return (
            f'{"" if self.owner == DEFAULT_REPO_OWNER else self.owner + "/"}'
            f'{"" if self.repo == DEFAULT_REPO_NAME else self.repo}'
            f"#{self.number}"
        )

    @property
    def display_name(self) -> str:
        return f"{self.type} {self.short_name}: {self.title} by {self.author}"

    @property
    def description(self) -> str:
        return "Search on GitHub"

    @property
    def short_description(self) -> str:
        # Needs to be here because of cyclical imports
        from .util import truncate_str  # pylint:disable=import-outside-toplevel

        string = f"{self.type} {self.short_name}: {self.title}"
        return truncate_str(string, 25)

    def html_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.display_name}</a>'

    def html_insertion_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def compare_to_query(self, search_query: str) -> float:
        search_query = search_query.lstrip("# ")
        if str(self.number) == search_query:
            return 100
        return fuzz.token_set_ratio(self.title.lower(), search_query.lower())


class PTBContrib(BaseEntry):
    """A contribution of ptbcontrib

    Args:
        name: The name of the contribution
        url: The url to the contribution
    """

    def __init__(self, name: str, url: str):
        self.name = name
        self.url = url

    @property
    def display_name(self) -> str:
        return f"ptbcontrib/{self.name}"

    @property
    def description(self) -> str:
        return "Community base extensions for python-telegram-bot"

    def html_markup(self, _: str = None) -> str:
        return f'<a href="{self.url}">{self.display_name}</a>'

    def html_insertion_markup(self, search_query: str = None) -> str:
        return self.html_markup(search_query)

    def compare_to_query(self, search_query: str) -> float:
        # Here we just assume that everything before thi first / is ptbcontrib
        # (modulo typos). That could be wrong, but then it's the users fault :)
        search_query = search_query.split("/", maxsplit=1)[-1]
        return fuzz.ratio(self.name.lower(), search_query.lower())


class TagHint(BaseEntry):
    """A tag hint for frequently used texts in the groups.

    Attributes:
        tag: The tag of this hint.
        message: The message to display in HTML layout. It may contain a ``{query}`` part, which
            will be filled appropriately.
        description: Description of the tag hint.
        default_query: Optional. Inserted into the ``message`` if no other query is provided.
        inline_keyboard: Optional. In InlineKeyboardMarkup to attach to the hint.
    """

    def __init__(
        self,
        tag: str,
        message: str,
        description: str,
        default_query: str = None,
        inline_keyboard: InlineKeyboardMarkup = None,
    ):
        self.tag = tag
        self._message = message
        self._default_query = default_query
        self._description = description
        self._inline_keyboard = inline_keyboard

    @property
    def display_name(self) -> str:
        return f"Tag hint: {self.short_name}"

    @property
    def short_name(self) -> str:
        return f"/{self.tag}"

    @property
    def description(self) -> str:
        return self._description

    def html_markup(self, search_query: str = None) -> str:
        return self._message.format(
            query=search_query.split(maxsplit=1)[-1] if search_query else self._default_query
        )

    def html_insertion_markup(self, search_query: str = None) -> str:
        return self.html_markup(search_query=search_query)

    def compare_to_query(self, search_query: str) -> float:
        first = search_query.lstrip("/").split(maxsplit=1)[0]
        return fuzz.ratio(self.tag.lower(), first.lower())

    @property
    def inline_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        return self._inline_keyboard
