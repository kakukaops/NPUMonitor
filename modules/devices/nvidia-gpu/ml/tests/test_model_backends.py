import ast,copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from gpu_ml.model_backends.contracts import validate_prediction,BackendProtocolError,BackendUnavailable,BackendUnsupported
from gpu_ml.model_backends.http import HttpModelBackend
from gpu_ml.store import Store

class BackendContractTests(unittest.TestCase):
    def sample(self):
        rows=[{'t':100.,'values':{'gpu_temp':60.}}];ref={'platform_id':'p1','model_ref':'m1','deployment_ref':'d1'}
        response={'contract_version':1,'platform_id':'p1','model_ref':'m1','deployment_ref':'d1','quality':'valid','points':[{'t':100.,'values':rows[0]['values'],'score':2.,'threshold':1.,'anomaly':True,'expected':{},'bounds':{}}]}
        return rows,ref,response
    def test_valid_and_invalid_model_responses(self):
        rows,ref,response=self.sample();self.assertTrue(validate_prediction(response,ref,rows).points[0]['anomaly'])
        for mutate in (lambda x:x.update(platform_id='other'),lambda x:x.update(deployment_ref='other'),lambda x:x['points'][0].update(t=101.),lambda x:x['points'][0].update(score=float('nan')),lambda x:x['points'][0].update(anomaly=False),lambda x:x['points'][0].update(values={'gpu_temp':61.}),lambda x:x.update(points=[])):
            changed=copy.deepcopy(response);mutate(changed)
            with self.assertRaises(BackendProtocolError):validate_prediction(changed,ref,rows)
    def test_backend_does_not_follow_returned_urls_or_cross_namespaces(self):
        backend=HttpModelBackend(url='http://localhost:9470',token_file='/not/read',backend_id='company-a')
        with self.assertRaises(BackendUnsupported):backend.predict({'backend_id':'company-b'},[],1.)
        for url in ('file:///data/model','http://user:password@host','http://host?token=secret'):
            with self.assertRaises(ValueError):HttpModelBackend(url=url)
    def test_submit_retry_uses_same_id_and_body(self):
        backend=HttpModelBackend(url='http://localhost:9470',token_file='/not/read')
        with patch.object(backend,'call',side_effect=[BackendUnavailable('timeout'),{'contract_version':1,'status':'queued'}]) as call:
            backend.submit('stable-id','fit',{'dataset':{'sha256':'a'}})
            self.assertEqual(call.call_args_list[0],call.call_args_list[1])
    def test_external_training_is_reconciled_after_monitor_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'db');store.put('job','external',{'status':'running','backend_request_id':'remote-id'})
            store.put('job','legacy',{'status':'running'})
            recovered=Store(Path(tmp)/'db');self.assertEqual(recovered.get('job','external')['status'],'pending_sync');self.assertEqual(recovered.get('job','legacy')['status'],'failed')
    def test_monitor_engine_and_coordinator_do_not_fit_or_save_models(self):
        import gpu_ml.engine
        root=Path(gpu_ml.engine.__file__).parent
        for path in (root/'engine.py',root/'model_backends/training.py'):
            tree=ast.parse(path.read_text())
            calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
            self.assertNotIn('fit',calls);self.assertNotIn('save',calls)

    def test_company_backend_can_replace_reference_without_local_training(self):
        import threading,time
        import gpu_ml.engine as engine_module
        import gpu_ml.model_backends.training as training_module
        from gpu_ml.model_backends.contracts import ScoreBatch,dataset_hash
        from gpu_ml.settings import TEMPLATES
        class CompanyStub:
            backend_id='company-contract-test'
            submits=0
            def info(self):return {'platform_id':'company-p','operations':['fit']}
            def submit(self,ident,operation,payload):
                self.submits+=1
                spec=payload['training_spec'];self.result={'contract_version':1,'platform_id':'company-p','model_ref':'company-m',
                    'dataset_sha256':payload['dataset']['sha256'],'feature_schema':spec['feature_schema'],'source_type':spec['source_type'],
                    'report':{'held_out_point_alert_rate':0.},'capabilities':{'history_samples':0,'cadence_seconds':2,'reference_kind':'none'},
                    'algorithm':spec['algorithm'],'pipeline':{},'status':'validated'}
                return {'contract_version':1,'platform_id':'company-p','status':'completed'}
            def job(self,ident):return {'contract_version':1,'platform_id':'company-p','status':'completed','result':self.result}
            def cancel(self,ident):return {'status':'cancelled'}
            def deploy(self,model_ref,platform_id):return {'deployment_ref':'company-d','model_ref':model_ref,'platform_id':platform_id,'status':'ready'}
            def predict(self,reference,rows,factor):return ScoreBatch([{'t':r['t'],'values':r['values'],'score':0.,'threshold':factor,'anomaly':False,'expected':{},'bounds':{}} for r in rows],'valid')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=Store(root/'db');store.put('task','task',{'entity':'cluster|gpu','template':'uni_gpu_temp','scope':'simulated','enabled':True,'active_model':None})
            with patch.object(engine_module,'DATA',root),patch.object(training_module,'DATA',root):
                engine=engine_module.Engine(store,object(),model_backend=CompanyStub())
                try:
                    rows=[{'t':float(i*2),'values':{'gpu_temp':60.}} for i in range(240)]
                    model_id=engine.train_now('task',rows,'contract-test','temporal_mad')
                    record=store.get('model',model_id);self.assertNotIn('artifact',record);self.assertEqual(record['backend']['backend_id'],'company-contract-test')
                    with patch.object(engine.backend,'deploy',return_value={'model_ref':'company-m','platform_id':'company-p','deployment_ref':'not-ready','status':'starting'}):
                        with self.assertRaises(BackendUnavailable):engine.publish('task',model_id,'tester')
                    self.assertIsNone(store.get('task','task')['active_model'])
                    engine.publish('task',model_id,'tester');self.assertEqual(store.get('model',model_id)['backend']['deployment_ref'],'company-d')
                    batch=engine.score_batch(engine.load(model_id),rows[-1:]);self.assertEqual(batch.quality,'valid')
                    self.assertFalse(batch.points[-1]['anomaly'])
                    # A monitor restart may leave an acknowledged external job pending.
                    first_job=next(j for j in store.list('job') if j.get('model_id')==model_id)
                    pending={k:v for k,v in first_job.items() if k not in ('id','revision','model_id')}
                    pending.update(status='pending_sync',model_version='reconciled-version')
                    store.put('job','pending-recovery',pending)
                    deadline=time.time()+6
                    while store.get('job','pending-recovery')['status']!='completed' and time.time()<deadline:time.sleep(.05)
                    self.assertEqual(store.get('job','pending-recovery')['status'],'completed')
                    self.assertEqual(engine.backend.submits,1)
                    self.assertEqual(store.get('task','task')['active_model'],model_id)
                    with patch.object(engine.backend,'submit',side_effect=BackendUnsupported('operation not supported')):
                        with self.assertRaises(BackendUnsupported):engine.reconfigure(model_id,factor=1.1)
                    self.assertTrue(all(j['status']=='failed' for j in store.list('job') if j.get('kind')=='model_operation'))
                    self.assertEqual(store.get('task','task')['active_model'],model_id)
                finally:engine.stop.set();engine.training.close();engine.executor.shutdown()

    def test_slow_api_cannot_turn_stale_observations_into_normal_evidence(self):
        from gpu_ml.engine import Engine
        engine=Engine.__new__(Engine)
        with patch('gpu_ml.engine.time.time',return_value=200.):
            self.assertFalse(engine.observation_is_fresh(150.))
            self.assertFalse(engine.observation_is_fresh(210.))
            self.assertTrue(engine.observation_is_fresh(199.))
