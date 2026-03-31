import sys
import asyncio
from dataclasses import dataclass
from asgiref.sync import sync_to_async

from maxapi import Router, F
from maxapi.types import BotStarted, MessageCreated
from maxapi.types.users import User
from maxapi.filters.contact import ContactFilter
from maxapi.types.attachments.contact import Contact
from maxapi.types.attachments.image import Image
from maxapi.types.attachments.file import File
from maxapi.types.attachments.attachment import PhotoAttachmentPayload
from maxapi.types.attachments.attachment import OtherAttachmentPayload

from bot.zulip_client import ZulipClient, ZulipException

import os

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")
django.setup()
from django.conf import settings
from django.db.utils import IntegrityError
from django.core.exceptions import ValidationError

from profiles.models import Profile, Company
from communications.models import Message
from bot.max_bot.utils.utils import make_random_password


from bot.logger import create_logger
from bot.max_bot import keyboards
from bot.helpers import BotType, get_zulip_topic_name


text_about = """
🌟 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА КИК-СОФТ 🌟

Добро пожаловать!

Для продолжения работы вам нужно нажать кнопку (внизу) "Отправить контакт" и "Поделиться" телефоном с нашим ботом поддержки.
Это безопасно. 
"""

logger = create_logger(logger_name=__name__)
user_router = Router()


try:
    zulip_client = ZulipClient()
except ZulipException:
    msg = "Фатальная ошибка при попытке коннекта к Zulip-серверу! Бот не запущен!"
    logger.critical(msg)
    sys.exit(msg)


def send_bot_event_msg_to_zulip(text:str, topic='info'):
    zulip_client.send_msg_to_channel(
        channel_name="bot_events",
        topic=topic,
        msg=text
    )


async def get_or_create_user_django(bot_user: User, company: Company) -> (User, bool):
    created = False
    try:
        user = await Profile.objects.aget(max_id=bot_user.user_id)
    except Profile.DoesNotExist:
        user = None

    if user:
        return (user, created)

    user = Profile(
        username=f"{bot_user.first_name}_{bot_user.user_id}",  # тут телефона нету, поэтому id, потом запишем телефон
        first_name=bot_user.first_name,
        last_name=bot_user.last_name or "",
        max_id=bot_user.user_id,
        company=company
    )
    password = make_random_password()
    user.set_password(password)

    try:
        await sync_to_async(user.full_clean)()
        await user.asave()
        created = True
    except (IntegrityError, ValidationError) as e:
        logger.error(f"Ошибка при сохранении нового пользователя. Поле не уникально: {e}")
        user = None
    return (user, created)


async def handle_start_command(bot_user: User, channel_id: int):
    msg_text = f"Команда /start от {bot_user.first_name} с ID {bot_user.user_id}. Channel_id={channel_id}."
    logger.info(msg_text)
    #send_bot_event_msg_to_zulip(f"{msg_text}")  # todo добавить в фоновые задачи (fastapi.BackgroundTask, aiojobs)

    # ищем или создаем компанию в Джанго
    # company, created = await Company.objects.aget_or_create(
    #     channel_id=channel_id,
    #     defaults={'name': company_name}
    # )
    # if created:
    #     logger.info(f"Создана компания в Джанго: {company_name}.")

    try:
        company = await Company.objects.aget(channel_id=channel_id)
    except Company.DoesNotExist:
        company = await Company.objects.aget(channel_id=settings.NONAME_CHANNEL_ID)

    # проверяем, есть ли канал компании в Zulip
    # if not company.channel_id:
    #     # канал в Zulip еще не создан. Создаем
    #     channel_id = zulip_client.get_or_create_channel(company_name, settings.ZULIP_STAFF_IDS)
    #     company.channel_id = channel_id
    #     await company.asave()

    #если в Джанго нет пользователя с таким max_id, то создаем
    user, created = await get_or_create_user_django(bot_user, company)
    if not user:
        msg_text = f"Ошибка при создании в Джанго пользователя по данныи из MAX {bot_user}."
        logger.error(msg_text)
        send_bot_event_msg_to_zulip(msg_text)
        return

    if created:
        msg_text = f"Создан пользователь в Джанго: {user}."
        logger.info(msg_text)
        send_bot_event_msg_to_zulip(msg_text)


