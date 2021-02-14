# coding=utf-8

import asyncore
import functools
import logging
import threading
import time
import struct
import json
import socket
from util import socketpair,BaseHTTPRequestHandler,HTTPServer

header_len = 4
header_fmt = ">I"


class RpcHandler(object):
	def __init__(self, con, handler=None):
		self.con = con
		self.con.message_callback = self.message_call_back
		con.on_close = self.on_close
		self.handler = handler
		if self.handler:
			self.handler.call = self.call

		if hasattr(self.handler,"on_connect"):
			self.handler.on_connect()

	def message_call_back(self, con, obj):
		self.rpc_method(obj)

	def rpc_method(self, data):
		# print "rpc_method ",data, type(data.keys()[0].encode("utf-8"))
		method_name = data.get("m")
		if not method_name:
			return
		args = data.get("a", [])
		kwargs = data.get("k", {})
		method = None
		if self.handler:
			method = getattr(self.handler, method_name, None)
		if method is None:
			method = getattr(self, method_name,None)
		if method:
			try:
				method(*args, **kwargs)
			except Exception or BaseException:
				pass
		else:
			print("not round rpc")

	def call(self, method, *args, **kwargs):
		if not self.con:
			print("not connected")
			return
		self.con.send({"m":method, "a":args, "k": kwargs})

	def on_close(self):
		if self.handler and hasattr(self.handler,"on_close"):
			self.handler.on_close()


class Connection(asyncore.dispatcher_with_send):
	def __init__(self, sock=None, map=None):
		asyncore.dispatcher_with_send.__init__(self, sock=sock, map=map)
		self._read_buff = "".encode("utf-8")
		self.message_callback = None
		self.on_close = None

	def handle_read(self):
		data = self.recv(8192)
		self._read_buff = self._read_buff + data
		while len(self._read_buff) >= header_len:
			data = self._read_buff[0:header_len]
			self._read_buff = self._read_buff[header_len:]
			length = struct.unpack(header_fmt, data)[0]
			data = self._read_buff[0:length]
			self._read_buff = self._read_buff[length:]
			obj = json.loads(data.decode("utf-8"))
			self.message_callback(self, obj)

	def send(self, obj):
		i = json.dumps(obj).encode("utf-8")
		i = struct.pack(header_fmt, len(i)) + i
		return asyncore.dispatcher_with_send.send(self, i)

	def handle_close(self):
		asyncore.dispatcher_with_send.handle_close(self)
		if self.on_close:
			self.on_close()


class Server(asyncore.dispatcher):
	def __init__(self, ip, port, sock=None, map=None):
		asyncore.dispatcher.__init__(self, sock=sock, map=map)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.set_reuse_addr()
		self.bind((ip, port))
		self.listen(100)
		self.logger = logging.getLogger(self.__class__.__name__)
		self.connection_callback = None
		self.close_callback = None

	def handle_accept(self):
		pair = self.accept()
		if pair is not None:
			sock, addr = pair
			self.logger.debug("accept %s",addr)
			con = Connection(sock)
			con.on_close = functools.partial(self.connection_close, con)
			self.connection_callback(con)

	def connection_close(self, con):
		if self.close_callback:
			self.close_callback(con)

class Client(Connection):
	def __init__(self, ip, port, sock=None, map=None):
		Connection.__init__(self, sock=sock, map=map)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.connect((ip, port))
		self.logger = logging.getLogger(self.__class__.__name__)

	def handle_connect(self):
		self.logger.debug("connect success")
		Connection.handle_connect(self)

	def handle_close(self):
		self.logger.debug("close")
		Connection.handle_close(self)


class WakeUp(asyncore.dispatcher):
	def __init__(self, sock=None, map=None):
		asyncore.dispatcher.__init__(self, sock=sock, map=map)
		self.func_array = []

	def add_func(self, func):
		self.func_array.append(func)

	def handle_read(self):
		self.recv(1024)
		for func in self.func_array:
			func()
		self.func_array = []


