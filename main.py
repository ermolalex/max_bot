import os
import asyncio
import logging

from dotenv import load_dotenv

from maxapi import Bot, Dispatcher
from maxapi.types import BotStarted, Command, MessageCreated, RequestContactButton, LinkButton, ButtonsPayload

from bot.max_bot.handlers import user_router
#from bot.tg_bot.create_bot import bot, dp, stop_bot, start_bot
from bot.logger import create_logger


load_dotenv()
token = os.environ.get("BOT_TOKEN")

bot = Bot(token=token)
dp = Dispatcher()
dp.include_routers(user_router)

logger = create_logger(logger_name=__name__)


async def main():
    await bot.subscribe_webhook(
        url='https://tediously-potent-merlin.cloudpub.ru:443',
        #secret='SuperSecretWord()<>'
    )


    await dp.handle_webhook(
        bot=bot,
        host='localhost',
        port=8000,
        log_level=logging.DEBUG  # Можно убрать, для подробного логирования
    )

    await bot.delete_webhook()


if __name__ == '__main__':
    asyncio.run(main())
