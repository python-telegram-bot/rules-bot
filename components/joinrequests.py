import datetime
from typing import Any, Dict, Tuple, Union, cast

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


def get_dtm_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S:%f")


async def approve_user(
    user: Union[int, User], chat_id: int, group_name: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user_data = cast(Dict[Any, Any], context.user_data)
    try:
        if isinstance(user, User):
            await user.approve_join_request(chat_id=chat_id)
        else:
            await context.bot.approve_chat_join_request(user_id=user, chat_id=chat_id)
        user_data.setdefault(int(chat_id), {}).setdefault("approved", []).append(get_dtm_str())
    except BadRequest as exc:
        user_mention = f"{user.username} - {user.id}" if isinstance(user, User) else str(user)
        error_message = f"{exc} - {user_mention} - {group_name}"
        user_data.setdefault(int(chat_id), {}).setdefault("approve failed", []).append(
            f"{get_dtm_str()}: {exc}"
        )
        raise BadRequest(error_message) from exc
    except Forbidden as exc:
        if "user is deactivated" not in exc.message:
            raise exc


async def decline_user(
    user: Union[int, User], chat_id: int, group_name: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user_data = cast(Dict[Any, Any], context.user_data)
    try:
        if isinstance(user, User):
            await user.decline_join_request(chat_id=chat_id)
        else:
            await context.bot.decline_chat_join_request(user_id=user, chat_id=chat_id)
        user_data.setdefault(int(chat_id), {}).setdefault("declined", []).append(get_dtm_str())
    except BadRequest as exc:
        user_mention = f"{user.username} - {user.id}" if isinstance(user, User) else str(user)
        error_message = f"{exc} - {user_mention} - {group_name}"
        user_data.setdefault(int(chat_id), {}).setdefault("declined failed", []).append(
            f"{get_dtm_str()}: {exc}"
        )
        raise BadRequest(error_message) from exc
    except Forbidden as exc:
        if "user is deactivated" not in exc.message:
            raise exc


async def join_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_request = cast(ChatJoinRequest, update.chat_join_request)
    user = join_request.from_user
    chat_id = join_request.chat.id
    jobs = cast(JobQueue, context.job_queue).get_jobs_by_name(f"JOIN_TIMEOUT {chat_id} {user.id}")
    if jobs:
        # No need to ping the user again if we already did
        return

    user_data = cast(Dict[Any, Any], context.user_data)
    on_topic = join_request.chat.username == ONTOPIC_USERNAME
    group_mention = ONTOPIC_CHAT_ID if on_topic else OFFTOPIC_CHAT_ID

    user_data.setdefault(int(chat_id), {}).setdefault("received join request", []).append(
        get_dtm_str()
    )

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
            callback_data=f"JOIN 1 {chat_id}",
        )
    )
    try:
        message = await user.send_message(text=text, reply_markup=reply_markup)
    except Forbidden:
        # If the user blocked the bot, let's give the admins a chance to handle that
        # TG also notifies the user and forwards the message once the user unblocks the bot, but
        # forwarding it still doesn't hurt ...
        user_data.setdefault("blocked bot", []).append(get_dtm_str())
        text = (
            f"User {user.mention_html()} with id {user.id} requested to join the group "
            f"{join_request.chat.username} but has blocked me. Please manually handle this."
        )
        await context.bot.send_message(chat_id=ERROR_CHANNEL_CHAT_ID, text=text)
        return

    cast(JobQueue, context.job_queue).run_once(
        callback=join_request_timeout_job,
        when=datetime.timedelta(hours=2),
        data=(user, message, group_mention),
        name=f"JOIN_TIMEOUT {chat_id} {user.id}",
        user_id=user.id,
        chat_id=chat_id,
    )


async def join_request_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_data = cast(Dict[Any, Any], context.user_data)
    callback_query = cast(CallbackQuery, update.callback_query)
    user = cast(User, update.effective_user)
    _, press, chat_id = cast(str, callback_query.data).split()
    if press == "2":
        user_data.setdefault(int(chat_id), {}).setdefault("pressed button 2", []).append(
            get_dtm_str()
        )
        jobs = cast(JobQueue, context.job_queue).get_jobs_by_name(
            f"JOIN_TIMEOUT {chat_id} {user.id}"
        )
        if jobs:
            for job in jobs:
                job.schedule_removal()
                user_data.setdefault(int(chat_id), {}).setdefault(
                    "removed join timeout", []
                ).append(get_dtm_str())

        try:
            await approve_user(
                user=user, chat_id=int(chat_id), group_name="Unknown", context=context
            )
        except BadRequest as exc:
            # If the user was already approved for some reason, we can just ignore the error
            if "User_already_participant" not in exc.message:
                raise exc

        context.application.create_task(
            user.send_message("Nice! Have fun in the group 🙂"), update=update
        )
        reply_markup = None
    else:
        user_data.setdefault(int(chat_id), {}).setdefault("pressed button 1", []).append(
            get_dtm_str()
        )
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton(
                text="⚠️ Tap again to confirm",
                callback_data=f"JOIN 2 {chat_id}",
            )
        )

    try:
        await callback_query.edit_message_reply_markup(reply_markup=reply_markup)
    except BadRequest as exc:
        # Ignore people clicking the button too quickly
        if "Message is not modified" not in exc.message:
            raise exc


async def join_request_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = cast(Job, context.job)
    chat_id = cast(int, job.chat_id)
    user, message, group = cast(Tuple[User, Message, str], job.data)
    text = (
        f"Your request to join the group {group} has timed out. Please send a new request to join."
    )
    await decline_user(user=user, chat_id=chat_id, group_name=group, context=context)
    try:
        await message.edit_text(text=text)
    except Forbidden as exc:
        if "user is deactivated" not in exc.message:
            raise exc
