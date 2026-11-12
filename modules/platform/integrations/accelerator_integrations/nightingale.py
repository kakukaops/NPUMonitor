"""Nightingale HTTP transport; rule ownership stays in device adapters."""
import json
from pathlib import Path
from urllib.request import Request, ProxyHandler, build_opener

class NightingaleClient:
    def __init__(self,url,token_file):
        self.url=url.rstrip('/');self.token_file=token_file
        self.opener=build_opener(ProxyHandler({}))

    def call(self,method,path,body=None):
        token=Path(self.token_file).read_text().strip()
        request=Request(self.url+'/api/n9e'+path,data=None if body is None else json.dumps(body).encode(),method=method,
                        headers={'X-User-Token':token,'Content-Type':'application/json'})
        with self.opener.open(request,timeout=8) as response:payload=json.load(response)
        if isinstance(payload,dict):
            if payload.get('error') or payload.get('err'):raise ValueError('夜莺API拒绝操作')
            return payload.get('dat',payload.get('data',payload))
        return payload

