import socket, json, re, select, time, random, websocket
from struct import pack, unpack

import requests

from .Abstract import AbstractDanMuClient

class _socket(websocket.WebSocket):
    def push(self, data, type = 7):
        data = (pack('>i', len(data) + 16) + b'\x00\x10\x00\x01' +
            pack('>i', type) + pack('>i', 1) + data)
        self.send(data)
    def pull(self):
        try: # for socket.settimeout
            return self.recv()
        except Exception as e:
            return ''

class BilibiliDanMuClient(AbstractDanMuClient):
    def _get_live_status(self):
        url = 'https://api.live.bilibili.com/room/v1/Room/room_init?id=' + self.url.split('/')[-1]
        r = requests.get(url)
        room_json = json.loads(r.content)
        self.roomId = room_json['data']['room_id']
        return True
    def _prepare_env(self):
        self.content = b''
        r = requests.get('https://api.live.bilibili.com/room/v1/Danmu/getConf?room_id=' + str(self.roomId))
        room_json = json.loads(r.content)
        # print(room_json)
        # self.serverUrl = 'wss://' + room_json['data']['host_server_list'][0]['host'] + '/sub'
        self.serverUrl = 'wss://broadcastlv.chat.bilibili.com/sub'
        return (self.serverUrl, room_json['data']['host_server_list'][0]['wss_port']), {}
    def _init_socket(self, danmu, roomInfo):
        self.danmuSocket = _socket()
        self.danmuSocket.connect(danmu[0])
        self.danmuSocket.settimeout(3)
        self.danmuSocket.push(data = json.dumps({
            'roomid': int(self.roomId),
            'uid': int(1e14 + 2e14 * random.random()),
            'protover': 1
            }, separators=(',', ':')).encode('ascii'))
    def _create_thread_fn(self, roomInfo):
        def keep_alive(self):
            self.danmuSocket.push(b'', 2)
            time.sleep(10)
        def get_danmu(self):
            tmp_content = self.danmuSocket.pull()
            if len(tmp_content) == 0:
                time.sleep(0.3)
                return

            self.content = self.content + tmp_content
            # print(self.content)
            dm_list = []
            ops = []
            while True:
                try:
                    packetLen, headerLen, ver, op, seq = unpack('!IHHII', self.content[0:16])
                except Exception as e:
                    break

                if len(self.content) < packetLen:
                    break
                ops.append(op)
                dm_list.append(self.content[16:packetLen])
                if len(self.content) == packetLen:
                    self.content = b''
                    break
                else:
                    self.content = self.content[packetLen:]
            # print(ops)
            # print(dm_list)
            for i, d in enumerate(dm_list):
                try:
                    msg = {}
                    if ops[i] == 5:
                        j = json.loads(d)
                        msg['NickName'] = (j.get('info', ['','',['', '']])[2][1]
                                           or j.get('data', {}).get('uname', ''))
                        msg['Content']  = j.get('info', ['', ''])[1]
                        msg['MsgType']  = {'SEND_GIFT': 'gift', 'DANMU_MSG': 'danmu',
                                           'WELCOME': 'enter'}.get(j.get('cmd'), 'other')
                    else:
                        # print(ops[i])
                        msg = {'NickName': '', 'Content': '', 'MsgType': 'other'}
                except Exception as e:
                    # print(e)
                    pass
                else:
                    self.danmuWaitTime = time.time() + self.maxNoDanMuWait
                    self.msgPipe.append(msg)



            # for msg in re.findall(b'\x00({[^\x00]*})', content):
            #     try:
            #         msg = json.loads(msg.decode('utf8', 'ignore'))
            #         msg['NickName'] = (msg.get('info', ['','',['', '']])[2][1]
            #             or msg.get('data', {}).get('uname', ''))
            #         msg['Content']  = msg.get('info', ['', ''])[1]
            #         msg['MsgType']  = {'SEND_GIFT': 'gift', 'DANMU_MSG': 'danmu',
            #             'WELCOME': 'enter'}.get(msg.get('cmd'), 'other')
            #     except Exception as e:
            #         pass
            #     else:
            #         self.danmuWaitTime = time.time() + self.maxNoDanMuWait
            #         self.msgPipe.append(msg)

        return get_danmu, keep_alive # danmu, heart
