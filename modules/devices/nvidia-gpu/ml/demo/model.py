"""Seeded healthy simulation -> Ridge seasonal baseline -> Isolation Forest.

No injection labels are features. Training and calibration use disjoint time windows.
All live inference inputs must be read back from Prometheus by app.py.
"""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import Ridge

SERVICES = ('checkout', 'gateway', 'training-api')
SIGNALS = ('qps', 'latency_ms', 'cpu_percent')
UNITS = ('req/s', 'ms', '%')
SCENARIOS = ('normal', 'spike', 'drop', 'drift', 'correlation', 'auto')


def calendar(ts):
    t = np.asarray(ts, dtype=float)
    return np.column_stack([np.sin(t * 2 * np.pi / 120), np.cos(t * 2 * np.pi / 120),
                            np.sin(t * 2 * np.pi / 360), np.cos(t * 2 * np.pi / 360)])


def healthy(ts, service=0, seed=71):
    t = np.asarray(ts, dtype=float)
    c = calendar(t + service * 17)
    load = c[:, 0] * 0.7 + c[:, 2] * 0.3
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 1, len(t))
    noise = rng.normal(0, 1, (len(t), 3))
    return np.column_stack([900 + service * 180 + load * 150 + common * 6 + noise[:, 0] * 3,
                            85 + service * 12 + load * 12 + common * .8 + noise[:, 1] * .9,
                            43 + service * 4 + load * 8 + common * .4 + noise[:, 2] * .5])


def inject(values, scenario, age):
    y = values.copy()
    if scenario == 'spike':
        y[:, 1] += 115
    elif scenario == 'drop':
        y[:, 0] *= .32
    elif scenario == 'drift':
        y[:, 2] += min(42, max(0, age) * 1.4)
    elif scenario == 'correlation':
        # Individually modest deviations but a broken cross-metric relationship.
        y[:, 1] += 8
        y[:, 2] += 6
    return y


def features(residuals):
    """Causal current + first difference + trailing three-point mean + relations."""
    r = np.asarray(residuals)
    previous = np.vstack([r[0], r[:-1]])
    average = np.vstack([r[max(0, i-2):i+1].mean(axis=0) for i in range(len(r))])
    return np.column_stack([r, r - previous, average, r[:, 1] - r[:, 0], r[:, 2] - r[:, 0]])


class Detector:
    def __init__(self, service):
        self.service = service
        # Fixed demo training provenance: not queried production history.
        train_t = np.arange(0, 7200, 2)
        cal_t = np.arange(7200, 9600, 2)
        train = healthy(train_t, service, 71)
        calibration = healthy(cal_t, service, 89)
        self.baseline = Ridge(alpha=.01).fit(calendar(train_t + service * 17), train)
        residual = train - self.expected(train_t)
        self.scale = np.maximum(np.std(residual, axis=0), .01)
        self.forest = IsolationForest(n_estimators=160, max_samples=256, random_state=42,
                                      contamination='auto', n_jobs=1)
        train_features = features(residual / self.scale)
        self.forest.fit(train_features)
        # A joint forest can dilute an extreme isolated in one dimension. Add
        # per-signal forests, then calibrate the combined maximum on held-out data.
        self.signal_forests = []
        for signal in range(3):
            forest = IsolationForest(n_estimators=160, max_samples=256, random_state=43+signal,
                                      contamination='auto', n_jobs=1)
            forest.fit(np.abs(train_features[:, [signal]]))
            self.signal_forests.append(forest)
        cal_features = features((calibration-self.expected(cal_t))/self.scale)
        component_scores = self.component_scores(cal_features)
        self.component_scales = np.quantile(component_scores, .99, axis=0)
        cal_scores = np.max(component_scores/self.component_scales, axis=1)
        self.threshold = float(np.quantile(cal_scores, .995))
        self.train_count = len(train)
        self.cal_count = len(calibration)

    def expected(self, ts):
        return self.baseline.predict(calendar(np.asarray(ts) + self.service * 17))

    def component_scores(self, x):
        return np.column_stack([-self.forest.score_samples(x)] + [
            -forest.score_samples(np.abs(x[:, [i]]))
            for i, forest in enumerate(self.signal_forests)])

    def evaluate(self, ts, values):
        expected = self.expected(ts)
        residuals = (np.asarray(values)-expected) / self.scale
        scores = np.max(self.component_scores(features(residuals))/self.component_scales, axis=1)
        return expected, scores, np.abs(residuals)
