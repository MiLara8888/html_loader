# -*- coding: utf-8 -*-
# !/usr/bin/env python
"""
инициализирует SELENIUM_WORKER_COUNT объектов webdriver

забирает у django по rest url-ки для извлечения html
запрос - "{DJANGO_HOST}/api/loader/nexturl/{GET_URLS_COUNT}/"

url открывается в окне webdriver для извлечения html
html по rest отправляется в django
ответ - {DJANGO_HOST}/api/puthtml/{info.get("id",None)}/

"""
import pathlib
import json
import os
import logging
from time import sleep
from urllib.parse import urlunparse
from multiprocessing.pool import ThreadPool
from logging import INFO, WARNING, ERROR, CRITICAL, FileHandler

import requests
from requests.models import Response, Request
from requests import get as req_get
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import WebDriverException    #отлов всех ошибок элемента драйвер

from global_param import DJANGO_HOST, SELENIUM_WORKER_COUNT


poll = None
request_data: Response = None
SELENIUM_WORKER_COUNT = SELENIUM_WORKER_COUNT
GET_URLS_COUNT = SELENIUM_WORKER_COUNT
responce = None


#настройки логгирования
log_format = '%(asctime)s   - %(name)s - %(levelname)s - %(message)s'
logger = logging.getLogger('loader_html')
logger.setLevel(logging.INFO)  # уровень на уровне всего логирования файла
class DebugFileHandler(FileHandler):
    """
    переопределение класса, чтобы warning и info падали в другой файл
    """
    def __init__(self, filename: str, mode='a', encoding=None, delay=False):
        super().__init__(filename, mode, encoding, delay)
    def emit(self, record):
        if record.levelno == CRITICAL or record.levelno == ERROR or record.levelno == WARNING:
            return
        super().emit(record)
info_handler = DebugFileHandler('log/loader-html-info.log')
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(info_handler)
error_handler = logging.FileHandler('log/loader-html-error.log')
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(logging.Formatter(log_format))
logger.addHandler(error_handler)


logger.info(f'Программа запущена, и будет работать в {SELENIUM_WORKER_COUNT} потока(ов)')


class SeleniumDriver:
    """класс для работы с webdriver

    методы:
    get_request() инициализирует webdriver
    get_page() удаление куки и основные действия с содержимым открытой страницы
    driver_close() закрытие драйвера

    """

    __dir_path = pathlib.Path.cwd()
    __PATH: str = pathlib.Path(__dir_path, 'geckodriver')

    def __init__(self):
        self.options = Options()
        self.options.add_argument('--disable-blink-features=AutomationControlled')
        self.options.set_preference("dom.webdriver.enabled", False)
        # self.options.set_preference("pdfjs.disabled", True)
        self.options.headless = True    #если раскоменчено то не открывает дополнительного окна
        # self.options.add_argument('window-size=1200x600')

    def get_request(self):
        """инициализация драйвера

        при любых проблемах с инициализацией в логи попадёт ошибка,
        а затем произойдёт попытка повторной инициализации через 5 минут

        """
        try:
            self.driver = webdriver.Firefox(executable_path=SeleniumDriver.__PATH, options=self.options, service_log_path=os.devnull)
            self.driver.implicitly_wait(5)
            logger.info('Драйвер инициализировался')
        except WebDriverException as wd:
            logger.warning(f'{wd} Проблемa с инициализацией драйвера в ошибке WebDriverException')
            sleep(5*60)
            self.get_request()
        except Exception as e:
            logger.warning(f'{e} Проблемa с инициализацией драйвера Exception')
            sleep(5*60)
            self.get_request()


    def get_page(self, url, id, attempt=5):
        """метод возвращает страницу в html формате"""
        """удаление куки открытие страницы"""
        for _ in range(attempt):
            sleep(0.3)
            try:
                self.driver.delete_all_cookies()
                self.driver.get(url=url)
                self.driver.set_page_load_timeout(60)   #если за 60 секунд не ответит страница упадёт с ошибкой
                return self.driver.page_source
            except WebDriverException as wde:
                logger.error(f'{id} {wde.msg} ошибка драйвера')
                self.driver_close()
                self.get_request()
                continue
            except:
                continue

        logger.error(f'{id} Драйвер не смог открыть страницу {url}')
        return ''

    def driver_close(self):
        """закрытие драйвера"""
        try:
            self.driver.close()
            self.driver.quit()
        except WebDriverException:    #может возникнуть если драйвер уже был закрыт
            pass



