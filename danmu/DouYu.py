import socket, json, re, select, time, websocket, ssl
from struct import pack

import requests

from .Abstract import AbstractDanMuClient

class _socket(websocket.WebSocket):
    def communicate(self, data):
        self.push(data)
        return self.pull()
    def push(self, data):
        s = pack('i', 9 + len(data)) * 2
        s += b'\xb1\x02\x00\x00' # 689
        s += data.encode('ascii') + b'\x00'
        # self.sendall(s)
        self.send(s)
    def pull(self):
        try: # for socket.settimeout
            return self.recv()
        except Exception as e:
            return ''

class DouYuDanMuClient(AbstractDanMuClient):
    def _get_live_status(self):
        url = 'https://m.douyu.com/%s' % (
            self.url.split('/')[-1] or self.url.split('/')[-2])
        r = requests.get(url)
        roomId = re.search(r'"rid":(\d+),', r.content.decode('utf-8'))[1]
        url = 'http://open.douyucdn.cn/api/RoomApi/room/%s' % roomId
        j = requests.get(url).json()
        if j.get('error') != 0 or j['data'].get('room_status') != '1': return False
        self.roomId = j['data']['room_id']
        return True
    def _prepare_env(self):
        return ('openbarrage.douyutv.com', 8601), {'room_id': self.roomId}
    def _init_socket(self, danmu, roomInfo):
        self.danmuSocket = _socket(sslopt={"cert_reqs": ssl.CERT_NONE})
        self.danmuSocket.connect('wss://danmuproxy.douyu.com:8506/')
        self.danmuSocket.settimeout(3)
        self.danmuSocket.communicate('type@=loginreq/roomid@=%s/'%roomInfo['room_id'])
        self.danmuSocket.push('type@=joingroup/rid@=%s/gid@=-9999/'%roomInfo['room_id'])
    def _create_thread_fn(self, roomInfo):
        def keep_alive(self):
            self.danmuSocket.push('type@=keeplive/tick@=%s/'%int(time.time()))
            time.sleep(30)
        def get_danmu(self):
            if not select.select([self.danmuSocket], [], [], 1)[0]: return
            content = self.danmuSocket.pull()
            for msg in re.findall(b'(type@=.*?)\x00', content):
                try:
                    msg = msg.replace(b'@=', b'":"').replace(b'/', b'","')
                    msg = msg.replace(b'@A', b'@').replace(b'@S', b'/')
                    msg = json.loads((b'{"' + msg[:-2] + b'}').decode('utf8', 'ignore'))
                    msg['NickName'] = msg.get('nn', '')
                    msg['Content']  = msg.get('txt', '')
                    msg['MsgType']  = {'dgb': 'gift', 'chatmsg': 'danmu',
                        'uenter': 'enter'}.get(msg['type'], 'other')
                except Exception as e:
                    pass
                else:
                    self.danmuWaitTime = time.time() + self.maxNoDanMuWait
                    self.msgPipe.append(msg)

        return get_danmu, keep_alive # danmu, heart
