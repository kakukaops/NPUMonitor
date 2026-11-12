"""Company-neutral JSON contracts; no sklearn/numpy/platform SDK dependency."""
from dataclasses import dataclass
from typing import Protocol
import hashlib,json,math

CONTRACT_VERSION=1
class BackendError(RuntimeError):pass
class BackendUnavailable(BackendError):pass
class BackendProtocolError(BackendError):pass
class BackendUnsupported(BackendError):pass

def canonical_rows(rows):return json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def dataset_hash(rows):return hashlib.sha256(canonical_rows(rows)).hexdigest()

@dataclass(frozen=True)
class ScoreBatch:
    points:list
    quality:str

class ModelBackend(Protocol):
    backend_id:str
    def info(self)->dict: ...
    def submit(self,request_id:str,operation:str,payload:dict)->dict: ...
    def job(self,request_id:str)->dict: ...
    def cancel(self,request_id:str)->dict: ...
    def deploy(self,model_ref:str,platform_id:str)->dict: ...
    def predict(self,reference:dict,rows:list,factor:float)->ScoreBatch: ...


def validate_prediction(payload,reference,rows):
    if payload.get('contract_version')!=CONTRACT_VERSION or payload.get('platform_id')!=reference['platform_id'] or payload.get('model_ref')!=reference['model_ref']:
        raise BackendProtocolError('模型平台身份或版本不匹配')
    if reference.get('deployment_ref') and payload.get('deployment_ref')!=reference['deployment_ref']:raise BackendProtocolError('模型部署身份不匹配')
    points=payload.get('points');quality=payload.get('quality')
    if not isinstance(points,list) or len(points)>len(rows) or quality not in ('valid','warmup','history_gap','outside_reference','reference_window_incomplete'):raise BackendProtocolError('模型平台评分响应不符合契约')
    originals={r['t']:r for r in rows};times=set(originals);previous=None
    if len(times)!=len(rows):raise BackendProtocolError('推理输入时间重复')
    def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    for p in points:
        if not isinstance(p,dict) or not finite(p.get('t')) or p['t'] not in times or (previous is not None and p['t']<=previous):raise BackendProtocolError('模型平台返回错误源时间')
        if not finite(p.get('score')) or not finite(p.get('threshold')) or p['threshold']<=0 or not isinstance(p.get('anomaly'),bool) or p['anomaly']!=(p['score']>p['threshold']):raise BackendProtocolError('模型平台返回无效评分或判定')
        for value in p.get('expected',{}).values():
            if not finite(value):raise BackendProtocolError('模型参考值无效')
        for pair in p.get('bounds',{}).values():
            if not isinstance(pair,list) or len(pair)!=2 or not all(finite(v) for v in pair) or pair[0]>pair[1]:raise BackendProtocolError('模型参考带无效')
        original=originals[p['t']]
        if p.get('values')!=original['values']:raise BackendProtocolError('模型平台篡改了原始观测')
        previous=p['t']
    if quality=='valid' and (not rows or not points or points[-1]['t']!=rows[-1]['t']):raise BackendProtocolError('有效评分必须覆盖最新输入时间')
    return ScoreBatch(points,quality)
