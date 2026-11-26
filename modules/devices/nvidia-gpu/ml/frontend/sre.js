'use strict';

const api = '/api/gpu-ml/v1';
const metricLabels = {
    util: 'GPU 利用率', power: '板卡功耗', gpu_temp: 'GPU 温度',
    memory_temp: 'HBM 温度', sm_clock: 'SM 时钟', mem_util: '显存控制器活动',
};
const methodNotes = {
    local_trend: '用前 5 点中位数，加上 0.35 倍的前后两段中位数差，外推当前点。',
    rolling_median: '以前 5 点中位数估计当前水平，避免单个尖峰拉动参考值。',
    historical_level: '用拟合段的中位数作为固定参考，便于观察持续水平偏移。',
};
const categories = {
    trend: '趋势预警', white: '白盒线索', black: '黑盒线索', quality: '数据质量', normal: '未确认异常',
};
const jointColors = ['#5fe3ce', '#a1bbff', '#ffc479'];
const views = {
    all: ['异常概览', '按节点和 GPU 查看行为偏离、关联证据与采集缺口。'],
    trend: ['单指标趋势预警', '对照观测、动态基线和残差参考带，切换方法比较同一段回放。'],
    joint: ['多指标关联检测', '查看白盒条件是否同时成立，或用黑盒模型定位联合偏离字段。'],
    quality: ['数据质量', '查看缺失字段和受影响的检测时间段。'],
};
function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
}

