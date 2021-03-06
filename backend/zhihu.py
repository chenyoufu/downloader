import re
import uuid
import subprocess
import json
import redis
import threading
import requests
import os
import sys
import hashlib

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import ffmpeg

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

basedir = os.path.abspath(os.path.dirname(__file__))


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/66.0.3359.181 Safari/537.36',
}
# 支持是 'ld' 'sd' 'hd' 分别是低清、中清、高清
QUALITY = 'ld'


def get_video_ids_from_url(url):
    """
    回答或者文章的 url
    """
    r = requests.get(url, headers=HEADERS)
    r.encoding='utf-8'
    html = r.text
    # print(html)
    video_ids = re.findall(r'data-lens-id="(\d+)"', html)
    print("video_ids: ", video_ids)
    if video_ids:
        return set([int(video_id) for video_id in video_ids])
    return []


def yield_video_m3u8_url_from_video_ids(video_ids):
    for video_id in video_ids:
        headers = {}
        headers['Referer'] = 'https://v.vzuu.com/video/{}'.format(video_id)
        headers['Origin'] = 'https://v.vzuu.com'
        headers['Host'] = 'lens.zhihu.com'
        headers['Content-Type'] = 'application/json'
        headers['Authorization'] = 'oauth c3cef7c66a1843f8b3a9e6a1e3160e20'

        api_video_url = 'https://lens.zhihu.com/api/videos/{}'.format(int(video_id))

        r = requests.get(api_video_url, headers={**HEADERS, **headers})
        # print(json.dumps(dict(r.request.headers), indent=2, ensure_ascii=False))
        # print(r.text.encode('utf-8').decode('unicode_escape'))
        playlist = r.json()['playlist']
        m3u8_url = playlist[QUALITY]['play_url']
        yield video_id, m3u8_url


def progress(m3u8_url, directory, filename):
    # '/path/to/dist/static/video/zhihu/xxx-yyy.mp4'
    prefix = directory + '/dist/'
    key = hashlib.md5(filename.encode('utf-8')).hexdigest()
    cmd = "ffmpeg -v quiet -progress /dev/stdout -i '{input}' {output}".format(input=m3u8_url, output=prefix+filename)
    # cmd = "cat xxx.txt"
    print(cmd)
    child1 = subprocess.Popen(cmd, cwd=basedir, shell=True, stdout=subprocess.PIPE)
    # https://stackoverflow.com/questions/7161821/how-to-grep-a-continuous-stream
    cmd2 = "grep --line-buffered -e out_time_ms -e progress"
    child2 = subprocess.Popen(cmd2, shell=True, stdin=child1.stdout, stdout=subprocess.PIPE)
    for line in iter(child2.stdout.readline, b''):
        tmp = line.decode('utf-8').strip().split('=')
        
        if tmp[0] == 'out_time_ms':
            out_time_ms = tmp[1]
            # print(out_time_ms)
            r.set(key, out_time_ms)
        else:
            if tmp[1] == 'end':
                r.delete(key)
                print("download complete")


def download(url, directory):
    video_ids = get_video_ids_from_url(url)
    m3u8_tuples = list(yield_video_m3u8_url_from_video_ids(video_ids))
    rets = []

    for idx, m3u8_url in m3u8_tuples:
        filename = 'static/video/zhihu/{}.mp4'.format(uuid.uuid4())
        print('download {}'.format(m3u8_url))
        duration = ffmpeg.duration_seconds(m3u8_url)
        threading.Thread(target=progress, args=(m3u8_url, directory, filename,)).start()
        # ret_code = subprocess.check_call(['ffmpeg', '-v', 'quiet', '-progress', '/dev/stdout', '-i', m3u8_url, prefix+filename])
        if duration != 0:
            ret = {
                'status': 'success',
                'video': filename,
                'duration': duration,
                "message": "正在下载"
            }
        else:
            ret = {
                'status': 'error',
                'duration': 0,
                "message": "下载失败，请稍后再试"
            }
        rets.append(ret.copy())
    else:
        return rets


if __name__ == '__main__':
    # 贴上你需要下载的 回答或者文章的链接
    seed = 'https://www.zhihu.com/question/277411517/answer/394112534'
    download(seed, '..')
