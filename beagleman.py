import alsaaudio
import json
import os.path
import os
import pycurl
import requests
import re
import sys
import time

from creds import *
from hdc1000 import getTemperature
from pocketsphinx.pocketsphinx import *
from requests.packages.urllib3.exceptions import *
from sphinxbase.sphinxbase import *
from StringIO import StringIO
from threading import Thread

# Avoid warning about insure request
requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

# ------ Start User configuration settings --------
sphinx_data_path = "/root/pocketsphinx/"
modeldir = sphinx_data_path+"/model/"
datadir = sphinx_data_path+"/test/data"

recording_file_path = "/root/beagleman/"
filename=recording_file_path+"/myfile.wav"
filename_raw=recording_file_path+"/myfile.pcm"

# Personalize the robot :)
username = "Franklin"

# Trigger phrase. Pick a phrase that is easy to save repeatedly the SAME way
# seems by default a single syllable word is better
trigger_phrase = "dog"

wit_token = "<Wit AI Token>"

# ----- End User Configuration -----

wit_ai_authorization = "Authorization: Bearer "+wit_token

# PocketSphinx configuration
config = Decoder.default_config()

# Set recognition model to US
config.set_string('-hmm', os.path.join(modeldir, 'en-us/en-us'))
config.set_string('-dict', os.path.join(modeldir, 'en-us/cmudict-en-us.dict'))

#Specify recognition key phrase
config.set_string('-keyphrase', trigger_phrase)
config.set_float('-kws_threshold',3)

# Hide the VERY verbose logging information
config.set_string('-logfn', '/dev/null')

path = os.path.realpath(__file__).rstrip(os.path.basename(__file__))

# Read microphone at 16 kHz. Data is signed 16 bit little endian format.
inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE)
inp.setchannels(1)
inp.setrate(16000)
inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
inp.setperiodsize(1024)

token = None
recording_file = None

start = time.time()

# Determine if trigger word/phrase has been detected
record_audio = False
wit_ai_received = False

# Process audio chunk by chunk. On keyword detected perform action and restart search
decoder = Decoder(config)
decoder.start_utt()

# Using slightly outdated urlib3 software by default. But disable harmless warning
requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)

# All Alexa code based on awesome code from AlexaPi
# https://github.com/sammachin/AlexaPi

# Verify that the user is connected to the internet
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
        # Set parameters to Alexa request for our audio recording
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

        # Send our recording audio to Alexa
	with open(filename_raw) as inf:
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

                # Write response audio to response.mp3 may or may not be played later
		with open(path+"response.mp3", 'wb') as f:
			f.write(audio)
	else:
		print "Debug: Alexa threw an error with code: ",r.status_code

def offline_speak(string):
	os.system('espeak -ven-uk -p50 -s140 "'+string+'" > /dev/null 2>&1')


# Code based on examples from Facebook's wit.ai
# https://wit.ai/docs/http/20141022
def handle_intent(response):
    intent = response[0]["intent"]

    if intent == "alarm":
        offline_speak("Your alarm has been set")
        return True

    elif intent == "seeedstudio":
        offline_speak("Seeed Studio is located in Shenzhen, China")
        return True

    elif intent == "temperature":
        offline_speak("Measuring room temperature")
        temp = getTemperature()
        temp = "{0:.2f}".format(temp)
        offline_speak("The current room temperature is "+temp+" degrees fahrenheit")
        return True

    return False

def wit_ai():
	global wit_ai_received

        #Make an HTTP request via python curl using our saved audio recording
        #Api document https://wit.ai/docs/http/20141022
	output = StringIO()
	c = pycurl.Curl()

	c.setopt(c.URL, 'https://api.wit.ai/speech?v=20141022')

        # Send authorization string along with indicate that we are sending audio
	c.setopt(c.HTTPHEADER, [wit_ai_authorization,
						'Content-Type: audio/wav'])
	c.setopt(c.FOLLOWLOCATION, True)

        # Specify that we are doing a POST request
	c.setopt(pycurl.POST, 1)

        # Get size of our audio file
	filesize = os.path.getsize(filename)
	c.setopt(c.POSTFIELDSIZE, filesize)

        # Pass a function that will read the audio file
	fin = open(filename, 'rb')
	c.setopt(c.READFUNCTION, fin.read)

	c.setopt(c.WRITEFUNCTION, output.write)

        # Ignore SSL verification
	c.setopt(pycurl.SSL_VERIFYPEER, 0)   
	c.setopt(pycurl.SSL_VERIFYHOST, 0)

        # Send our Web Service request
	c.perform()

	c.close()

        # Get our response
	response =  json.loads(output.getvalue())

	wit_ai_received = False
   
        # Check if we got an error
	if 'error' not in response.keys():
                print "Debug: Wit.ai believe the audio said: ", response["_text"]

                # See if our code handles the specified intent
		if response["outcomes"][0]["intent"] == "UNKNOWN" or not handle_intent(response["outcomes"]):
                    print "Debug: Unrecognized Wit.ai intent. Let Alexa handle it"
                else:
			wit_ai_received = True
                        print "Debug: Wit.ai handled response ignore response from Alexa"
        else:
            print "Debug: Wit.ai returned an error"

def web_service():
	global wit_ai_received

	# Call the two speech recognitions services in parallel
	alexa_thread = Thread( target=alexa, args=() )
	wit_ai_thread = Thread( target=wit_ai, args=( ) )

	alexa_thread.start()
	wit_ai_thread.start()

        # Prioritize a response from Wit.ai
	wit_ai_thread.join()

        # See if Wit.ai code handled response
	if wit_ai_received != True:
                # Wait until Alexa code handles response
		alexa_thread.join()

                # Play Alexa response
		os.system('play  -c 1 -r 24000 -q {}response.mp3  > /dev/null 2>&1'.format(path))
		time.sleep(.5)
		

while internet_on() == False:
	print "."

offline_speak("Hello "+username+", Ask me any question")

print "Debug: Ready to receive request"
while True:
	try:
		# Read from microphone
		l,buf = inp.read()
	except:
                # Hopefully we read fast enough to avoid overflow errors
		print "Debug: Overflow"
		continue

        #Process microphone audio via PocketSphinx only when trigger word
        # hasn't been detected
	if buf and record_audio == False:
		decoder.process_raw(buf, False, False)

	# Detect if keyword/trigger word was said
	if record_audio == False and decoder.hyp() != None:
                # Trigger phrase has been detected
		record_audio = True
		start = time.time()

                # To avoid overflows close the microphone connection
		inp.close()

                # Open file that will be used to save raw micrphone recording
		recording_file = open(filename_raw, 'w')
		recording_file.truncate()

                # Indicate that the system is listening to request
                offline_speak("Yes")

                # Reenable reading microphone raw data
		inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE)
		inp.setchannels(1)
		inp.setrate(16000)
		inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
		inp.setperiodsize(1024)

		print ("Debug: Start recording")


	# Only write if we are recording
	if record_audio == True:
		recording_file.write(buf)

	# Stop recording after 5 seconds
	if record_audio == True and time.time() - start > 5:
		print ("Debug: End recording")
		record_audio = False

		# Close file we are saving microphone data to
		recording_file.close()

		# Convert raw PCM to wav file (includes audio headers)
		os.system("sox -t raw -r 16000 -e signed -b 16 -c 1 "+filename_raw+" "+filename+" && sync");

		print "Debug: Sending audio to services to be processed"
		# Send recording to our speech recognition web services
		web_service()

		# Now that request is handled restart audio decoding
		decoder.end_utt()
		decoder.start_utt()