# Обработчик команды "/start
# Чтобы в payload передать channel_id, нужно
# - создать канала (его id и нужно будет передать в payload)
# - в админ-базе создать Компанию и указать Channel_name и Channel_id
@user_router.bot_started()
async def bot_started(event: BotStarted):
    # async def cmd_start(message: Message, command: CommandObject):
    from_user = event.from_user
    channel_id = event.payload

    if not channel_id:
        channel_id = settings.NONAME_CHANNEL_ID

    try:
        channel_id = int(channel_id)
    except ValueError:
        channel_id = settings.NONAME_CHANNEL_ID

    await handle_start_command(from_user, channel_id)

    # await message.answer(get_about_us_text(), reply_markup=kbs.contact_keyboard())
    kbd = keyboards.contact_keyboard()

    await event.bot.send_message(
        chat_id=event.chat_id,
        text=text_about,
        attachments=[kbd, ]
    )

@user_router.message_created(ContactFilter())
async def on_contact(event, contact: Contact):
    from_user = event.from_user
    contact = contact.payload.vcf
    logger.info(f"Получены контакты: {contact}")

    # клиент мог повторно отправить контакты, поэтому сначала ищем его в БД
    try:
        user = await Profile.objects.select_related('company').aget(max_id=from_user.user_id)
    except Profile.DoesNotExist:
        user = None

    if user:
        if not user.phone:
            # первый раз поделился контактом
            user.phone = contact.phone
            await user.asave()

        # отправим "тестовое" сообщение в Zulip
        channel_id = user.company.channel_id
        topic_name = get_zulip_topic_name(user, BotType.max)
        message_text = "Я новый пользователь"
        zulip_client.send_msg_to_channel(channel_id, topic_name, message_text)
    else:
        msg_text = f"Получены контакты, но пользователя нет в Джанго: {contact}"  # todo  может записать в Noname ?
        logger.error(msg_text)
        send_bot_event_msg_to_zulip(msg_text)

    answer_text = f"Спасибо! Теперь вы можете написать нам о своей проблеме."
    await event.message.answer(answer_text)


@user_router.message_created(F.message.body.text)
async def text_handler(event: MessageCreated):
    user_id = event.from_user.user_id
    try:
        user = await Profile.objects.select_related('company').aget(max_id=user_id)
    except Profile.DoesNotExist:
        user = None

    if not user:
        kbd = keyboards.contact_keyboard()
        await event.message.answer(
            "Вы еще не отправили ваш номер телефона.\n"
            "Нажмите на кнопку ОТПРАВИТЬ ниже.",
            attachments=[kbd, ]
        )
        return

    logger.info(f"Получено сообщение от пользователя бота {user}: {event.message.body.text}")

    topic_name = get_zulip_topic_name(user, BotType.max)
    message_text = event.message.body.text
    channel_id = user.company.channel_id

    # chat_type = message.chat.type
    # if 'group' in chat_type:  # сообщение отправлено из группы
    #     topic_name = f"Группа_{message.chat.id}"
    #     message_text = f"{user.get_full_name()}: {message_text}"

    # отправим сообщение в Zulip
    zulip_client.send_msg_to_channel(channel_id, topic_name, message_text)

    # сохраним сообщение в Джанго
    dj_message = Message(
        sender=user,
        content=message_text,
    )
    await dj_message.asave()


@user_router.message_created(F.message.body.attachments)
async def on_attachment(event: MessageCreated):
    images = []
    for attachment in event.message.body.attachments:
        if isinstance(attachment, Image) and isinstance(attachment.payload, PhotoAttachmentPayload):
            print('Image attachment', attachment)
            images.append(attachment.payload.url)
        elif isinstance(attachment, File) and isinstance(attachment.payload, OtherAttachmentPayload):
            print('File attachment', attachment)
            images.append(attachment.payload.url)

    user_id = event.from_user.user_id
    try:
        user = await Profile.objects.select_related('company').aget(max_id=user_id)
    except Profile.DoesNotExist:
        user = None

    if not user:
        kbd = keyboards.contact_keyboard()
        await event.message.answer(
            "Вы еще не отправили ваш номер телефона.\n"
            "Нажмите на кнопку ОТПРАВИТЬ ниже.",
            attachments=[kbd, ]
        )
        return

    logger.info(f"Получена картинка от пользователя бота {user}")

    topic_name = get_zulip_topic_name(user, BotType.max)
    channel_id = user.company.channel_id

    for img_url in images:
        message_text = f"Image: {img_url}"

        zulip_client.send_msg_to_channel(channel_id, topic_name, message_text)

        # сохраним сообщение в Джанго
        dj_message = Message(
            sender=user,
            content=message_text,
        )
        await dj_message.asave()

    await asyncio.sleep(0)

# @user_router.message_created(F.message.body.attachments)
# async def on_attachment(event: MessageCreated, context):
#     print('files', event.message.body.attachments)
    # images = []
    # for attachment in event.message.body.attachments:
    #     print('attachment', attachment)
    #     print('type', type(attachment))
    #     print('type payload', type(attachment.payload))
    #     if isinstance(attachment, Image) and isinstance(attachment.payload, PhotoAttachmentPayload):
    #         images.append(attachment.payload.url)
    #     elif isinstance(attachment, File) and isinstance(attachment.payload, OtherAttachmentPayload):
    #         images.append(attachment.payload.url)
    #
    # print('images', images)
    # await asyncio.sleep(0)
    #await event.message.answer(f"Получена картинка")



