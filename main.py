import socket
import struct
import time

IPADDR = "ntp.padnet.home"
PORTNUM = 123
VERSION = 4
MODE = 7

# Used as a data buffer
# request is 8 bytes, response is 48 bytes
PACKETDATA = bytearray(8)

PACKETDATA[0] = VERSION << 3 | MODE
PACKETDATA[1] = 0      # sequence number
PACKETDATA[2] = 0x10   # implementation code - custom
PACKETDATA[3] = 1      # request code, use 1 for now

PACKETDATA[4] = 0
PACKETDATA[5] = 0
PACKETDATA[6] = 0
PACKETDATA[7] = 0

# reference time in seconds since 1900-01-01 00:00:00
# for conversion from NTP time to system time
TIME1970 = 2208988800


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press ⌘F8 to toggle the breakpoint.

    server_address = (IPADDR, PORTNUM)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.5)

    sent = sock.sendto(PACKETDATA, server_address)

    response, server = sock.recvfrom(1024)


    ref_ts0 = (struct.unpack('<I', response[16:20])[0]) / 4294967296.0
    ref_ts1 = struct.unpack('<I', response[20:24])[0]
    uptime  = struct.unpack('<I', response[24:28])[0]
    ntp_requests = struct.unpack('<I', response[28:32])[0]
    cmd_served  = struct.unpack('<I', response[32:36])[0]
    lock_time   = struct.unpack('<I', response[36:40])[0]
  #  flags = struct.unpack('b', bytes(response[40]))[0]
    satellites = struct.unpack_from('<B',response, 41) [0]
    serial_number = struct.unpack('<H', response[42:44])[0]
    firmware = struct.unpack('<I', response[44:48])[0]

    sock.close()

    t = time.gmtime(ref_ts1 - TIME1970)

    #print( "UTC time: %d-%02d-%02d %02d:%02d:%02.04" % (t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec + ref_ts0))

    print( "UTC time {0}-{1}-{2} {3}:{4}:{5}".format(
        t.tm_year,
        t.tm_mon,
        t.tm_mday,
        t.tm_hour,
        t.tm_min,
        t.tm_sec + ref_ts0))

    print( "NTP time: {0}".format(ref_ts1 + ref_ts0))

    print( "Satellites locked: {0}".format(satellites))
    print( "Lock time: {0} seconds, {1} hours, {2} days".format( lock_time, lock_time /3600, lock_time / 86400 ))

    print( "NTP requests served: {0}".format(ntp_requests))

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
