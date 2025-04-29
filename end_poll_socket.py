# Licence GPL V2

# STANDARE PYTHON LIBRARIES
import asyncio
from multiprocessing.shared_memory import SharedMemory

# PIP LIBRARIES
import websockets

# LIBRARY INIT
lock_end_poll = asyncio.Lock()
share = SharedMemory(name="INTERNAL_PACKET_TRANSFER_NODE")

# CORE

### handles the end_poll websocket
async def end_poll_handler(websocket):
	async for message in websocket:		
		if message == "end": share.buf[1] = 1 # poll end state
		elif message == "quit": share.buf[1] = 2 # software quit state
		elif message == "restart": share.buf[1] = 3 # software restart state
	None
None 

async def main():
	async with websockets.serve(end_poll_handler, "localhost", 36460) as server: # mounts end_poll_socket to port 36460
		print("WebSocket server started at ws://localhost:36460")
		await asyncio.Future()
	None
None

def end_poll_socket():
	asyncio.run(main())
None

if __name__ == "__main__":
	asyncio.run(main())
None