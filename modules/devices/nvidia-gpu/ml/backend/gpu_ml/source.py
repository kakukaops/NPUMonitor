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
        entities={};nodes={}
        for row in values:
            labels=row['metric'];eid=self.identity(labels);name=labels.get('__name__');key=BY_NAME.get(name)
            if not eid or not key:continue
            entity=entities.setdefault(eid,{'id':eid,'cluster':eid.split('|',1)[0],'uuid':labels['UUID'],
                'name':labels.get('modelName','unverified'),'source_type':'simulated' if labels.get('simulated')=='true' else 'real_unverified',
                'values':{},'times':{},'quality':{},'seen_at':time.time()})
            for label in ('Hostname','hostname','node'):
                if labels.get(label):nodes.setdefault(eid,set()).add(labels[label])
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
        for eid,candidates in nodes.items():
            if len(candidates)==1:entities[eid]['node']=next(iter(candidates))
        return entities

    def history_samples(self, entity, start, end, step, metrics=None):
        cluster,uid=entity.split('|',1)
        filters='UUID='+json.dumps(uid)
        if cluster!=DEFAULT_CLUSTER:filters+=',cluster_id='+json.dumps(cluster)
        names = [METRICS[key]['name'] for key in metrics] if metrics else list(BY_NAME)
        selector = '{__name__=~' + json.dumps('|'.join(names)) + ',' + filters + '}'
        stamps=' or '.join('label_replace(timestamp('+name+'{'+filters+'}),"source_metric","'+name+'","",".*")' for name in names)
        rows=self.query(selector+' or '+stamps,start,end,step)
        values=[r for r in rows if 'source_metric' not in r['metric']]
        stamps=[r for r in rows if 'source_metric' in r['metric']]
        times, data, duplicates = {}, {}, {}
        for rows,is_time in [(stamps,True),(values,False)]:
            seen=set()
            for row in rows:
                labels=row['metric']
                if self.identity(labels)!=entity:continue
                name=labels.get('source_metric') if is_time else labels.get('__name__')
                key=BY_NAME.get(name)
                if key is None:continue
                target=times if is_time else data
                current=target.setdefault(key,{})
                series={float(t):float(v) for t,v in row['values']}
                if key in seen:
                    duplicates.setdefault(key,set()).update(current.keys()&series.keys())
                seen.add(key)
                current.update(series)
        return times, data, duplicates

    def history(self,entity,start,end,step=2,required=None):
        times, data, duplicates = self.history_samples(entity, start, end, step, required)
        required=required or list(data)
        if set(required).intersection(duplicates):raise ValueError('历史输入包含重复实体序列')
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

    def rolling_history(self, entity, current, cadence, required, window):
        if not window:
            return [current]
        stamp = current['t']
        # Query just after each historical cadence boundary so a scrape arriving a
        # few milliseconds later is not replaced by the preceding scrape.
        phase = min(cadence / 8, .5)
        try:
            history = self.history(
                entity, stamp - (window + 3) * cadence + phase, stamp - cadence + phase, cadence, required,
            )
        except ValueError as exc:
            if str(exc) != '历史缺少必需指标':
                raise
            history = []
        # Use the already validated current observation at its exact source time.
        return [*history, current]

    def monitor_history(self, entity, start, end, step, required, show):
        """Keep each evaluation opportunity and each displayed metric's observations."""
        keys = list(dict.fromkeys([*required, *show]))
        start = math.ceil(start * 1000) / 1000
        times, data, duplicates = self.history_samples(entity, start, end, step, keys)
        observations, frames = {key: {} for key in show}, []
        for index in range(int((end - start) / step) + 1):
            evaluation = round(start + index * step, 3)
            values, stamps, issues = {}, {}, {}
            for key in keys:
                value = data.get(key, {}).get(evaluation)
                stamp = times.get(key, {}).get(evaluation)
                spec = METRICS[key]
                if evaluation in duplicates.get(key, ()):
                    issues[key] = 'duplicate'
                elif value is None or stamp is None:
                    issues[key] = 'missing'
                elif (not math.isfinite(value) or not spec['min'] <= value <= spec['max']
                      or (key == 'job_running' and value not in (0, 1))):
                    issues[key] = 'invalid'
                elif not 0 <= evaluation - stamp <= FRESHNESS:
                    issues[key] = 'stale'
                else:
                    values[key], stamps[key] = value, stamp
            for key in show:
                if key in stamps and start <= stamps[key] <= end:
                    observations[key][stamps[key]] = values[key]
            blocking = sorted({issues[key] for key in required if key in issues})
            frame = {'t': evaluation, 'values': values}
            if blocking:
                frame['quality'] = ','.join(blocking)
                frame['input_issues'] = {key: issues[key] for key in required if key in issues}
            else:
                selected_times = [stamps[key] for key in required]
                if max(selected_times) - min(selected_times) > 2:
                    frame['quality'] = 'unaligned'
                else:
                    frame['source_time'] = min(selected_times)
            frames.append(frame)
        observed = {key: [{'t': stamp, 'values': {key: value}, 'cadence_seconds': step}
                          for stamp, value in sorted(series.items())] for key, series in observations.items()}
        return frames, observed
