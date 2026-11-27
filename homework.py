import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
import telegram

import exceptions

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

TOKEN_NAMES = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')

RETRY_TIME = 600
RETRY_PERIOD = RETRY_TIME
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def configure_logging():
    """Настройка логирования согласно требованиям задания."""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                filename='program.log',
                mode='w',
                maxBytes=5000000,
                backupCount=5,
                encoding='utf-8',
            )
        ]
    )


def check_tokens():
    """
    Проверяет наличие всех обязательных переменных окружения.
    Возвращает True, если все токены присутствуют.
    Логирует CRITICAL, если чего-то не хватает.
    """
    missing_tokens = [
        token for token in TOKEN_NAMES
        if not os.getenv(token)
    ]

    if missing_tokens:
        msg = (
            f'Отсутствует обязательная переменная окружения: '
            f'{", ".join(missing_tokens)}'
        )
        logging.critical(msg)
        return False

    return True


def get_api_answer(current_timestamp):
    """
    Делает запрос к API Практикума.
    Возвращает распарсенный JSON (dict).
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}

    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params=params, timeout=10
        )
    except requests.RequestException as e:
        logging.error(f'Сбой при запросе к эндпоинту {ENDPOINT}: {e}')
        raise exceptions.RequestError(f'Ошибка запроса к API: {e}') from e

    if response.status_code != HTTPStatus.OK:
        logging.error(
            f'Недоступность эндпоинта {ENDPOINT}. '
            f'Код ответа API: {response.status_code}'
        )
        raise exceptions.RequestError(
            f'API вернул код {response.status_code}'
        )

    try:
        return response.json()
    except ValueError as e:
        logging.error(f'Ошибка парсинга JSON из ответа API: {e}')
        raise exceptions.RequestError(
            'Не удалось распарсить JSON ответа API'
        ) from e


def check_response(response):
    """
    Проверяет структуру ответа API.
    Возвращает список работ (homeworks).
    """
    if not isinstance(response, dict):
        logging.error('Ответ API не соответствует ожидаемому типу <dict>')
        raise TypeError('Ответ API не соответствует ожидаемому типу <dict>')

    homeworks = response.get('homeworks')
    if homeworks is None:
        logging.error('В ответе API отсутствует ожидаемый ключ "homeworks"')
        raise KeyError('В ответе API отсутствует ключ <homeworks>')

    if not isinstance(homeworks, list):
        logging.error('Под ключом "homeworks" должен быть список <list>')
        raise TypeError('Под ключом <homeworks> должен быть список <list>')

    return homeworks


def parse_status(homework):
    """
    Извлекает статус одной работы.
    Возвращает строку для Telegram.
    Выбрасывает исключения при некорректных данных, чтобы тесты были довольны.
    """
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
    except KeyError as e:
        logging.error(f'В данных о домашней работе отсутствует ключ: {e}')
        raise exceptions.ResponseStructureError(
            f'Отсутствует ключ в данных работы: {e}'
        ) from e

    if homework_status not in HOMEWORK_VERDICTS:
        logging.error(f'Неожиданный статус домашней работы: {homework_status}')
        raise exceptions.UnexpectedStatusError(
            f'Неизвестный статус работы: {homework_status}'
        )

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус работы "{homework_name}": {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug('Сообщение успешно отправлено в Telegram.')
    except Exception as e:
        logging.error(f'Сбой при отправке сообщения в Telegram: {e}')


def main():
    """Основная функция запуска бота."""
    configure_logging()

    if not check_tokens():
        logging.critical(
            'Программа принудительно остановлена из-за отсутствия токенов.'
        )
        raise SystemExit('Программа принудительно остановлена')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_error_message = None

    logging.info('Бот запущен. Начинаю опрос API каждые 10 минут.')

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logging.debug('В ответе API нет новых статусов.')
                current_timestamp = response.get(
                    'current_date', int(time.time())
                )
                continue

            current_homework = homeworks
            message = parse_status(current_homework)
            if message:
                send_message(bot, message)

            current_timestamp = response.get('current_date', int(time.time()))

        except Exception as e:
            logging.critical(f'Критическая ошибка в работе программы: {e}')

            if str(e) != last_error_message:
                try:
                    send_message(bot, f'💥 Критическая ошибка бота: {e}')
                    last_error_message = str(e)
                except Exception as send_err:
                    logging.error(
                        f'Не удалось отправить сообщение '
                        f'об ошибке в Telegram: {send_err}'
                    )

        time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
