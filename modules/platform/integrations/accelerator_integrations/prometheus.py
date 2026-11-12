"""Bounded Prometheus HTTP queries; no vendor metric names or identity rules."""
import base64, json, math, threading, time
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

class PrometheusClient:
    def __init__(self, url, auth_file=None, max_points=12000):
        if urlsplit(url).scheme not in ('http','https') or urlsplit(url).username:
            raise ValueError('数据源URL需要HTTP(S)，凭据请使用独立认证文件')
        self.url=url; self.auth_file=auth_file; self.max_points=max_points
        self.opener=build_opener(ProxyHandler({})); self.semaphore=threading.BoundedSemaphore(2)
        self.stats={'queries':0,'failures':0,'last_success':None,'last_error':None,'duration':0}

    def query(self,expression,start=None,end=None,step=2):
        if start is None: path='/api/v1/query'; params={'query':expression,'timeout':'5s'}
        else:
            if end-start>86400*31 or (end-start)/step>self.max_points: raise ValueError('查询窗口或点数超过配额')
            path='/api/v1/query_range';params={'query':expression,'start':start,'end':end,'step':step,'timeout':'5s'}
        began=time.monotonic()
        if not self.semaphore.acquire(timeout=2): raise RuntimeError('数据源查询并发配额已满')
        try:
            headers={}
            auth_path=self.auth_file
            auth=json.loads(Path(auth_path).read_text()) if auth_path else {}
            if auth and auth.get('type') not in ('bearer','basic'):raise ValueError('数据源认证类型无效')
            if auth.get('type')=='bearer':headers['Authorization']='Bearer '+auth['token']
            elif auth.get('type')=='basic':
                headers['Authorization']='Basic '+base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
            request=Request(self.url+path+'?'+urlencode(params),headers=headers)
            with self.opener.open(request,timeout=7) as response:
                body=response.read(24*1024*1024+1)
            if len(body)>24*1024*1024:raise ValueError('数据源响应超过配额')
            payload=json.loads(body)
            if payload.get('status')!='success' or payload.get('warnings'):raise ValueError('数据源查询失败或返回不完整结果')
            rows=payload['data']['result']
            if len(rows)>5000: raise ValueError('返回序列超过配额')
            self.stats.update(last_success=time.time(),last_error=None)
            return rows
        except Exception as exc:
            self.stats['failures']+=1;self.stats['last_error']=type(exc).__name__
            raise
        finally:
            self.stats['queries']+=1;self.stats['duration']=round(time.monotonic()-began,4);self.semaphore.release()

