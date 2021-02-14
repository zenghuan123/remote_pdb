# coding=utf-8
import functools
import logging
import time
import pdb
import sys
import socket
import util
from threading import RLock
from net import RpcHandler

from net import LoopThread, Server,HttpServerAsyn

debugger = None
__ip = None
__port = None
__socket_fd = None
__w = None  # type: socket.socket
__r =None 	# type: socket.socket
__lock = RLock()
__server = None
__loop = None
__handler = None
__http_port = None
__http_server = None
__logger = None

def message_call_back(con, obj):
	if not debugger:
		return
	debugger.handler.rpc_method(obj)


def new_connection(con):
	con.message_callback = message_call_back
	rpc = RpcHandler(con, __handler)


class HttpHandlerWrap(object):
	def __getattr__(self, item):
		return getattr(debugger.handler,item,None)


def server_init_call_back(ip, port,loop):
	global __server
	global __http_server
	__server = Server(ip, port)
	__server.close_callback = client_close
	__server.connection_callback = new_connection
	__logger.info("server init")
	if __http_port:
		__http_server = HttpServerAsyn(ip, __http_port, __handler)

def client_close(con):
	if debugger:
		send_command("c")


def start_debugger(ip, port, handler, http_port=None):
	global debugger
	if debugger:
		return
	global __socket_fd
	global __w
	global __r
	global __loop
	global __handler
	global __http_port
	global __http_server
	global __ip
	global __port
	global __logger

	__ip = ip
	__port = port
	__http_port = http_port
	__w, __r = util.socketpair()
	__socket_fd = __r.makefile("rw")
	debugger = RemotePdb(__socket_fd)
	__handler = handler
	code = util.get_func_code(__just_break)
	funcname = code.co_name
	lineno = code.co_firstlineno
	filename = code.co_filename
	debugger.set_break(filename, lineno, 0, None, funcname)
	__logger = logging.getLogger("debugger")
	th = LoopThread()
	th.set_init_call_back(functools.partial(server_init_call_back, ip, port))
	__loop = th.start_loop()


def __just_break():
	pass


def send_command(cmd, *args):
	__lock.acquire()
	s = str(cmd)
	for ar in args:
		s = s + " " + ar
	s = s + "\n"
	print("send_command ",s)
	__w.send(s)
	__lock.release()


class RemotePdb(pdb.Pdb):
	def __init__(self, fd):
		pdb.Pdb.__init__(self, completekey="tag", stdin=fd, stdout=fd, skip=["bdb", "pdb", "linecache", "RemotePdb"])
		self.fd = fd		# io
		self.handler = None

	def cmdloop(self, intro=None):
		return pdb.Pdb.cmdloop(self, intro)

	def precmd(self, line):
		line = pdb.Pdb.precmd(self, line)
		# print "precmd ",line,current_thread()
		return line

	def onecmd(self, line):
		stop = pdb.Pdb.onecmd(self, line)
		# print "onecmd ",stop,line,current_thread()
		return stop

	def postcmd(self, stop, line):
		stop = pdb.Pdb.postcmd(self, stop, line)
		return stop

	def do_quit(self, arg):
		# print "debug do_quit",os.getpid()
		return self.do_continue(arg)

	def stop_here(self, frame):
		b = pdb.Pdb.stop_here(self, frame)
		if self.handler:
			return b or self.handler.stop_here(frame)

	def break_here(self, frame):
		b = pdb.Pdb.break_here(self, frame)
		if self.handler:
			return b or self.handler.break_here(frame)

	do_q = do_quit

	def do_EOF(self, arg):
		# print "debug do_EOF",os.getpid()
		return self.do_continue(arg)


def set_trace():
	global debugger
	global socket_fd
	if not debugger:
		return
	if not debugger.handler:
		return
	try:
		frame = sys._getframe().f_back
		debugger.set_trace(frame)
	except:
		pass
	finally:
		pass


class BaseRemoteDebugger(object):
	def __init__(self):
		self.logger = logging.getLogger(self.__class__.__name__)

	def call(self,method_name,*args,**kwargs):
		pass

	def step_run(self):
		# 单步调试
		send_command("s")

	def continue_run(self):
		# 继续执行
		send_command("c")

	def go_to_return(self):
		# 跳转到方法返回处
		send_command("r")


def A():
	print("A run")
	set_trace()


def test():
	print("test run 1")
	A()
	print("test run 2")


if __name__ == '__main__':
	start_debugger("127.0.0.1", 5555,BaseRemoteDebugger())
	while True:
		time.sleep(1)
		test()