function initializeReplay(root, {embedded = false, initialView = 'all'} = {}) {
    const byId = id => root.getElementById(id);
    const state = {
        data: null, filter: initialView, view: initialView, device: null, tab: 'trend', metric: 'gpu_temp',
        compare: false, point: null, method: 'local_trend', generation: 0, checked: new Set(), announced: new Set(),
    };
    const last = rows => rows.at(-1);
    const fixed = (value, places = 1) => Number.isFinite(value) ? value.toFixed(places) : '—';
    const clock = new Intl.DateTimeFormat('zh-CN', {
        timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    });
    const time = index => clock.format(new Date((state.data.start + state.data.step * index) * 1000));
    const written = (value, metric) => Number.isFinite(value)
        ? `${fixed(value)} ${state.data.metrics[metric].unit}` : '缺失';
    let toastTimer;

    function pressed(parent, key, value) {
        parent.querySelectorAll(`button[data-${key}]`).forEach(button => {
            button.setAttribute('aria-pressed', String(button.dataset[key] === value));
        });
    }

    function detector(device, category, metric) {
        return category === 'trend' ? device.trends[metric][state.method] : device[category];
    }

    function events() {
        return state.data.devices.flatMap(device => {
            // Each simulated device has one configured monitoring task in the queue.
            const result = detector(device, device.category, device.primaryMetric);
            const period = last(result.periods);
            if (!period) return [];
            const peak = result.scores ? Math.max(...result.scores.slice(period.start, period.end + 1)) : null;
            return [{device, period, peak}];
        }).sort((a, b) => b.period.confirmed - a.period.confirmed);
    }

    function matches(category, filter) {
        return filter === 'all' || filter === category || (filter === 'joint' && joint(category));
    }

    const joint = tab => tab === 'white' || tab === 'black';

    function eventKey(event) {
        if (!event) return '';
        const {device, period} = event;
        const method = device.category === 'trend' ? state.method : device.category;
        return `${device.id}/${method}/${period.confirmed}`;
    }

    function notify(event, {again = false} = {}) {
        if (!event || (!again && state.announced.has(eventKey(event)))) return;
        state.announced.add(eventKey(event));
        byId('toast-title').textContent = '回放捕获趋势预警';
        byId('toast-text').textContent = `${event.device.node} / GPU ${event.device.gpu} · 峰值 ${fixed(event.peak, 2)}× 门槛 · ${time(event.period.confirmed)}`;
        byId('toast').hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => byId('toast').hidden = true, 6500);
    }

    function selectDevice(device, category = device.category) {
        state.device = device;
        state.metric = device.primaryMetric;
        selectTab(category);
    }

    function selectTab(category) {
        state.tab = category;
        state.compare = joint(category);
        state.point = null;
        byId('tip').hidden = true;
    }

    function queueItem(event) {
        const {device, period, peak} = event;
        const button = node('button', undefined, 'queue-item');
        button.type = 'button';
        button.dataset.device = device.id;
        button.setAttribute('aria-pressed', String(device === state.device));
        const top = node('span', undefined, 'queue-top');
        top.append(node('span', categories[device.category], `pill ${device.category}`), node('time', time(period.confirmed), 'event-time'));
        const bottom = node('span', undefined, 'queue-bottom');
        bottom.append(node('span', `${device.node} · GPU ${device.gpu}`),
            node('span', state.checked.has(eventKey(event)) ? '已查看' : peak === null ? '证据不足' : `${fixed(peak, 2)}× 峰值`));
        button.append(top, node('strong', device.title, 'event-title'), bottom);
        button.onclick = () => {
            selectDevice(device);
            render();
            byId('queue').querySelector(`[data-device="${device.id}"]`)?.focus({preventScroll: true});
            if (window.matchMedia('(max-width: 620px)').matches) byId('detail').scrollIntoView({block: 'start'});
        };
        return button;
    }

    function render() {
        if (!state.data) return;
        const all = events();
        const visible = all.filter(e => matches(e.device.category, state.filter));
        byId('stat-devices').textContent = state.data.devices.length;
        byId('stat-trend').textContent = all.filter(e => e.device.category === 'trend').length;
        byId('stat-joint').textContent = all.filter(e => matches(e.device.category, 'joint')).length;
        byId('stat-quality').textContent = all.filter(e => e.device.category === 'quality').length;
        byId('queue-count').textContent = visible.length;
        byId('queue').replaceChildren(...(visible.length ? visible.map(queueItem) : [
            node('p', '当前筛选下没有确认事件，可查看右侧回放曲线。', 'empty'),
        ]));
        const [title, description] = views[state.view];
        byId('view-title').textContent = title;
        byId('view-description').textContent = description;
        pressed(root, 'view', state.view);
        pressed(byId('filters'), 'filter', state.filter);
        renderDetail(all.find(e => e.device === state.device));
    }

    function evidenceCard(label, value, caption, emphasis = '', samples = null) {
        const card = node('div', undefined, `evidence-card ${emphasis}`);
        card.append(node('span', label), node('strong', value), node('small', caption));
        if (samples) {
            const spark = node('canvas', undefined, 'spark');
            spark.setAttribute('aria-hidden', 'true');
            card.append(spark);
            requestAnimationFrame(() => {
                if (!spark.isConnected) return;
                const plot = preparePlot(spark);
                if (!plot) return;
                const finite = samples.filter(Number.isFinite);
                if (!finite.length) return;
                const low = Math.min(...finite), span = Math.max(Math.max(...finite) - low, .01);
                stroke(plot.ctx, samples, index => 2 + index * (plot.width - 4) / (samples.length - 1),
                    value => 2 + (1 - (value - low) / span) * (plot.height - 4), '#7dbfaf', 1.1);
            });
        }
        return card;
    }

    function rankedContributions(result, index) {
        return Object.entries(result.contributions)
            .map(([key, values]) => [key, values[index]])
            .filter(([, share]) => Number.isFinite(share))
            .sort((a, b) => b[1] - a[1]);
    }

    function evidenceFor(device, result, index) {
        const metric = state.metric;
        const raw = device.series[metric][index];
        const score = result.scores?.[index];
        if (state.tab === 'trend') {
            const expected = result.expected[index];
            return {
                title: '当前点证据', description: `${time(index)} · 回放采样点`,
                note: `${methodNotes[state.method]} 参考带使用正常校准段的残差分位数与最小带宽；连续 ${state.data.confirmation} 点达到门槛才确认。`,
                cards: [
                    evidenceCard('实际观测', written(raw, metric), metricLabels[metric]),
                    evidenceCard('模型参考', written(expected, metric), `半带宽 ±${fixed(result.bandWidth)} ${state.data.metrics[metric].unit}`),
                    evidenceCard('绝对残差', Number.isFinite(score) ? written(Math.abs(raw - expected), metric) : '不可评分',
                        Number.isFinite(score) ? `${fixed(score, 2)}× 门槛` : '需要连续有效输入', score >= 1 ? 'hit' : ''),
                ],
            };
        }
        if (state.tab === 'white') {
            return {
                title: '条件逐项核验', description: `${time(index)} · 以下条件须同时成立`,
                note: '板卡功耗与 SM 时钟参考值由模拟正常历史拟合，按当前利用率估计。最小达标倍数达到 1.0× 时，全部条件同时达标。',
                cards: result.conditions.map(condition => {
                    const actual = condition.values[index];
                    const hit = actual >= condition.threshold;
                    return evidenceCard(condition.name, written(actual, condition.metric),
                        `${condition.op} ${condition.threshold} ${state.data.metrics[condition.metric].unit} · ${actual === null ? '缺失' : hit ? '命中' : '未命中'}`,
                        hit ? 'hit' : '', device.series[condition.metric]);
                }),
            };
        }
        if (state.tab === 'black') {
            const ranked = rankedContributions(result, index);
            return {
                title: '重构残差贡献', description: `${time(index)} · 前三项指标占重构误差的比例`,
                note: `窗口 PCA 使用最近 ${state.data.jointWindow} 个采样点的六项 DCGM 指标。贡献表示重构偏离，现场可结合业务与设备证据确认原因。`,
                cards: ranked.length ? ranked.slice(0, 3).map(([key, share]) =>
                    evidenceCard(metricLabels[key], `${fixed(share * 100)}%`, `实际 ${written(device.series[key][index], key)}`, '', device.series[key])
                ) : [evidenceCard('证据不足', '不可评分', '联合输入中存在采集缺口')],
            };
        }
        const keys = Object.keys(device.series);
        return {
            title: '字段有效性', description: `${time(index)} · ${result.validFields[index]} / ${keys.length} 项可用`,
            note: '缺失点用断线显示。白盒所需输入或 PCA 窗口不完整时，该时点无分数。',
            cards: keys.map(key => {
                const value = device.series[key][index];
                return evidenceCard(metricLabels[key], written(value, key), state.data.metrics[key].name, value === null ? 'missing' : '');
            }),
        };
    }

    function renderDetail(event) {
        const device = state.device;
        if (!device) return;
        const status = byId('detail-status');
        status.className = `pill ${event ? device.category : 'normal'}`;
        status.textContent = categories[event ? device.category : 'normal'];
        byId('detail-device').textContent = device.uuid;
        byId('detail-title').textContent = event ? device.title : `${device.node} · GPU ${device.gpu} 回放`;
        byId('detail-subtitle').textContent = event
            ? `${device.node} · GPU ${device.gpu} · ${time(event.period.start)} 开始 · ${time(event.period.confirmed)} 确认 · ${event.period.end === state.data.points - 1 ? '回放结束时仍持续' : `${time(event.period.end)} 最后越界`}`
            : `${device.node} · GPU ${device.gpu} · 当前配置下未达到连续确认条件`;
        const ack = byId('ack');
        ack.hidden = !event;
        ack.disabled = state.checked.has(eventKey(event));
        ack.textContent = ack.disabled ? '已查看' : '标为已查看';
        ack.onclick = () => {
            state.checked.add(eventKey(event));
            render();
        };
        pressed(byId('detail-tabs'), 'tab', state.tab);
        const metric = state.metric;
        const info = state.data.metrics[metric];
        byId('metric').querySelector('[value="compare"]').hidden = !joint(state.tab);
        byId('metric').value = state.compare ? 'compare' : metric;
        byId('method').hidden = state.tab !== 'trend';
        const result = detector(device, state.tab, metric);
        const period = last(result.periods);
        const index = state.point ?? period?.end ?? state.data.points - 1;
        const comparison = state.compare ? jointSeries(device, result, period?.end ?? state.data.points - 1) : [];
        byId('chart-title').textContent = state.compare ? '关联指标同览' : `${metricLabels[metric]} · 回放时序`;
        byId('metric-name').textContent = state.compare ? '与各指标正常历史均值的距离（标准差倍数）' : info.name;
        const score = result.scores?.[index];
        const scoreTitle = {
            trend: '残差分数', white: '白盒条件最小达标倍数', black: 'PCA 联合偏离分数', quality: '有效字段数',
        };
        byId('score-title').textContent = scoreTitle[state.tab];
        byId('score-value').textContent = state.tab === 'quality'
            ? `${result.validFields[index]} / ${Object.keys(device.series).length}`
            : Number.isFinite(score) ? `${fixed(score, 2)}× 门槛 · ${time(index)}` : '当前点不可评分';
        byId('legend').replaceChildren(...[
            ...(state.compare ? comparison.map(({key, color}) => ['observed', metricLabels[key], color]) : [['observed', '实际观测']]),
            ...(result.expected ? [['expected', '模型参考'], ['band', '参考带']] : []),
            [state.tab === 'quality' ? 'gap' : 'anomaly', state.tab === 'quality' ? '确认缺口' : '确认越界区间'],
        ].map(([className, label, color]) => {
            const item = node('span');
            const swatch = node('i', undefined, className);
            if (color) swatch.style.background = color;
            item.append(swatch, node('span', label));
            return item;
        }));
        const evidence = evidenceFor(device, result, index);
        byId('evidence-title').textContent = evidence.title;
        byId('evidence-context').textContent = evidence.description;
        byId('evidence').className = 'evidence cards';
        byId('evidence').replaceChildren(...evidence.cards);
        byId('method-note').textContent = evidence.note;

        if (state.compare) plotComparison(comparison, result.periods, index);
        else plotTrace(device.series[metric], result, index, info.unit);
        plotScore(result, index);
    }

    function jointSeries(device, result, referencePoint) {
        const rank = state.tab === 'white'
            ? result.conditions.map(c => c.metric)
            : rankedContributions(result, referencePoint).map(([key]) => key);
        const keys = rank.length ? rank.slice(0, 3) : [device.primaryMetric, 'util', 'sm_clock'];
        return [...new Set(keys)].map((key, i) => ({
            key, color: jointColors[i], normalized: device.standardized[key], raw: device.series[key],
        }));
    }

    function preparePlot(canvas) {
        const {width, height} = canvas.getBoundingClientRect();
        if (width < 2 || height < 2) return null;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        const ctx = canvas.getContext('2d');
        ctx.scale(ratio, ratio);
        return {ctx, width, height};
    }

    function stroke(ctx, values, x, y, color, width, dashed = false) {
        ctx.beginPath();
        ctx.setLineDash(dashed ? [5, 4] : []);
        let open = false;
        values.forEach((value, index) => {
            if (!Number.isFinite(value)) {
                open = false;
                return;
            }
            ctx[open ? 'lineTo' : 'moveTo'](x(index), y(value));
            open = true;
        });
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.stroke();
        ctx.setLineDash([]);
    }

    function frame(canvas, low, high, format, periods, cursor, quality = false, small = false) {
        const plot = preparePlot(canvas);
        if (!plot) return null;
        const {ctx, width, height} = plot;
        const left = small ? 38 : 52, right = width - 16, top = 12, bottom = height - (small ? 8 : 25);
        const dx = (right - left) / (state.data.points - 1);
        const x = index => left + index * dx;
        const y = value => bottom - (value - low) * (bottom - top) / (high - low);
        ctx.font = '10px ui-monospace, SFMono-Regular, monospace';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = quality ? '#7389a53b' : '#f4819340';
        periods.forEach(period => {
            const start = Math.max(left, x(period.start) - dx / 2);
            const end = Math.min(right, x(period.end) + dx / 2);
            ctx.fillRect(start, top, end - start, bottom - top);
            ctx.fillRect(x(period.confirmed), top, 1, bottom - top);
        });
        const ticks = small ? 2 : 4;
        for (let i = 0; i <= ticks; i++) {
            const value = low + (high - low) * i / ticks;
            ctx.fillStyle = '#233347';
            ctx.fillRect(left, y(value), right - left, 1);
            ctx.fillStyle = '#a2b4c8';
            ctx.textAlign = 'right';
            ctx.fillText(format(value), left - 7, y(value));
        }
        if (!small) {
            const step = width < 450 ? 15 : 10;
            for (let index = 0; index <= state.data.points - 1; index += step) {
                ctx.fillStyle = '#a2b4c8';
                ctx.textAlign = index ? 'center' : 'left';
                ctx.fillText(time(index).slice(0, 5), x(index), bottom + 14);
            }
        }
        ctx.fillStyle = '#7a96ad80';
        ctx.fillRect(x(cursor), top, 1, bottom - top);
        return {ctx, x, y, nearest: pixels => Math.max(0, Math.min(state.data.points - 1, Math.round((pixels - left) / dx)))};
    }

    function plotTrace(observed, result, index, unit) {
        const canvas = byId('trace');
        const all = observed.concat(result.lower || [], result.upper || []).filter(Number.isFinite);
        const min = all.length ? Math.min(...all) : 0, max = all.length ? Math.max(...all) : 1;
        const padding = Math.max((max - min) * .08, .25);
        const plot = frame(canvas, min - padding, max + padding, v => fixed(v, unit === '°C' ? 1 : 0),
            result.periods, index, state.tab === 'quality');
        if (!plot) return;
        const {ctx, x, y} = plot;
        if (result.expected) {
            ctx.fillStyle = '#5b86c12e';
            result.lower.forEach((value, i) => {
                if (!i || ![value, result.lower[i - 1], result.upper[i], result.upper[i - 1]].every(Number.isFinite)) return;
                ctx.beginPath();
                ctx.moveTo(x(i - 1), y(result.lower[i - 1]));
                ctx.lineTo(x(i), y(value));
                ctx.lineTo(x(i), y(result.upper[i]));
                ctx.lineTo(x(i - 1), y(result.upper[i - 1]));
                ctx.closePath();
                ctx.fill();
            });
            stroke(ctx, result.expected, x, y, '#a1bbff', 1.5, true);
        }
        stroke(ctx, observed, x, y, '#5fe3ce', 2);
        if (Number.isFinite(observed[index])) {
            ctx.beginPath();
            ctx.arc(x(index), y(observed[index]), 3.3, 0, Math.PI * 2);
            ctx.fillStyle = '#ddfff7';
            ctx.fill();
        }
        bindTrace(canvas, plot.nearest, i => `${time(i)} · 观测 ${written(observed[i], state.metric)}`
            + (result.expected ? `\n参考 ${written(result.expected[i], state.metric)}` : ''));
    }

    function plotComparison(series, periods, index) {
        const canvas = byId('trace');
        const values = series.flatMap(field => field.normalized).filter(Number.isFinite);
        const low = Math.min(0, ...values), high = Math.max(0, ...values);
        const margin = Math.max(.25, (high - low) * .08);
        const plot = frame(canvas, low - margin, high + margin, v => fixed(v), periods, index);
        if (!plot) return;
        const {ctx, x, y} = plot;
        stroke(ctx, series[0].normalized.map(() => 0), x, y, '#60738a', 1, true);
        series.forEach(({normalized, color}) => stroke(ctx, normalized, x, y, color, 1.8));
        bindTrace(canvas, plot.nearest, i => [
            time(i), ...series.map(({key, raw}) => `${metricLabels[key]} ${written(raw[i], key)}`),
        ].join('\n'));
    }

    function bindTrace(canvas, nearest, describe) {
        canvas.onpointermove = event => {
            const i = nearest(event.clientX - canvas.getBoundingClientRect().left);
            const tip = byId('tip');
            tip.textContent = describe(i);
            tip.hidden = false;
        };
        canvas.onpointerleave = () => byId('tip').hidden = true;
        canvas.onclick = event => {
            state.point = nearest(event.clientX - canvas.getBoundingClientRect().left);
            render();
        };
    }

    function plotScore(result, index) {
        const quality = state.tab === 'quality';
        const values = quality ? result.validFields : result.scores;
        // Compress high peaks so the threshold stays readable, retaining its original unit.
        const transform = quality ? value => value : value => Math.log2(1 + value);
        const points = values.map(value => Number.isFinite(value) ? transform(value) : null);
        const high = quality ? Object.keys(state.data.metrics).length + .2 : Math.max(1.4, ...points.filter(Number.isFinite)) * 1.06;
        const low = quality ? Math.max(0, Math.min(...values) - .3) : 0;
        const plot = frame(byId('score'), low, high, value => quality ? fixed(value, 0) : `${fixed(2 ** value - 1)}×`,
            result.periods, index, quality, true);
        if (!plot) return;
        const {ctx, x, y} = plot;
        const threshold = quality ? Object.keys(state.data.metrics).length : 1;
        const line = points.map(() => transform(threshold));
        stroke(ctx, line, x, y, '#b8a080', 1.3, true);
        stroke(ctx, points, x, y, quality ? '#a1bbff' : '#ffc479', 1.75);
    }

    function setFilter(filter, asView = false) {
        state.filter = filter;
        if (asView) state.view = filter;
        else state.view = 'all';
        const matching = events().filter(event => matches(event.device.category, filter));
        const device = matching[0]?.device ?? state.data.devices.find(d => matches(d.category, filter)) ?? state.device;
        const preferred = {trend: 'trend', joint: joint(device.category) ? device.category : 'white', quality: 'quality'};
        selectDevice(device, preferred[filter] ?? device.category);
        render();
    }

    async function request(path, options) {
        const response = await fetch(api + path, options);
        const body = await response.json();
        if (!response.ok) {
            const error = new Error(typeof body.detail === 'string' ? body.detail : '回放请求失败');
            error.status = response.status;
            throw error;
        }
        return body;
    }

    async function load({again = false} = {}) {
        const generation = ++state.generation;
        const scenario = byId('scenario').value;
        byId('replay').disabled = true;
        byId('error').hidden = true;
        try {
            const data = await request('/sre-preview?scenario=' + encodeURIComponent(scenario));
            if (generation !== state.generation) return;
            state.data = data;
            byId('access').hidden = true;
            byId('content').hidden = false;
            byId('replay-range').textContent = `回放时间 ${time(0)}–${time(data.points - 1)} UTC+8`;
            byId('replay-points').textContent = `${data.points} 点 / GPU · ${data.referencePoints} 点正常参考`;
            byId('metric').replaceChildren(...['compare', ...Object.keys(data.metrics)].map(metric => {
                const option = node('option', metricLabels[metric] || '关联指标同览');
                option.value = metric;
                return option;
            }));
            if (!embedded) {
                state.filter = 'all';
                state.view = 'all';
            }
            selectDevice(data.devices[0]);
            if (state.filter === 'all') render();
            else setFilter(state.filter, state.view !== 'all');
            if (matches('trend', state.filter)) {
                notify(events().find(event => event.device.category === 'trend'), {again});
            }
        } catch (error) {
            if (generation !== state.generation) return;
            state.data = null;
            byId('content').hidden = true;
            byId('replay-range').textContent = '回放未加载';
            byId('replay-points').textContent = '—';
            if (error.status === 401) {
                byId('access').hidden = false;
                if (embedded) {
                    byId('access-message').textContent = '请重新登录工作台，再点击重放。';
                    byId('login').hidden = true;
                }
            }
            else {
                byId('error').textContent = error.message;
                byId('error').hidden = false;
            }
        } finally {
            if (generation === state.generation) byId('replay').disabled = false;
        }
    }

    byId('login').onclick = async () => {
        byId('login').disabled = true;
        try {
            await request('/session', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({role: 'viewer'}),
            });
            await load();
        } catch (error) {
            byId('access-message').textContent = error.message;
        } finally {
            byId('login').disabled = false;
        }
    };
    byId('scenario').onchange = () => {
        byId('toast').hidden = true;
        load();
    };
    byId('replay').onclick = () => load({again: true});
    byId('close-toast').onclick = () => byId('toast').hidden = true;
    byId('metric').onchange = event => {
        state.compare = event.target.value === 'compare';
        if (!state.compare) state.metric = event.target.value;
        state.point = null;
        byId('tip').hidden = true;
        render();
    };
    byId('method').onchange = event => {
        state.method = event.target.value;
        state.point = null;
        render();
        notify(events().find(e => e.device.category === 'trend' && e.device === state.device));
    };
    root.querySelectorAll('[data-view]').forEach(button => button.onclick = () => {
        if (state.data) setFilter(button.dataset.view, true);
    });
    root.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => setFilter(button.dataset.filter));
    root.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => {
        selectTab(button.dataset.tab);
        render();
    });
    let frameId;
    function redraw() {
        cancelAnimationFrame(frameId);
        frameId = requestAnimationFrame(render);
    }
    if (embedded) {
        let previousWidth = 0;
        new ResizeObserver(([entry]) => {
            const width = entry.contentRect.width;
            if (width > 0 && width !== previousWidth) redraw();
            previousWidth = width;
        }).observe(root.host);
    } else window.addEventListener('resize', redraw);
    load();

    return view => {
        if (state.data) {
            setFilter(view, true);
            redraw();
        } else {
            state.view = view;
            state.filter = view;
        }
    };
}

