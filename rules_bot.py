import configparser
import logging
import os
from typing import cast

import httpx
from telegram import (
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    CommandHandler,
    Defaults,
    InlineQueryHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from components import inlinequeries
from components.callbacks import (
    ban_sender_channels,
    buy,
    command_token_warning,
    compat_warning,
    delete_message,
    leave_chat,
    long_code_handling,
    off_on_topic,
    privacy,
    raise_app_handler_stop,
    regex_token_warning,
    reply_search,
    rules,
    sandwich,
    say_potato_button,
    say_potato_command,
    start,
    tag_hint,
)
from components.const import (
    COMPAT_ERRORS,
    DESCRIPTION,
    ERROR_CHANNEL_CHAT_ID,
    OFFTOPIC_CHAT_ID,
    OFFTOPIC_USERNAME,
    ONTOPIC_CHAT_ID,
    ONTOPIC_USERNAME,
    SHORT_DESCRIPTION,
)
from components.errorhandler import error_handler
from components.joinrequests import join_request_buttons, join_request_callback
from components.rulesjobqueue import RulesJobQueue
from components.search import Search
from components.taghints import TagHintFilter
from components.util import FindAllFilter, build_command_list, rate_limit_tracker

if os.environ.get("ROOLSBOT_DEBUG"):
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
    )
else:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("gql").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    bot = application.bot
    await cast(Search, application.bot_data["search"]).initialize(application)

    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_description(DESCRIPTION)

    # set commands
    await bot.set_my_commands(
        build_command_list(private=True),
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        build_command_list(private=False),
        scope=BotCommandScopeAllGroupChats(),
    )

    for group_name in [ONTOPIC_CHAT_ID, OFFTOPIC_CHAT_ID]:
        await bot.set_my_commands(
            build_command_list(private=False, group_name=group_name),
            scope=BotCommandScopeChat(group_name),
        )
        await bot.set_my_commands(
            build_command_list(private=False, group_name=group_name, admins=True),
            scope=BotCommandScopeChatAdministrators(group_name),
        )


async def post_shutdown(application: Application) -> None:
    await cast(Search, application.bot_data["search"]).shutdown()


def main() -> None:
    config = configparser.ConfigParser()
    config.read("bot.ini")

    defaults = Defaults(parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    application = (
        ApplicationBuilder()
        .token(config["KEYS"]["bot_api"])
        .defaults(defaults)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .job_queue(RulesJobQueue())
        .build()
    )

    application.bot_data["search"] = Search(github_auth=config["KEYS"]["github_auth"])

    if "pastebin_auth" in config["KEYS"]:
        application.bot_data["pastebin_client"] = httpx.AsyncClient(
            auth=httpx.BasicAuth(username="Rools", password=config["KEYS"]["pastebin_auth"])
        )

    # Note: Order matters!

    # Don't handle messages that were sent in the error channel
    application.add_handler(
        MessageHandler(filters.Chat(chat_id=ERROR_CHANNEL_CHAT_ID), raise_app_handler_stop),
        group=-2,
    )
    # Leave groups that are not maintained by PTB
    application.add_handler(
        TypeHandler(
            type=Update,
            callback=leave_chat,
        ),
        group=-2,
    )

    application.add_handler(MessageHandler(~filters.COMMAND, rate_limit_tracker), group=-2)

    # We need several different patterns, so filters.REGEX doesn't do the trick
    # therefore we catch everything and do regex ourselves. In case the message contains a
    # long code block, we'll raise AppHandlerStop to prevent further processing.
    application.add_handler(MessageHandler(filters.TEXT, long_code_handling), group=-1)

    application.add_handler(
        MessageHandler(
            filters.SenderChat.CHANNEL & ~filters.ChatType.CHANNEL & ~filters.IS_AUTOMATIC_FORWARD,
            ban_sender_channels,
            block=False,
        )
    )

    # Simple commands
    # The first one also handles deep linking /start commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("buy", buy))
    application.add_handler(CommandHandler("privacy", privacy))

    # Stuff that runs on every message with regex
    application.add_handler(
        MessageHandler(
            filters.Regex(r"(?i)[\s\S]*?((sudo )?make me a sandwich)[\s\S]*?"), sandwich
        )
    )
    application.add_handler(MessageHandler(filters.Regex("/(on|off)_topic"), off_on_topic))

    # Warn user who shared a bot's token
    application.add_handler(CommandHandler("token", command_token_warning))
    application.add_handler(
        MessageHandler(FindAllFilter(r"([0-9]+:[a-zA-Z0-9_-]{35})"), regex_token_warning)
    )

    # Tag hints - works with regex
    application.add_handler(MessageHandler(TagHintFilter(), tag_hint))

    # Compat tag hint via regex
    application.add_handler(MessageHandler(filters.Regex(COMPAT_ERRORS), compat_warning))

    # We need several matches so filters.REGEX is basically useless
    # therefore we catch everything and do regex ourselves
    application.add_handler(
        MessageHandler(filters.TEXT & filters.UpdateType.MESSAGES & ~filters.COMMAND, reply_search)
    )

    # Inline Queries
    application.add_handler(InlineQueryHandler(inlinequeries.inline_query))

    # Captcha for userbots
    application.add_handler(
        CommandHandler(
            "say_potato",
            say_potato_command,
            filters=filters.Chat(username=[ONTOPIC_USERNAME, OFFTOPIC_USERNAME]),
        )
    )
    application.add_handler(CallbackQueryHandler(say_potato_button, pattern="^POTATO"))

    # Join requests
    application.add_handler(ChatJoinRequestHandler(callback=join_request_callback, block=False))
    application.add_handler(CallbackQueryHandler(join_request_buttons, pattern="^JOIN"))

    # Delete unhandled commands - e.g. for users that like to click on blue text in other messages
    application.add_handler(MessageHandler(filters.COMMAND, delete_message))

    # Status updates
    application.add_handler(
        MessageHandler(
            filters.Chat(username=[ONTOPIC_USERNAME, OFFTOPIC_USERNAME])
            & filters.StatusUpdate.NEW_CHAT_MEMBERS,
            delete_message,
            block=False,
        ),
        group=1,
    )

    # Error Handler
    application.add_error_handler(error_handler)

    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)


if __name__ == "__main__":
    main()
