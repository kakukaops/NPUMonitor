"""Source-time replay metrics. Unlabelled points are never presumed healthy."""
import math
import numpy as np

def validate_labels(labels,start,end):
    if not isinstance(labels,list) or len(labels)>100:raise ValueError('标注最多100段')
    clean=[]
    for label in labels:
        a=float(label['start']);b=float(label['end']);kind=label['kind']
        if not math.isfinite(a+b) or not start<=a<b<=end or kind not in ('fault','normal_change','collection_problem','unconfirmed'):raise ValueError('标注类型或时间范围无效')
        if any(a<x['end'] and b>x['start'] for x in clean):raise ValueError('标注时间段不可重叠')
        clean.append({'start':a,'end':b,'kind':kind})
    return clean

def summarize(points,rows,labels=None,cadence=2,elapsed=None):
    annotations=labels or [];normal=[];fault=[]
    for p in points:
        kind=next((x['kind'] for x in annotations if x['start']<=p['t']<x['end']),None)
        if kind=='normal_change':normal.append(p)
        elif kind=='fault':fault.append(p)
    fault_events=[]
    for label in annotations:
        if label['kind']!='fault':continue
        observed=[p for p in points if label['start']<=p['t']<label['end']]
        hits=[p for p in observed if p['anomaly']]
        fault_events.append({'start':label['start'],'end':label['end'],'scored_points':len(observed),'detected':bool(hits) if observed else None,'first_detection_delay_seconds':hits[0]['t']-label['start'] if hits else None})
    tp=sum(p['anomaly'] for p in fault);fp=sum(p['anomaly'] for p in normal)
    episodes=0;previous=None
    for p in points:
        if p['anomaly'] and (previous is None or not previous['anomaly'] or p['t']-previous['t']>cadence*4):episodes+=1
        previous=p
    out={'source_points':len(rows),'scored_points':len(points),'unscored_points':max(0,len(rows)-len(points)),
         'point_alert_rate':float(np.mean([p['anomaly'] for p in points])) if points else None,
         'condition_episode_count':episodes,'source_gap_count':sum(b['t']-a['t']>cadence*1.25 for a,b in zip(rows,rows[1:])),
         'normal_labelled_points':len(normal),'fault_labelled_points':len(fault),
         'normal_labelled_alert_rate':fp/len(normal) if normal else None,
         'labelled_point_recall':tp/len(fault) if fault else None,
         'labelled_point_precision':tp/(tp+fp) if fault and normal and tp+fp else None,
         'fault_intervals':fault_events,'label_scope':'explicit annotations only; unlabelled is not normal',
         'metric_scope':'raw detector decisions; condition episodes are not Nightingale events'}
    if elapsed is not None:out.update(scoring_seconds=elapsed,scoring_ms_per_point=1000*elapsed/len(points) if points else None)
    return out