class GPUReplayPanel extends HTMLElement {
    static observedAttributes = ['view'];

    attributeChangedCallback(_name, previous, view) {
        if (!view || previous === view) return;
        if (this.selectView) this.selectView(view);
        else this.mount();
    }

    async mount() {
        if (this.loading) return;
        this.loading = true;
        try {
            const response = await fetch('/sre');
            if (!response.ok) throw Error('回放界面暂不可用');
            const page = new DOMParser().parseFromString(await response.text(), 'text/html');
            const shell = node('div', undefined, 'embedded');
            shell.append(page.querySelector('.workbench'), page.getElementById('toast'));

            const stylesheet = document.createElement('link');
            stylesheet.rel = 'stylesheet';
            stylesheet.href = '/assets/sre.css';
            const styled = new Promise((resolve, reject) => {
                stylesheet.onload = resolve;
                stylesheet.onerror = () => reject(Error('回放样式加载失败'));
            });
            const root = this.shadowRoot ?? this.attachShadow({mode: 'open'});
            root.replaceChildren(stylesheet, shell);
            shell.hidden = true;
            await styled;
            shell.hidden = false;
            this.selectView = initializeReplay(root, {embedded: true, initialView: this.getAttribute('view')});
        } catch (error) {
            const retry = node('button', '重新加载回放');
            retry.type = 'button';
            retry.onclick = () => this.mount();
            (this.shadowRoot ?? this).replaceChildren(node('p', error.message), retry);
        } finally {
            this.loading = false;
        }
    }
}

if (document.body.hasAttribute('data-sre-standalone')) initializeReplay(document);
else customElements.define('gpu-replay-panel', GPUReplayPanel);
