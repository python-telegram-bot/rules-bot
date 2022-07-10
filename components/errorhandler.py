import html
import json
import logging
import traceback
from typing import Optional, cast

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackContext

from components.const import ERROR_CHANNEL_CHAT_ID

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: CallbackContext) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(
        None, context.error, cast(Exception, context.error).__traceback__
    )
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message_1 = (
        f"An exception was raised while handling an update\n\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>"
    )
    message_2 = f"<pre>{html.escape(tb_string)}</pre>"

    user_id: Optional[int] = None
    message_3 = ""
    if isinstance(update, Update) and update.effective_user:
        user_id = update.effective_user.id
    if context.job:
        user_id = context.job.user_id
    if user_id:
        data_str = html.escape(
            json.dumps(context.application.user_data[user_id], indent=2, ensure_ascii=False)
        )
        message_3 = (
            "<code>user_data</code> associated with this exception:\n\n" f"<pre>{data_str}</pre>"
        )

    # Finally, send the messages
    # We send update and traceback in two parts to reduce the chance of hitting max length
    try:
        sent_message = await context.bot.send_message(
            chat_id=ERROR_CHANNEL_CHAT_ID, text=message_1
        )
        await sent_message.reply_html(message_2)
    except BadRequest as exc:
        if "too long" in str(exc):
            message = (
                f"Hey.\nThe error <code>{html.escape(str(context.error))}</code> happened."
                f" The traceback is too long to send, but it was written to the log."
            )
            sent_message = await context.bot.send_message(
                chat_id=ERROR_CHANNEL_CHAT_ID, text=message
            )
        else:
            raise exc
    finally:
        if message_3:
            await sent_message.reply_html(message_3)
