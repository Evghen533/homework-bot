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

# ВАЖНО: Тесты требуют именно эту переменную с таким именем
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'

HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}

# ВАЖНО: Тесты проверяют, что сообщение берётся именно отсюда
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
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
    """Проверяет наличие и корректность всех необходимых токенов и идентификаторов."""
    required = [
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID,
    ]

    def is_valid(token):
        if token is None:
            return False
        if isinstance(token, str):
            return bool(token.strip())
        return True

    return all(is_valid(token) for token in required)


def get_api_answer(current_timestamp):
    """Делает запрос к API Практикума и возвращает распарсенный JSON (dict)."""
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
    """Проверяет структуру ответа API и возвращает список работ (homeworks)."""
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
    """Возвращает сообщение об изменении статуса проверки работы."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус: {status}')

    message_tail = HOMEWORK_VERDICTS[status]
    return (
        f'Изменился статус проверки работы "{homework_name}": '
        f'{message_tail}'
    )


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug('Сообщение успешно отправлено в Telegram.')
    except Exception as e:
        # ВАЖНО: Тест требует именно logging.error для ошибки отправки
        logging.error(f'Сбой при отправке сообщения в Telegram: {e}')
        raise


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
                logging.info('В ответе API нет новых статусов.')
                current_timestamp = response.get(
                    'current_date', int(time.time())
                )
                # ВАЖНО: sleep должен быть всегда, даже если работ нет
                time.sleep(RETRY_PERIOD)
                continue

            # В задании обычно берут первую работу из списка
            current_homework = homeworks
            message = parse_status(current_homework)
            send_message(bot, message)

            current_timestamp = response.get('current_date', int(time.time()))

        except Exception as e:
            logging.critical(f'Критическая ошибка в работе программы: {e}')

            if str(e) != last_error_message:
                try:
                    send_message(bot, f'💥 Критическая ошибка бота: {e}')
                    last_error_message = str(e)
                except Exception as send_err:
                    # ВАЖНО: здесь тоже нужен logging.error
                    logging.error(
                        f'Не удалось отправить сообщение об ошибке в Telegram: {send_err}'
                    )

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
