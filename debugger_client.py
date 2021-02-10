from net import LoopThread, Client, RpcHandler

__ip = None
__port = None
__handler_class = None
__loop = None


def client_init_call_back(loop):
	client = Client(__ip, __port)
	__handler_class(client)


def debugger_client(ip, port, handler):
	global __ip
	global __port
	global __handler_class
	global __loop
	__ip = ip
	__port = port
	__handler_class = handler

	th = LoopThread()
	th.set_init_call_back(client_init_call_back)
	__loop = th.start_loop()
