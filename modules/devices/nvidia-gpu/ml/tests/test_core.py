import json
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np
from gpu_ml.models import GPUModel
from gpu_ml.simulation import healthy,Simulator,UUIDS
from gpu_ml.store import Store,Conflict
from gpu_ml.source import Source
from gpu_ml.settings import METRICS


def rows(start=0,count=900,seed=5):
    ts=np.arange(start,start+count*2,2,dtype=float);values=healthy(ts,0,seed)
    return [{'t':float(t),'values':{k:float(v[i]) for k,v in values.items()}} for i,t in enumerate(ts)]


class ModelTests(unittest.TestCase):
    def test_gpu_anomalies_and_normal_high_load(self):
        train=rows()
        for template,signals in [('thermal',('gpu_temp','memory_temp')),('relation',('power','sm_clock')),('activity',('util',))]:
            with self.subTest(template=template):
                model=GPUModel(template);report=model.fit(train)
                normal=rows(3000,200,23)
                scores=model.predict(normal)
                self.assertLess(sum(p['anomaly'] for p in scores)/len(scores),.08)
                abnormal=json.loads(json.dumps(normal))
                for r in abnormal:
                    if template=='thermal':r['values']['gpu_temp']+=18;r['values']['memory_temp']+=16
                    elif template=='relation':r['values']['power']+=90;r['values']['sm_clock']-=240
                    else:r['values']['util']=4
                self.assertGreater(np.mean([p['anomaly'] for p in model.predict(abnormal)]),.95)
                self.assertLess(report['train_end'],report['calibration_start'])
                self.assertLess(report['calibration_start'],report['test_start'])
                a=model.predict(normal[:20]);b=model.predict(normal)
                self.assertEqual(a,b[:20])

    def test_robust_model_and_artifact_integrity(self):
        model=GPUModel('thermal','robust_mad');model.fit(rows())
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'model.joblib';digest=model.save(p)
            self.assertEqual(model.predict(rows(2000,3)),GPUModel.load(p,digest).predict(rows(2000,3)))
            p.write_bytes(p.read_bytes()+b'x')
            with self.assertRaises(ValueError):GPUModel.load(p,digest)

    def test_insufficient_and_duplicate_training_rejected(self):
        with self.assertRaises(ValueError):GPUModel('thermal').fit(rows(count=30))
        sample=rows();sample[1]['t']=sample[0]['t']
        with self.assertRaises(ValueError):GPUModel('thermal').fit(sample)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.store=Store(self.path)
    def tearDown(self):self.tmp.cleanup()
    def sample(self,t,anomaly):
        return {'t':t,'model':'v1','score':2 if anomaly else .5,'threshold':1.,'anomaly':anomaly,'values':{},'expected':{},'bounds':{}}
    def test_duplicates_do_not_confirm_and_unknown_holds_across_restart(self):
        self.store.apply('t',self.sample(100,True),now=100)
        for _ in range(10):self.store.apply('t',self.sample(100,True),now=100)
        self.assertFalse(self.store.get('state','t')['active'])
        self.store.apply('t',self.sample(102,True),now=102);self.store.apply('t',self.sample(104,True),now=104)
        episode=self.store.get('state','t')['episode_id'];self.assertTrue(self.store.get('state','t')['active'])
        self.store.apply('t',quality='missing',now=106);self.store=Store(self.path)
        self.assertEqual(self.store.get('state','t')['episode_id'],episode)
        self.assertTrue(self.store.get('state','t')['active'])
        for t in (120,122,124):self.store.apply('t',self.sample(t,False),now=t)
        self.assertFalse(self.store.get('state','t')['active'])
        self.assertEqual(self.store.get('state','t')['reason'],'fresh_normal_confirmed')
    def test_gap_resets_pending_and_out_of_order_ignored(self):
        for t in (100,102,120):self.store.apply('t',self.sample(t,True),now=t)
        self.assertFalse(self.store.get('state','t')['active'])
        self.store.apply('t',self.sample(99,True),now=121)
        self.assertEqual(self.store.get('state','t')['last_source'],120)
    def test_revision_backup_and_jobs_interrupted(self):
        self.store.put('task','a',{'enabled':True},expected=0)
        with self.assertRaises(Conflict):self.store.put('task','a',{'enabled':False},expected=0)
        self.store.put('job','j',{'status':'running'})
        self.store.backup(Path(self.tmp.name)/'backup')
        restored=Store(Path(self.tmp.name)/'backup')
        self.assertTrue(restored.get('task','a')['enabled'])
        self.assertEqual(restored.get('job','j')['status'],'failed')


class SourceTests(unittest.TestCase):
    def test_quality_duplicate_stale_and_mig_exclusion(self):
        now=time.time();name=METRICS['gpu_temp']['name']
        def observation(uid,val,ts,replica=None,mig=False):
            labels={'cluster_id':'c','UUID':uid,'__name__':name}
            if replica:labels['replica']=replica
            if mig:labels['GPU_I_ID']='1'
            timestamp=dict(labels);timestamp.pop('__name__');timestamp['source_metric']=name
            return [{'metric':labels,'value':[now,str(val)]},{'metric':timestamp,'value':[now,str(ts)]}]
        sample=observation('GPU-1',55,now)+observation('GPU-2','NaN',now)+observation('GPU-3',50,now-100)+observation('GPU-4',50,now)+observation('GPU-4',50,now,'b')+observation('GPU-MIG',55,now,mig=True)
        class Fake(Source):
            def query(self,*args,**kwargs):return sample
        entities=Fake().current()
        self.assertEqual(entities['c|GPU-1']['values']['gpu_temp'],55)
        self.assertEqual(entities['c|GPU-2']['quality']['gpu_temp'],'invalid')
        self.assertEqual(entities['c|GPU-3']['quality']['gpu_temp'],'stale')
        self.assertEqual(entities['c|GPU-4']['quality']['gpu_temp'],'duplicate')
        self.assertNotIn('c|GPU-MIG',entities)
    def test_query_limits_and_simulator_scope(self):
        with self.assertRaises(ValueError):Source().query('up',0,86400*100,2)
        simulator=Simulator();simulator.set(UUIDS[0],'temperature_spike');body=simulator.metrics()
        self.assertIn('modelName="SIMULATED-H100"',body)
        with self.assertRaises(ValueError):simulator.set('GPU-REAL','missing')



class ExtensionTests(unittest.TestCase):
    def test_registered_adapter_and_shadow_never_updates_live_state(self):
        from gpu_ml.models import build_model,RobustMADModel,register_model
        model=build_model('thermal','robust_mad')
        self.assertIsInstance(model,RobustMADModel)
        with self.assertRaises(ValueError):register_model('robust_mad','duplicate',RobustMADModel)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db')
            store.record_shadow('task',{'t':100,'model':'shadow-v1','score':100,'threshold':1,'anomaly':True})
            self.assertIsNone(store.get('state','task'))
            self.assertEqual(store.history('task'),[])
            self.assertTrue(store.get('shadow','task')['anomaly'])

class InitializationTests(unittest.TestCase):
    def test_lost_volume_and_source_change_refuse_silent_reinitialization(self):
        from gpu_ml.store import check_initialization
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);guard=root/'guard';guard.write_text('pending')
            check_initialization(root/'db',guard)
            store=Store(root/'db');store.bind_source('binding-a');store.bind_source('binding-a')
            with self.assertRaises(ValueError):store.bind_source('binding-b')
            guard.write_text('initialized');check_initialization(root/'db',guard)
            with self.assertRaises(ValueError):check_initialization(root/'lost-db',guard)

if __name__=='__main__':unittest.main()
