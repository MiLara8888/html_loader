# -*- coding: utf-8 -*-
# !/usr/bin/env python
"""
глобальные параметры для программ
-хост имя
-количество потоков (SeleniumWeb браузеров)
"""
import os

#количество потоков в которой работает программа
SELENIUM_WORKER_COUNT = int(os.environ.get('SELENIUM_WORKER_COUNT', 3))
DJANGO_HOST = str(os.environ.get('DJANGO_HOST', 'http://127.0.0.1:8000'))