# Licence GPL V2

# STANDARD PYTHON LIBRARIES
import json

# PIP LIBRARIES
import requests

# LIBRARY INIT
header = {
	"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-", 
	"Accept-Encoding": "gzip",
	"Accept-Language": "en-US,en;q=0.9",
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" # fairly sure this can be anything
}

# CORE

### internal used by initialize stream
### some of these are probably unnecessary but I haven't tested which
### @param payload the paylaod to update
### @return nothing, alters payload
def update_payload(payload):
	payload["client"].update({
		"screenWidthPoints": 425,
		"screenHeightPoints": 594,
		"screenPixelDensity": 1,
		"screenDensityFloat": 1,
		"utcOffsetMinutes": -240,
		"userInterfaceTheme": "USER_INTERFACE_THEME_LIGHT",
		"connectionType": "CONN_CELLULAR_4G", # not sure why it's marked as cellular, I copied this from the browser.  Maybe I copied this from holodex and they are the ones marking as cellular? 
		"memoryTotalKbytes": "8000000",
		"mainAppWebInfo": {
			"graftUrl": payload["client"]["originalUrl"], # <- this is the really important part
			"webDisplayMode": "WEB_DISPLAY_MODE_BROWSER",
			"isWebNativeShareAvailable": True
		}
	})
	payload.update({
		"user": { 
			"lockedSafetyMode": False 
		},
		"request": {
			"useSsl": True,
			"internalExperimentFlags": [],
			"consistencyTokenJars": []
		}
	})
None




### Initializes the live stream chat
### @params the youtube video id of the livestream
### @returns the payload to post to {https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?prettyPrint=false} to get the subsequent live chat data packets
### @throws KeyError if the stream is not active
def initialize_stream(stream_id):
	stream_request = requests.get("https://www.youtube.com/watch", params={ "v": stream_id }, headers=header) #! Our initial request for the stream, this is the user facing livestream url

	html = stream_request.text 
#	print(html, file=open("stream_request.dump.html", 'w'))

	# pulls the continuation token out of the (very long) html response
	chaturl = html.rfind('"continuation":"')
	chaturl = html.rfind('"continuation":"', 0, chaturl-1)
	chaturl = html.rfind('"continuation":"', 0, chaturl-1) +16
	chaturl = html[chaturl:html.find('"', chaturl)]
	chaturl = f"https://www.youtube.com/live_chat?continuation={chaturl}&authuser=0" # this is the internal url to pull in the live chat data when you open a livestream.  If you directly connect to this link you can actually get the live chat on it's own browser page.

	r = requests.get(chaturl, params={ "v": stream_id }, headers=header) # we pull the initial live chat data
#	print(html, file=open("chat_initialization_request.dump.html", 'w'))

	# digs out the initial payload
	html = r.text
	html_index = html.find('"INNERTUBE_CONTEXT":') + 20
	payload = html[html_index:html.find(',"user":', html_index)] # this is json
	payload = json.loads("%s}" % payload) 

	html_index = html.find('window["ytInitialData"] = ', html_index) + 26
	live_chat_response = html[html_index:html.find(';</script>', html_index)] # this is json

	update_payload(payload)
	payload = {
		"context": payload, # <-- make note
		"continuation": json.loads(live_chat_response)["contents"]["liveChatRenderer"]["continuations"][0]["invalidationContinuationData"]["continuation"],
		"webClientInfo": { "isDocumentHidden": False },
		"isInvalidationTimeoutRequest": "true"
	}	

	return payload
None



### sends the next request to a connected chat
### @param payload the output of initialize_stream
### @param responses where we track the messages sent
### @param responses_helper where we track the user data associated with the messages sent
### @param params the params passed from control-pannel.html
def iterate_request(payload, responses, responses_helper, params):
	r = requests.post("https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?prettyPrint=false", json=payload, headers=header) # this is the url that gets posted too to get updated chat data.  Returns json describing all chat messages since last request.

	try: payload["continuation"] = r.json()["continuationContents"]["liveChatContinuation"]["continuations"][0]["invalidationContinuationData"]["continuation"] # pulls out the continuation data for the next packet.
	except KeyError as e: 
		print("request failed with packet:")
		json.dumps(r.json(), ensure_ascii=False, indent=4) # if you don't check ensure_ascii the program will have an anneurism when hit by foreign languages (like JP)
		raise KeyError("Failure connecting to YouTube, try restarting the poll.")
	None
	
	messages = r.json()["continuationContents"]["liveChatContinuation"].get("actions") # this is the part of the returned json that actually stores the messages
	if messages is None: return # no messages since last ping
#	json.dump(r.json(), fp=open("continuation_request.dump.json",'w'), indent=4, ensure_ascii=False)
	for message in messages: parse_message(message, responses, responses_helper, params) # updates responses with messages.  TODO: thread this, it's likely bottlenecking on large streamers
None


### Parses a message into responses and responses_helper
### @params message the message being parsed
### @params responses the response dict being written too
### @params responses_helper the response helper dict being written too
### @param params the params passed from control-pannel.html
### @return nothing, modifies responses and responses_helper
def parse_message(message:dict, responses:dict[str, int], responses_helper:dict[str, list[str]], params:dict):
	try: # if anything goes worng it will just continue to the next message, this likely *will* happen with things like supas and memberships
		# gets the meaningful data out of the message packet
		message_data = message["addChatItemAction"]["item"]["liveChatTextMessageRenderer"]
		message_text = message_data["message"]["runs"][0]["text"]

		if params['prefix'] is not None: # if a prefix was given, we ignore any messages that do not start with it
			if message_text[:len(params['prefix'])] != params['prefix']: return
			message_text = message_text[len(params['prefix']):]
		None

		if params['ignore_case']: message_text = message_text.casefold() # removes case if needed
		
		if params['target_responses'] is not None and message_text not in params['target_responses'].keys(): return # if we were given target responses to track, we ignore any that aren't one of the targets

		# pulls the author and performs necessary checks
		message_author = message_data["authorName"]["simpleText"] 
		if (auth_msgs:= responses_helper.get(message_author)) is not None: # we check that the author has sent messages already
			if message_text in auth_msgs: # we check if the message currently sent has already been sent before
				if params["allow_duplicate_responses"]: responses[message_text] += 1 # adds one to the response counter if we are allowing duplicates
				return
			elif not params["allow_multiple_responses"]: # if we are allowing multiple responses we can just continue and add the new response
				if not params["allow_changed_responses"] or params["allow_duplicate_responses"]: return # if we are not allowing multiple responses, and we are allowing duplicate responses or not allowing changed responses, then their is nothing more to do
				msg = auth_msgs.pop(0) # if we are allowing changed responses, remove the old responses
				responses[msg] -= 1 # subtract one from the response counter
				if responses[msg] == 0: responses.pop(msg) # if the response is now 0, we remove it from the response pool (this prevents it from showing up in the graph as 0)
			None
		else: responses_helper[message_author] = [] # intializes the author if this is their first response

		responses_helper[message_author].append(message_text) # adds the message to the author's data
		if responses.get(message_text) is None: responses[message_text] = 0 # intializes the response
		responses[message_text] += 1 # adds one tally to the response data
	except Exception as e: return
None

