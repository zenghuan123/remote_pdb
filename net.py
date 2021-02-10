# coding=utf-8
import asyncore
import functools
import threading
import time
import struct
import json
import socket
from util import socketpair

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
		super(Connection, self).handle_close()
		if self.on_close:
			self.on_close()


class Server(asyncore.dispatcher):
	def __init__(self, ip, port, sock=None, map=None):
		asyncore.dispatcher.__init__(self, sock=sock, map=map)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.set_reuse_addr()
		self.bind((ip, port))
		self.listen(100)

		self.connection_callback = None
		self.close_callback = None

	def handle_accept(self):
		pair = self.accept()
		if pair is not None:
			sock, addr = pair
			con = Connection(sock)
			if self.close_callback:
				con.handle_close = functools.partial(self.close_callback, con)
			self.connection_callback(con)


class Client(Connection):
	def __init__(self, ip, port, sock=None, map=None):
		Connection.__init__(self, sock=sock, map=map)
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.connect((ip, port))

	def handle_connect(self):
		super(Client, self).handle_connect()
		pass

	def handle_close(self):
		super(Client, self).handle_close()
		# TODO reconnect
		print("to do reconnect")


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
