#!/usr/bin/env python

#!/usr/local/bin/python

import os
import random
import socket
import sys
import types
import asyncore
import asynchat

MAX_BUFFER_SIZE = 256

# Defaults.
DEFAULT_PORT = 113
DEFAULT_REALM = 'UNIX'
DEFAULT_USER = 'pyIRDC'

# The different errors.
INVALID_PORT, NO_USER      = 'INVALID-PORT', 'NO-USER'
HIDDEN_USER, UNKNOWN_ERROR = 'HIDDEN-USER', 'UNKNOWN-ERROR'


class Responder:
    def __init__(self):
        if self.__class__ is Responder: raise NotImplementedError
        
    def check(self, clientPort, serverPort): raise NotImplementedError

class FailureResponder(Responder):
    def __init__(self, errorType=NO_USER):
        Responder.__init__(self)
        self.errorType = errorType

    def check(self, clientPort, serverPort): return ['ERROR', self.errorType]

class SuccessResponder(Responder):
    def __init__(self, realm=DEFAULT_REALM, users=DEFAULT_USER, suffix=0, permute=0):
        Responder.__init__(self)
        self.realm = realm
        if type(users) is types.StringType:
            self.users = [users]
        else:
            self.users = users
        self.suffix = suffix
        self.permute = permute

    def chooseUser(self):
        if len(self.users) == 1:
            user = self.users[0]
        else:
            user = random.choice(self.users)
        if self.permute:
            letters = list(user)
            user = ''
            while letters:
                i = random.randrange(len(letters))
                user += letters[i]
                del letters[i]
        return user

    def chooseSuffix(self):
        if self.suffix > 0:
            number = random.randrange(10**self.suffix)
            return ('%%0%dd' % self.suffix) % number
        else:
            return ''

    def check(self, clientPort, serverPort):
        response = self.chooseUser() + self.chooseSuffix()
        return ['USERID', self.realm, response]


class Connection(asynchat.async_chat):
    def __init__(self, server, (sock, addr)):
        asynchat.async_chat.__init__(self, sock)
        self.server = server
        self.set_terminator('\r\n')
        self.buffer = ''

    def collect_incoming_data(self, data):
        self.buffer += data
        if len(self.buffer) > MAX_BUFFER_SIZE:
            self.respond(0, 0, ['ERROR', UNKNOWN_ERROR])
            self.close_when_done()

    def handle_close(self):
        self.close()

    def handle_error(self):
        self.close()
        raise

    def found_terminator(self):
        data, self.buffer = self.buffer, ''
        data = data.strip()
        if data.find(',') >= 0:
            try:
                clientPort, serverPort = data.split(',', 1)
                clientPort = int(clientPort.strip())
                serverPort = int(serverPort.strip())
                if 0 <= clientPort < 65536 and 0 <= serverPort < 65536:
                    self.succeed(clientPort, serverPort)
                else:
                    self.respond(clientPort, serverPort,  ['ERROR', INVALID_PORT])
            except ValueError:
                self.respond(0, 0, ['ERROR', INVALID_PORT])
        else:
            self.respond(0, 0, ['ERROR', UNKNOWN_ERROR])

    def respond(self, clientPort, serverPort, response):
        self.push('%d , %d : %s\r\n' % (clientPort, serverPort, ' : '.join(response)))
        self.close_when_done()

    def succeed(self, clientPort, serverPort):
        response = self.server.responder.check(clientPort, serverPort)
        self.respond(clientPort, serverPort, response)


class Server(asyncore.dispatcher):
    ConnectionFactory = Connection

    def __init__(self, address=('', DEFAULT_PORT), responder=None):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(address)
        self.listen(5)
        if responder is None: responder = Responder()
        self.responder = responder

    def handle_error(self):
        self.close()
        raise

    def handle_accept(self):
        self.ConnectionFactory(self, self.accept())

class Identd_Server(object):
    def __init__(self):
        self.responder = SuccessResponder(DEFAULT_REALM, DEFAULT_USER, 0, 0)
        
    def start(self):
        self.server = Server(("", DEFAULT_PORT), self.responder)
        print "[Identd Server] Started listening on port %d." % DEFAULT_PORT
    
    def stop(self):
        self.server.close()
        self.server = None
        print "[Identd Server] Stopped listening."

if __name__ == "__main__":
    Identd_Server().start()
    asyncore.loop()   