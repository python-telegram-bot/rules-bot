from copy import deepcopy
from typing import cast
from uuid import uuid4

from telegram import (
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from components.const import ENCLOSED_REGEX, ENCLOSING_REPLACEMENT_CHARACTER
from components.entrytypes import Issue
from components.search import Search


def article(
    title: str = "",
    description: str = "",
    message_text: str = "",
    key: str = None,
    reply_markup: InlineKeyboardMarkup = None,
) -> InlineQueryResultArticle:
    return InlineQueryResultArticle(
        id=key or str(uuid4()),
        title=title,
        description=description,
        input_message_content=InputTextMessageContent(message_text=message_text),
        reply_markup=reply_markup,
    )


async def inline_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:  # pylint: disable=R0915
    ilq = cast(InlineQuery, update.inline_query)
    query = ilq.query
    switch_pm_text = "❓ Help"
    search = cast(Search, context.bot_data["search"])

    if ENCLOSED_REGEX.search(query):
        results_list = []
        symbols = tuple(ENCLOSED_REGEX.findall(query))
        search_results = await search.multi_search_combinations(symbols)

        for combination in search_results:
            description = ", ".join(entry.short_description for entry in combination.values())
            message_text = query
            index = []
            keyboard = None

            for symbol, entry in combination.items():
                char = ENCLOSING_REPLACEMENT_CHARACTER
                message_text = message_text.replace(
                    f"{char}{symbol}{char}", entry.html_insertion_markup(symbol)
                )
                if isinstance(entry, Issue):
                    index.append(entry.html_markup(symbol))
                # Merge keyboards into one
                if entry_kb := entry.inline_keyboard:
                    if not keyboard:
                        keyboard = deepcopy(entry_kb)
                    else:
                        keyboard.inline_keyboard.extend(entry_kb.inline_keyboard)

            if index:
                message_text += "\n\n" + "\n".join(index)

            results_list.append(
                article(
                    title="Insert links into message",
                    description=description,
                    message_text=message_text,
                    reply_markup=keyboard,
                )
            )
    else:
        simple_search_results = await search.search(query)
        if not simple_search_results:
            results_list = []
            switch_pm_text = "❌ No Search Results Found"
        else:
            results_list = [
                article(
                    title=entry.display_name,
                    description=entry.description,
                    message_text=entry.html_markup(query),
                    reply_markup=entry.inline_keyboard,
                )
                for entry in simple_search_results
            ]

    try:
        await ilq.answer(
            results=results_list,
            switch_pm_text=switch_pm_text,
            switch_pm_parameter="inline-help",
            cache_time=0,
            auto_pagination=True,
        )
    except BadRequest as exc:
        if "can't parse entities" not in exc.message:
            raise exc
        await ilq.answer(
            results=[],
            switch_pm_text="❌ Invalid entities. Click me.",
            switch_pm_parameter="inline-entity-parsing",
        )
