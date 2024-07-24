from flask import Flask, request, render_template, jsonify
from flask_socketio import SocketIO, emit
import telnyx
import os
import tempfile
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
import logging
import openai

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Set up logging
logging.basicConfig(level=logging.INFO)

# Telnyx API Key
telnyx.api_key = os.getenv('TELNYX_API_KEY')

# Azure Speech Services Config
speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SERVICE_REGION'))

# OpenAI API Key
openai.api_key = os.getenv('OPENAI_API_KEY')

def text_to_speech(text):
    """Convert text to speech and return the audio file path."""
    temp_audio_output = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
    audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_audio_output.name)
    speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    result = speech_synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        logging.info("Speech synthesized to [{}]".format(temp_audio_output.name))
    else:
        logging.error("Speech synthesis failed: {}".format(result.reason))
        raise Exception("Speech synthesis failed")

    return temp_audio_output.name

def speech_to_text(audio_file_path):
    """Convert speech to text from an audio file."""
    audio_input = speechsdk.audio.AudioConfig(filename=audio_file_path)
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)
    result = speech_recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text
    else:
        logging.error("Speech recognition failed: {}".format(result.reason))
        raise Exception("Speech recognition failed")

def generate_response(prompt):
    """Generate response using OpenAI's GPT."""
    response = openai.Completion.create(
        engine="gpt-4",
        prompt=prompt,
        max_tokens=150
    )
    return response.choices[0].text.strip()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/initiate_call", methods=["POST"])
def initiate_call():
    try:
        data = request.get_json()
        target_phone_number = data['phone_number']
        message = data['message']

        # Create the call
        call = telnyx.Call.create(
            connection_id=os.getenv('TELNYX_CONNECTION_ID'),
            to=target_phone_number,
            from_=os.getenv('TELNYX_PHONE_NUMBER')
        )

        # Save the call ID to play audio later
        call_id = call.id

        # Convert message to speech
        audio_path = text_to_speech(message)

        # Save the audio file path to be used in the webhook handler
        with open("current_audio_path.txt", "w") as f:
            f.write(audio_path)

        logging.info(f"Call initiated with ID: {call_id}")
        return jsonify({"call_id": call_id})

    except Exception as e:
        logging.error(f"Error initiating call: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.json
        logging.info(f"Received webhook: {data}")
        event = data['data']['event_type']
        call_control_id = data['data']['payload']['call_control_id']

        if event == "call.initiated":
            # Answer the call
            telnyx.CallControl(call_control_id).answer()
            logging.info(f"Call answered with ID: {call_control_id}")

            # Send an initial message
            initial_message = "Hello, welcome to the bot. How can I assist you today?"
            audio_path = text_to_speech(initial_message)
            telnyx.CallControl(call_control_id).play_audio(audio_url=f"http://your-azure-web-app-url/static/{os.path.basename(audio_path)}")

        elif event == "call.answered":
            # Handle when the call is answered
            logging.info(f"Call answered with ID: {call_control_id}")

        elif event == "call.hangup":
            # Handle call hangup
            logging.info(f"Call hung up with ID: {call_control_id}")

        return '', 204

    except Exception as e:
        logging.error(f"Error handling webhook: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/generate_gpt_response", methods=["POST"])
def generate_gpt_response():
    try:
        data = request.get_json()
        prompt = data['prompt']
        
        response_text = generate_response(prompt)
        
        return jsonify({"response": response_text})

    except Exception as e:
        logging.error(f"Error generating GPT response: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
