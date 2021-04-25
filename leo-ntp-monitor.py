import socket
import struct
import time
import json
import sys
import os
import getopt
import threading
import logging
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

NTP_DEFAULT_PORT_NUM = 123

NTP_POLLING_RATE_SECONDS = 60
NTP_POLLING_ONCE_ONLY = -1

# reference time in seconds since 1900-01-01 00:00:00
# for conversion from NTP time to system time
TIME1970 = 2208988800

# the default timeout for socket operations
SOCKET_TIMEOUT_SECS = 1.0

logging.basicConfig(level=logging.NOTSET, format='%(asctime)s - %(levelname)s - %(message)s')


def get_ntp_metrics(host, port, timeout_sec=SOCKET_TIMEOUT_SECS):
    version = 4
    mode = 7

    # Used as a data buffer
    # request is 8 bytes, response is 48 bytes
    packet = bytearray(8)

    packet[0] = version << 3 | mode
    packet[1] = 0     # sequence number
    packet[2] = 0x10  # implementation code - custom
    packet[3] = 1     # request code, use 1 for now

    packet[4] = 0
    packet[5] = 0
    packet[6] = 0
    packet[7] = 0

    recv_buffer = 1024
    server_address = (host, port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_sec)
        sock.sendto(packet, server_address)
        response, server = sock.recvfrom(recv_buffer)

        # Not really needed from within a with context, but
        # I like to be explicit
        sock.close()

    ref_ts0 = (struct.unpack_from('<I', response[16:20])[0]) / 4294967296.0
    ref_ts1 = struct.unpack_from('<I', response[20:24])[0]
    uptime = struct.unpack_from('<I', response[24:28])[0]
    ntp_requests = struct.unpack_from('<I', response[28:32])[0]
    # cmd_served = struct.unpack_from('<I', response[32:36])[0]
    lock_time = struct.unpack_from('<I', response[36:40])[0]
    flags = struct.unpack_from('<B', bytes(response[40]))[0]
    satellites = struct.unpack_from('<B', response, 41)[0]
    serial_number = struct.unpack_from('<H', response[42:44])[0]
    firmware = struct.unpack_from('<I', response[44:48])[0]

    t = time.gmtime(ref_ts1 - TIME1970)

    utc = '{0}-{1:02}-{2:02}T{3:02}:{4:02}:{5:02.04}Z'.format(
        t.tm_year,
        t.tm_mon,
        t.tm_mday,
        t.tm_hour,
        t.tm_min,
        t.tm_sec + ref_ts0)

    ntp_time = ref_ts1 + ref_ts0

    metrics = {
        'serial-number': serial_number,
        'firmware': firmware,
        'flags': flags,
        'uptime-hours': uptime / 3600,
        'ntp-requests': ntp_requests,
        'utc-time': utc,
        'ntp-time': ntp_time,
        'lock-time-hours': lock_time / 3600,
        'satellites': satellites
        }

    return metrics


def get_command_line(argv):
    host = ''
    port = NTP_DEFAULT_PORT_NUM
    polling = NTP_POLLING_ONCE_ONLY

    try:
        opts, args = getopt.getopt(argv, "", ["ntpserver=", "port=", "polling="])

        for opt, arg in opts:
            if opt == '-h':
                 print('leo-ntp-monitor.py --ntpserver=SERVER|IP_ADDRESS --port=NTP_PORT')
                 sys.exit()
            elif opt in ("-ntpserver", "--ntpserver"):
                 host = arg
            elif opt in ("-p", "--port"):
                 port = int(arg)
            elif opt in ("--polling"):
                 polling = int(arg)

        return host, port, polling

    except getopt.GetoptError:
        print('usage:  --ntpserver=SERVERNAME --port=NTP-PORT')
        sys.exit(2)


def get_environment_args():
    host = os.getenv('NTP_SERVER')
    port = os.getenv('NTP_PORT')
    polling = os.getenv('NTP_POLLING_PERIOD_SECONDS')

    if port is None:
        port = NTP_DEFAULT_PORT_NUM
    elif port is not None:
        port = int(port)

    if polling is None:
        polling = NTP_POLLING_RATE_SECONDS
    elif polling is not None:
        polling = int(polling)

    logging.info('env variables NTP_SERVER=%s, NTP_PORT=%s, NTP_POLLING_PERIOD_SECONDS=%s', host, port, polling)

    return host, port, polling


