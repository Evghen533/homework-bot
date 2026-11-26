class RequestError(Exception):
    """Прочие ошибки запроса к API."""
    pass


class SendMessageFailure(Exception):
    """Сбой отправки сообщения в Telegram."""
    pass


class ResponseStructureError(Exception):
    """Ошибка структуры ответа API (отсутствуют ключи или неверный тип данных)."""
    pass


class UnexpectedStatusError(Exception):
    """Неожиданный статус домашней работы, не описанный в документации."""
    pass
