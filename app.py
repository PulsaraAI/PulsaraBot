from flask import Flask, request, jsonify
import telnyx
import os
import tempfile
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.INFO)

# Telnyx API Key
telnyx.api_key = os.getenv('TELNYX_API_KEY')

# Azure Speech Services Config
speech_config = speechsdk.SpeechConfig(subscription=os.getenv('AZURE_SPEECH_KEY'), region=os.getenv('AZURE_SERVICE_REGION'))

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
            telnyx.CallControl(call_control_id).play_audio(
                audio_url='https://your-audio-file-url.wav'
            )

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

def cli_call_and_speak(phone_number, message):
    try:
        gpt_response = message  # Here you would call your GPT-3 API to generate the response
        response_audio_path = text_to_speech(gpt_response)

        # Initiate the call using Telnyx
        call = telnyx.Call.create(
            connection_id=os.getenv('TELNYX_CONNECTION_ID'),
            to=phone_number,
            from_=os.getenv('TELNYX_PHONE_NUMBER')
        )

        # Save the audio file path to be used in the webhook handler
        with open("current_audio_path.txt", "w") as f:
            f.write(response_audio_path)

        logging.info(f"Call initiated with ID: {call.id}")
        print(f"Call initiated with ID: {call.id}")
        print(f"GPT-3 Response: {gpt_response}")
    
    except Exception as e:
        logging.error(f"Error in CLI call: {e}")
        print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CLI for initiating calls and sending messages")
    parser.add_argument("--phone_number", type=str, help="The phone number to call")
    parser.add_argument("--message", type=str, help="The message to send")

    args = parser.parse_args()
    
    if args.phone_number and args.message:
        cli_call_and_speak(args.phone_number, args.message)
    else:
        app.run(host="0.0.0.0", port=5000)