"""    
@user_router.message(F.photo)
async def get_photo(message: Message):
    # todo ниже большой кусок дублируетс
    tg_user_id = message.from_user.id
    try:
        user = await Profile.objects.select_related('company').aget(tg_id=tg_user_id)
    except Profile.DoesNotExist:
        user = None

    if not user:
        await message.answer(
            "Вы еще не отправили ваш номер телефона.\n"
            "Нажмите на кнопку ОТПРАВИТЬ ниже.",
            reply_markup=kbs.contact_keyboard()
        )
        return

    logger.info(f"Получено фото от пользователя {user}")

    topic_name = get_zulip_topic_name(user, BotType.max)
    channel_id = user.company.channel_id

    chat_type = message.chat.type
    if 'group' in chat_type:  # сообщение отправлено из группы
        topic_name = f"Группа_{message.chat.id}"

    largest_photo = message.photo[-1]
    max_size = settings.MAX_FILE_SIZE * 1024 * 1024
    if largest_photo.file_size > max_size:
        await message.answer(
            f"Очень большой размер фото.\n"
            f"Макс допустимый размер - {max_size}Б."
        )
        return

    # фото сначала сохраняем на сервере ТГ
    destination = f"/tmp/{largest_photo.file_id}.jpg"
    await message.bot.download(file=largest_photo.file_id, destination=destination)

    #затем отправляем на сервер zulip
    try:
        with open(destination, "rb") as f:
            uploaded_file_url = zulip_client.upload_file(f)
            if uploaded_file_url:
                message_text = f"{message.caption}\n[Фото]({uploaded_file_url})"
            else:
                message_text = "Тут должна быть ссылка на файл, но файл не удалось получить."
    except Exception as e:
        message_text = f"Тут должна быть ссылка на файл, но файл не удалось получить: {e}"

    #и отправим сообщение в Zulip с ссылкой на файл
    zulip_client.send_msg_to_channel(channel_id, topic_name, message_text)

    await asyncio.sleep(0)

"""


"""
bot=<maxapi.bot.Bot object at 0x7eb465bffb00> update_type=<UpdateType.MESSAGE_CREATED: 'message_created'> 
timestamp=1774294959025 
from_user=User(user_id=184560163, first_name='Александр', last_name='', username=None, is_bot=False, 
    last_activity_time=1774294939000, description=None, avatar_url=None, full_avatar_url=None, commands=None) 
chat=Chat(chat_id=9553880, type=<ChatType.DIALOG: 'dialog'>, status=<ChatStatus.ACTIVE: 'active'>, title=None, 
    icon=None, last_event_time=1774294959025, participants_count=2, owner_id=None, participants=None, 
    is_public=False, link=None, description=None, 
        dialog_with_user=User(user_id=184560163, first_name='Александр', last_name='', username=None, 
        is_bot=False, last_activity_time=1774294939000, description=None, avatar_url=None, full_avatar_url=None, commands=None), 
    messages_count=None, chat_message_id=None, pinned_message=None) 
message=Message(bot=<maxapi.bot.Bot object at 0x7eb465bffb00>, 
    sender=User(user_id=184560163, first_name='Александр', last_name='', username=None, is_bot=False, 
        last_activity_time=1774294939000, description=None, avatar_url=None, full_avatar_url=None, commands=None), 
    recipient=Recipient(user_id=194113019, chat_id=9553880, chat_type=<ChatType.DIALOG: 'dialog'>), 
    timestamp=1774294959025, link=None, 
    body=MessageBody(mid='mid.000000000091c7d8019d1c3883b17b7f', seq=116280194434694015, text='', 
        attachments=[Image(type='image', payload=PhotoAttachmentPayload(photo_id=9677135651, 
            token='Mm+nJbWc9UiMZ7wjtFKNBpUmBZXNOpGNt9+/Je7RU0RUzXYeZnWAxKHAhztz8sgvOH7iZnTKKRDGHv0hNcbfIYCKNrC4PzSf', 
            url='https://i.oneme.ru/i?r=BTGBPUwtwgYUeoFhO7rESmr8CXtywNzE0iuqP2X4yJrSndwS0Gkbqc8ftHl9Gyzjaes'), 
            bot=<maxapi.bot.Bot object at 0x7eb465bffb00>)], markup=[]), stat=None, url=None) user_locale='ru'

"""