class TargetUrl(object):
    _driver: SeleniumDriver = None
    _id: int = None
    _domain_name: str = None
    _url: str = None
    _attempt_site: int = None
    _state: int = 0  # статус состояния
    _status: int = None


    def __init__(self, *args, **kwargs) -> None:
        """Создание объекта driver и его инициализация"""
        self._driver = SeleniumDriver()
        self._driver.get_request()

    def set_data(self, *args, **kwargs):
        """метод извлекает из пришедшего dict необходимую для обработки информацию"""
        self._state = 1
        self._id = kwargs.get('id', None)
        self._domain_name = kwargs.get('domain_name', None)
        self._url = kwargs.get('url', None)
        self._attempt_site = kwargs.get('attempt_site', None)
        self._status = 20  # Html станицы не извлекался

    @property
    def url(self):
        params = ('https', self._domain_name, self._url, None, None, None)
        url = urlunparse(params)
        return url

    @property
    def state(self):
        return self._state

    @property
    def id(self):
        return self._id

    @state.setter
    def state(self, value):
        self._state = value

    def close_driver(self):
        self._driver.driver_close()

    def validate(self):
        """метод определяет будет ли информация отправлена на переработку,
        в дальнейшем можно прописать более детальную валидацию"""
        if self._id and self._attempt_site and self._domain_name and self._url and type(self._id)==int:
            return 1, {'id': self._id, 'status': self._status}
        elif self._id:
            self._status = 98
            logger.warning(f'{self._id} не все данные были переданы в валидацию')
            return 1, {'id': self._id, 'status': self._status}
        else:
            return 0, ''

    def get_page(self):  # инициализация драйвера(его открытие в окне)
        return self._driver.get_page(self.url, self._id, self._attempt_site)


# def worker(cls: TargetUrl):    #с аатемптами
#     state, info = cls.validate()
#     if state:
#         page = cls.get_page()
#         if page=='' and info['status'] != 98:
#             response = requests.put(f'{DJANGO_HOST}/api/change-status/{info["id"]}/', json = {'status':20})    #снова извлекаем html
#             if response.status_code==201:
#                 logger.error(f'{info["id"]} Django часть добавила attempt')
#             elif response.status_code==500:
#                 logger.error(f'{response.text}  {info["id"]}  django часть не приняла запрос на обновление attempта')

#         elif info['status'] == 98:
#             status = 98
#             response = requests.put(f'{DJANGO_HOST}/api/puthtml/{info.get("id",None)}/', json={'html_page': page, 'status': status})

#         elif page and info['status'] != 98:
#             status = 30  # HTML успешно извлечён страница готова к извлечению url-ок
#             response = requests.put(f'{DJANGO_HOST}/api/puthtml/{info.get("id",None)}/', json={'html_page': page, 'status': status})
#         else:
#             logger.error('Ошибка в логике')

#         if response.status_code != 201:
#             logger.error(f'Не удалось в сделать put запрос со страницей {cls.url} ошибка {response.text}')
#             sleep(200)
#         elif response.status_code == 201:
#             logger.info(f'{os.getpid()} страница {cls.url} переработана')
#         cls.state = 0

def worker(cls: TargetUrl):
    state, info = cls.validate()
    if state:
        page = cls.get_page()
        if info['status'] == 98:
            status = 98
        # Ошибка при передаче данных в get запросе в loader
        elif page and info['status'] != 98:
            status = 30  # HTML успешно извлечён страница готова к извлечению url-ок
        else:
            status = 20  # html страницы не извлекался
        response = requests.put(f'{DJANGO_HOST}/api/puthtml/{info.get("id",None)}/', json={'html_page': page, 'status': status})
        if response.status_code != 201:
            logger.error(f'Не удалось в сделать put запрос со страницей {cls.url} ошибка {response.text}')
        elif response.status_code == 201:
            logger.info(f'{os.getpid()} страница {cls.url} переработана')
        cls.state = 0



# инициализация селениум тут откроются окна драйверов
list_cls = []
for i in range(SELENIUM_WORKER_COUNT):
    list_cls.append(TargetUrl())  # заполняем экземплярами класса Target


def main():
    while True:

        try:  # отлов глобальной ошибки в соединении
            request_data = req_get(f'{DJANGO_HOST}/api/loader/nexturl/{GET_URLS_COUNT}/')
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