#!/usr/bin/env python3
# encoding: utf-8
# SSH PLUS MANAGER - Proxy HTTP local compatível com Python 3
# Correção de estabilidade: bytes/strings, threads, timeouts e logs.
import socket
import threading
import select
import signal
import sys
import time
from os import system

system("clear")
IP = '0.0.0.0'
try:
    PORT = int(sys.argv[1])
except Exception:
    PORT = 8080

PASS = ''
BUFLEN = 8192 * 8
TIMEOUT = 60
MSG = 'DARKSSH'
DEFAULT_HOST = '127.0.0.1:1194'
RESPONSE = b"HTTP/1.1 200 DARKSSH\r\n\r\n"


def to_text(data):
    if isinstance(data, bytes):
        return data.decode('latin-1', errors='ignore')
    return str(data)


class Server(threading.Thread):
    def __init__(self, host, port):
        super().__init__()
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()
        self.logLock = threading.Lock()
        self.soc = None

    def run(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        self.soc.bind((self.host, self.port))
        self.soc.listen(100)
        self.running = True
        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(True)
                    c.settimeout(TIMEOUT)
                except socket.timeout:
                    continue
                except OSError:
                    break
                conn = ConnectionHandler(c, self, addr)
                conn.daemon = True
                conn.start()
                self.addConn(conn)
        finally:
            self.running = False
            try:
                self.soc.close()
            except Exception:
                pass

    def printLog(self, log):
        with self.logLock:
            print(log)

    def addConn(self, conn):
        with self.threadsLock:
            if self.running:
                self.threads.append(conn)

    def removeConn(self, conn):
        with self.threadsLock:
            if conn in self.threads:
                self.threads.remove(conn)

    def close(self):
        self.running = False
        with self.threadsLock:
            threads = list(self.threads)
        for c in threads:
            c.close()
        try:
            if self.soc:
                self.soc.close()
        except Exception:
            pass


class ConnectionHandler(threading.Thread):
    def __init__(self, socClient, server, addr):
        super().__init__()
        self.clientClosed = False
        self.targetClosed = True
        self.client = socClient
        self.client_buffer = b''
        self.server = server
        self.log = 'Conexao: ' + str(addr)
        self.target = None

    def close(self):
        for attr in ('client', 'target'):
            soc = getattr(self, attr, None)
            if soc:
                try:
                    soc.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    soc.close()
                except Exception:
                    pass
        self.clientClosed = True
        self.targetClosed = True

    def run(self):
        try:
            self.client_buffer = self.client.recv(BUFLEN)
            hostPort = self.findHeader(self.client_buffer, 'X-Real-Host') or DEFAULT_HOST
            split = self.findHeader(self.client_buffer, 'X-Split')
            if split:
                try:
                    self.client.recv(BUFLEN)
                except Exception:
                    pass
            passwd = self.findHeader(self.client_buffer, 'X-Pass')
            if PASS and passwd != PASS:
                self.client.sendall(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
                return
            self.method_CONNECT(hostPort)
        except Exception as e:
            self.log += ' - error: ' + str(e)
            self.server.printLog(self.log)
        finally:
            self.close()
            self.server.removeConn(self)

    def findHeader(self, head, header):
        text = to_text(head)
        marker = header + ': '
        aux = text.find(marker)
        if aux == -1:
            return ''
        start = aux + len(marker)
        end = text.find('\r\n', start)
        if end == -1:
            return ''
        return text[start:end].strip()

    def connect_target(self, host):
        if ':' in host:
            h, p = host.rsplit(':', 1)
            port = int(p)
            host = h.strip('[]')
        else:
            port = 1194
        infos = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        last_error = None
        for family, socktype, proto, _, address in infos:
            try:
                self.target = socket.socket(family, socktype, proto)
                self.target.settimeout(TIMEOUT)
                self.target.connect(address)
                self.targetClosed = False
                return
            except Exception as e:
                last_error = e
                try:
                    self.target.close()
                except Exception:
                    pass
        raise last_error or OSError('Nao foi possivel conectar ao destino')

    def method_CONNECT(self, path):
        self.log += ' - CONNECT ' + path
        self.connect_target(path)
        self.client.sendall(RESPONSE)
        self.server.printLog(self.log)
        self.doCONNECT()

    def doCONNECT(self):
        socs = [self.client, self.target]
        idle = 0
        while True:
            recv, _, err = select.select(socs, [], socs, 3)
            if err:
                break
            if not recv:
                idle += 1
                if idle >= TIMEOUT:
                    break
                continue
            idle = 0
            for src in recv:
                try:
                    data = src.recv(BUFLEN)
                    if not data:
                        return
                    dst = self.client if src is self.target else self.target
                    dst.sendall(data)
                except Exception:
                    return


def main(host=IP, port=PORT):
    print("\033[0;34m" + "━" * 8 + "\033[1;32m PROXY HTTP \033[0;34m" + "━" * 8 + "\n")
    print("\033[1;33mIP:\033[1;32m " + IP)
    print("\033[1;33mPORTA:\033[1;32m " + str(PORT) + "\n")
    server = Server(host, port)
    server.daemon = True
    server.start()
    def stop(*_):
        print('\nParando...')
        server.close()
        sys.exit(0)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while True:
        time.sleep(2)

if __name__ == '__main__':
    main()
