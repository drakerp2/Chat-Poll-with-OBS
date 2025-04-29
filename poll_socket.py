# Licence GPL V2

# STANDARD PYTHON LIBRARIES
import io
import asyncio
from multiprocessing.shared_memory import SharedMemory
import textwrap

# PIP LIBRARIES
import websockets
from matplotlib import pyplot as plt, font_manager as fonts

# LOCAL LIBRARIES
from get_live_chat import initialize_stream, iterate_request

# CONFIG SETTINGS (TODO: marked to be moved to drivers suite as a cli flag)
NUMBER_OF_POLL_OPTIONS = 10
font_dir_path = './fonts/'
font_path_list = [ # pulls in fonts as to utilize monospace and allow for JP, KR, SC, and TC to be used.  Note: most languages are included in Noto Sans, but these handful of kanji based languages are packaged seperately
	'Noto_Sans_JP/NotoSansJP-VariableFont_wght.ttf', # japanese
	'Noto_Sans_KR/NotoSansKR-VariableFont_wght.ttf', # korean
	'Noto_Sans_SC/NotoSansSC-VariableFont_wght.ttf', # simplified chinese
	'Noto_Sans_TC/NotoSansTC-VariableFont_wght.ttf', # traditional chinese
]

# LIBRARY INIT

share = SharedMemory(name="INTERNAL_PACKET_TRANSFER_NODE") # connects too our shared memory block

for i in range(len(font_path_list)): font_path_list[i] = font_dir_path+font_path_list[i] # TODO: marked to be removed and replaced with static project path
# initializes fonts
for font_path in font_path_list: fonts.fontManager.addfont(font_path)
plt.rcParams['font.family'] = ['Noto Sans Mono', *fonts.get_font_names()] # Noto Sans Mono by Google is our default font, but we have the entire Noto suite (including imported JP, KR, SC, TC) as fallbacks if a symbol isn't found

# we use this lock in a vain attempt to fight the elder gods that are race conditions
poll_lock = asyncio.Lock()

# CORE

### converts colors from a hexcode into the format used by matplotlib (where hex FF is 1.0 and hex 00 is 0.0)
### @param params the params dict being worked on
### @param color_key the key of the color in params we are accessing
### @param default_color what to set the color too if no param was given by control-pannel.html
### @param alpha_key the key for the coresponding alpha in params if the color was not given
### @returns nothing, modifies params[color_key] and params[alpha_key]
def convert_color(params:dict, color_key, defualt_color:tuple[float, float, float], alpha_key=None) -> None:
	if params[color_key] is not None: 
		try: params[color_key] = (int(params[color_key][3:5], 16)/255, int(params[color_key][5:7], 16)/255, int(params[color_key][7:9], 16)/255); return # we start at index 3 because the codes come in as "%23rrggbb"
		except (ValueError, IndexError) as e: None
	None
	if alpha_key is not None: params[alpha_key] = 0.0; 
	params[color_key] = defualt_color; 
None


### takes the url params sent from run-poll.html after redirect from control-pannel.html and converts them into a dictionary
### @param params the url params being parsed
### @return params dictionary to be used by python
### @throws KeyError if the url params are missing expected keys
def parse_request_parameters(params:str) -> dict:
	ret = {}
	params = params[1:] # shave the ? from the front

	# converts the url params into a dictionary of strings or Nones
	j = -1
	while True:
		i = j+1
		k = params.find('=', i)
		j = params.find('&', k)
		if j == -1: 
			ret[params[i:k]] = tmp if (tmp:=params[k+1:]) != "" else None
			break
		ret[params[i:k]] = tmp if (tmp:=params[k+1:j]) != "" else None
	None

	## correct strings to be the propper data type, and Nones to be their default value
	
	for key in ["allow_multiple_responses", "allow_duplicate_responses", "allow_changed_responses", "ignore_case", "sort_responses"]: ret[key] = (ret.get(key) is not None)

	conversion = lambda key, typefun, default=None: typefun(ret[key]) if ret[key] is not None else default

	ret["duration"] = conversion("duration", int)
	ret["frametime"] = conversion("frametime", int, default=1000) 
	ret["dpi"] = conversion("dpi", float, default=100.0) 
	ret["fontsize"] = conversion("fontsize", float, default=10.0) 
	ret["legfontsize"] = conversion("legfontsize", float, default=ret["fontsize"]*0.75) 
	ret["bgalpha"] = conversion("bgalpha", float, default=1.0)
	ret["legbgalpha"] = conversion("legbgalpha", float, default=1.0)

	

	convert_color(ret, "bgcolor", (1.0, 1.0, 1.0), "bgalpha")
	convert_color(ret, "edgecolor", (0.0, 0.0, 0.0))
	convert_color(ret, "txtcolor", (0.0, 0.0, 0.0))
	convert_color(ret, "legbgcolor", (1.0, 1.0, 1.0), "legbgalpha")
	convert_color(ret, "legedgecolor", (0.0, 0.0, 0.0))
	convert_color(ret, "legtxtcolor", (0.0, 0.0, 0.0))

	# parses aspect ratio from 'x:y' into (x, y)
	# would this be too illegable?: ret["aspectratio"] = conversion("aspectratio", lambda val: (float(val[:(tmp:=val.find('%3A'))]), float(val[tmp+3:])), (6.0, 6.0))
	if ret["aspectratio"] is not None:
		tmp = ret["aspectratio"].find('%3A') # hex value corseponding to colon (':')
		ret["aspectratio"] = (float(ret["aspectratio"][:tmp]), float(ret["aspectratio"][tmp+3:]))
	else: ret["aspectratio"] = (6.0, 6.0)


	if ret["prefix"] is not None and '%' in ret["prefix"]:
		while '%' in ret["prefix"]:
			i = ret["prefix"].find('%')
			ret["prefix"] = ret["prefix"][:i] + chr(int(ret["prefix"][i+1:i+3], 16)) + ret["prefix"][i+3:]
		None
	None
	
	ret['target_responses'] = get_target_responses(ret)

	return ret
