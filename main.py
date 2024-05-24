import os
import sys
import time
import ctypes
import requests
import threading
import keyboard
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
from pyngrok import ngrok, conf
from pytube import YouTube
from flask import Flask, request, jsonify, Response
from flask_cors import CORS


load_dotenv()

video_queue = []
switcher = False
is_currently_played = False
port = 11097
access_token = os.environ.get("CHANNEL_ACCESS_TOKEN")
client_access_token = os.environ.get("CLIENT_ACCESS_TOKEN")
client_id = os.environ.get("CLIENT_ID")
secret = os.environ.get("SECRET")
url = "https://api.twitch.tv/helix/eventsub/subscriptions"
headers = {
    "Client-id": client_id,
    "Authorization": f'Bearer {client_access_token}',
    'Content-Type': 'application/json'
}

json_data = {
    "type": "channel.channel_points_custom_reward_redemption.add",
    "version": "1",
    "condition": {
    "broadcaster_user_id": os.environ.get("BROADCASTER_USER_ID"),
    "reward_id": os.environ.get("REWARD_ID")
    },
    "transport": {
    "method": "webhook",
    "callback": "https://yourcallbackurl.com/path",
    "secret": secret
    }
}

def run_ngrok(): #ngrok для создания туннеля на наш айпишник
    """
    A function to run ngrok tunnel
    """
    conf.get_default().config_path = "ngrok/ngrok.yml"
    ngrok.set_auth_token(os.environ.get("NGROK_AUTH_TOKEN"))

    ngrok_tunnel = ngrok.connect(port)
    public_url = ngrok_tunnel.public_url
    json_data['transport']['callback'] = f"{public_url}/webhook"
    print(f"ngrok tunnel {public_url} -> http://127.0.0.1:{port}")
    while True:
        time.sleep(10)

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def clear_previous_subs():
    url = "https://api.twitch.tv/helix/eventsub/subscriptions"
    get_subs = requests.get(url, headers={"Authorization": f"Bearer {client_access_token}",
                                        "Client-Id": client_id}).json()
    print(get_subs)
    for i in get_subs['data']:
        print(requests.delete(f'https://api.twitch.tv/helix/eventsub/subscriptions?id={i['id']}', headers={"Authorization": f"Bearer {client_access_token}",
                                        "Client-Id": client_id}))

def get_video_id(value):
    query = urlparse(value)
    if query.hostname == 'youtu.be':
        return query.path[1:]
    if query.hostname in ('www.youtube.com', 'youtube.com'):
        if query.path == '/watch':
            p = parse_qs(query.query)
            return p['v'][0]
        if query.path[:7] == '/embed/':
            return query.path.split('/')[2]
        if query.path[:3] == '/v/':
            return query.path.split('/')[2]
    return None

def get_video_length(video_url):
    video_id = get_video_id(video_url)
    if video_id:
        video_url = f"www.youtube.com/watch?v={video_id}"
        yt = YouTube(video_url)
        duration = yt.length
        print(f"Длительность видео: {duration} секунд")
        return duration
    
    else:
        return None

def send_play_pause():
    keyboard.send('play/pause')
    print("Команда play/pause отправлена")

def send_play_pause_timer():
    global switcher
    global is_currently_played
    keyboard.send('play/pause')
    print("Команда play/pause отправлена")
    switcher = False
    is_currently_played = False

def skip_song_from_queue():
    global queue_thread
    global switcher
    global timer
    print(switcher)
    print(timer.is_alive())
    if timer.is_alive():
        switcher = False
        cancel_timer()
        send_play_pause()
        is_currently_played = False
    else:
        pass
    print('Песня была пропущена')

def start_timer(timer):
    global start_timer_time
    if not timer.is_alive():
        timer.start()
        print("Таймер запущен")
        start_timer_time = time.time()

def cancel_timer():
    global timer
    global is_currently_played
    if timer.is_alive():
        timer.cancel()
        print("Таймер отменён")

def queue_manager() -> None:
    global video_queue
    global switcher
    global timer
    global is_currently_played
    global start_timer_time
    global end_timer_time
    print("Поток queue_manager был запушен")
    timer = threading.Timer(1, send_play_pause_timer)
    while True:
        if video_queue and switcher == False:
            switcher = True
            time_to_sleep = video_queue[0]+0.5
            if not is_currently_played:
                send_play_pause()
                is_currently_played = True
                print("Воспроизведение было приостановлено")
            else:
                end_timer_time = time.time()
                time_to_sleep = (timer.interval-(end_timer_time - start_timer_time))+time_to_sleep
            video_queue.pop(0)
            timer = threading.Timer(time_to_sleep, send_play_pause_timer)
            start_timer(timer)
        else:
            if not timer.is_alive():
                switcher = False
        time.sleep(0.5)


app = Flask(__name__)
CORS(app)
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Request from Twitch: ", data)
    global video_queue
    global timer
    global is_currently_played

    if data['subscription']['status'] == 'webhook_callback_verification_pending':
        challenge = data['challenge']
        # Отправляем challenge обратно, как требует Twitch
        print('challenge')
        return Response(challenge, mimetype="text/plain", status=200)

    else:
        song_request_url = data['event']['user_input']
        duration = get_video_length(song_request_url)
        if duration:
            if timer.is_alive():
                cancel_timer()
            video_queue.append(duration)
        else:
            print("Ссылка не ведет на действительное Youtube видео")
            pass
    return 'Success', 200

@app.route('/trigger', methods=['GET'])
def trigger_post_request():
    req = requests.post(url, headers=headers, json=json_data)
    return jsonify({"status": req.status_code, "data": req.json()})

# что-бы скрипт не закрылся мгновенно
os.system("pause")

if __name__=='__main__':
    if is_admin():
        pass
    else:
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, __file__, None, 1
        )
        exit()
    clear_previous_subs()
    ngrok_thread = threading.Thread(target=run_ngrok)
    ngrok_thread.start()
    queue_thread = threading.Thread(target=queue_manager)
    queue_thread.start()
    keyboard.add_hotkey(']', skip_song_from_queue, suppress=True, trigger_on_release=True)
    app.run(port=port, debug=True)