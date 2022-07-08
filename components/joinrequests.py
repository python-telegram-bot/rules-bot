import datetime
from typing import Tuple, cast

from telegram import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    Update,
    User,
)
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes, Job, JobQueue

from components.const import (
    ERROR_CHANNEL_CHAT_ID,
    OFFTOPIC_CHAT_ID,
    OFFTOPIC_RULES,
    ONTOPIC_CHAT_ID,
    ONTOPIC_RULES,
    ONTOPIC_USERNAME,
)


async def approve_user(
    user_id: int, chat_id: int, group_name: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await context.bot.approve_chat_join_request(user_id=user_id, chat_id=chat_id)


async def decline_user(
    user_id: int, chat_id: int, group_name: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await context.bot.decline_chat_join_request(user_id=user_id, chat_id=chat_id)


async def join_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_request = cast(ChatJoinRequest, update.chat_join_request)
    user = join_request.from_user
    on_topic = join_request.chat.username == ONTOPIC_USERNAME
    group_mention = ONTOPIC_CHAT_ID if on_topic else OFFTOPIC_CHAT_ID
    text = (
        f"Hi, {user.mention_html()}! I'm {context.bot.bot.mention_html()}, the "
        f"guardian of the group {group_mention}, that you requested to join.\n\nBefore you can "
        "join the group, please carefully read the following rules of the group. Confirm that you "
        "have read them by double-tapping the button at the bottom of the message - that's it 🙃"
        f"\n\n{ONTOPIC_RULES if on_topic else OFFTOPIC_RULES}\n\n"
        "ℹ️ If I fail to react to your confirmation within 2 hours, please contact one of the"
        "administrators of the group. Admins are marked as such in the list of group members."
    )
    reply_markup = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton(
            text="I have read the rules 📖",
            callback_data=f"JOIN 1 {join_request.chat.id}",
        )
    )
    try:
        message = await user.send_message(text=text, reply_markup=reply_markup)
    except Forbidden:
        # If the user blocked the bot, let's give the admins a chance to handle that
        # TG also notifies the user and forwards the message once the user unblocks the bot, but
        # forwarding it still doesn't hurt ...
        text = (
            f"User {user.mention_html()} with id {user.id} requested to join the group "
            f"{join_request.chat.username} but has blocked me. Please manually handle this."
        )
        await context.bot.send_message(chat_id=ERROR_CHANNEL_CHAT_ID, text=text)
        return

    cast(JobQueue, context.job_queue).run_once(
        callback=join_request_timeout_job,
        when=datetime.timedelta(hours=2),
        data=(message, group_mention),
        name=f"JOIN_TIMEOUT {user.id}",
        user_id=user.id,
        chat_id=join_request.chat.id,
    )


async def join_request_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    callback_query = cast(CallbackQuery, update.callback_query)
    user = cast(User, update.effective_user)
    _, press, chat_id = cast(str, callback_query.data).split()
    if press == "2":
        jobs = cast(JobQueue, context.job_queue).get_jobs_by_name(f"JOIN_TIMEOUT {user.id}")
        if jobs:
            jobs[0].schedule_removal()

        await approve_user(
            user_id=user.id, chat_id=int(chat_id), group_name="Unknown", context=context
        )
        context.application.create_task(
            user.send_message("Nice! Have fun in the group 🙂"), update=update
        )
        reply_markup = None
    else:
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton(
                text="⚠️ Tap again to confirm",
                callback_data=f"JOIN 2 {chat_id}",
            )
        )

    try:
        context.application.create_task(
            callback_query.edit_message_reply_markup(reply_markup=reply_markup), update=update
        )
    except BadRequest as exc:
        # Ignore people clicking the button too quickly
        if "Message is not modified" not in exc.message:
            raise exc


async def join_request_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = cast(Job, context.job)
    user_id = cast(int, job.user_id)
    chat_id = cast(int, job.chat_id)
    message, group = cast(Tuple[Message, str], job.data)
    text = (
        f"Your request to join the group {group} has timed out. Please send a new request to join."
    )
    await decline_user(user_id=user_id, chat_id=chat_id, group_name=group, context=context)
    await message.edit_text(text=text)