None


def get_target_responses(params) -> dict[str, list[str, tuple[float, float, float], str]]:
	ret = {}

	color_list = []
	global_color = None
	tr_len = 0

	# iterates over each poll option
	for i in range(NUMBER_OF_POLL_OPTIONS, 0, -1):
		# skips option if it has no key
		if (key:= params.get(f"option{i}key")) is None: 
			# ensure colors are in correct state
			convert_color(params, f"option{i}color", None)
			if tr_len == 0 and color_list is not None: # we only need to deal with the colors on a null key if there are no other keys in the list, and only color list if every color is present
				if params[f"option{i}color"] is None: color_list = None # If not all colors present, we only use one global color
				else: 
					if len(color_list) == 0: global_color = params[f"option{i}color"] # sets the global color to the first item found (the last in the list)
					color_list.append(params[f"option{i}color"]) # adds the color to the color list
				None
			elif params[f"option{i}color"] is not None and global_color is None: global_color = params[f"option{i}color"] # This makes ensures the first entry is the global color and not the last
			continue
		None

		## If key is found

		key = key.replace('+', ' ')

		if (value:= params.get(f"option{i}value")) is None: value = params[f"option{i}key"] # checks for value
		else: value = value.replace('+', ' ')

		if tr_len == 0: params["has_colors"] = int(params.get(f"option{i}color") is not None) # converts the boolean to 0 if false, 1 if true.  0 means we use randomized colors, 1 means we use selected colors, and 2 indicates the state where 1 color is given but not all colors, and thus set everything to a uniform color
		if tr_len > 0 and params["has_colors"] == 2: params[f"option{i}color"] = global_color # This makes ensures the first entry is the global color and not the last
		else: 
			convert_color(params, f"option{i}color", None)
			if tr_len == 0: global_color = params[f"option{i}color"] # sets the global color if this is the first item
			elif tr_len == 1 and global_color is not None and params[f"option{i}color"] is None: params["has_colors"] = 2; params[f"option{i}color"] = global_color
			elif tr_len > 0 and (params[f"option{i}color"] is None) == bool(params["has_colors"]): # discrete math don't fail me now! (ret[f"option{i}color"] is None and ret["has_colors"] == 1) or (ret[f"option{i}color"] is not None and ret["has_colors"] == 0)
				params["has_colors"] = 2 # only some colors
				if global_color is None: global_color = params[f"option{i}color"] # sets global color if it hasn't been already
				else: params[f"option{i}color"] = global_color # sets color to global color if there is one
				for resp in ret.values(): resp[1] = global_color # corrects other colors to global color
			None
		None
		
		literal = (key.casefold() if params['ignore_case'] else key) # makes key lowercase for the dict index if we are ignoring case
		ret[literal] = [value, params[f"option{i}color"], key]
		tr_len += 1
	None

	# performs some finalizations if there were no keys given
	if tr_len == 0: 
		ret = None; 
		params["sort_responses"] = True
		params['color_list'] = color_list if color_list is not None else [global_color]*NUMBER_OF_POLL_OPTIONS
	None

	return ret
None


