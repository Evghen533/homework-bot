import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
import telebot
from dotenv import load_dotenv

import exceptions

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'

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
            ),
        ],
    )


def check_tokens():
    """Проверяет наличие и корректность токенов и идентификаторов."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing = [
        name for name, val in tokens.items()
        if not val or (isinstance(val, str) and not val.strip())
    ]
    if missing:
        logging.critical(
            'Отсутствуют обязательные переменные окружения: %s',
            ', '.join(missing),
        )
        return False
    return True


def get_api_answer(current_timestamp):
    """Делает запрос к API Практикума и возвращает распарсенный JSON."""
    params = {'from_date': current_timestamp}
    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params=params, timeout=10
        )
    except requests.RequestException as error:
        raise exceptions.RequestError(
            f'Сбой при запросе к эндпоинту {ENDPOINT}: {error}'
        ) from error

    if response.status_code != HTTPStatus.OK:
        raise exceptions.RequestError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )

    try:
        return response.json()
    except ValueError as error:
        raise exceptions.RequestError(
            'Не удалось распарсить JSON ответа API'
        ) from error


def check_response(response):
    """Проверяет структуру ответа API и возвращает список работ."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API не соответствует ожидаемому типу <dict>')

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ <homeworks>')

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Под ключом <homeworks> должен быть список <list>')

    return homeworks


def parse_status(homework):
    """Возвращает сообщение об изменении статуса проверки работы."""
    if 'homework_name' not in homework:
        raise KeyError('В ответе API отсутствует ключ "homework_name"')
    if 'status' not in homework:
        raise KeyError('В ответе API отсутствует ключ "status"')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неизвестный статус: {status}')

    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def send_message(bot, message):
    """Отправляет сообщение в Telegram."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logging.debug('Сообщение успешно отправлено в Telegram.')
        return True
    except Exception as error:
        logging.error(f'Сбой при отправке сообщения в Telegram: {error}')
        return False


def main():
    """Основная функция запуска бота."""
    if not check_tokens():
        sys.exit('Программа принудительно остановлена')

    bot = telebot.TeleBot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    last_error_message = ''

    logging.info('Бот запущен. Начинаю опрос API каждые 10 минут.')

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    current_timestamp = response.get(
                        'current_date', current_timestamp
                    )
                    last_error_message = ''
            else:
                logging.debug('В ответе API нет новых статусов.')
                current_timestamp = response.get(
                    'current_date', current_timestamp
                )
                last_error_message = ''

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)
            if message != last_error_message and send_message(bot, message):
                last_error_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    configure_logging()
    main()
