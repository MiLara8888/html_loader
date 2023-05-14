# -*- coding: utf-8 -*-
# !/usr/bin/env python
"""
инициализирует SELENIUM_WORKER_COUNT объектов webdriver

забирает у django по rest url-ки для извлечения картинок
запрос - "{DJANGO_HOST}/api/loader/next-image-url/{GET_URLS_COUNT}/"

url открывается в окне webdriver для извлечения cookie и юзер-агента
с помощью этих данных происходит requests запрос на извлечение b'' картинки
b'' декодируется в base64, а затем информация отправляется обратно в django
ответ - {DJANGO_HOST}/api/putbase64/{cls.site_id}/{cls.id}/

"""
import os
import json
import base64
import logging
from time import sleep
from multiprocessing.pool import ThreadPool
from logging import INFO, WARNING, ERROR, CRITICAL, FileHandler
import pathlib

import requests
from requests.models import Response
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import WebDriverException    #отлов всех ошибок элемента драйвер


from global_param import DJANGO_HOST, SELENIUM_WORKER_COUNT


poll = None
request_data: Response = None
SELENIUM_WORKER_COUNT = SELENIUM_WORKER_COUNT
GET_URLS_COUNT = SELENIUM_WORKER_COUNT    #попадает в url requests
image_base64 = ''
status = 3


#настройки логгирования
log_format = '%(asctime)s   - %(name)s - %(levelname)s - %(message)s'
logger = logging.getLogger('loader_base64')
logger.setLevel(logging.INFO)  # уровень на уровне всего логирования файла

class DebugFileHandler(FileHandler):
    """переопределение класса, чтобы info падали в один файл, а всё, что выше Warning в другой """

    def __init__(self, filename: str, mode='a', encoding=None, delay=False):
        super().__init__(filename, mode, encoding, delay)

    def emit(self, record):
        if record.levelno == CRITICAL or record.levelno == ERROR or record.levelno == WARNING:
            return
        super().emit(record)

info_handler = DebugFileHandler('log/loader-base64-info.log')
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(info_handler)
error_handler = logging.FileHandler('log/loader-base64-error.log')
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(error_handler)


logger.info(f'Программа запущена, и будет работать в {SELENIUM_WORKER_COUNT} потока(ов)')

# base64_img = image_base64    #декодирование

# base64_img_bytes = base64_img.encode('utf-8')
# with open('decoded_image.jpg', 'wb') as file_to_save:
#     decoded_image_data = base64.decodebytes(base64_img_bytes)
#     file_to_save.write(decoded_image_data)


class SeleniumDriver:
    """класс для работы с webdriver

    методы:
    get_request() инициализирует webdriver
    get_page() удаление куки и основные действия с содержимым открытой страницы
    driver_close() закрытие драйвера"""

    _user_agent: str = None
    __dir_path = pathlib.Path.cwd()
    __PATH: str = pathlib.Path(__dir_path, 'geckodriver')
    headers = {"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding":"gzip, deflate, br",
			"Accept-Language":"ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
            "Connection":"keep-alive",
			"Sec-Fetch-Dest":"document",
			"Sec-Fetch-Mode":"navigate",
			"Sec-Fetch-Site":"none",
			"Sec-Fetch-User":"?1",
			"Upgrade-Insecure-Requests":"1"}

    def __init__(self):
        self.options = Options()
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.set_preference("dom.webdriver.enabled", False)
        self.options.headless = True
        # self.options.add_argument('window-size=1200x600')

    def get_request(self):
        """инициализация драйвера

        при любых проблемах с инициализацией в логи попадёт ошибка,
        а затем произойдёт попытка повторной инициализации через 5 минут

        """
        try:
            self.driver = webdriver.Firefox(executable_path=SeleniumDriver.__PATH, options=self.options, service_log_path=os.devnull)
            self.driver.implicitly_wait(5)
            self._user_agent = self.driver.execute_script("return navigator.userAgent;")
            logger.info('Драйвер инициализировался')
        except WebDriverException as wd:
            logger.warning(f'{wd} Проблемa с инициализацией драйвера')
            sleep(5*60)
            self.get_request()
        except Exception as e:
            logger.warning(f'{e} Проблемa с инициализацией драйвера')
            sleep(5*60)
            self.get_request()


    def get_page(self, url, id, site_id, attempt=5):
        """удаление куки открытие страницы и извлечение информации

        метод вызывается из класса TargetUrl
        извлекаем куки и используем их в requests

        """
        for _ in range(attempt):
            try:
                self.driver.delete_all_cookies()
                self.driver.get(url=url)
                self.driver.set_page_load_timeout(60)   #если за 15 секунд не ответит страница упадёт с ошибкой
                se = requests.Session()
                cookies = self.driver.get_cookies()
                for cookie in cookies:
                    se.cookies.set(cookie['name'], cookie['value'])
                self.headers["User-Agent"] = self._user_agent
                content_page = se.get(url, headers=self.headers)
                if content_page.status_code==200:
                    return content_page.content
            except WebDriverException as wde:
                logger.error(f'{id} {wde.msg} ошибка драйвера')
                self.driver_close()
                self.get_request()
                continue
            except Exception as e:
                continue

        logger.error(f'{id} проблема извлечения страницы {url}')
        return ''


    def driver_close(self):
        """закрытие драйвера"""
        try:
            self.driver.close()
            self.driver.quit()
        except WebDriverException:
            pass


