FROM alpine:latest
RUN apk update 
RUN apk upgrade
RUN apk add --no-cache python3 py3-pip python3-dev build-base bash

ENV NTP_SERVER ntp.notset
ENV NTP_PORT 123

WORKDIR /app

# Setup our python package dependencies
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt && \
    apk del python3-dev build-base

COPY leo-ntp-monitor.py /app

CMD [ "python3",  "/app/leo-ntp-monitor.py"]
