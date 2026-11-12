"""Bounded, read-only queries; join observations by original source timestamps."""
import json
import os
import base64
from pathlib import Path
import math
import time
from urllib.parse import urlencode,urlsplit
from urllib.request import ProxyHandler, Request, build_opener
import threading
from .settings import METRICS, PROMETHEUS, DEFAULT_CLUSTER, FRESHNESS, MAX_POINTS

BY_NAME={v['name']:k for k,v in METRICS.items()}
SELECTOR='{__name__=~"'+ '|'.join(BY_NAME)+'"}'
TIMESTAMPS=' or '.join('label_replace(timestamp('+v['name']+'),"source_metric","'+v['name']+'","",".*")' for v in METRICS.values())


from accelerator_integrations.prometheus import PrometheusClient

class Source(PrometheusClient):
    def __init__(self,url=PROMETHEUS):
        super().__init__(url,auth_file=os.environ.get('GPU_ML_PROMETHEUS_AUTH_FILE'),max_points=MAX_POINTS)

    @staticmethod
    def identity(labels):
        uuid=labels.get('UUID')
        if not uuid or labels.get('GPU_I_ID') or labels.get('GPU_I_PROFILE'): return None
        cluster=labels.get('cluster_id',DEFAULT_CLUSTER)
        return cluster+'|'+uuid

    def current(self):
        rows=self.query(SELECTOR+' or '+TIMESTAMPS)
        values=[r for r in rows if 'source_metric' not in r['metric']]
        timestamps=[r for r in rows if 'source_metric' in r['metric']]
        time_map={}
        for row in timestamps:
            labels=row['metric'];entity=self.identity(labels)
            if entity:
                key=(entity,labels.get('source_metric'),tuple(sorted((k,v) for k,v in labels.items() if k not in ('__name__','source_metric'))))
                time_map[key]=float(row['value'][1])
        entities={}
        for row in values:
            labels=row['metric'];eid=self.identity(labels);name=labels.get('__name__');key=BY_NAME.get(name)
            if not eid or not key:continue
            entity=entities.setdefault(eid,{'id':eid,'cluster':eid.split('|',1)[0],'uuid':labels['UUID'],
                'name':labels.get('modelName','unverified'),'source_type':'simulated' if labels.get('simulated')=='true' else 'real_unverified',
                'values':{},'times':{},'quality':{},'seen_at':time.time()})
            signature=(eid,name,tuple(sorted((k,v) for k,v in labels.items() if k not in ('__name__','source_metric'))))
            stamp=time_map.get(signature)
            value=float(row['value'][1]);spec=METRICS[key]
            quality='valid'
            if key in entity['quality']:quality='duplicate'
            elif key=='job_running' and value not in (0,1):quality='invalid'
            elif not math.isfinite(value) or not spec['min']<=value<=spec['max']:quality='invalid'
            elif stamp is None or not 0<=time.time()-stamp<=FRESHNESS:quality='stale'
            entity['quality'][key]=quality
            if quality=='valid':entity['values'][key]=value;entity['times'][key]=stamp
            else:entity['values'].pop(key,None);entity['times'].pop(key,None)
        return entities

    def history(self,entity,start,end,step=2,required=None):
        cluster,uid=entity.split('|',1)
        filters='UUID='+json.dumps(uid)
        if cluster!=DEFAULT_CLUSTER:filters+=',cluster_id='+json.dumps(cluster)
        selector=SELECTOR[:-1]+','+filters+'}'
        stamps=' or '.join('label_replace(timestamp('+v['name']+'{'+filters+'}),"source_metric","'+v['name']+'","",".*")' for v in METRICS.values())
        rows=self.query(selector+' or '+stamps,start,end,step)
        values=[r for r in rows if 'source_metric' not in r['metric']]
        stamps=[r for r in rows if 'source_metric' in r['metric']]
        times={};data={};duplicates=set()
        for rows,is_time in [(stamps,True),(values,False)]:
            seen=set()
            for row in rows:
                labels=row['metric']
                if self.identity(labels)!=entity:continue
                name=labels.get('source_metric') if is_time else labels.get('__name__')
                key=BY_NAME.get(name)
                if key is None:continue
                if key in seen:duplicates.add(key)
                seen.add(key)
                target=times if is_time else data
                target[key]={float(t):float(v) for t,v in row['values']}
        required=required or list(data)
        if set(required)&duplicates:raise ValueError('历史输入包含重复实体序列')
        if any(k not in data or k not in times for k in required):raise ValueError('历史缺少必需指标')
        grid=sorted(set.intersection(*(set(data[k]) for k in required))) if required else []
        output={}
        for evaluation in grid:
            sample={};source_times=[]
            for key in required:
                val=data[key].get(evaluation);stamp=times[key].get(evaluation);spec=METRICS[key]
                if val is None or stamp is None or not math.isfinite(val) or not spec['min']<=val<=spec['max'] or not 0<=evaluation-stamp<=FRESHNESS:break
                sample[key]=val;source_times.append(stamp)
            else:
                # Do not combine columns whose scrape epochs are far apart.
                if max(source_times)-min(source_times)<=2:
                    output[min(source_times)]={'t':min(source_times),'values':sample}
        return [output[k] for k in sorted(output)]