class TargetUrl(object):
    """
    класс для формирования информации для обработки получений из get запроса
    set_data() извлекает информацию
    validate() проверка на валидность информации из запроса
    get_page() отправляет url на открытие картинки и извлечение кода


    """
    _driver: SeleniumDriver = None
    _id: int = None
    _url: str = None
    _state: int = 0  # статус состояния
    _status: int = None
    _site_id: int = None

    def close_driver(self):
        self._driver.driver_close()


    def __init__(self, *args, **kwargs) -> None:
        """Создание объекта driver и его инициализация"""

        self._driver = SeleniumDriver()
        self._driver.get_request()

    def set_data(self, *args, **kwargs):
        """метод извлекает из пришедшего dict необходимую для обработки информацию"""
        self._state:int = 1
        self._url: str = kwargs.get('url', None)
        self._site_id: int = kwargs.get('site_id', None)
        self._id :int = kwargs.get('id', None)
        self._status: int = 3    #'Картинка не извлекалась'

    @property
    def url(self):
        return self._url

    @property
    def id(self):
        return int(self._id)

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def site_id(self):
        return int(self._site_id)

    def validate(self):
        """метод определяет будет ли информация отправлена на переработку,
        в дальнейшем можно прописать более детальную валидацию"""
        if self._id and self._url and self._site_id:
            return 1
        else:
            return 0

    def get_page(self):
        return self._driver.get_page(self.url, self._id, self._site_id)


def worker(cls: TargetUrl):
    state = cls.validate()    #получаю стейт
    if state:
        page = cls.get_page()
        if page:    #если страница открылась вернёт статус Картинка успешно извлечена
            image_base64 = base64.b64encode(page).decode('ascii')
            if image_base64:
                status = 5    #Картинка успешно извлечена
            else:
                status = 3    #Картинка не извлекалась
        else:
            logger.error(f'{cls.id} - {cls.url} проблемы с открытием страницы, ушла со статусом 3')
            image_base64 = ''
            status = 104

        cls.state = 0
    else:
        status = 104
        image_base64 = ''
        logger.error(f'{cls.id} не пройдена валидация')

    resp = requests.put(f'{DJANGO_HOST}/api/putbase64/{cls.site_id}/{cls.id}/', json={'html_page':image_base64, 'status': status })
    if resp.status_code!=201:
        logger.error(f'{cls.id} - {resp.text}')
        sleep(100)
    elif resp.status_code==201 and status==5:
        logger.info(f' {os.getpid()} {cls.id} - картинка успешно обработана')



# инициализация селениум тут откроются окна драйверов
list_cls = []
for i in range(SELENIUM_WORKER_COUNT):
    list_cls.append(TargetUrl())  # заполняем экземплярами класса Target

def main():
    while True:

        try:  # отлов глобальной ошибки в соединении
            request_data = requests.get(f'{DJANGO_HOST}/api/loader/next-image-url/{GET_URLS_COUNT}/')
            if request_data.status_code == 201:
                url_objects = json.loads(request_data.content)
                if url_objects:
                    # мержим даные и драйвер
                    for i, obj in enumerate(url_objects):
                        list_cls[i].set_data(**obj)

                    # выбирает экземпляры со стейтом 1
                    list_workers = list(filter(lambda o: o.state == 1, list_cls))
                    if len(list_workers) > 0:
                        with ThreadPool(processes=len(list_workers)) as poll:
                            poll.map(worker, list_workers)
                else:
                    logger.info('Пустой список к исполнению спим минуту')
                    sleep(60)

            elif request_data.status_code==500:
                logger.error(request_data.text)
                sleep(100)

        except ConnectionError as e:
            logger.error('Проблемы в соединении с django сервером')
            sleep(100)

        except Exception as e:
            logger.error(e)
            sleep(100)

if __name__ == "__main__":
    main()

for cls_workers in list_cls:
    cls_workers.close_driver()