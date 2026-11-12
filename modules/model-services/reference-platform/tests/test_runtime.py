import copy,json,tempfile,time,unittest,threading
from pathlib import Path
from unittest.mock import patch
from gpu_ml_platform.runtime import Runtime,Conflict
from model_contracts import dataset_hash,validate_prediction
from gpu_ml_runtime.catalog import TEMPLATES
import numpy as np

def payload(ident='job1'):
    ts=np.arange(0,2400,2,dtype=float);rng=np.random.default_rng(7);u=72+17*np.sin(ts*2*np.pi/180)+rng.normal(0,.8,len(ts));power=70+3.5*u+rng.normal(0,1.3,len(ts));temp=30+.055*power+.1*u+rng.normal(0,.25,len(ts))
    rows=[{'t':float(t),'values':{'gpu_temp':float(temp[i])}} for i,t in enumerate(ts)]
    return {'contract_version':1,'request_id':ident,'operation':'fit','training_spec':{'template':'uni_gpu_temp','algorithm':'temporal_mad','feature_schema':TEMPLATES['uni_gpu_temp'],'source_type':'simulated','pipeline':{},'labels':[]},'dataset':{'sha256':dataset_hash(rows),'rows':rows}}

class RuntimeTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.runtime=Runtime(self.tmp.name,True)
    def tearDown(self):self.runtime.close();self.tmp.cleanup()
    def done(self,ident):
        deadline=time.time()+15
        while time.time()<deadline:
            j=self.runtime.job(ident)
            if j['status'] in ('completed','failed','cancelled'):return j
            time.sleep(.02)
        self.fail('worker timeout')
    def train(self,ident='job1'):
        self.runtime.submit(payload(ident));job=self.done(ident);self.assertEqual(job['status'],'completed',job)
        return job['result']
    def test_idempotency_training_deployment_prediction(self):
        body=payload();self.runtime.submit(body);self.runtime.submit(body)
        altered=copy.deepcopy(body);altered['training_spec']['pipeline']={'decision':{'factor':1.2}}
        with self.assertRaises(Conflict):self.runtime.submit(altered)
        job=self.done('job1');self.assertEqual(job['status'],'completed',job);model=job['result'];pid=model['platform_id']
        deployed=self.runtime.deploy(model['model_ref'],pid);self.assertEqual(deployed,self.runtime.deploy(model['model_ref'],pid))
        rows=body['dataset']['rows'][-80:];output=self.runtime.predict(deployed['deployment_ref'],rows,1.,True,pid)
        batch=validate_prediction(output,{'platform_id':pid,'model_ref':model['model_ref'],'deployment_ref':deployed['deployment_ref']},rows)
        self.assertEqual(batch.quality,'valid');self.assertTrue(batch.points)
        with self.assertRaises(Conflict):self.runtime.predict(model['model_ref'],rows,platform_id='other-platform')
    def test_dataset_digest_mismatch_is_failed_not_a_model(self):
        body=payload();body['dataset']['sha256']='wrong';self.runtime.submit(body);job=self.done('job1')
        self.assertEqual(job['status'],'failed');self.assertEqual(self.runtime.registry.list('model'),[])
    def test_postprocess_keeps_detector_and_creates_new_version(self):
        model=self.train();self.runtime.submit({'contract_version':1,'request_id':'post','operation':'postprocess','platform_id':model['platform_id'],'model_ref':model['model_ref'],'factor':1.5})
        job=self.done('post');self.assertEqual(job['status'],'completed',job);new=job['result']
        self.assertEqual(model['pipeline']['detector_id'],new['pipeline']['detector_id']);self.assertNotEqual(model['pipeline']['decision_id'],new['pipeline']['decision_id'])
    def test_deployment_survives_restart_with_stable_platform_identity(self):
        model=self.train();deployment=self.runtime.deploy(model['model_ref'],model['platform_id']);self.runtime.close()
        self.runtime=Runtime(self.tmp.name,True);self.assertEqual(self.runtime.registry.platform_id,model['platform_id'])
        result=self.runtime.predict(deployment['deployment_ref'],payload()['dataset']['rows'][-60:],deployed=True,platform_id=model['platform_id']);self.assertEqual(result['quality'],'valid')
    def test_queued_cancel_and_restarted_job_failure(self):
        real=self.runtime.execute;entered=threading.Event();release=threading.Event()
        def blocked(key):
            if key=='first':entered.set();release.wait(5)
            return real(key)
        self.runtime.execute=blocked
        self.runtime.submit(payload('first'));self.assertTrue(entered.wait(2));self.runtime.submit(payload('second'));self.runtime.cancel('second');release.set()
        self.assertEqual(self.done('second')['status'],'cancelled')
        self.runtime.close();self.runtime.registry.put('job','interrupted',{'request_id':'interrupted','status':'running'})
        self.runtime=Runtime(self.tmp.name,True);self.assertEqual(self.runtime.job('interrupted')['status'],'failed')
    def test_profile_is_enforced_by_platform_itself(self):
        body=payload();body['training_spec'].update(template='dcgm_thermal_relation_laboratory',algorithm='dcgm_conditional',feature_schema=TEMPLATES['dcgm_thermal_relation_laboratory'],source_type='real_unverified')
        self.runtime.submit(body);self.assertEqual(self.done('job1')['status'],'failed')
