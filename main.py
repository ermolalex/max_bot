import os
import asyncio
import logging
import time

from dotenv import load_dotenv
from typing import Any, Awaitable, Callable, Dict

from maxapi import Bot, Dispatcher
from maxapi.filters.middleware import BaseMiddleware

from bot.max_bot.handlers import user_router
#from bot.tg_bot.create_bot import bot, dp, stop_bot, start_bot
from bot.logger import create_logger


load_dotenv()
token = os.environ.get("MAX_BOT_TOKEN")
max_webhook_url = os.environ.get("MAX_WEBHOOK_URL")

bot = Bot(token=token)
dp = Dispatcher()
dp.include_routers(user_router)

logger = create_logger(logger_name=__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
            event_object: Any,
            data: Dict[str, Any],
    ) -> Any:
        log_msg = f"""
            Обработка события: {event_object.update_type}
            bot.me = {event_object.bot.me}
            chat = {event_object.chat}
            from_user.user_id = {event_object.from_user.user_id}
            
        """
        try:
            log_msg += f"""
                message.body = {event_object.message.body}
                message.recipient = {event_object.message.recipient}
            """
        except Exception:
            pass

        #print(log_msg)
        logger.debug(log_msg)
        result = await handler(event_object, data)
        #print(f"Обработка завершена")
        return result

dp.middleware(LoggingMiddleware())

async def main():
    await bot.subscribe_webhook(
        url=f'{max_webhook_url}:443',
        #secret='SuperSecretWord()<>'
    )


    await dp.handle_webhook(
        bot=bot,
        host='0.0.0.0',
        port=8000,
        # host='localhost',
        # port=8000,
        log_level=logging.DEBUG  # Можно убрать, для подробного логирования
    )

    await bot.delete_webhook()


if __name__ == '__main__':
    asyncio.run(main())



""" Я пишу в чат на телефоне:
data.'context':
chat_id = 9553880
user_id = 184560163
  
event_object:
bot.me = User(user_id=194113019, first_name='КиК-софт', last_name=None, username='id7805103139_bot', is_bot=True, 
last_activity_time=1775391731420, description='Техническая поддержка клиентов компании', 
avatar_url='https://i.oneme.ru/i?r=BTFjO43w8Yr1OSJ4tcurq5HiKWSm8XLj40l99bjEMRzRfsbpcWxyNuQegOP5Atw2q5A', 
full_avatar_url='https://i.oneme.ru/i?r=BTFjO43w8Yr1OSJ4tcurq5HigV0mN-0lS9mx5NA8VZiihMbpcWxyNuQegOP5Atw2q5A', commands=None)

chat = Chat(chat_id=9553880, type=<ChatType.DIALOG: 'dialog'>, status=<ChatStatus.ACTIVE: 'active'>, title=None, 
icon=None, last_event_time=1775391740526, participants_count=2, owner_id=None, participants=None, is_public=False, 
link=None, description=None, dialog_with_user=User(user_id=184560163, first_name='Александр', last_name='', username=None, 
is_bot=False, last_activity_time=1775391735000, description=None, avatar_url=None, full_avatar_url=None, commands=None), 
messages_count=None, chat_message_id=None, pinned_message=None)

from_user = User(user_id=184560163, ...)

message.body = MessageBody(mid='mid.000000000091c7d8019d5d98126e4330', seq=116352073107129136, text='Пинг', attachments=[], markup=[])
message.recipient = Recipient(user_id=194113019, chat_id=9553880, chat_type=<ChatType.DIALOG: 'dialog'>)
message.sender = User(user_id=184560163, first_name='Александр', ...)

update_type = <UpdateType.MESSAGE_CREATED: 'message_created'>

"""