### takes a list of responses and creates a bar plot of them
### @param responses the dictionary containing the poll responses
### @param params the params passed into the poll by control-pannel
### @return png stored as a bytes array-like object 
def plot_iteration(responses, params):

	## Parse out the responses we want to print

	meaningful_responses: dict[str, tuple[int, str, None|tuple[float,float,float]]] = {}

	if params['target_responses'] is not None: # if keys were given
		for value, color, key in params['target_responses'].values():
			if (count:= responses.get(key)) is None: meaningful_responses[key] = (0, value, color)
			else: meaningful_responses[key] = (count, value, color)
		None
		if params['sort_responses']: meaningful_responses = dict(sorted(meaningful_responses.items(), key=lambda item: item[1][0])) # sorts by count
	else: # if keys were not given
		meaningful_responses = dict([(k, (c, k, None)) for k, c in sorted(responses.items(), key=lambda item: item[1])[-10:]]) # takes the 10 most common responses
		if params["color_list"] is not None: # sets colors if color list is present
			i = -1
			for k in meaningful_responses: meaningful_responses[k] = (*meaningful_responses[k][:2], params["color_list"][i:=i+1]) # sets color data
		None
	None

	## Creates our plot

	total = sum(responses.values())
	has_legend = False

	fig, ax = plt.subplots(figsize=params["aspectratio"], dpi=params["dpi"]) 
	
	for key, (count, value, color) in meaningful_responses.items(): 

		args = { 
			'y': textwrap.fill(f"{key:>20}", width=20, break_long_words=True, break_on_hyphens=True, ), # tries to keep constant width so graph doesn't expand and shrink
			'width': count, 
			'edgecolor': 
			params['edgecolor'] 
		}
		if color is not None: args['color'] = color
		if key != value: has_legend = True; args['label'] = f'{key} -> {value}' # only adds to the legend if value was given
		bar = ax.barh(**args)

		# formatter function to be passed into bar_label, this is the text at the end of the bar showing the response count and percentage.  Trys to pad and center them.
		def fmt(count:float) -> str:
			number = f"{int(count):,d}" 
			percentage = f"{100*count/total if total > 0 else 0:.1f}%"
			length = a if (a:=len(number)) > (b:=len(percentage)) else b
			return f" {percentage.center(length)}\n {number.center(length)}"
		None
		ax.bar_label(bar, fontsize=params['fontsize'], color=params['txtcolor'], fmt=fmt) # right hand count and percentage label
	None

	fig.patch.set_facecolor(params['bgcolor']); fig.patch.set_alpha(params['bgalpha']); fig.patch.set_edgecolor(params['edgecolor']) # sets the background color and edges
	ax.patch.set_alpha(0.0) # we only use the figure for bg color and hide the subplot
	ax.tick_params(axis='y', color=params['edgecolor'], labelcolor=params['txtcolor'], labelsize=params['fontsize']) # sets the tick marks and their text labels
	ax.spines['left'].set_color(params['edgecolor']) # sets the y axis color 
	ax.get_xaxis().set_visible(False); ax.spines['bottom'].set_visible(False); ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False) # hides all other axes

	# uses fig.legend if sorted, ensuring it goes as far in the bottom right corner as possible, otherwise has ax.legend try and find the place with the least overlap
	if has_legend: (fig if params["sort_responses"] else ax).legend(loc=('lower right' if params["sort_responses"] else 'best'), fontsize=params['legfontsize'], framealpha=params['legbgalpha'], labelcolor=params['legtxtcolor'], facecolor=params['legbgcolor'], edgecolor=params['legedgecolor'])
	
	# we save and return the png as a series of bytes in memory
	buf = io.BytesIO() 
	fig.savefig(buf, format='png', bbox_inches='tight')
	plt.close(fig)
	buf.seek(0)
	return buf.getvalue()
None


### This is the main process loop of the websocket
async def handler(websocket):
	async for message in websocket:
		async with poll_lock: 
			params = parse_request_parameters(message) # the url params passed by control-pannel.html to run-poll.html are then sent into the websocket, which are recieved and converted into a dictionary here
			
			# sets the next continuation token for the next request
			try: payload = initialize_stream(params["streamid"])
			except KeyError: print("stream not currently active"); continue

			responses = {} # tracks the response counts
			responses_helper = {} # tracks the author data for the responses

			for i in range(int((1000/params["frametime"])*params["duration"])):
				if share.buf[1] == 1: break # end poll state

				iterate_request(payload, responses, responses_helper, params) # gets next request

				buf = bytearray(plot_iteration(responses, params)) # this is our png
				if len(buf) > 10000000-8: raise IndexError("buffer could not fit image") # makes sure we don't overflow our buffer
				share.buf[2:10] = bytearray(len(buf).to_bytes(8, byteorder='big')) # writes the local buffer size to the shared buffer
				share.buf[10:len(buf)+10] = buf # writes the local buffer to the shared memory buffer
				share.buf[0] = 1 # sets the ready for read state on the shared memory buffer
				while share.buf[0] != 0: continue # waits for the read finish state to be set on the shared memory buffer 

				await asyncio.sleep(params["frametime"]/1000) # waits for next frame
			None
		None
	None
	
None

async def main():
	async with websockets.serve(handler, "localhost", 36458) as server: # mounts poll_socket to port 36458
		print("WebSocket server started at ws://localhost:36458")
		await asyncio.Future()
	None
None

def poll_socket():
	asyncio.run(main())
None

if __name__ == "__main__":
	asyncio.run(main())
None