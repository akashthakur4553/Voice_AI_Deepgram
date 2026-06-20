import os
import sys
from dotenv import load_dotenv
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect

load_dotenv()


def make_call(to_number):
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")
    public_ws_url = os.getenv("PUBLIC_WS_URL")

    for name, value in [
        ("TWILIO_ACCOUNT_SID", account_sid),
        ("TWILIO_AUTH_TOKEN", auth_token),
        ("TWILIO_PHONE_NUMBER", from_number),
        ("PUBLIC_WS_URL", public_ws_url),
    ]:
        if not value:
            raise Exception(f"{name} not found in environment")

    client = Client(account_sid, auth_token)

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=public_ws_url)
    response.append(connect)

    call = client.calls.create(
        to=to_number,
        from_=from_number,
        twiml=str(response),
    )
    print(f"Call started: {call.sid} -> {to_number}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python make_call.py +15551234567")
        sys.exit(1)
    make_call(sys.argv[1])
