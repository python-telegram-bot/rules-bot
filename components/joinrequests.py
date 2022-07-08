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
from telegram.ext import ContextTypes, Job, JobQueue

from components.const import (
    OFFTOPIC_CHAT_ID,
    OFFTOPIC_RULES,
    ONTOPIC_CHAT_ID,
    ONTOPIC_RULES,
    ONTOPIC_USERNAME,
)


async def join_request_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    join_request = cast(ChatJoinRequest, update.chat_join_request)
    on_topic = join_request.chat.username == ONTOPIC_USERNAME
    group_mention = ONTOPIC_CHAT_ID if on_topic else OFFTOPIC_CHAT_ID
    text = (
        f"Hi, {join_request.from_user.mention_html()}! I'm {context.bot.bot.mention_html()}, the "
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
    message = await join_request.from_user.send_message(text=text, reply_markup=reply_markup)
    cast(JobQueue, context.job_queue).run_once(
        callback=join_request_timeout_job,
        when=datetime.timedelta(hours=2),
        data=(join_request.from_user, join_request.chat.id, message, group_mention),
        name=f"JOIN_TIMEOUT {join_request.from_user.id}",
    )


async def join_request_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    callback_query = cast(CallbackQuery, update.callback_query)
    user = cast(User, update.effective_user)
    _, press, chat = cast(str, callback_query.data).split()
    if press == "2":
        await user.approve_join_request(chat_id=int(chat))
        context.application.create_task(
            user.send_message("Nice! Have fun in the group 🙂"), update=update
        )
        reply_markup = None
        jobs = cast(JobQueue, context.job_queue).get_jobs_by_name(f"JOIN_TIMEOUT {user.id}")
        if jobs:
            jobs[0].schedule_removal()
    else:
        reply_markup = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton(
                text="⚠️ Tap again to confirm",
                callback_data=f"JOIN 2 {chat}",
            )
        )

    context.application.create_task(
        callback_query.edit_message_reply_markup(reply_markup=reply_markup), update=update
    )


async def join_request_timeout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = cast(Job, context.job)
    user, chat, message, group = cast(Tuple[User, int, Message, str], job.data)
    text = (
        f"Your request to join the group {group} has timed out. Please send a new request to join."
    )
    await user.decline_join_request(chat_id=int(chat))
    context.application.create_task(message.edit_text(text=text))
