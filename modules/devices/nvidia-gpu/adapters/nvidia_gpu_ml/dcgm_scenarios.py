"""DCGM-only conditional relationships and frozen-baseline residual trends.
No job/workload/ambient/throughput features are fabricated or inferred.
"""
import copy
import json
import math
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from .plugin_config import BASE
from gpu_ml_runtime.catalog import TEMPLATES
from gpu_ml_runtime.detectors import BaseDetector,register_detector

CATALOG=json.loads((BASE/'config/dcgm-scenarios.json').read_text())

def template_name(scenario,profile):return 'dcgm_'+scenario+'_'+profile

def install_templates():
    for ident,scene in CATALOG['scenarios'].items():
        for profile,policy in CATALOG['profiles'].items():
            trend=scene['algorithm']=='dcgm_residual_trend'
            spec=copy.deepcopy(scene);spec.update(kind='multivariate',name=scene['name']+(' · 加速实验' if profile=='laboratory' else ' · 生产参考'),algorithms=[scene['algorithm']],
                scenario={'id':ident,'profile':profile,'minimum_history_seconds':policy['trend_history_seconds' if trend else 'relation_history_seconds'],
                          'trend_seconds':policy['trend_seconds'] if trend else 0,'lag_samples':12,'limitations':CATALOG['scope']})
            TEMPLATES[template_name(ident,profile)]=spec

class ConditionalDCGMDetector(BaseDetector):
    reference_kind='conditional_baseline'
    interval=True
    def __init__(self,spec,window=12):
        super().__init__(spec);self.lag=spec.get('scenario',{}).get('lag_samples',12);self.window=self.lag
    def features(self,segment):
        keys=self.spec['features'];current=np.array([segment[-1]['values'][k] for k in keys])
        history=np.array([[r['values'][k] for k in keys] for r in segment[:-1]])
        return np.concatenate([current,history.mean(axis=0)])
    def segments(self,rows):
        for i in range(self.lag,len(rows)):
            segment=rows[i-self.lag:i+1];gaps=np.diff([r['t'] for r in segment])
            if np.any(np.abs(gaps-self.cadence)>self.cadence*.25):continue
            yield segment,self.features(segment)
    def fit(self,rows):
        self.cadence=max(2,int(round(np.median(np.diff([r['t'] for r in rows])))))
        segments=list(self.segments(rows))
        if len(segments)<30:raise ValueError('条件基线连续训练样本不足')
        x=np.array([x for seg,x in segments]);y=np.array([[seg[-1]['values'][k] for k in self.spec['targets']] for seg,x in segments])
        self.scaler=StandardScaler().fit(x);self.regression=Ridge(alpha=1.).fit(self.scaler.transform(x),y)
        residual=y-np.asarray(self.regression.predict(self.scaler.transform(x))).reshape(-1,len(self.spec['targets']));self.scale=np.maximum(1.4826*np.median(np.abs(residual-np.median(residual,axis=0)),axis=0),.2)
        # Training-only envelope: do not interpret unseen load/configuration as hardware damage.
        self.low=np.min(x,axis=0);self.high=np.max(x,axis=0);self.padding=np.maximum((self.high-self.low)*.35,.05)
        clocks=np.array([r['values']['mem_clock'] for r in rows]);self.clock_center=float(np.median(clocks))
        self.clock_margin=max(float(8*1.4826*np.median(np.abs(clocks-self.clock_center))),10.)
        if np.quantile(clocks,.95)-np.quantile(clocks,.05)>max(50.,self.clock_margin*2):raise ValueError('参考历史含多个显存时钟模式，请选择配置一致的历史')
    def comparable(self,segment,x):
        return bool(np.all(x>=self.low-self.padding) and np.all(x<=self.high+self.padding) and
                    abs(segment[-1]['values']['mem_clock']-self.clock_center)<=self.clock_margin)
    def latest_quality(self,rows):
        if len(rows)<self.window+1:return 'warmup'
        recent=rows[-self.window-1:]
        if np.any(np.abs(np.diff([r['t'] for r in recent])-self.cadence)>self.cadence*.25):return 'history_gap'
        segment=rows[-self.lag-1:]
        return 'valid' if self.comparable(segment,self.features(segment)) else 'outside_reference'
    def conditional_points(self,rows):
        out=[]
        for segment,x in self.segments(rows):
            if not self.comparable(segment,x):continue
            row=segment[-1];expected=np.asarray(self.regression.predict(self.scaler.transform([x]))).reshape(-1,len(self.spec['targets']))[0]
            actual=np.array([row['values'][k] for k in self.spec['targets']]);residual=actual-expected
            out.append((row,expected,residual))
        return out
    def tail(self,residual):
        return np.array([max(float(v),0) if d=='high' else max(float(-v),0) if d=='low' else abs(float(v)) for v,d in zip(residual,self.spec['directions'])])
    def score_raw(self,rows):
        out=[]
        for row,expected,residual in self.conditional_points(rows):
            components={k+':conditional_residual':float(self.tail(residual)[i]/self.scale[i]) for i,k in enumerate(self.spec['targets'])}
            out.append({'t':row['t'],'values':row['values'],'raw_components':components,
                'component_metrics':{k+':conditional_residual':k for k in self.spec['targets']},
                'expected':dict(zip(self.spec['targets'],map(float,expected))),
                'bounds':{k:[float(expected[i]-3*self.scale[i]),float(expected[i]+3*self.scale[i])] for i,k in enumerate(self.spec['targets'])},
                'evidence':{'residuals':dict(zip(self.spec['targets'],map(float,residual))),'reference_scope':'same GPU; observed load and memory-clock envelope only','conclusion':'conditional relationship deviation; cause unverified'}})
        return out
    def capabilities(self):
        return dict(super().capabilities(),scenario=self.spec.get('scenario'),history_samples=self.window,reference_kind=self.reference_kind,
                    reference_band=True,metric_contributions=True,conclusion_scope='behavioral evidence, not hardware diagnosis or remaining life')

