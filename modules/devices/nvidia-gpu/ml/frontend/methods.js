'use strict';
(() => {
  const data = window.METHODS_DATA;
  const $ = id => document.getElementById(id);
  if (!data) {
    $('benchmarkNote').textContent = '评测数据尚未生成。请运行 build_methods_frontend_data.py。';
    return;
  }
  const smd = data.smd;
  const gwdg = data.gwdg.core5;
  const trace = data.trace;
  let selectedDataset = 'smd';
  let selectedMetric = 'gpu_temp';
  const metricLabels = {gpu_temp:'GPU 温度', power:'板卡功耗', util:'GPU 利用率', mem_util:'显存控制器活动', sm_clock:'SM 时钟'};
  const number = value => Number(value).toLocaleString('zh-CN');
  const fraction = (a,b) => b ? Math.round(a / b * 1000) / 10 : 0;

  function setText(id, value) { $(id).textContent = String(value); }
  function node(tag, className, content) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (content !== undefined) element.textContent = String(content);
    return element;
  }

  function renderHero() {
    setText('heroHit', `${smd.adaptive.hit_events} / ${smd.events}`);
    setText('heroNoise', `−${fraction(smd.static.false_alert_episodes - smd.adaptive.false_alert_episodes, smd.static.false_alert_episodes)}%`);
    setText('heroCoverage', `${gwdg.scored_incidents} / ${gwdg.input_incidents}`);
  }

  function benchmarkRow(label, ratio, value, cost, highlighted) {
    const row = node('div','benchmark-row');
    const name = node('div','benchmark-name',label);
    const track = node('div','benchmark-track');
    const fill = node('i','benchmark-fill'+(highlighted?' teal':''));
    fill.style.width = `${Math.max(2,Math.min(100,ratio))}%`;
    track.append(fill);
    row.append(name,track,node('div','benchmark-value',value),node('div','benchmark-cost',cost));
    return row;
  }

  function renderBenchmark() {
    const isSmd = selectedDataset === 'smd';
    $('tabSmd').classList.toggle('selected',isSmd);
    $('tabGwdg').classList.toggle('selected',!isSmd);
    $('tabSmd').setAttribute('aria-selected',String(isSmd));
    $('tabGwdg').setAttribute('aria-selected',String(!isSmd));
    $('benchmarkBadge').textContent = isSmd?'SMD / SERVER':'GWDG / DCGM';
    $('benchmarkBadge').className = 'pill '+(isSmd?'pill-blue':'pill-amber');
    setText('benchmarkTitle',isSmd?'有标签的服务器异常区间':'真实 DCGM 的事件前候选');
    setText('benchmarkSubtitle',isSmd?'28 台机器 · 38 个匿名指标 · 327 个连续异常标签区间':'50 个事件中心窗口 · 22 个可评分 · 88 条 GPU 曲线');
    const bars = $('benchmarkBars');
    if (isSmd) {
      const staticHit = fraction(smd.static.hit_events,smd.events);
      const adaptiveHit = fraction(smd.adaptive.hit_events,smd.events);
      bars.replaceChildren(
        benchmarkRow('冻结 P99.5',staticHit,`${staticHit}%`,`${number(smd.static.false_alert_episodes)} 段无标签告警`,false),
        benchmarkRow('历史动态 P99.5',adaptiveHit,`${adaptiveHit}%`,`${number(smd.adaptive.false_alert_episodes)} 段无标签告警`,true)
      );
      setText('benchmarkNote','区间命中：至少一处确认点落入异常标签。动态阈值少了 12 个区间命中，同时减少 538 段未与标签重叠的告警。SMD 指标匿名，不能解释为 GPU 故障准确率。');
      setText('sideRingValue',`${adaptiveHit}%`);
      setText('sideRingLabel','区间命中');
      setText('sideTitle','窗口 PCA · 动态阈值');
      setText('sideDescription','只用过去 2,000 个分数更新 P99.5，每 100 点更新一次，连续 3 点确认。');
      setText('sideStatLabel','告警段与标签重叠');
      setText('sideStatValue',`${fraction(smd.adaptive.true_alert_episodes,smd.adaptive.alert_episodes)}%`);
      setText('sideCoverageLabel','正常点启动 / 万点');
      setText('sideCoverageValue',smd.adaptive.normal_starts_per_10000_normal_points.toFixed(1));
    } else {
      const frozen = fraction(gwdg.frozen_last_2h_hit_incidents,gwdg.scored_incidents);
      const adaptive = fraction(gwdg.adaptive_last_2h_hit_incidents,gwdg.scored_incidents);
      bars.replaceChildren(
        benchmarkRow('冻结 P99.5',frozen,`${gwdg.frozen_last_2h_hit_incidents} / ${gwdg.scored_incidents}`,`${number(gwdg.frozen_alert_episodes)} 段候选`,false),
        benchmarkRow('历史动态 P99.5',adaptive,`${gwdg.adaptive_last_2h_hit_incidents} / ${gwdg.scored_incidents}`,`${number(gwdg.adaptive_alert_episodes)} 段候选`,true)
      );
      setText('benchmarkNote','这里的“命中”只表示 Slurm 事件前两小时出现候选，不是物理故障召回。动态阈值减少了 240 段候选，也减少了 9 个有候选的事件窗口。缺少独立健康机群，不能计算误报率。');
      setText('sideRingValue',`${fraction(gwdg.scored_minutes,gwdg.pre_event_minutes)}%`);
      setText('sideRingLabel','分钟可评分');
      setText('sideTitle','DCGM 覆盖先于模型');
      setText('sideDescription','5 个核心字段、同卡同分钟、连续 5 点。字段缺失或采集缺口返回不可评分。');
      setText('sideStatLabel','可评分事件窗口');
      setText('sideStatValue',`${gwdg.scored_incidents} / ${gwdg.input_incidents}`);
      setText('sideCoverageLabel','可评分 GPU 曲线');
      setText('sideCoverageValue',gwdg.scored_gpu_traces);
    }
  }

  function renderModels() {
    const titles = {window_pca:'窗口 PCA',window_autoencoder:'普通自编码器',usad:'USAD'};
    const rows = ['window_pca','window_autoencoder','usad'].map(id => {
      const value = smd.deep[id];
      const item = node('div','model-chip');
      item.append(node('span',null,titles[id]),node('strong',null,`F1 ${value.f1.toFixed(3)}`),node('small',null,`${value.hit_events} / ${value.labelled_events} 区间命中`));
      return item;
    });
    $('modelCompareRows').replaceChildren(...rows);
  }

  function renderTraceHeader() {
    setText('traceTitle',`${trace.node} · ${trace.gpu_uuid.slice(0,16)}…`);
    setText('traceSubtitle',`${trace.event_time_utc.replace('T',' ').slice(0,16)} UTC · 事件前 180 分钟 · 五个真实 DCGM 字段 · 缺口保持为空`);
  }

  function drawChart(canvas, scoreMode) {
    const box = canvas.getBoundingClientRect();
    if (!box.width || !box.height) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(box.width*dpr);
    canvas.height = Math.round(box.height*dpr);
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr,0,0,dpr,0,0);
    const width=box.width,height=box.height,left=48,right=15,top=16,bottom=scoreMode?23:28;
    const plotWidth=width-left-right,plotHeight=height-top-bottom;
    const points=trace.points;
    const x = index => left+index/(points.length-1)*plotWidth;
    const series=scoreMode?points.map(p=>p.score):points.map(p=>p.values[selectedMetric]);
    const threshold=scoreMode?points.map(p=>p.threshold):[];
    const values=[...series,...threshold].filter(Number.isFinite);
    if (!values.length) return;
    const rawMin=Math.min(...values),rawMax=Math.max(...values),pad=Math.max((rawMax-rawMin)*.13,scoreMode?.015:.8);
    const min=Math.max(0,rawMin-pad),max=rawMax+pad;
    const y = value => top+plotHeight-(value-min)/(max-min)*plotHeight;
    ctx.clearRect(0,0,width,height);
    for(let i=0;i<4;i++){
      const value=min+(max-min)*i/3;
      ctx.strokeStyle='#edf1f6';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(left,y(value));ctx.lineTo(width-right,y(value));ctx.stroke();
      ctx.fillStyle='#9baaBC';ctx.font='10px system-ui';ctx.textAlign='right';ctx.fillText(value.toFixed(scoreMode?2:0),left-8,y(value)+3);
    }
    if(!scoreMode){
      for(let i=0;i<points.length;i++)if(points[i].candidate){ctx.fillStyle='#ee7a6c17';ctx.fillRect(x(i)-plotWidth/points.length,top,Math.max(2,plotWidth/points.length*2),plotHeight);}
    }
    function line(data,color,widthLine=2,dashed=false){
      ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=widthLine;ctx.setLineDash(dashed?[5,4]:[]);
      let active=false;
      for(let i=0;i<data.length;i++){
        const value=data[i];
        if(!Number.isFinite(value)){active=false;continue;}
        if(active)ctx.lineTo(x(i),y(value));else ctx.moveTo(x(i),y(value));
        active=true;
      }
      ctx.stroke();ctx.setLineDash([]);
    }
    if(scoreMode){line(threshold,'#e4a24c',1.5,true);line(series,'#29b6a6',2);}
    else line(series,'#4d77ef',2.2);
    for(let i=0;i<points.length;i++){
      const value=series[i];if(!points[i].candidate||!Number.isFinite(value))continue;
      ctx.fillStyle=scoreMode?'#ee7a6c':'#ee786d';ctx.beginPath();ctx.arc(x(i),y(value),2.7,0,Math.PI*2);ctx.fill();
    }
    ctx.strokeStyle='#c9d6e4';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(x(points.length-1),top);ctx.lineTo(x(points.length-1),top+plotHeight);ctx.stroke();ctx.setLineDash([]);
    if(!scoreMode){
      ctx.fillStyle='#9aa9ba';ctx.font='9px system-ui';ctx.textAlign='center';
      for(const tick of [-180,-120,-60,0]){
        const index=points.findIndex(p=>p.minute>=tick);
        if(index>=0)ctx.fillText(tick===0?'事件':`${tick}m`,x(index),height-6);
      }
      ctx.fillStyle='#60768e';ctx.font='10px system-ui';ctx.textAlign='left';ctx.fillText(`${metricLabels[selectedMetric]} / ${trace.metric_units[selectedMetric]}`,left+3,10);
    }
  }

  function drawTrace(){drawChart($('observedChart'),false);drawChart($('anomalyChart'),true);}

  function attachTooltip(canvas) {
    canvas.addEventListener('pointermove',event=>{
      const bounds=canvas.getBoundingClientRect(),left=48,right=15;
      const normalized=(event.clientX-bounds.left-left)/(bounds.width-left-right);
      const index=Math.max(0,Math.min(trace.points.length-1,Math.round(normalized*(trace.points.length-1))));
      const p=trace.points[index];
      const actual=p.values[selectedMetric];
      const tooltip=$('traceTooltip');
      tooltip.textContent=`Slurm 事件前 ${Math.abs(p.minute)} 分钟\n${metricLabels[selectedMetric]}：${actual===null?'缺失':actual+' '+trace.metric_units[selectedMetric]}\nPCA 分数：${p.score===null?'不可评分':p.score}\n动态阈值：${p.threshold===null?'—':p.threshold}\n${p.candidate?'● 已确认异常候选':'未确认异常候选'}`;
      tooltip.style.left=`${Math.max(10,Math.min(bounds.width-225,event.clientX-bounds.left+13))}px`;
      tooltip.style.top=canvas.id==='observedChart'?'90px':'315px';
      tooltip.hidden=false;
    });
    canvas.addEventListener('pointerleave',()=>{$('traceTooltip').hidden=true;});
  }

  async function updateLive() {
    const indicator=$('liveIndicator');
    try {
      const response=await fetch('/api/gpu-ml/v1/state',{credentials:'same-origin',cache:'no-store'});
      if (!response.ok) throw new Error('not signed in');
      const state=await response.json();
      const count=state.entities.filter(e=>e.source_type==='simulated').length;
      indicator.lastChild.textContent=`实时工作台 · ${count} 张模拟 GPU`;
      indicator.classList.add('connected');
    } catch {
      indicator.lastChild.textContent='离线评测可浏览 · 实时工作台需登录';
      indicator.classList.remove('connected');
    }
  }

  $('tabSmd').addEventListener('click',()=>{selectedDataset='smd';renderBenchmark();});
  $('tabGwdg').addEventListener('click',()=>{selectedDataset='gwdg';renderBenchmark();});
  $('traceMetric').addEventListener('change',event=>{selectedMetric=event.target.value;drawTrace();});
  window.addEventListener('resize',drawTrace);
  attachTooltip($('observedChart'));attachTooltip($('anomalyChart'));
  renderHero();renderBenchmark();renderModels();renderTraceHeader();drawTrace();updateLive();
  setInterval(updateLive,12000);
})();
