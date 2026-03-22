from maxapi.types import RequestContactButton, LinkButton, ButtonsPayload


def contact_keyboard() -> ButtonsPayload:
    buttons = [
        [
            RequestContactButton(text="Отправить контакт"),
            # LinkButton(
            #     text="Документация MAX",
            #     url="https://dev.max.ru/docs"
            # ),
        ],
    ]
    buttons_payload = ButtonsPayload(buttons=buttons).pack()
    return buttons_payload


# def contact_keyboard() -> ReplyKeyboardMarkup:
#     kb = ReplyKeyboardBuilder()
#     kb.button(text="📱 Отправить", request_contact=True)
#     # kb.button(text="ℹ️ О нас")
#     # # if user_id == settings.ADMIN_ID:
#     # kb.button(text="🔑 Админ панель")
#     kb.adjust(1)
#     return kb.as_markup(resize_keyboard=True)
#
#
# def main_keyboard(user_id: int, first_name: str) -> ReplyKeyboardMarkup:
#     kb = ReplyKeyboardBuilder()
#     # url_applications = f"{settings.BASE_SITE}/applications?user_id={user_id}"
#     # url_add_application = f'{settings.BASE_SITE}/form?user_id={user_id}&first_name={first_name}'
#     # kb.button(text="🌐 Мои заявки", web_app=WebAppInfo(url=url_applications))
#     # kb.button(text="📝 Оставить заявку", web_app=WebAppInfo(url=url_add_application))
#     kb.button(text="ℹ️ О нас")
#     # if user_id == settings.ADMIN_ID:
#     kb.button(text="🔑 Админ панель")
#     kb.adjust(1)
#     return kb.as_markup(resize_keyboard=True)
