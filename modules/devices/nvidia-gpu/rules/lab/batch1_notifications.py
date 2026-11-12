"""Conservative local notification contract. Raw engine exits never prove repair."""
HARDWARE={'batch1_sram_threshold_exceeded','batch1_row_remap_failed'}


def interpret(payload):
    result=[]
    if not isinstance(payload,list): return result
    for event in payload:
        if not isinstance(event,dict): continue
        tags=event.get('tags_map') or dict(t.split('=',1) for t in event.get('tags',[]) if '=' in t)
        rule=tags.get('rule_id','')
        if not rule.startswith('batch1_'): continue
        exited=bool(event.get('is_recovered'))
        hardware=rule in HARDWARE
        result.append({'rule_id':rule,'UUID':tags.get('UUID'),'metric_name':tags.get('metric_name'),
            'cluster_id':tags.get('cluster_id'),'hash':event.get('hash'),
            'state':'condition_exited' if exited else 'condition_active',
            'end_reason':('unverified_condition_exit' if hardware else 'quality_condition_exit') if exited else None,
            'hardware_recovery_confirmed':False,
            'raw_nightingale_is_recovered':exited,
            'message':('检测条件退出，原因待核验；不能据此判断硬件修复' if hardware else '数据质量检测条件退出') if exited else '检测条件成立'})
    return result