class ResidualTrendDetector(ConditionalDCGMDetector):
    def fit(self,rows):
        super().fit(rows)
        self.trend_seconds=self.spec['scenario']['trend_seconds'];self.trend_samples=max(12,int(math.ceil(self.trend_seconds/self.cadence)))
        self.window=self.lag+self.trend_samples-1
    def score_raw(self,rows):
        conditional=self.conditional_points(rows);out=[]
        for end in range(self.trend_samples-1,len(conditional)):
            sample=conditional[end-self.trend_samples+1:end+1];stamps=np.array([p[0]['t'] for p in sample])
            if np.any(np.abs(np.diff(stamps)-self.cadence)>self.cadence*.25):continue
            residual=np.array([p[2] for p in sample]);x=stamps-stamps[0];x=x-x.mean()
            clipped=np.clip(residual,np.quantile(residual,.05,axis=0),np.quantile(residual,.95,axis=0))
            slope=np.sum(x[:,None]*clipped,axis=0)/np.sum(x*x);level=np.median(residual,axis=0)
            directional=np.array([1. if d=='high' else -1. for d in self.spec['directions']]);components={};mapping={}
            for i,k in enumerate(self.spec['targets']):
                components[k+':sustained_offset']=float(max(0,directional[i]*level[i])/self.scale[i])
                components[k+':trend']=float(max(0,directional[i]*slope[i])*self.trend_seconds/self.scale[i])
                mapping[k+':sustained_offset']=k;mapping[k+':trend']=k
            row,expected,last_residual=sample[-1]
            out.append({'t':row['t'],'values':row['values'],'raw_components':components,'component_metrics':mapping,
                'expected':dict(zip(self.spec['targets'],map(float,expected))),
                'bounds':{k:[float(expected[i]-3*self.scale[i]),float(expected[i]+3*self.scale[i])] for i,k in enumerate(self.spec['targets'])},
                'evidence':{'residuals':dict(zip(self.spec['targets'],map(float,last_residual))),
                    'residual_medians':dict(zip(self.spec['targets'],map(float,level))),
                    'residual_slope_per_hour':dict(zip(self.spec['targets'],map(float,slope*3600))),
                    'window_start':float(stamps[0]),'window_end':float(stamps[-1]),'window_seconds':self.trend_seconds,
                    'conclusion':'sustained residual shift / trend; ambient, workload and configuration changes not excluded; not a lifetime prediction',
                    'profile':self.spec['scenario']['profile']}})
        return out

install_templates()
register_detector('dcgm_conditional','DCGM条件关系基线＋残差',ConditionalDCGMDetector)
register_detector('dcgm_residual_trend','DCGM条件残差长期漂移',ResidualTrendDetector)
