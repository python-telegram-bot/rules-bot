import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar, List, Optional

from telegram import InlineKeyboardMarkup
from thefuzz import fuzz

from components.const import (
    ARROW_CHARACTER,
    DEFAULT_REPO_NAME,
    DEFAULT_REPO_OWNER,
    DOCS_URL,
    TELEGRAM_SUPERSCRIPT,
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

    def html_reply_markup(self, search_query: str = None) -> str:
        """HTML markup to be used for reply search. May depend on the search query.
        Defaults to :meth:`html_insertion_markup`, but may be overridden.
        """
        return self.html_insertion_markup(search_query=search_query)

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
    """

    def __init__(self, name: str):
        self._name = name
        self._search_name = f"example {self._name}"

        if name.endswith(".py"):
            href = name[:-3]
        else:
            href = name
        self.url = f"{DOCS_URL}examples.html#examples-{href}"

    @property
    def display_name(self) -> str:
        return f"Examples {ARROW_CHARACTER} {self._name}"

    @property
    def short_name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Examples directory of python-telegram-bot"

    def html_markup(self, search_query: str = None) -> str:
        return (
            "Examples directory of <i>python-telegram-bot</i>:"
            f"\n{self.html_insertion_markup(search_query)}"
        )

    def html_insertion_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def compare_to_query(self, search_query: str) -> float:
        if search_query.endswith(".py"):
            search_query = search_query[:-3]

        return fuzz.partial_token_set_ratio(self._search_name, search_query)


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
        self._compare_name = f"{self.category} {self.name}"

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

    def html_insertion_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def html_reply_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">Wiki Category <i>{self.category}</i>: {self.short_name}</a>'

    def compare_to_query(self, search_query: str) -> float:
        return fuzz.token_set_ratio(self._compare_name, search_query)


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


class FRDPEntry(WikiPage):
    """A frequently requested design pattern entry

    Args:
        name: The name of the entry
        url: URL of the entry
    """

    def __init__(self, name: str, url: str):
        super().__init__(category="Design Pattern", name=name, url=url)


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
        return self._display_name or self.name

    @property
    def short_name(self) -> str:
        name = self._display_name or self.name

        if name.startswith("telegram."):
            return name[len("telegram.") :]
        return name

    @property
    def description(self) -> str:
        return "Documentation of python-telegram-bot"

    def html_markup(self, search_query: str = None) -> str:
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

    def html_insertion_markup(self, search_query: str = None) -> str:
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
            score += fuzz.ratio(target, value)
        # ... and the full name because we're generous
        score += fuzz.ratio(search_query, self.name)
        # To stay <= 100 as not to overrule other results
        score = score / 2

        # IISC std: is the domain for general stuff like headlines and chapters.
        # we'll wanna give those a little less weight
        if self.entry_type.startswith("std:"):
            score *= 0.8
        return score


class ParamDocEntry(DocEntry):
    """An entry to the PTB docs. Special case of a parameter of a function or method.

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
        if ".params." not in name:
            raise ValueError("The passed name doesn't match a parameter name.")

        base_name, parameter_name = name.split(".params.")
        self._base_name = base_name
        self._parameter_name = parameter_name
        super().__init__(
            url=url,
            entry_type=entry_type,
            name=name,
            display_name=f"Parameter {self._parameter_name} of {self._base_name}",
            telegram_name=telegram_name,
            telegram_url=telegram_url,
        )
        self._base_url = self.url.split(".params.")[0]
        self._parsed_name_wo_params = self.parse_search_query(self.name.replace(".params.", ""))

    def html_markup(self, search_query: str = None) -> str:
        base = (
            f"<code>{self._base_name}(..., {self._parameter_name}=...)</code>\n"
            f"<i>python-telegram-bot</i> documentation for this {self.effective_type} "
            f'of <a href="{self._base_url}">{self._base_name}</a>:\n'
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
        return f'<a href="{self.url}">{self._parameter_name}</a>'

    def html_insertion_markup(self, search_query: str = None) -> str:
        base_markup = (
            f'Parameter <a href="{self.url}">{self._parameter_name}</a> of '
            f'<a href="{self._base_url}">{self._base_name}</a>'
        )
        if not self.telegram_name and not self.telegram_url:
            return base_markup
        return f'{base_markup} <a href="{self.telegram_url}">' f"{TELEGRAM_SUPERSCRIPT}</a>"

    def compare_to_query(self, search_query: str) -> float:
        score = 0.0
        processed_query = self.parse_search_query(search_query)

        # We compare all the single parts of the query, with & without the ".params."
        for target, value in zip(processed_query, self._parsed_name):
            score += fuzz.ratio(target, value)
        for target, value in zip(processed_query, self._parsed_name_wo_params):
            score += fuzz.ratio(target, value)
        # ... and the full name because we're generous with & without leading "parameter"
        score += fuzz.ratio(search_query, self.name)
        score += fuzz.ratio(search_query, f"parameter {self.name}")

        # To stay <= 100 as not to overrule other results
        return score / 4


@dataclass
class Commit(BaseEntry):
    """A commit on Github

    Args:
        owner: str
        repo: str
        sha: str
        url: str
        title: str
        author: str
    """

    owner: str
    repo: str
    sha: str
    url: str
    title: str
    author: str

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

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

    def html_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">{self.display_name}</a>'

    def html_insertion_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def html_reply_markup(self, search_query: str = None) -> str:
        return self.html_markup(search_query=search_query)

    def compare_to_query(self, search_query: str) -> float:
        search_query = search_query.lstrip("@ ")
        if self.sha.startswith(search_query):
            return 100
        return 0


@dataclass
class _IssueOrPullRequestOrDiscussion(BaseEntry):
    _TYPE: ClassVar = ""  # pylint:disable=invalid-name
    owner: str
    repo: str
    number: int
    title: str
    url: str
    author: Optional[str]

    @property
    def short_name(self) -> str:
        return (
            f'{"" if self.owner == DEFAULT_REPO_OWNER else self.owner + "/"}'
            f'{"" if self.repo == DEFAULT_REPO_NAME else self.repo}'
            f"#{self.number}"
        )

    @property
    def display_name(self) -> str:
        if self.author:
            return f"{self._TYPE} {self.short_name}: {self.title} by {self.author}"
        return f"{self._TYPE} {self.short_name}: {self.title}"

    @property
    def description(self) -> str:
        return "Search on GitHub"

    @property
    def short_description(self) -> str:
        # Needs to be here because of cyclical imports
        from .util import truncate_str  # pylint:disable=import-outside-toplevel

        string = f"{self._TYPE} {self.short_name}: {self.title}"
        return truncate_str(string, 50)

    def html_markup(self, search_query: str = None) -> str:  # pylint:disable=unused-argument
        return f'<a href="{self.url}">{self.display_name}</a>'

    # pylint:disable=unused-argument
    def html_insertion_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">{self.short_name}</a>'

    def html_reply_markup(self, search_query: str = None) -> str:
        return self.html_markup(search_query=search_query)

    def compare_to_query(self, search_query: str) -> float:
        search_query = search_query.lstrip("# ")
        if str(self.number) == search_query:
            return 100
        return fuzz.token_set_ratio(self.title, search_query)


@dataclass
class Issue(_IssueOrPullRequestOrDiscussion):
    """An issue on GitHub

    Args:
        number: the number
        repo: the repo name
        owner: the owner name
        url: the url of the issue
        title: title of the issue
    """

    _TYPE: ClassVar = "Issue"


@dataclass
class PullRequest(_IssueOrPullRequestOrDiscussion):
    """An pullRequest on GitHub

    Args:
        number: the number
        repo: the repo name
        owner: the owner name
        url: the url of the pull request
        title: title of the pull request
    """

    _TYPE: ClassVar = "PullRequest"


@dataclass
class Discussion(_IssueOrPullRequestOrDiscussion):
    """A Discussion on GitHub

    Args:
        number: the number
        repo: the repo name
        owner: the owner name
        url: the url of the pull request
        title: title of the pull request
    """

    _TYPE: ClassVar = "Discussion"


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

    def html_markup(self, search_query: str = None) -> str:
        return f'<a href="{self.url}">{self.display_name}</a>'

    def html_insertion_markup(self, search_query: str = None) -> str:
        return self.html_markup(search_query)

    def compare_to_query(self, search_query: str) -> float:
        # Here we just assume that everything before thi first / is ptbcontrib
        # (modulo typos). That could be wrong, but then it's the users fault :)
        search_query = search_query.split("/", maxsplit=1)[-1]
        return fuzz.ratio(self.name, search_query)


class TagHint(BaseEntry):
    """A tag hint for frequently used texts in the groups.

    Attributes:
        tag: The tag of this hint.
        message: The message to display in HTML layout. It may contain a ``{query}`` part, which
            will be filled appropriately.
        description: Description of the tag hint.
        default_query: Optional. Inserted into the ``message`` if no other query is provided.
        inline_keyboard: Optional. In InlineKeyboardMarkup to attach to the hint.
        group_command: Optional. Whether this tag hint should be listed as command in the groups.
    """

    def __init__(
        self,
        tag: str,
        message: str,
        description: str,
        default_query: str = None,
        inline_keyboard: InlineKeyboardMarkup = None,
        group_command: bool = False,
    ):
        self.tag = tag
        self._message = message
        self._default_query = default_query
        self._description = description
        self._inline_keyboard = inline_keyboard
        self.group_command = group_command

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
        parts = search_query.split(maxsplit=1) if search_query else []
        insert = parts[1] if len(parts) > 1 else None
        return self._message.format(query=insert or self._default_query)

    def html_insertion_markup(self, search_query: str = None) -> str:
        return self.html_markup(search_query=search_query)

    def compare_to_query(self, search_query: str) -> float:
        parts = search_query.lstrip("/").split(maxsplit=1)
        if parts:
            return fuzz.ratio(self.tag, parts[0])
        return 0

    @property
    def inline_keyboard(self) -> Optional[InlineKeyboardMarkup]:
        return self._inline_keyboard
