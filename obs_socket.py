# Licence GPL V2

# STANDARE PYTHON LIBRARIES
import asyncio
from multiprocessing.shared_memory import SharedMemory

# PIP LIBRARIES
import websockets

# LIBRARY INIT
with open("transparent.png", 'rb') as f: default_image = f.read() # we "erase" the image when a poll ends by writing a fully transparent png

lock_obs = asyncio.Lock()

share = SharedMemory(name="INTERNAL_PACKET_TRANSFER_NODE")

async def obs_handler(websocket):
	async with lock_obs: # only allows one "obs socket" to be initialized at once
		while(True):
			while share.buf[0] == 0 and share.buf[1] != 1: continue # waits for ready state or end poll state

			if share.buf[1] == 1: # end poll state
				print("erasing image")
				await asyncio.sleep(1)
				await websocket.send(default_image)
				if share.buf[0] != 0: await asyncio.sleep(1) # double checks race conditions 
				share.buf[0] = 0; share.buf[1] = 0 # resets states
				print("image erased")
				continue
			None
			
			size = int.from_bytes(bytes(share.buf[2:10]), byteorder='big') # gets the image size off the share buffer
			buf = share.buf[10:size+10] # reads the image off the share buffer
			try: await websocket.send(buf) # sends the image to obs-endpoint.html 
			except websockets.exceptions.ConnectionClosedError: print("OBS websocket connection was reported as closed, if errors persist restart chat-poll") 
			share.buf[0] = 0 # sets the finish state
		None
	None
None 

async def main():
	async with websockets.serve(obs_handler, "localhost", 36459) as server: # mounts end_poll_socket to port 36459
		print("WebSocket server started at ws://localhost:36459")
		await asyncio.Future()
	None

def obs_socket():
	asyncio.run(main())
None

if __name__ == "__main__":
	asyncio.run(main())
None