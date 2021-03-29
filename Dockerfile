FROM alpine:latest

RUN apk add --no-cache python3

# Setup the environment variables
ENV NTP_SERVER ntp.notset
ENV NTP_PORT 123

WORKDIR /app

COPY leo-ntp-monitor.py /app

CMD [ "python3",  "/app/leo-ntp-monitor.py"]