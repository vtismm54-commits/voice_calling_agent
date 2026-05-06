import webbrowser
import urllib.parse

def open_whatsapp_web(mobile):

    if not mobile:
        return

    message = (
        "Here are our Voice Over & Green Screen samples:\n\n"
        "Voice Over Sample: https://your-voice-link\n"
        "Green Screen Sample: https://your-green-link\n\n"
        "Regards,\nVoice Tunes India"
    )

    encoded_message = urllib.parse.quote(message)

    url = f"https://wa.me/{mobile.replace('+','')}?text={encoded_message}"

    webbrowser.open(url)