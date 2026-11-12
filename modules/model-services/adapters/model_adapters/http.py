"""Reference HTTP adapter. Company native APIs can be mapped behind this port."""
import json,os
from pathlib import Path
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit,quote
from model_contracts import CONTRACT_VERSION,BackendUnavailable,BackendProtocolError,BackendUnsupported,validate_prediction

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class HttpModelBackend:
    def __init__(self,url=None,token_file=None,backend_id=None,timeout=12):
        self.url=(url or os.environ.get('GPU_ML_MODEL_PLATFORM_URL','http://model-platform:9470')).rstrip('/')
        parts=urlsplit(self.url)
        if parts.scheme not in ('http','https') or parts.username or parts.password or parts.query or parts.fragment:raise ValueError('模型平台URL无效，凭据使用独立文件')
        self.token_file=token_file or os.environ.get('GPU_ML_MODEL_PLATFORM_TOKEN_FILE','/run/secrets/model-platform-token')
        self.backend_id=backend_id or os.environ.get('GPU_ML_MODEL_BACKEND_ID','reference-http-v1');self.timeout=timeout
        self.opener=build_opener(ProxyHandler({}),NoRedirect())
    def call(self,method,path,body=None):
        try:
            token=Path(self.token_file).read_text().strip()
            if not token:raise BackendUnavailable('模型平台凭据未配置')
            req=Request(self.url+path,data=None if body is None else json.dumps(body,allow_nan=False).encode(),method=method,
                        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with self.opener.open(req,timeout=self.timeout) as response:raw=response.read(16*1024*1024+1)
            if len(raw)>16*1024*1024:raise BackendProtocolError('模型平台响应超出配额')
            value=json.loads(raw)
            if not isinstance(value,dict) or value.get('contract_version')!=CONTRACT_VERSION:raise BackendProtocolError('模型平台契约版本不匹配')
            return value
        except HTTPError as exc:
            if exc.code==409:raise BackendUnsupported('模型平台拒绝操作：能力、幂等键或模型自检不满足') from None
            if exc.code==404:raise BackendUnsupported('模型平台未找到任务或模型') from None
            if exc.code in (400,422):raise BackendProtocolError('模型平台拒绝输入契约') from None
            raise BackendUnavailable('模型平台请求失败，HTTP '+str(exc.code)) from None
        except (URLError,TimeoutError,OSError):raise BackendUnavailable('模型平台不可用或请求超时') from None
        except (json.JSONDecodeError,UnicodeDecodeError):raise BackendProtocolError('模型平台响应无法解析') from None
    def info(self):return self.call('GET','/v1/info')
    def submit(self,request_id,operation,payload):
        body={'contract_version':1,'request_id':request_id,'operation':operation,**payload}
        # Exactly the same idempotency key and input on retry; never blindly create a second job.
        try:return self.call('POST','/v1/jobs',body)
        except BackendUnavailable:return self.call('POST','/v1/jobs',body)
    def job(self,request_id):return self.call('GET','/v1/jobs/'+quote(request_id,safe=''))
    def cancel(self,request_id):return self.call('POST','/v1/jobs/'+quote(request_id,safe='')+'/cancel',{})
    def deploy(self,model_ref,platform_id):
        result=self.call('POST','/v1/deployments',{'model_ref':model_ref,'platform_id':platform_id})
        if result.get('model_ref')!=model_ref or result.get('platform_id')!=platform_id or not isinstance(result.get('deployment_ref'),str):raise BackendProtocolError('部署回执身份无效')
        if result.get('status')!='ready':raise BackendUnavailable('模型部署尚未就绪，当前检测版本保持不变')
        return result
    def predict(self,reference,rows,factor=1.):
        if reference.get('backend_id')!=self.backend_id:raise BackendUnsupported('该模型属于其他模型后端，不能静默切换')
        deployed=reference.get('deployment_ref');kind='deployments' if deployed else 'models';ident=deployed or reference['model_ref']
        value=self.call('POST','/v1/'+kind+'/'+quote(ident,safe='')+'/predict',{'platform_id':reference['platform_id'],'rows':rows,'decision_factor':factor})
        return validate_prediction(value,reference,rows)

class RemoteModel:
    def __init__(self,backend,record):
        self.backend=backend;self.record=record;self.spec=record['feature_schema'];self.algorithm=record['algorithm'];self.report=record['report']
        self.capabilities=record['capabilities'];self.window=int(self.capabilities.get('history_samples',0));self.cadence=self.capabilities.get('cadence_seconds') or 2
    def evaluate(self,rows,factor=1.):return self.backend.predict(self.record['backend'],rows,factor)
    def predict(self,rows,factor=1.):return self.evaluate(rows,factor).points
