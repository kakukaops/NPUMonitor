"""Causal GPU conditional models; artifacts and calibrations are one release unit."""
import hashlib
import json
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import Ridge
from gpu_ml_runtime.catalog import TEMPLATES

ALGORITHMS = {'ridge_iforest':'Ridge 条件基线 + Isolation Forest', 'robust_mad':'条件基线 + 稳健 MAD'}


class GPUModel:
    schema=1

    def __init__(self,template,algorithm='ridge_iforest'):
        if template not in TEMPLATES or algorithm not in ALGORITHMS:raise ValueError('未知模板或算法')
        self.template=template;self.algorithm=algorithm;self.spec=TEMPLATES[template]

    def _arrays(self,rows):
        y=np.asarray([[r['values'][k] for k in self.spec['targets']] for r in rows],dtype=float)
        x=np.asarray([[r['values'][k] for k in self.spec['features']] for r in rows],dtype=float)
        if not np.isfinite(y).all() or not np.isfinite(x).all():raise ValueError('模型输入必须为有限值')
        return x,y

    def fit(self,rows):
        if self.template=='activity':rows=[r for r in rows if r['values'].get('job_running')==1]
        if len(rows)<180:raise ValueError('至少需要180个有效且唯一的源样本，活动模板仅计运行上下文')
        # Train, calibrate and evaluate on disjoint chronological samples.
        rows=sorted(rows,key=lambda r:r['t'])
        if len({r['t'] for r in rows})!=len(rows):raise ValueError('训练样本时间重复')
        a=int(len(rows)*.6);b=int(len(rows)*.8)
        train,cal,test=rows[:a],rows[a:b],rows[b:]
        x,y=self._arrays(train)
        self.center=np.median(y,axis=0)
        self.baseline=Ridge(alpha=.1).fit(x,y) if self.spec['features'] else None
        expected=self._expected(x,len(y))
        residual=y-expected
        self.scale=np.maximum(1.4826*np.median(np.abs(residual-np.median(residual,axis=0)),axis=0),.2)
        self.forests=[]
        for i in range(y.shape[1]):
            forest=IsolationForest(n_estimators=96,max_samples=min(256,len(train)),random_state=101+i,n_jobs=1)
            # Tail magnitudes avoid high-dimensional dilution and boundary direction bias.
            forest.fit(np.abs(residual[:,[i]])/self.scale[i])
            self.forests.append(forest)
        # Calibration includes a robust tail score so far-out deviations do not saturate
        # below a forest threshold. Both score components are explicitly calibrated.
        self.threshold=1.
        components=self._components(cal)
        self.component_scale=np.maximum(np.quantile(components,.99,axis=0),.01)
        scores=np.max(components/self.component_scale,axis=1)
        self.threshold=float(np.quantile(scores,.995))
        test_results=self.predict(test)
        self.report={'samples':len(rows),'train_samples':len(train),'calibration_samples':len(cal),'test_samples':len(test),
                     'train_start':train[0]['t'],'train_end':train[-1]['t'],'calibration_start':cal[0]['t'],
                     'test_start':test[0]['t'],'test_end':test[-1]['t'],
                     'held_out_point_alert_rate':float(np.mean([r['anomaly'] for r in test_results])),
                     'threshold':self.threshold,'labelled_fault_recall':None,'production_admitted':False}
        return self.report

    def _expected(self,x,count):
        return self.baseline.predict(x) if self.baseline is not None else np.tile(self.center,(count,1))

    def _components(self,rows):
        x,y=self._arrays(rows);res=(y-self._expected(x,len(y)))/self.scale
        if self.template=='thermal':tail=np.maximum(res,0)
        elif self.template=='activity':tail=np.maximum(-res,0)
        else:tail=np.abs(res)
        if self.algorithm=='robust_mad':return np.maximum(tail,.001)
        forest_scores=np.column_stack([-f.score_samples(tail[:,[i]]) for i,f in enumerate(self.forests)])
        return np.column_stack([forest_scores,tail])

    def predict(self,rows):
        if not rows:return []
        x,y=self._arrays(rows);expected=self._expected(x,len(rows));components=self._components(rows)
        scores=np.max(components/self.component_scale,axis=1)
        result=[]
        for i,row in enumerate(rows):
            baseline={k:float(expected[i,j]) for j,k in enumerate(self.spec['targets'])}
            limits={k:[float(expected[i,j]-3*self.scale[j]),float(expected[i,j]+3*self.scale[j])] for j,k in enumerate(self.spec['targets'])}
            residual=np.abs((y[i]-expected[i])/self.scale)
            result.append({'t':row['t'],'values':row['values'],'expected':baseline,'bounds':limits,
                           'score':float(scores[i]),'threshold':self.threshold,'anomaly':bool(scores[i]>self.threshold),
                           'reason_metric':self.spec['targets'][int(np.argmax(residual))]})
        return result

    def save(self,path):
        path=Path(path);joblib.dump(self,path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def load(path,digest):
        path=Path(path)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('模型制品摘要不匹配')
        model=joblib.load(path)  # Only server-created immutable local artifacts; no upload API.
        if not isinstance(model,GPUModel) or model.schema!=1:raise ValueError('模型格式不兼容')
        return model


class RobustMADModel(GPUModel):
    """Reference Python adapter: same GPU contract, independently selected scorer."""
    def __init__(self,template,algorithm='robust_mad'):
        super().__init__(template,algorithm='robust_mad')


MODEL_REGISTRY={'ridge_iforest':GPUModel,'robust_mad':RobustMADModel}


def register_model(name,title,factory):
    """Controlled, installed Python extension; never accepts code/artifact uploads."""
    if name in MODEL_REGISTRY or not name.replace('_','').isalnum():
        raise ValueError('模型注册名称重复或无效')
    MODEL_REGISTRY[name]=factory
    ALGORITHMS[name]=title


def build_model(template,algorithm):
    if algorithm not in MODEL_REGISTRY:raise ValueError('模型适配器未注册')
    allowed=TEMPLATES[template].get('algorithms')
    if allowed and algorithm not in allowed:raise ValueError('算法与检测类型不兼容')
    if not allowed and algorithm in ('temporal_mad','joint_pca'):raise ValueError('新算法需要对应的时序或联合模板')
    return MODEL_REGISTRY[algorithm](template,algorithm=algorithm)


class TemporalMADModel(GPUModel):
    """Causal lag regression with separately calibrated innovation and level scores."""
    window=12
    def __init__(self,template,algorithm='temporal_mad'):
        self.template=template;self.algorithm=algorithm;self.spec=TEMPLATES[template]
    def windows(self,rows):
        rows=sorted(rows,key=lambda r:r['t']);out=[]
        for i in range(self.window,len(rows)):
            segment=rows[i-self.window:i+1]
            gaps=np.diff([r['t'] for r in segment])
            if np.any(gaps<=0) or np.any(np.abs(gaps-self.cadence)>self.cadence*.25):continue
            values=np.array([r['values'][self.spec['targets'][0]] for r in segment],float)
            if np.isfinite(values).all():out.append((rows[i],values[:-1],values[-1]))
        return out
    def fit(self,rows):
        times=[r['t'] for r in rows]
        if len(rows)<240 or len(set(times))!=len(times):raise ValueError('时序模型至少240个唯一样本')
        rows=sorted(rows,key=lambda r:r['t']);self.cadence=max(2,int(round(np.median(np.diff(sorted(times))))))
        a=int(len(rows)*.6);b=int(len(rows)*.8)
        train=self.windows(rows[:a]);cal=self.windows(rows[a:b]);test=rows[b:]
        if min(len(train),len(cal),len(self.windows(test)))<20:raise ValueError('连续时序窗口不足，不能跨缺口训练')
        x=np.array([r[1] for r in train]);y=np.array([r[2] for r in train])
        self.baseline=Ridge(alpha=1).fit(x,y);self.center=float(np.median(y))
        self.scale=max(float(1.4826*np.median(np.abs(y-self.baseline.predict(x)))),.2)
        self.level_scale=max(float(1.4826*np.median(np.abs(y-self.center))),.2)
        components=self.components(cal);self.component_scale=np.maximum(np.quantile(components,.99,axis=0),.01)
        self.threshold=max(float(np.quantile(np.max(components/self.component_scale,axis=1),.995)),.01)
        predictions=self.predict(test)
        self.report={'samples':len(rows),'train_samples':a,'calibration_samples':b-a,'test_samples':len(predictions),'held_out_point_alert_rate':float(np.mean([p['anomaly'] for p in predictions])),'cadence_seconds':self.cadence,'window_samples':self.window,'threshold':self.threshold,'production_admitted':False}
        return self.report
    def components(self,windows):
        x=np.array([r[1] for r in windows]);y=np.array([r[2] for r in windows])
        return np.column_stack([np.abs(y-self.baseline.predict(x))/self.scale,np.abs(y-self.center)/self.level_scale])
    def predict(self,rows):
        windows=self.windows(rows)
        if not windows:return []
        scores=np.max(self.components(windows)/self.component_scale,axis=1)
        expected=self.baseline.predict(np.array([r[1] for r in windows]));key=self.spec['targets'][0]
        return [{'t':r[0]['t'],'values':r[0]['values'],'expected':{key:float(expected[i])},'bounds':{key:[float(expected[i]-3*self.scale),float(expected[i]+3*self.scale)]},'score':float(scores[i]),'threshold':self.threshold,'anomaly':bool(scores[i]>self.threshold),'reason_metric':key,'contributions':{key:float(scores[i])},'reference_kind':'causal_forecast','window_samples':self.window} for i,r in enumerate(windows)]


class JointPCAModel(GPUModel):
    """Trainable multivariate point detector; no claim of temporal forecasting."""
    def __init__(self,template,algorithm='joint_pca'):
        self.template=template;self.algorithm=algorithm;self.spec=TEMPLATES[template]
    def array(self,rows):return np.array([[r['values'][k] for k in self.spec['targets']] for r in rows],float)
    def components(self,y):
        z=(y-self.center)/self.scale;latent=self.pca.transform(z);reconstructed=self.pca.inverse_transform(latent)
        residual=np.square(z-reconstructed)
        distance=np.sum(np.square(latent)/np.maximum(self.pca.explained_variance_,.01),axis=1)
        return np.column_stack([residual,distance]),reconstructed*self.scale+self.center
    def fit(self,rows):
        from sklearn.decomposition import PCA
        if len(rows)<240 or len({r['t'] for r in rows})!=len(rows):raise ValueError('联合模型至少240个唯一样本')
        rows=sorted(rows,key=lambda r:r['t']);a=int(len(rows)*.6);b=int(len(rows)*.8);y=self.array(rows[:a])
        if not np.isfinite(self.array(rows)).all():raise ValueError('输入必须有限')
        self.center=np.mean(y,axis=0);self.scale=np.maximum(np.std(y,axis=0),.2)
        self.pca=PCA(n_components=max(1,len(self.spec['targets'])-1)).fit((y-self.center)/self.scale)
        components,_=self.components(self.array(rows[a:b]));self.component_scale=np.maximum(np.quantile(components,.99,axis=0),.01)
        self.threshold=max(float(np.quantile(np.max(components/self.component_scale,axis=1),.995)),.01)
        predictions=self.predict(rows[b:]);self.report={'samples':len(rows),'train_samples':a,'calibration_samples':b-a,'test_samples':len(predictions),'held_out_point_alert_rate':float(np.mean([p['anomaly'] for p in predictions])),'threshold':self.threshold,'production_admitted':False}
        return self.report
    def predict(self,rows):
        if not rows:return []
        components,expected=self.components(self.array(rows));normalized=components/self.component_scale;scores=np.max(normalized,axis=1);out=[]
        for i,row in enumerate(rows):
            contributions={k:float(normalized[i,j]) for j,k in enumerate(self.spec['targets'])}
            out.append({'t':row['t'],'values':row['values'],'expected':dict(zip(self.spec['targets'],map(float,expected[i]))),'bounds':{},'score':float(scores[i]),'threshold':self.threshold,'anomaly':bool(scores[i]>self.threshold),'reason_metric':max(contributions,key=contributions.get),'contributions':contributions,'joint_distance_score':float(normalized[i,-1]),'reference_kind':'joint_reconstruction'})
        return out

register_model('temporal_mad','单指标 · 滞后回归 + 稳健残差/水平',TemporalMADModel)
register_model('joint_pca','多指标 · PCA联合行为',JointPCAModel)

# V3 production-facing adapters are constructed by pipeline.build_pipeline.
ALGORITHMS.update({'joint_iforest':'多指标 · Isolation Forest（仅评分）','level_mad':'单指标 · 稳健水平偏离（仅评分）'})

ALGORITHMS['ensemble_max']='冻结模型集成 · 校准阈值比最大值'
