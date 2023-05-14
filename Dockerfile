FROM python:3.9
LABEL autor="LOADER"
LABEL description="APP"

WORKDIR /usr/src/html_loader/
COPY . /usr/src/html_loader/

RUN apt-get update

RUN echo "Y" | apt-get install alien
RUN echo "Y" | apt-get install gunicorn
RUN echo "Y" | apt-get install memcached
RUN echo "Y" | apt-get install unixodbc
RUN echo "Y" | apt-get install unixodbc-dev
RUN echo "Y" | apt-get install cifs-utils
RUN echo "Y" | apt-get install libgtk-3-dev
RUN echo "Y" | apt-get install libgtk-3-0
RUN echo "Y" | apt-get install libdbus-glib-1-2
RUN echo "Y" | apt-get install xvfb

RUN apt-get install libaio1

RUN echo "deb http://deb.debian.org/debian/ unstable main contrib non-free" >> /etc/apt/sources.list.d/debian.list
RUN apt-get update
RUN echo "Y" | apt-get install -y --no-install-recommends firefox
RUN apt-get update && apt-get install -y wget bzip2 libxtst6 libgtk-3-0 libx11-xcb-dev libdbus-glib-1-2 libxt6 libpci-dev && rm -rf /var/lib/apt/lists/*

ENV pip=pip3
ENV python=python3


RUN pip3 install --upgrade pip

COPY requirements.txt .
RUN pip3 install -r requirements.txt

RUN apt-get update --allow-releaseinfo-change
RUN Xvfb &

EXPOSE 4666
EXPOSE 4888

