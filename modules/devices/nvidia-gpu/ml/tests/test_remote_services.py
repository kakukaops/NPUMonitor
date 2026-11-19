import copy
from pathlib import Path
from types import SimpleNamespace
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

from gpu_ml.model_backends.services import ModelServices
from gpu_ml.model_backends.contracts import ScoreBatch,BackendProtocolError,BackendUnavailable
from gpu_ml.store import Store
from gpu_ml.settings import TEMPLATES
from gpu_ml.cli import restore


class FakePlatform:
    backend_id='default-test'
    url='http://model-platform:9470'
    def __init__(self,url=None,token_file=None,backend_id=None,timeout=12):
        self.url=url or self.url;self.token_file=token_file;self.backend_id=backend_id or self.backend_id
        self.platform_id='platform-1';self.failing=False;self.deploy_calls=0
    def info(self):
        if self.failing:raise BackendUnavailable('offline')
        return {'platform_id':self.platform_id,'operations':[]}
    def descriptor(self):return {'platform_id':self.platform_id,'model_ref':'remote-m','deployment_ref':'remote-d','entity':'cluster|gpu','source_type':'simulated','status':'validated','algorithm':'temporal_mad','input_contract':{'gpu_temp':{'metric_id':'nvidia.gpu_temp','unit':'°C'}},'feature_schema':copy.deepcopy(TEMPLATES['uni_gpu_temp']),'capabilities':{'history_samples':12,'cadence_seconds':2,'reference_kind':'causal_forecast'},'report':{}}
    def describe(self,ref):return self.descriptor()
    def catalog(self):
        wrong=self.descriptor();wrong.update(entity='other|gpu')
        return {'platform_id':self.platform_id,'models':[self.descriptor(),wrong]}
    def deployment(self,ref):return {'platform_id':self.platform_id,'model_ref':'remote-m','deployment_ref':ref,'status':'ready'}
    def deploy(self,*args):self.deploy_calls+=1;raise AssertionError('Do not redeploy an imported existing deployment')
    def predict(self,reference,rows,factor):
        if self.failing:raise BackendUnavailable('offline')
        return ScoreBatch([{'t':r['t'],'values':r['values'],'score':0.,'threshold':1.,'anomaly':False,'expected':{'gpu_temp':60.},'bounds':{'gpu_temp':[55.,65.]}} for r in rows],'valid')


class RemoteServicesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.store=Store(self.root/'db')
        self.store.put('task','task',{'entity':'cluster|gpu','scope':'simulated','template':'uni_gpu_temp','enabled':True,'active_model':'old'})
        self.now=time.time();self.store.put('entity','cluster|gpu',{'quality':{'gpu_temp':'valid'},'values':{'gpu_temp':60.},'times':{'gpu_temp':self.now}})
        self.backend=FakePlatform()
        source=SimpleNamespace(history=lambda entity,start,end,cadence,required:[{'t':end-2*i,'values':{'gpu_temp':60.+i*.01}} for i in reversed(range(16))])
        self.engine=SimpleNamespace(store=self.store,backend=self.backend,training=SimpleNamespace(status={'state':'available'}),source=source)
        self.services=ModelServices(self.engine);self.services.secret_root=self.root/'secrets'
    def tearDown(self):self.tmp.cleanup()
    def test_catalog_filters_scope_import_is_idempotent_and_does_not_publish(self):
        catalog=self.services.catalog(self.backend.backend_id,'task')
        self.assertEqual(len(catalog['models']),1);self.assertEqual(catalog['excluded'],1)
        model=self.services.register(self.backend.backend_id,'task','remote-m')
        again=self.services.register(self.backend.backend_id,'task','remote-m')
        self.assertEqual(model['id'],again['id']);self.assertEqual(len(self.store.list('model')),1)
        self.assertTrue(model['external_registration']);self.assertNotIn('snapshot',model)
        self.assertEqual(model['backend']['deployment_ref'],'remote-d');self.assertEqual(model['execution_location'],'reference')
        self.assertEqual(self.store.get('task','task')['active_model'],'old');self.assertEqual(self.store.history('task'),[])
        self.assertTrue(model['connection_validation']['passed'])
    def test_invalid_schema_platform_and_unavailable_preserve_online_model(self):
        original=self.backend.describe
        for change in ({'input_contract':{}},{'entity':'other|gpu'},{'source_type':'real_unverified'},{'platform_id':'wrong'},{'status':'review_required'},{'capabilities':{'history_samples':True,'cadence_seconds':2,'reference_kind':'causal_forecast'}}):
            with patch.object(self.backend,'describe',return_value={**original('remote-m'),**change}):
                with self.assertRaises((ValueError,BackendProtocolError)):self.services.register(self.backend.backend_id,'task','remote-m')
        self.backend.failing=True
        with self.assertRaises(BackendUnavailable):self.services.register(self.backend.backend_id,'task','remote-m')
        self.assertEqual(self.store.list('model'),[]);self.assertEqual(self.store.get('task','task')['active_model'],'old')
    def test_fresh_history_and_declared_reference_are_required(self):
        with patch.object(self.engine.source,'history',return_value=[]):
            with self.assertRaises(ValueError):self.services.register(self.backend.backend_id,'task','remote-m')
        with patch.object(self.backend,'predict',return_value=ScoreBatch([{'t':self.now,'expected':{}}],'valid')):
            with self.assertRaises(BackendProtocolError):self.services.register(self.backend.backend_id,'task','remote-m')
        self.assertEqual(self.store.list('model'),[])
    def test_credentials_are_private_and_rotation_is_atomic(self):
        with patch('gpu_ml.model_backends.services.HttpModelBackend',FakePlatform):
            service=self.services.create('Company','https://models.example.internal','secret-one',8)
            secret=self.services.secret_root/service['id']
            self.assertEqual(secret.stat().st_mode&0o777,0o600)
            self.assertNotIn('secret-one',repr(self.services.list()))
            self.assertIsNot(self.services.backend(service['id']),self.backend)
            self.services.credentials(service['id'],'secret-two');self.assertEqual(secret.read_text(),'secret-two')
            with patch.object(FakePlatform,'info',return_value={'platform_id':'different'}):
                with self.assertRaises(BackendProtocolError):self.services.credentials(service['id'],'secret-three')
            self.assertEqual(secret.read_text(),'secret-two');self.assertFalse(list(self.services.secret_root.glob('*.pending')))
            with patch.object(FakePlatform,'info',side_effect=BackendUnavailable('offline')):
                with self.assertRaises(BackendUnavailable):self.services.create('Bad','https://bad.invalid','no-save',8)
            self.assertEqual(len(self.store.list('model_service')),1)
    def test_imported_reference_backup_restore_without_training_snapshot(self):
        self.services.register(self.backend.backend_id,'task','remote-m')
        saved=self.root/'copy.sqlite';self.store.backup(saved);archive=self.root/'backup.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:tar.add(saved,arcname='gpu-ml.sqlite')
        target=self.root/'restored';restore(archive,target)
        self.assertEqual(Store(target/'gpu-ml.sqlite').list('model')[0]['backend']['model_ref'],'remote-m')
    def test_existing_deployment_can_be_published_without_local_weights(self):
        from gpu_ml.engine import Engine
        model=self.services.register(self.backend.backend_id,'task','remote-m')
        engine=Engine.__new__(Engine);engine.store=self.store;engine.services=self.services;engine.models={}
        import threading
        engine.lock=threading.RLock()
        engine.publish('task',model['id'],'tester')
        self.assertEqual(self.store.get('task','task')['active_model'],model['id']);self.assertEqual(self.backend.deploy_calls,0)
        result=engine.load(model['id']).evaluate([{'t':self.now,'values':{'gpu_temp':60.}}])
        self.assertEqual(result.quality,'valid')
        self.backend.failing=True
        with self.assertRaises(BackendUnavailable):engine.load(model['id']).evaluate([{'t':self.now,'values':{'gpu_temp':60.}}])