class HttpResquest(BaseHTTPRequestHandler):
	def do_POST(self):
		try:
			data = self.rfile.read(int(self.headers['content-length']))
			if hasattr(self.server, "handler"):
				method_name = self.path[1:]
				data = data.decode('utf-8')
				request_data = json.loads(data)
				method = getattr(self.server.handler, method_name,None)
				response_data = method(**request_data)
				data = json.dumps(response_data)
				self.send_response(200)
				self.send_header('Content-type', 'application/json')
				self.end_headers()
				self.wfile.write(data.encode('utf-8'))
				return
		except Exception or BaseException:
			import traceback
			logging.getLogger(self.__class__.__name__).error(traceback.format_exc(10))
		self.send_response(404, "not method")
		self.send_header('Content-type', 'application/json')
		self.end_headers()
		self.wfile.write("not method")


class HttpConnection(asyncore.dispatcher_with_send):
	def __init__(self,handler,sock=None, map=None):
		self.handler = handler
		asyncore.dispatcher_with_send.__init__(self, sock=sock, map=map)

	def handle_read(self):
		request = HttpResquest(self.socket, self.addr, self)
		# request.close()
		self.close()


class HttpServerAsyn(asyncore.dispatcher):
	def __init__(self, ip, port, handler=None, map=None):
		self.handler = handler
		asyncore.dispatcher.__init__(self, sock=None, map=map)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.set_reuse_addr()
		self.bind((ip, port))
		self.listen(100)

		# self.http_server = HTTPServer((ip, port), HttpResquest)
		# asyncore.dispatcher.__init__(self, sock=self.http_server.socket, map=map)
		# self.http_server.handler = handler
		# self.set_reuse_addr()
		# self.addr = (ip, port)
		#
		# #self.bind((ip, port))
		# self.listen(100)
		self.logger = logging.getLogger(self.__class__.__name__)
		self.logger.info("http server start on port %s", port)

	def handle_accept(self):
		# 感觉不太好
		# self.http_server._handle_request_noblock()
		pair = self.accept()
		if pair is not None:
			sock, addr = pair
			con = HttpConnection(self.handler,sock=sock)


	def handle_close(self):
		pass


class Loop(object):
	def __init__(self):
		self._map = {}
		self._thread = threading.current_thread()
		r, w = socketpair()
		self._wake_up = WakeUp(sock=r)
		self._w = w

	def loop(self):
		asyncore.loop()

	def call_in_loop(self, func):
		self._wake_up.add_func(func)
		self._w.send("1".encode("utf-8"))


class LoopThread(object):

	def __init__(self):
		self._condition = threading.Condition()
		self._loop = None
		self._thread = threading.Thread(target=self._run, name=str(time.time()))
		self._init_call_back = None

	def set_init_call_back(self, func):
		self._init_call_back = func

	def _run(self):
		self._condition.acquire()
		if not self._loop:
			self._loop = Loop()
		self._condition.notify()
		self._condition.release()
		if self._init_call_back and callable(self._init_call_back):
			self._init_call_back(self._loop)
		self._loop.loop()

	def start_loop(self):
		self._thread.start()
		self._condition.acquire()
		while not self._loop:
			self._condition.wait()
		self._condition.release()
		return self._loop


def server_init_call_back(loop):
	server = Server("127.0.0.1", 9999)
	server.connection_callback = new_connection


def new_connection(con):
	con.message_callback = message_call_back


def message_call_back(con, obj):
	print("debug receive ", obj)
	con.send({"message": "hello"})


def client_init_call_back(loop):
	client = Client("127.0.0.1", 5555)
	#client.send({"m": "continue_run", "a": [], "k": {}})
	client.message_callback = message_call_back
	rpc = RpcHandler(client)


if __name__ == '__main__':
	th = LoopThread()
	th.set_init_call_back(client_init_call_back)
	loop = th.start_loop()
	th._thread.join()