def use_influx():

    # Assume we are using influx
    result = True

    bucket = os.getenv('INFLUXDB_V2_BUCKET')
    if not bucket:
        logging.warning("INFLUXDB_V2_URL environment variable is not set. This must be set to use influx")
        result = False

    url = os.getenv('INFLUXDB_V2_URL')
    if not url:
        logging.warning("INFLUXDB_V2_URL environment variable is not set. This must be set to use influx")
        result = False

    token = os.getenv('INFLUXDB_V2_TOKEN')
    if not token:
        logging.warning("INFLUXDB_V2_TOKEN environment variable is not set. This must be set to use influx")
        result = False
    else:
        unmasked_chars = 5
        if len(token) > unmasked_chars:
            prefix = token[0:unmasked_chars]
            masked = '*' * (len(token) - unmasked_chars)
            token = prefix + masked
        else:
            # we have a short string, so mask everything
            token = '*' * len(token)

    org = os.getenv('INFLUXDB_V2_ORG')
    if not org:
        logging.warning("INFLUXDB_V2_ORG environment variable is not set. This must be set to use influx")
        result = False

    if result is True:
        logging.info(
            "found influxdb env variables. INFLUXDB_V2_BUCKET=%s, INFLUXDB_V2_URL=%s, INFLUXDB_V2_ORG=%s, INFLUXDB_V2_ORG=%s",
            bucket, url, org, token
        )

    return result


def send_to_influx(metrics):

    bucket = os.getenv('INFLUXDB_V2_BUCKET')

    logging.info('sending ntp metrics to influxdb')

    try:
        p0 = Point("ntp").tag("serial-number", metrics["serial-number"]).field(
            "satellites", metrics["satellites"]).time(metrics["utc-time"])

        p1 = Point("ntp").tag("serial-number", metrics["serial-number"]).field(
            "lock-time-hours", metrics["lock-time-hours"]).time(metrics["utc-time"])

        p2 = Point("ntp").tag("serial-number", metrics["serial-number"]).field(
            "uptime-hours", metrics["uptime-hours"]).time(metrics["utc-time"])

        p3 = Point("ntp").tag("serial-number", metrics["serial-number"]).field(
            "ntp-requests", metrics["ntp-requests"]).time(metrics["utc-time"])

        # Note tried using a with statement and these
        # keep blowing up. So f-it for now.
        client = InfluxDBClient.from_env_properties();
        write_api = client.write_api(write_options=SYNCHRONOUS)
        try:
            write_api.write(bucket=bucket, record=[p0, p1, p2, p3])
        finally:
            write_api.close()

        client.close()

    except Exception as e:
        logging.exception('a fatal exception happened while trying to send ntp metrics to influx')


def process():
    host, port, polling = get_environment_args()

    capture_metrics = use_influx()

    # if we don't have a host, then assume the
    # environment variables are not set, and try
    # to grab the config from the command line
    if host is None:
        host, port, polling = get_command_line(sys.argv[1:])

    if host is None:
        print("You must either set the NTP_SERVER/NTP_PORT environment variables OR")
        print("pass the --ntp-server/--ntp_port command line options")
        sys.exit(2)

    print('Using host={0}, port={1}, polling={2}'.format(host, port, polling))

    logging.info('using host=%s, port=%s, polling=%s', host, port, polling)

    # We are using an event because a ctrl-c (or other signals)
    # will cause it to break out - i.e. more responsive than a sleep
    looping = threading.Event();

    if polling == NTP_POLLING_ONCE_ONLY:
        metrics = get_ntp_metrics(host, port)
        logging.info(json.dumps(metrics))
    else:
        bail = False
        while not bail:
            try:
                metrics = get_ntp_metrics(host, port)
                logging.info(json.dumps(metrics))

                if capture_metrics is True:
                    send_to_influx(metrics)

                logger.info("next polling period will be in %s seconds", polling)
                bail = looping.wait(polling)
            except socket.error as err:
                logging.error(
                    'a socket exception occurred trying to connect to host=%s, port=%s, error=%s',
                    host, port, err
                )

    sys.exit(0)


if __name__ == '__main__':
    process()


