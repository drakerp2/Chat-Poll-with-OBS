# Licence GPL V2

# STANDARD PYTHON LIBRARIES
from sys import argv, executable as python # executable is the path to the instance of python being used to run the current script
from time import sleep
import importlib
import subprocess 
import asyncio
import multiprocessing # thats right, we are using not 1, not 2, but 3(!!!) parrallism libraries, now all we need is threading and we'll have the whole family!
from multiprocessing.shared_memory import SharedMemory

# PIP LIBRARIES
# in theory, this allows someone to simply execute the driver.py file with a double click on windows after installing it from the windows store, and they never will actually need to open the terminal.  In theory.  I do not have a windows machine to test on.
try: import matplotlib
except ModuleNotFoundError: subprocess.run([python, '-m', 'pip', 'install', 'matplotlib'])
try: import requests
except ModuleNotFoundError: subprocess.run([python, '-m', 'pip', 'install', 'requests'])
try: import websockets
except ModuleNotFoundError: subprocess.run([python, '-m', 'pip', 'install', 'websockets'])

# LIBRARY INIT
try: share = SharedMemory(name="INTERNAL_PACKET_TRANSFER_NODE", create=True, size=10000000) # 10 MB
except FileExistsError: share = SharedMemory(name="INTERNAL_PACKET_TRANSFER_NODE") # if the programmed crashed out on last run, this prevents it from locking up when the shared memory already exists
share.buf[0] = 0; share.buf[1] = 0

# LOCAL LIBRARIES
import poll_socket
import obs_socket
import end_poll_socket
import get_live_chat #for the purposes of reloading

# CORE

### watches share buffer for program quit state and program restart state
### @param processes the list of child processes
### @return 0 on quit, 1 on restart
def oracle(processes):
	while share.buf[1] not in [2, 3]: continue
	if share.buf[1] == 2: # quit
		quit(processes)
		return 0
	elif share.buf[1] == 3: # restart
		quit(processes) 
		share.buf[0] = 0; share.buf[1] = 0
		return 1
	None
None


### violently and inelequently kills the processes
### @param processes the list of child processes
def quit(processes):
	for p in processes: p.terminate()
	sleep(1)
	for p in processes: 
		if p.is_alive(): p.kill()
	None	
None



async def main():
	server = subprocess.Popen([python, '-m', 'http.server', '36457']) # intializes our local web server on localhost port 36457 using python's built in http.server module
	if '--headless' not in argv: subprocess.run([python, '-m', 'webbrowser', '-t', 'http://localhost:36457/control-pannel.html']) # opens the control pannel in the browser using python's built in webbrowser module
	
	while True: 
		processes = [multiprocessing.Process(target=foo) for foo in [poll_socket.poll_socket, obs_socket.obs_socket, end_poll_socket.end_poll_socket]] # initializes the websocket processes
		for p in processes: p.start() # starts the websockets
		cont = await asyncio.get_event_loop().run_in_executor(None, oracle, processes)
		if cont == 0: break # exit loop on quit
		if '--reload-on-restart' in argv: importlib.reload(poll_socket); importlib.reload(obs_socket); importlib.reload(end_poll_socket); importlib.reload(get_live_chat) # reloads the libraries, this is primarily for dev use
	None

	# stops the server
	server.terminate()
	sleep(1)
	if server.poll() is None: server.kill()

	# unlink and close the shared memory
	share.close()
	share.unlink()
None

if __name__ == "__main__":
	asyncio.run(main())
None