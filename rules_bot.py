import configparser
import logging
import os

from telegram import (
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeChatAdministrators,
    Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatJoinRequestHandler,
    CommandHandler,
    Defaults,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from components import inlinequeries
from components.callbacks import (
    ban_sender_channels,
    delete_new_chat_members_message,
    docs,
    help_callback,
    join_request_buttons,
    join_request_callback,
    leave_chat,
    off_on_topic,
    raise_app_handler_stop,
    reply_search,
    rules,
    sandwich,
    say_potato_button,
    say_potato_command,
    start,
    tag_hint,
    wiki,
)
from components.const import (
    ALLOWED_CHAT_IDS,
    ALLOWED_USERNAMES,
    ERROR_CHANNEL_CHAT_ID,
    OFFTOPIC_CHAT_ID,
    OFFTOPIC_RULES,
    OFFTOPIC_RULES_MESSAGE_ID,
    OFFTOPIC_USERNAME,
    ONTOPIC_CHAT_ID,
    ONTOPIC_RULES,
    ONTOPIC_RULES_MESSAGE_ID,
    ONTOPIC_USERNAME,
)
from components.errorhandler import error_handler
from components.github import github_issues
from components.taghints import TagHintFilter
from components.util import build_command_list, rate_limit_tracker

if os.environ.get("ROOLSBOT_DEBUG"):
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
    )
else:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("github3").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    bot = application.bot

    # Update rules messages
    try:
        await bot.edit_message_text(
            chat_id=ONTOPIC_CHAT_ID,
            message_id=ONTOPIC_RULES_MESSAGE_ID,
            text=ONTOPIC_RULES,
        )
    except (BadRequest, Forbidden) as exc:
        logger.warning("Updating on-topic rules failed: %s", exc)
    try:
        await bot.edit_message_text(
            chat_id=OFFTOPIC_CHAT_ID,
            message_id=OFFTOPIC_RULES_MESSAGE_ID,
            text=OFFTOPIC_RULES,
        )
    except (BadRequest, Forbidden) as exc:
        logger.warning("Updating off-topic rules failed: %s", exc)

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


def main() -> None:
    config = configparser.ConfigParser()
    config.read("bot.ini")

    defaults = Defaults(parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    application = (
        ApplicationBuilder()
        .token(config["KEYS"]["bot_api"])
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )

    # Note: Order matters!

    # Don't handle messages that were sent in the error channel
    application.add_handler(
        MessageHandler(filters.Chat(chat_id=ERROR_CHANNEL_CHAT_ID), raise_app_handler_stop),
        group=-2,
    )
    # Leave groups that are not maintained by PTB
    application.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & ~(filters.Chat(username=ALLOWED_USERNAMES) | filters.Chat(chat_id=ALLOWED_CHAT_IDS)),
            leave_chat,
        ),
        group=-2,
    )

    application.add_handler(MessageHandler(~filters.COMMAND, rate_limit_tracker), group=-1)
    application.add_handler(
        MessageHandler(
            filters.SenderChat.CHANNEL & ~filters.IS_AUTOMATIC_FORWARD,
            ban_sender_channels,
            block=False,
        )
    )

    # Simple commands
    # The first one also handles deep linking /start commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("docs", docs))
    application.add_handler(CommandHandler("wiki", wiki))
    application.add_handler(CommandHandler("help", help_callback))

    # Stuff that runs on every message with regex
    application.add_handler(
        MessageHandler(
            filters.Regex(r"(?i)[\s\S]*?((sudo )?make me a sandwich)[\s\S]*?"), sandwich
        )
    )
    application.add_handler(MessageHandler(filters.Regex("/(on|off)_topic"), off_on_topic))

    # Tag hints - works with regex
    application.add_handler(MessageHandler(TagHintFilter(), tag_hint))

    # We need several matches so filters.REGEX is basically useless
    # therefore we catch everything and do regex ourselves
    application.add_handler(
        MessageHandler(filters.TEXT & filters.UpdateType.MESSAGES & ~filters.COMMAND, reply_search)
    )

    # Status updates
    application.add_handler(
        MessageHandler(
            filters.Chat(username=[ONTOPIC_USERNAME, OFFTOPIC_USERNAME])
            & filters.StatusUpdate.NEW_CHAT_MEMBERS,
            delete_new_chat_members_message,
            block=False,
        ),
        group=1,
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

    # Error Handler
    application.add_error_handler(error_handler)

    try:
        github_issues.set_auth(
            config["KEYS"]["github_client_id"], config["KEYS"]["github_client_secret"]
        )
    except KeyError:
        logging.info("No github api token set. Rate-limit is 60 requests/hour without auth.")

    # github_issues.init_ptb_contribs(application.job_queue)  # type: ignore[arg-type]
    # github_issues.init_issues(application.job_queue)  # type: ignore[arg-type]

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
