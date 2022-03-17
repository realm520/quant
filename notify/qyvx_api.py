import time
import ujson
import requests

class QYVXAPI(object):
    def __init__(self, agentId, corpId, secret) -> None:
        self.agentId = agentId
        self.corpId = corpId
        self.secret = secret
        self.statFile = 'stat.json'
        self.load_config()

    def load_config(self):
        with open(self.statFile, 'r') as f:
            self.stat = ujson.load(f)

    def _refresh_access_token(self):
        now = int(time.time())
        if now - self.stat['accessToken'][1] < 90*60:
            return
        params = {
            "corpid": self.corpId,
            "corpsecret": self.secret
        }
        response = requests.get(f"https://qyapi.weixin.qq.com/cgi-bin/gettoken", params=params)
        data = ujson.loads(response.text)
        print(response.text)
        self.stat['accessToken'] = [data['access_token'], int(time.time())]
        with open(self.statFile, 'w') as f:
            ujson.dump(self.stat, f, indent=2)

    def push_message_QiYeVX(self, _message, userIdList=['ZhangZhenTao']):
        self._refresh_access_token()
        userIdStr = '|'.join(userIdList)
        msgData = {
            "touser" : userIdStr,
            # "toparty" : "PartyID1|PartyID2",
            # "totag" : "TagID1 | TagID2",
            "msgtype" : "text",
            "agentid" : self.agentId,
            "text" : {
                "content" : _message
            },
            "safe":0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 0,
            "duplicate_check_interval": 1800
        }
        params = {
            "access_token": self.stat['accessToken'][0]
        }
        response = requests.request('POST', f"https://qyapi.weixin.qq.com/cgi-bin/message/send", params=params, json=msgData)
        print(response.text)
        return ujson.loads(response.text)['errmsg'] == 'ok'
