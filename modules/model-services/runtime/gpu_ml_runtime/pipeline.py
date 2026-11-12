"""Versioned train-only preprocessing -> raw detector -> calibration -> decision.
This module implements the design locally; it does not import Merlion.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time
import uuid
import joblib
import numpy as np
from .catalog import TEMPLATES, LEGACY_TYPES, legacy_model
from .detectors import DETECTORS
from .evaluation import summarize


def finite_number(value,low,high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError('参数范围无效')
    return float(value)

class StrictPreprocessor:
    def __init__(self,required,config=None):
        self.required=list(required);self.config=copy.deepcopy(config if config is not None else {'kind':'identity'})
        if not isinstance(self.config,dict):raise ValueError('预处理配置需要对象')
        if set(self.config)-{'kind'} or self.config.get('kind') not in ('identity','robust_scale'):raise ValueError('仅支持identity或训练集robust_scale；不支持插值填缺')
    def validate(self,rows):
        previous=None
        for row in rows:
            t=float(row['t'])
            if not math.isfinite(t) or (previous is not None and t<=previous):raise ValueError('源时间必须有限、严格递增且唯一')
            for k in self.required:
                if not math.isfinite(float(row['values'][k])):raise ValueError('必需指标缺失或非有限数值')
            previous=t
        return rows
    def fit(self,rows):
        self.validate(rows);self.centers={k:0. for k in self.required};self.scales={k:1. for k in self.required}
        if self.config['kind']=='robust_scale':
            for k in self.required:
                v=np.array([r['values'][k] for r in rows]);c=float(np.median(v));self.centers[k]=c
                self.scales[k]=max(float(1.4826*np.median(np.abs(v-c))),.2)
    def transform(self,rows):
        self.validate(rows)
        return [dict(r,values={**r['values'],**{k:(r['values'][k]-self.centers[k])/self.scales[k] for k in self.required}}) for r in rows]
    def inverse_value(self,key,value):return float(value*self.scales[key]+self.centers[key])
    def metadata(self):return {'config':self.config,'centers':self.centers,'scales':self.scales,'fitted_on':'training partition only','missing':'reject; never interpolate'}

class QuantileCalibrator:
    def __init__(self,config=None):
        self.config=copy.deepcopy(config if config is not None else {'component_quantile':.99,'threshold_quantile':.995})
        if not isinstance(self.config,dict):raise ValueError('校准配置需要对象')
        if set(self.config)!={'component_quantile','threshold_quantile'}:raise ValueError('校准配置字段无效')
        for v in self.config.values():finite_number(v,.9,.9999)
    def fit(self,points):
        if len(points)<12:raise ValueError('独立校准段有效评分不足12点')
        self.keys=sorted(points[0]['raw_components'])
        raw=np.array([[p['raw_components'][k] for k in self.keys] for p in points])
        if not self.keys or not np.isfinite(raw).all() or np.any(raw<0):raise ValueError('原始评分分量必须有限、非负且非空')
        self.scales=dict(zip(self.keys,map(float,np.maximum(np.quantile(raw,self.config['component_quantile'],axis=0),.01))))
        scores=[max(p['raw_components'][k]/self.scales[k] for k in self.keys) for p in points]
        self.default_threshold=max(float(np.quantile(scores,self.config['threshold_quantile'])),.01)
    def transform(self,raw):
        if any(not math.isfinite(float(v)) or v<0 for v in raw.values()):raise ValueError('原始评分分量无效')
        if sorted(raw)!=self.keys:raise ValueError('原始评分分量schema不兼容')
        return {k:float(raw[k]/self.scales[k]) for k in self.keys}

class ThresholdPolicy:
    def __init__(self,threshold,factor=1.):
        self.threshold=finite_number(threshold,1e-12,1e12);self.factor=finite_number(factor,.8,2.)
    def apply(self,score,factor=1.):
        threshold=self.threshold*self.factor*finite_number(factor,.8,2.)
        return threshold,bool(score>threshold)

class DetectionPipeline:
    schema=3
    def __init__(self,template,algorithm,config=None,spec=None):
        self.template=template;self.algorithm=algorithm;self.spec=copy.deepcopy(TEMPLATES[template] if spec is None else spec);self.config=copy.deepcopy(config if config is not None else {})
        if not isinstance(self.config,dict):raise ValueError('流水线配置需要对象')
        if algorithm not in self.spec.get('algorithms',[]) or algorithm not in DETECTORS:raise ValueError('算法与检测配置不兼容')
        if set(self.config)-{'preprocessing','calibration','detector','decision'}:raise ValueError('流水线配置字段无效')
        params=self.config.get('detector',{})
        if not isinstance(params,dict) or set(params)-{'window'}:raise ValueError('检测器参数无效')
        window=params.get('window',12)
        if not isinstance(window,int) or isinstance(window,bool) or not 4<=window<=60:raise ValueError('历史窗口范围4至60点')
        if algorithm!='temporal_mad' and params:raise ValueError('该检测器不使用历史窗口参数')
        self.preprocessor=StrictPreprocessor(self.spec['required'],self.config.get('preprocessing'))
        self.detector=DETECTORS[algorithm](self.spec,window=window)
        self.calibrator=QuantileCalibrator(self.config.get('calibration'))
        decision=self.config.get('decision',{})
        if not isinstance(decision,dict) or set(decision)-{'factor'}:raise ValueError('判定参数无效')
        self.factor=finite_number(decision.get('factor',1.),.8,2.)
        self.pipeline_id=uuid.uuid4().hex;self.detector_id=uuid.uuid4().hex;self.preprocessor_id=uuid.uuid4().hex
        self.calibrator_id=uuid.uuid4().hex;self.decision_id=uuid.uuid4().hex
    @property
    def window(self):return self.detector.window
    @property
    def capabilities(self):return dict(self.detector.capabilities(),cadence_seconds=getattr(self,'cadence',None),stateful=False,artifact_schema=3)
    def partitions(self,rows):
        self.preprocessor.validate(rows)
        if len(rows)<240:raise ValueError('流水线至少240个唯一样本，生产训练范围需另行验证')
        a=int(len(rows)*.6);b=int(len(rows)*.8);c=int(len(rows)*.9)
        return rows[:a],rows[a:b],rows[b:c],rows[c:]
    def fit(self,rows,labels=None):
        started=time.perf_counter();train,cal,selection,test=self.partitions(rows)
        scenario=self.spec.get('scenario')
        if scenario and rows[-1]['t']-rows[0]['t']<scenario['minimum_history_seconds']-5:raise ValueError('该场景需要更长参考历史；不能将实验窗口当作生产退化证据')
        self.cadence=max(2,int(round(np.median(np.diff([r['t'] for r in train])))))
        self.preprocessor.fit(train);self.detector.fit(self.preprocessor.transform(train))
        self.calibrator.fit(self.detector.score_raw(self.preprocessor.transform(cal)))
        self.policy=ThresholdPolicy(self.calibrator.default_threshold,self.factor)
        self.report=self.evaluate_partitions(rows,labels)
        self.report['fit_seconds']=time.perf_counter()-started
        return self.report
    def evaluate_partitions(self,rows,labels=None):
        train,cal,selection,test=self.partitions(rows);reports={}
        for key,part in [('selection',selection),('test',test)]:
            started=time.perf_counter();points=self.predict(part)
            if len(points)<6:raise ValueError('独立'+key+'段有效评分不足6点，请扩大训练范围或缩短历史窗口')
            reports[key]=summarize(points,part,[l for l in (labels or []) if l['end']>part[0]['t'] and l['start']<=part[-1]['t']],self.cadence,time.perf_counter()-started)
        return {'samples':len(rows),'train_samples':len(train),'calibration_samples':len(cal),'selection_samples':len(selection),'test_samples':reports['test']['scored_points'],
                'held_out_point_alert_rate':reports['test']['point_alert_rate'],'labelled_fault_recall':reports['test']['labelled_point_recall'],
                'selection':reports['selection'],'test':reports['test'],
                'partitions':{key:{'start':part[0]['t'],'end':part[-1]['t'],'source_points':len(part)} for key,part in [('train',train),('calibration',cal),('selection',selection),('test',test)]},
                'threshold':self.policy.threshold*self.policy.factor,'cadence_seconds':self.cadence,'window_samples':self.window,'production_admitted':False,
                'self_check':'held-out alert fraction; not fault accuracy or automatic model selection'}
    def predict(self,rows,factor=1.):
        original={r['t']:r for r in rows};processed=self.preprocessor.transform(rows);raw=self.detector.score_raw(processed);out=[]
        for p in raw:
            components=self.calibrator.transform(p['raw_components']);score=max(components.values());threshold,anomaly=self.policy.apply(score,factor)
            contributions={}
            for component,key in p['component_metrics'].items():contributions[key]=max(contributions.get(key,0.),components[component])
            expected={k:self.preprocessor.inverse_value(k,v) for k,v in p['expected'].items()}
            bounds={k:[self.preprocessor.inverse_value(k,v) for v in pair] for k,pair in p['bounds'].items()}
            out.append({'t':p['t'],'values':original[p['t']]['values'],'expected':expected,'bounds':bounds,
                        'raw_components':p['raw_components'],'raw_score':max(p['raw_components'].values()),'calibrated_components':components,
                        'score':score,'calibrated_score':score,'threshold':threshold,'anomaly':anomaly,
                        'contributions':contributions,'reason_metric':max(contributions,key=contributions.get) if contributions else None,
                        'reference_kind':self.detector.reference_kind,'capabilities':self.capabilities,'pipeline_id':self.pipeline_id,
                        'calibrator_id':self.calibrator_id,'decision_id':self.decision_id,'preprocessor_id':self.preprocessor_id,
                        'raw_score_semantics':'maximum raw detector component; not comparable across algorithms',
                        'cadence_seconds':self.cadence,'joint_distance_score':components.get('joint_distance'),
                        'scenario':self.spec.get('scenario'),'evidence':{k:({metric:float(value*self.preprocessor.scales[metric]) for metric,value in v.items()} if k in ('residuals','residual_medians','residual_slope_per_hour') else v) for k,v in p.get('evidence',{}).items()}})
        return out
    def reconfigure(self,rows,calibration=None,factor=None):
        clone=copy.deepcopy(self);clone.pipeline_id=uuid.uuid4().hex
        if calibration is not None:
            clone.calibrator=QuantileCalibrator(calibration);cal=clone.partitions(rows)[1]
            clone.calibrator.fit(clone.detector.score_raw(clone.preprocessor.transform(cal)));clone.calibrator_id=uuid.uuid4().hex
        if factor is not None:clone.factor=finite_number(factor,.8,2.)
        clone.policy=ThresholdPolicy(clone.calibrator.default_threshold,clone.factor);clone.decision_id=uuid.uuid4().hex
        clone.report=clone.evaluate_partitions(rows);clone.report.update(detector_retrained=False,preprocessor_refitted=False)
        return clone
    def metadata(self):
        return {'schema':3,'pipeline_id':self.pipeline_id,'preprocessor_id':self.preprocessor_id,'detector_id':self.detector_id,
                'calibrator_id':self.calibrator_id,'decision_id':self.decision_id,'preprocessing':self.preprocessor.metadata(),
                'detector':{'algorithm':self.algorithm,'window':self.window},'calibration':dict(self.calibrator.config,scales=self.calibrator.scales),
                'decision':{'kind':'upper_threshold','threshold':self.policy.threshold,'factor':self.policy.factor},'online_updates':False}
    def save(self,path):
        path=Path(path);joblib.dump(self,path);return hashlib.sha256(path.read_bytes()).hexdigest()


def build_pipeline(template,algorithm,config=None,spec=None):
    selected=TEMPLATES[template] if spec is None else spec
    if selected.get('kind') in ('univariate','multivariate'):return DetectionPipeline(template,algorithm,config,spec=selected)
    if spec is not None and spec!=TEMPLATES.get(template):raise ValueError('旧模板schema不兼容')
    if config:raise ValueError('旧模板不接受新流水线配置，请创建新检测配置')
    return legacy_model(template,algorithm)


def load_artifact(path,digest):
    path=Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('模型制品摘要不匹配')
    model=joblib.load(path)
    if not ((isinstance(model,DetectionPipeline) and model.schema==3) or (isinstance(model,tuple(LEGACY_TYPES)) and model.schema==1)):raise ValueError('模型格式不兼容')
    return model


def capabilities_for(model):
    if hasattr(model,'backend'):return model.capabilities
    if isinstance(model,DetectionPipeline):return model.capabilities
    reference='joint_reconstruction' if model.algorithm=='joint_pca' else 'causal_forecast' if model.algorithm=='temporal_mad' else 'conditional_baseline'
    return {'history_samples':getattr(model,'window',0),'cadence_seconds':getattr(model,'cadence',2),'reference_kind':reference,'reference_band':model.algorithm!='joint_pca','metric_contributions':model.algorithm in ('temporal_mad','joint_pca'),'online_update':False,'stateful':False,'artifact_schema':1}


def describe_algorithms():
    return {key:{'capabilities':adapter({'targets':['metric_a','metric_b'] if key.startswith('joint_') else ['metric'],'required':['metric']}).capabilities(),
                 'preprocessing':['identity','robust_scale'],'calibration':'component quantiles on disjoint calibration partition',
                 'score_semantics':'raw components -> calibrated maximum -> upper threshold'} for key,adapter in DETECTORS.items()}

class CalibratedMaxEnsemble(DetectionPipeline):
    """Explicit frozen ensemble; threshold ratios, no invented forecast or root cause."""
    def __init__(self,members,member_ids,factor=1.):
        self.members=copy.deepcopy(members);self.member_ids=list(member_ids)
        self.template=members[0].template;self.algorithm='ensemble_max';self.spec=copy.deepcopy(members[0].spec)
        self.cadence=members[0].cadence
        if any(m.cadence!=self.cadence or m.spec['required']!=self.spec['required'] for m in members):raise ValueError('集成成员的输入或采样周期不同')
        self.pipeline_id=uuid.uuid4().hex;self.detector_id=uuid.uuid4().hex;self.preprocessor_id='member-preprocessing'
        self.calibrator_id='member-threshold-ratios';self.decision_id=uuid.uuid4().hex
        self.factor=finite_number(factor,.8,2.);self.policy=ThresholdPolicy(1.,self.factor)
    @property
    def window(self):return max(m.window for m in self.members)
    @property
    def capabilities(self):return {'multivariate':len(self.spec['targets'])>1,'history_samples':self.window,'reference_kind':'none','reference_band':False,'metric_contributions':False,'online_update':False,'stateful':False,'artifact_schema':3,'cadence_seconds':self.cadence,'minimum_samples':240}
    def fit(self,rows,labels=None):raise ValueError('集成使用已训练冻结成员，请创建集成版本')
    def partitions(self,rows):return self.members[0].partitions(rows)
    def predict(self,rows,factor=1.):
        scored=[{p['t']:p for p in m.predict(rows)} for m in self.members]
        if not scored:return []
        common=sorted(set.intersection(*(set(s) for s in scored)));original={r['t']:r for r in rows};out=[]
        for stamp in common:
            components={key:float(scored[i][stamp]['score']/scored[i][stamp]['threshold']) for i,key in enumerate(self.member_ids)}
            score=max(components.values());threshold,anomaly=self.policy.apply(score,factor)
            out.append({'t':stamp,'values':original[stamp]['values'],'raw_score':score,'raw_components':components,'raw_score_semantics':'maximum frozen-member calibrated score / member threshold',
                        'score':score,'calibrated_score':score,'calibrated_components':components,'threshold':threshold,'anomaly':anomaly,
                        'expected':{},'bounds':{},'reference_kind':'none','contributions':{},'reason_metric':None,'capabilities':self.capabilities,
                        'pipeline_id':self.pipeline_id,'calibrator_id':self.calibrator_id,'decision_id':self.decision_id,'preprocessor_id':self.preprocessor_id,'cadence_seconds':self.cadence})
        return out
    def metadata(self):return {'schema':3,'kind':'calibrated_max_ensemble','pipeline_id':self.pipeline_id,'detector_id':self.detector_id,'preprocessor_id':self.preprocessor_id,'calibrator_id':self.calibrator_id,'decision_id':self.decision_id,
                               'members':self.member_ids,'member_pipelines':[m.pipeline_id for m in self.members],'preprocessing':'frozen per member','calibration':'identity on calibrated member threshold ratios',
                               'decision':{'kind':'upper_threshold','threshold':1.,'factor':self.factor},'online_updates':False}
    def reconfigure(self,rows,calibration=None,factor=None):
        if calibration is not None:raise ValueError('集成不重新校准成员；请先创建成员新版本')
        clone=copy.deepcopy(self);clone.factor=finite_number(factor,.8,2.);clone.policy=ThresholdPolicy(1.,clone.factor)
        clone.pipeline_id=uuid.uuid4().hex;clone.decision_id=uuid.uuid4().hex;clone.report=clone.evaluate_partitions(rows)
        return clone
