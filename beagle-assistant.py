import alsaaudio
import json
import os.path
import os
import pycurl
import requests
import re
import sys
import time

from pocketsphinx.pocketsphinx import *
from sphinxbase.sphinxbase import *
from creds import *
from threading import Thread
from requests.packages.urllib3.exceptions import *

requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

modeldir = "/root/pocketsphinx/model/"
datadir = "/root/pocketsphinx/test/data"

filename="/root/tmp/myfile.wav"
filename_raw="/root/tmp/myfile.pcm"

token = "<Wit AI Token>"

authentication_string = "Authorization: Bearer "+token

# Create a decoder with certain model
config = Decoder.default_config()
config.set_string('-hmm', os.path.join(modeldir, 'en-us/en-us'))
config.set_string('-dict', os.path.join(modeldir, 'en-us/cmudict-en-us.dict'))
config.set_string('-keyphrase', 'robot')
config.set_float('-kws_threshold',5)
config.set_string('-logfn', '/dev/null')

path = os.path.realpath(__file__).rstrip(os.path.basename(__file__))

inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE)
inp.setchannels(1)
inp.setrate(16000)
inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
inp.setperiodsize(1024)

token = None
target = None

start = time.time()
said_phrase = False
facebook_received = False

# Process audio chunk by chunk. On keyword detected perform action and restart search
decoder = Decoder(config)
decoder.start_utt()

#requests.packages.urllib3.disable_warnings(SNIMissingWarning)
requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

# Alexa code based on awesome code from AlexaPi
# https://github.com/sammachin/AlexaPi

def internet_on():
	print "Checking Internet Connection"
	try:
		r =requests.get('https://api.amazon.com/auth/o2/token')
	print "Connection OK"
		return True
	except:
		print "Connection Failed"
		return False

#Get Alexa Token
def gettoken():
	global token
	refresh = refresh_token
	if token:
		return token
	elif refresh:
		payload = {"client_id" : Client_ID, "client_secret" : Client_Secret, "refresh_token" : refresh, "grant_type" : "refresh_token", }
		url = "https://api.amazon.com/auth/o2/token"
		r = requests.post(url, data = payload)
		resp = json.loads(r.text)
		token = resp['access_token']
		return token
	else:
		return False
		
def alexa():
	url = 'https://access-alexa-na.amazon.com/v1/avs/speechrecognizer/recognize'
	headers = {'Authorization' : 'Bearer %s' % gettoken()}
	d = {
   		"messageHeader": {
       		"deviceContext": [
           		{
               		"name": "playbackState",
               		"namespace": "AudioPlayer",
               		"payload": {
                   		"streamId": "",
        			   	"offsetInMilliseconds": "0",
                   		"playerActivity": "IDLE"
               		}
           		}
       		]
		},
   		"messageBody": {
       		"profile": "alexa-close-talk",
       		"locale": "en-us",
       		"format": "audio/L16; rate=44100; channels=1"
   		}
	}

	with open(path+"myfile.pcm") as inf:
		files = [
				('file', ('request', json.dumps(d), 'application/json; charset=UTF-8')),
				('file', ('audio', inf, 'audio/L16; rate=44100; channels=1'))
				]	
		r = requests.post(url, headers=headers, files=files)

	if r.status_code == 200:
		print "Debug: Alexa provided a response"

		for v in r.headers['content-type'].split(";"):
			if re.match('.*boundary.*', v):
				boundary =  v.split("=")[1]
		data = r.content.split(boundary)
		for d in data:
			if (len(d) >= 1024):
				audio = d.split('\r\n\r\n')[1].rstrip('--')
		with open(path+"response.mp3", 'wb') as f:
			f.write(audio)
	else:
		print "Debug: Alexa threw an error with code: ",r.status_code

def offline_speak(string):
	os.system('espeak -ven-uk -p50 -s140 "'+string+'" > /dev/null 2>&1')


# Code based on examples from Facebook's wit.ai
# https://wit.ai/docs/http/20141022
def facebook():
	global facebook_received
	output = StringIO()
	c = pycurl.Curl()
	c.setopt(c.URL, 'https://api.wit.ai/speech?v=20141022')
	c.setopt(c.HTTPHEADER, [authentication_string,
						'Content-Type: audio/wav'])
	c.setopt(c.FOLLOWLOCATION, True)
	c.setopt(pycurl.POST, 1)
	filesize = os.path.getsize(filename)
	c.setopt(c.POSTFIELDSIZE, filesize)
	fin = open(filename, 'rb')
	c.setopt(c.READFUNCTION, fin.read)

	c.setopt(c.WRITEFUNCTION, output.write)
	c.setopt(pycurl.SSL_VERIFYPEER, 0)   
	c.setopt(pycurl.SSL_VERIFYHOST, 0)
	c.perform()

	c.close()

	value =  output.getvalue()

	the =  json.loads(value)

	facebook_received = False
    
	if 'error' not in the.keys():
		print the["_text"]
		print the["outcomes"][0]["intent"]

		if the["outcomes"][0]["intent"] != "UNKNOWN":
			offline_speak("Your alarm has been set")
			facebook_received = True


def service():
	global facebook_received

	# Call the two speech recognitions services in parallel
	alexa_thread = Thread( target=alexa, args=() )
	facebook_thread = Thread( target=facebook, args=( ) )

	alexa_thread.start()
	facebook_thread.start()
	facebook_thread.join()

	if facebook_received != True:
		os.system('play  -c 1 -r 24000 -q {}response.mp3  > /dev/null 2>&1'.format(path))
		alexa_thread.join()
		time.sleep(1)
		offline_speak("Hello Franklin, Ask me another question")
		

while internet_on() == False:
	print "."

offline_speak("Hello Franklin, Ask me any question")

while True:
	try:
		# Read from microphone
		l,buf = inp.read()
	except:
		print "Debug: Overflow"
		continue

	if buf and said_phrase == False:
		decoder.process_raw(buf, False, False)

	# Detect if keyword/trigger word was said
	if said_phrase == False and decoder.hyp() != None:
		said_phrase = True
		start = time.time()
		inp.close()

		target = open("myfile.pcm", 'w')
		target.truncate()

		os.system('play  -c 1 -r 24000 -q {}alert.mp3  > /dev/null 2>&1'.format(path))
		inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE)
		inp.setchannels(1)
		inp.setrate(16000)
		inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
		inp.setperiodsize(1024)

		print ("Debug: Start recording")


	# Only write if we are recording
	if said_phrase == True:
		target.write(buf)

	# Stop recording after 5 seconds
	if said_phrase == True and time.time() - start > 5:
		print ("Debug: End recording")
		said_phrase = False

		target.close()
		os.system("sox -t raw -r 16000 -e signed -b 16 -c 1 myfile.pcm myfile.wav && sync");
		service()
		decoder.end_utt()
		decoder.start_utt()
