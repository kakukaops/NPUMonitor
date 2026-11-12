"""Installed detector adapters: train on training rows, emit raw components only.
No thresholds, calibration or mutable online updates live in these adapters.
"""
from typing import Protocol
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest

class Detector(Protocol):
    window: int
    reference_kind: str
    def fit(self, rows): ...
    def score_raw(self, rows): ...

class BaseDetector:
    window=0
    reference_kind='none'
    interval=False
    def __init__(self,spec,window=12):self.spec=spec
    def array(self,rows):return np.array([[r['values'][k] for k in self.spec['targets']] for r in rows],float)
    def fit(self,rows):raise NotImplementedError
    def score_raw(self,rows):raise NotImplementedError
    def capabilities(self):
        return {'multivariate':len(self.spec['targets'])>1,'history_samples':self.window,
                'reference_kind':self.reference_kind,'reference_band':self.interval,
                'metric_contributions':True,'online_update':False,'minimum_samples':240,
                'input_sampling':'fixed cadence for windowed detectors; no interpolation'}

class LagRidgeDetector(BaseDetector):
    reference_kind='causal_forecast'
    interval=True
    def __init__(self,spec,window=12):super().__init__(spec);self.window=window
    def windows(self,rows):
        out=[]
        for i in range(self.window,len(rows)):
            segment=rows[i-self.window:i+1];gaps=np.diff([r['t'] for r in segment])
            if np.any(np.abs(gaps-self.cadence)>self.cadence*.25):continue
            v=self.array(segment)[:,0];out.append((rows[i],v[:-1],v[-1]))
        return out
    def fit(self,rows):
        self.cadence=max(2,int(round(np.median(np.diff([r['t'] for r in rows])))))
        windows=self.windows(rows)
        if len(windows)<20:raise ValueError('训练集连续窗口不足')
        x=np.array([r[1] for r in windows]);y=np.array([r[2] for r in windows])
        self.regression=Ridge(alpha=1).fit(x,y);self.center=float(np.median(y))
        self.residual_scale=max(float(1.4826*np.median(np.abs(y-self.regression.predict(x)))),.2)
        self.level_scale=max(float(1.4826*np.median(np.abs(y-self.center))),.2)
    def score_raw(self,rows):
        windows=self.windows(rows)
        if not windows:return []
        expected=self.regression.predict(np.array([r[1] for r in windows]));key=self.spec['targets'][0];out=[]
        for i,(row,x,y) in enumerate(windows):
            out.append({'t':row['t'],'values':row['values'],
                        'raw_components':{key+':innovation':abs(y-expected[i])/self.residual_scale,key+':level':abs(y-self.center)/self.level_scale},
                        'component_metrics':{key+':innovation':key,key+':level':key},
                        'expected':{key:float(expected[i])},'bounds':{key:[float(expected[i]-3*self.residual_scale),float(expected[i]+3*self.residual_scale)]}})
        return out

class PCADetector(BaseDetector):
    reference_kind='joint_reconstruction'
    def fit(self,rows):
        y=self.array(rows);self.center=np.mean(y,axis=0);self.scale=np.maximum(np.std(y,axis=0),.2)
        self.pca=PCA(n_components=max(1,len(self.spec['targets'])-1)).fit((y-self.center)/self.scale)
    def score_raw(self,rows):
        if not rows:return []
        z=(self.array(rows)-self.center)/self.scale;latent=self.pca.transform(z);r=self.pca.inverse_transform(latent)
        residual=np.square(z-r);distance=np.sum(np.square(latent)/np.maximum(self.pca.explained_variance_,.01),axis=1)
        expected=r*self.scale+self.center;out=[]
        for i,row in enumerate(rows):
            components={k+':reconstruction':float(residual[i,j]) for j,k in enumerate(self.spec['targets'])};components['joint_distance']=float(distance[i])
            out.append({'t':row['t'],'values':row['values'],'raw_components':components,
                        'component_metrics':{k+':reconstruction':k for k in self.spec['targets']},
                        'expected':dict(zip(self.spec['targets'],map(float,expected[i]))),'bounds':{}})
        return out

class IsolationDetector(BaseDetector):
    def fit(self,rows):
        self.forest=IsolationForest(n_estimators=96,random_state=301,n_jobs=1).fit(self.array(rows))
    def score_raw(self,rows):
        if not rows:return []
        scores=-self.forest.score_samples(self.array(rows))
        return [{'t':r['t'],'values':r['values'],'raw_components':{'isolation':float(scores[i])},'component_metrics':{},'expected':{},'bounds':{}} for i,r in enumerate(rows)]
    def capabilities(self):return dict(super().capabilities(),metric_contributions=False)

class LevelMADDetector(BaseDetector):
    def fit(self,rows):
        y=self.array(rows);self.center=np.median(y,axis=0);self.scale=np.maximum(1.4826*np.median(np.abs(y-self.center),axis=0),.2)
    def score_raw(self,rows):
        if not rows:return []
        scores=np.abs((self.array(rows)-self.center)/self.scale)
        return [{'t':r['t'],'values':r['values'],'raw_components':{k+':level':float(scores[i,j]) for j,k in enumerate(self.spec['targets'])},'component_metrics':{k+':level':k for k in self.spec['targets']},'expected':{},'bounds':{}} for i,r in enumerate(rows)]

DETECTORS={'temporal_mad':LagRidgeDetector,'joint_pca':PCADetector,'joint_iforest':IsolationDetector,'level_mad':LevelMADDetector}


def register_detector(name,title,factory):
    """Register installed code only. Templates explicitly opt in to each adapter."""
    if not isinstance(name,str) or not name.replace('_','').isalnum() or name in DETECTORS:raise ValueError('检测器名称无效或重复')
    from .models import ALGORITHMS
    DETECTORS[name]=factory;ALGORITHMS[name]=title
