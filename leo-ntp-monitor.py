import socket
import struct
import time
import json
import sys
import os
import getopt

NTP_DEFAULT_PORT_NUM = 123

# reference time in seconds since 1900-01-01 00:00:00
# for conversion from NTP time to system time
TIME1970 = 2208988800

# the default timeout for socket operations
SOCKET_TIMEOUT_SECS = 10.0


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

    try:
        opts, args = getopt.getopt(argv, "", ["ntpserver=", "port="])

        for opt, arg in opts:
            if opt == '-h':
                 print('leo-ntp-monitor.py --ntpserver=SERVER|IP_ADDRESS --port=NTP_PORT')
                 sys.exit()
            elif opt in ("-ntpserver", "--ntpserver"):
                 host = arg
            elif opt in ("-p", "--port"):
                 port = int(arg)

        return host, port

    except getopt.GetoptError:
        print('usage:  --ntpserver=SERVERNAME --port=NTP-PORT')
        sys.exit(2)

def get_environment_args():
    host = os.getenv('NTP_SERVER')
    port = os.getenv('NTP_PORT')

    if port is None:
        port = NTP_DEFAULT_PORT_NUM
    elif port is not None:
        port = int(port)

    return host, port

def process():

    host, port = get_environment_args()

    # if we don't have a host, then assume the
    # environment variables are not set, and try
    # to grab the config from the command line
    if host is None:
        host, port = get_command_line(sys.argv[1:])

    if host is None:
        print("You must either set the NTP_SERVER/NTP_PORT environment variables OR")
        print("pass the --ntp-server/--ntp_port command line options")
        sys.exit(2)

    print('Using host={0}, port={1}'.format(host, port))

    metrics = get_ntp_metrics(host, port)

    print(json.dumps(metrics))

    sys.exit(0)

if __name__ == '__main__':
    process()
