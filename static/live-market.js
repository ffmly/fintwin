/* Fintwin Live Market — deterministic simulation visualisation.
   Consumes normalized events and structured factors from the backend adapter.
   Features stylized 3D low-poly architectural scene, humanoid characters,
   smart non-overlapping billboard pins, collapsible drawers, and factor-based decision views. */
(() => {
  'use strict';

  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => [...parent.querySelectorAll(selector)];
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const esc = (value = '') => String(value).replace(/[&<>'"]/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  }[c]));
  const num = (value) => new Intl.NumberFormat('fr-DZ').format(Math.round(Number(value) || 0));
  const dzd = (value) => `${num(value)} دج`;
  const pct = (value, digits = 1) => `${(Number(value) || 0).toFixed(digits)}%`;

  const COLORS = {
    bg: '#070a09', panel: '#0c1512', line: '#26332e', lime: '#64fbd2',
    green: '#138a72', white: '#f2f6f3', muted: '#93a49b', coral: '#df5849',
    amber: '#d4a359', steel: '#7a8f86',
  };

  const LEAVE_STATES = new Set(['left', 'abandoned', 'cancelled', 'parking_left']);
  const ACTIVE_STATES = new Set([
    'inside', 'browsing', 'comparing', 'queueing', 'waiting', 'buying',
    'purchased', 'using_service', 'booking', 'in_service', 'returned', 'repeat', 'sitting',
  ]);

  const FILTER_SPEC = [
    ['segment', 'الشريحة'],
    ['wilaya', 'الولاية'],
    ['age_group', 'الفئة العمرية'],
    ['income_band', 'شريحة الدخل'],
    ['decision', 'نتيجة القرار'],
    ['payment_method', 'طريقة الدفع'],
    ['customer_type', 'نوع الزبون'],
  ];

  const DECISION_LABELS = { accepted: 'اشترى', abandoned: 'لم يشتر' };

  // Centralized Arabic state translations (Section 7)
  const STATE_TRANSLATIONS = {
    unexposed: 'لم يصل بعد',
    noticed: 'لاحظ المشروع',
    approaching: 'يقترب من المشروع',
    searching_parking: 'يبحث عن موقف',
    parking_left: 'غادر لعدم وجود موقف',
    inside: 'داخل المشروع',
    entered: 'دخل المشروع',
    browsing: 'يتصفح القائمة والخيارات',
    comparing: 'يدرس العرض ويقارن الأسعار',
    checking_price: 'يقارن الأسعار',
    queueing: 'ينتظر في الطابور',
    waiting: 'ينتظر',
    buying: 'ينفّذ عملية الشراء',
    purchasing: 'ينفّذ عملية الشراء',
    purchased: 'أتم الشراء',
    paying: 'يدفع',
    sitting: 'يستخدم الخدمة',
    using_service: 'يستخدم الخدمة',
    booking: 'يحجز موعداً',
    in_service: 'في مرحلة تقديم الخدمة',
    returned: 'زبون عائد للمشروع',
    repeat: 'زبون دائم',
    abandoned: 'تراجع عن الشراء',
    abandoning: 'تراجع عن الشراء',
    left: 'يغادر',
    leaving: 'يغادر',
    satisfied: 'راضٍ عن التجربة',
    cancelled: 'ألغى الموعد',
  };

  function translateState(state) {
    return STATE_TRANSLATIONS[state] || state || '';
  }

  const S = {
    root: null, mounted: false, projectId: null, demoId: null, demo: false,
    runId: null, activeRunId: null, scenarioMessage: null,
    data: null, baseline: null, comparison: null, pendingOpen: null,
    playing: false, speed: 1, time: 0, duration: 180,
    mode: '3d', lowPerf: false, split: false, comparisonOpen: false,
    filters: {}, selectedId: null, selectedEventId: null, hoverId: null,
    tab: 'decision', rightTab: 'feed', rightDrawerOpen: false,
    personSearch: '', chat: [], chatBusy: false,
    renderer: null, compareRenderer: null, raf: 0, lastTick: 0, lastHud: 0,
    lastFeedKey: '', resumeAfterHidden: false, loading: false,
    reduceMotion: false, openToken: 0,
  };

  const emptyFilters = () => ({
    segment: '', wilaya: '', age_group: '', income_band: '',
    decision: '', payment_method: '', customer_type: '',
  });

  function hashUnit(value) {
    let hash = 2166136261;
    for (const c of String(value)) {
      hash ^= c.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0) / 4294967295;
  }

  function notify(message, error = false) {
    if (typeof window.toast === 'function') window.toast(message, error);
    else console[error ? 'warn' : 'log'](message);
  }

  async function lmApi(url, options = {}) {
    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || 'تعذر الاتصال بمحرك المحاكاة.');
    return data;
  }

  function clockAt(seconds, duration) {
    const start = 9 * 60;
    const span = 12 * 60;
    const minutes = Math.round(start + (clamp(seconds, 0, duration) / Math.max(1, duration)) * span);
    return `${String(Math.floor(minutes / 60) % 24).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  }

  function elapsed(seconds) {
    const total = Math.max(0, Math.round(seconds));
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  }

  function decisionLabel(value) {
    return DECISION_LABELS[value] || value || '—';
  }

  function prepareDataset(data) {
    if (!data || typeof data !== 'object') throw new Error('بيانات السوق الحي غير صالحة.');
    data.personas = Array.isArray(data.personas) ? data.personas : [];
    data.events = Array.isArray(data.events) ? data.events : [];
    data.representatives = Array.isArray(data.representatives) ? data.representatives : [];
    data.runs = Array.isArray(data.runs) ? data.runs : [];
    data.filters = data.filters || {};
    data.metrics = data.metrics || {};
    data.environment = data.environment || { locations: {}, route: [], kind: 'journey', business: {} };
    const byPersona = new Map();
    for (const event of data.events) {
      if (!byPersona.has(event.personaId)) byPersona.set(event.personaId, []);
      byPersona.get(event.personaId).push(event);
    }
    for (const list of byPersona.values()) list.sort((a, b) => a.timestamp - b.timestamp);
    let last = 0;
    for (const persona of data.personas) {
      persona._events = byPersona.get(persona.id) || [];
      for (const event of persona._events) last = Math.max(last, Number(event.timestamp) || 0);
    }
    data._duration = Math.max(120, Number(data.metrics?.live?.simulation_duration_seconds) || 180, last + 6);
    data._repSet = new Set(data.representatives);
    return data;
  }

  function locationOf(data, key) {
    const locations = data?.environment?.locations || {};
    return locations[key] || locations[(data?.environment?.route || [])[0]] || { x: 0, z: 0, label: key || '' };
  }

  function positionAt(data, persona, time) {
    const events = persona._events || [];
    const digital = ['ecommerce', 'other'].includes(data?.environment?.activity);
    if (!events.length) {
      const first = locationOf(data, (data.environment.route || [])[0]);
      return { x: first.x, z: first.z, event: null, state: 'unexposed', isSitting: false };
    }

    const firstEvent = events[0];
    const lastEvent = events[events.length - 1];

    // Smooth sidewalk walk-in before first event
    if (time < firstEvent.timestamp) {
      const streetLoc = locationOf(data, firstEvent.location || 'street');
      const timeDiff = firstEvent.timestamp - time;
      const approachOffset = clamp(timeDiff / 8.0, 0, 1);
      const sign = (persona.id % 2 === 0) ? 1 : -1;
      return {
        x: streetLoc.x,
        z: streetLoc.z + (sign * (digital ? 1.45 : 6.0) * approachOffset),
        event: firstEvent,
        state: 'approaching',
        isSitting: false,
        isMoving: approachOffset > 0.05,
      };
    }

    // Smooth sidewalk walk-away after final event
    if (time > lastEvent.timestamp) {
      const exitLoc = locationOf(data, lastEvent.location || 'exit');
      const timeDiff = time - lastEvent.timestamp;
      const leaveOffset = clamp(timeDiff / 12.0, 0, 1);
      const sign = (persona.id % 2 === 0) ? 1 : -1;
      return {
        x: digital ? exitLoc.x + sign * 0.8 * leaveOffset : exitLoc.x + (-6.0 - exitLoc.x) * clamp(leaveOffset * 2.0, 0, 1),
        z: exitLoc.z + (sign * (digital ? 1.45 : 7.5) * leaveOffset),
        event: lastEvent,
        state: 'leaving',
        isSitting: false,
        isMoving: leaveOffset < 0.95,
      };
    }

    let current = events[0];
    let next = null;
    for (const event of events) {
      if (event.timestamp <= time) {
        current = event;
        next = null;
      } else {
        next = event;
        break;
      }
    }
    const from = locationOf(data, current.location);
    const to = next ? locationOf(data, next.location) : from;
    let progress = 0;
    if (next && next.timestamp > current.timestamp) {
      progress = clamp((time - current.timestamp) / (next.timestamp - current.timestamp), 0, 1);
    }
    const eased = progress * progress * (3 - 2 * progress);
    const jitterX = (hashUnit(`${persona.id}:x`) - 0.5) * 0.45;
    const jitterZ = (hashUnit(`${persona.id}:z`) - 0.5) * 0.4;
    const queueIndex = Number(persona.id) % 6;
    const waitingOffset = data.environment?.kind === 'physical' && current.location === 'queue'
      ? { x: -queueIndex * 0.42, z: (queueIndex % 2) * 0.35 }
      : { x: 0, z: 0 };
    const isSitting = (current.newState === 'sitting' || current.location === 'wifi' || current.location === 'tables') && progress === 0;

    return {
      x: from.x + (to.x - from.x) * eased + (isSitting ? 0 : jitterX) + waitingOffset.x * (1-eased),
      z: from.z + (to.z - from.z) * eased + (isSitting ? 0 : jitterZ) + waitingOffset.z * (1-eased),
      event: current,
      state: current.newState,
      isSitting,
      isMoving: next !== null && progress > 0.01 && progress < 0.99,
    };
  }

  function eventById(id) {
    return (S.data?.events || []).find((e) => e.id === id) || null;
  }

  function personaById(id) {
    return (S.data?.personas || []).find((p) => String(p.id) === String(id)) || null;
  }

  function passesFilters(persona) {
    const f = S.filters;
    return (!f.segment || persona.segment === f.segment)
      && (!f.wilaya || persona.wilaya === f.wilaya)
      && (!f.age_group || persona.age_group === f.age_group)
      && (!f.income_band || persona.income_band === f.income_band)
      && (!f.decision || persona.outcome === f.decision)
      && (!f.payment_method || persona.preferred_payment === f.payment_method)
      && (!f.customer_type || persona.customer_type === f.customer_type);
  }

  function visiblePersonas(data = S.data) {
    if (!data) return [];
    return data.personas.filter((p) => p.representative && passesFilters(p));
  }

  function visibleIds(data = S.data) {
    return new Set(visiblePersonas(data).map((p) => p.id));
  }

  function computeLive(data, time, ids) {
    const set = ids instanceof Set ? ids : new Set(ids || []);
    const result = { exposed: 0, buyers: 0, left: 0, active: 0, revenue: 0, lost: 0 };
    for (const persona of data.personas) {
      if (!set.has(persona.id)) continue;
      const reached = (persona._events || []).filter((e) => e.timestamp <= time);
      if (!reached.length) continue;
      result.exposed += 1;
      const last = reached[reached.length - 1];
      result.revenue += Number(last.financialImpact?.revenueDzd) || 0;
      result.lost += Number(last.financialImpact?.lostRevenueDzd) || 0;
      if (last.newState === 'purchased' || last.newState === 'repeat') result.buyers += 1;
      if (LEAVE_STATES.has(last.newState)) result.left += 1;
      else if (ACTIVE_STATES.has(last.newState)) result.active += 1;
    }
    return result;
  }

  function impactText(event) {
    const impact = event?.financialImpact || {};
    if (Number(impact.revenueDzd) > 0) return `إيراد +${dzd(impact.revenueDzd)}`;
    if (Number(impact.lostRevenueDzd) > 0) return `خسارة −${dzd(impact.lostRevenueDzd)}`;
    return '';
  }

  /* ----------------------------------------------------------------------- */
  /* Shell HTML Structure (Section 6)                                        */
  /* ----------------------------------------------------------------------- */
  const SHELL = `
    <div class="lm-shell" data-mode="3d">
      <header class="lm-top">
        <div class="lm-topbar">
          <div class="lm-topbar-start">
            <button class="lm-back" type="button" data-lm-close title="العودة للصفحة السابقة">← رجوع</button>
            <div class="lm-brand">
              <span class="lm-kicker">FINTWIN LIVE MARKET</span>
              <b id="lmProjectName">—</b>
              <span class="lm-activity-chip" id="lmActivity">—</span>
            </div>
            <span class="lm-scenario-badge" id="lmScenarioName">Baseline</span>
            <span class="lm-demo-badge hidden" data-lm-demo-badge>حالة عرض غير محفوظة</span>
          </div>
          <div class="lm-topbar-end">
            <button type="button" class="lm-btn lm-btn-soft lm-btn-sm" data-lm-open-compare>مقارنة قبل/بعد</button>
            <button type="button" class="lm-btn lm-btn-ghost lm-btn-sm" data-lm-run-select>التشغيلات المحفوظة</button>
            <button type="button" class="lm-btn lm-btn-ghost lm-btn-sm" data-lm-toggle-right id="lmToggleRightBtn">الأحداث والمرشحات ☰</button>
          </div>
        </div>
        <div class="lm-metrics-bar" id="lmMetrics"></div>
      </header>

      <div class="lm-main-container">
        <!-- Left Collapsible Persona Drawer -->
        <aside class="lm-drawer lm-drawer-left hidden" id="lmPersonaDrawer">
          <div class="lm-drawer-header">
            <div class="lm-insp-head-compact">
              <div class="lm-avatar" id="lmAvatar">◇</div>
              <div class="lm-insp-info">
                <h3 id="lmInsName">اختر شخصية</h3>
                <span id="lmInsSegment">—</span>
              </div>
              <span class="lm-decision-pill hidden" id="lmInsDecision">—</span>
            </div>
            <button type="button" class="lm-close-drawer-btn" data-lm-close-persona title="إغلاق">✕</button>
          </div>
          <div class="lm-tabs" role="tablist">
            <button type="button" role="tab" data-lm-tab="decision" class="active">القرار</button>
            <button type="button" role="tab" data-lm-tab="journey">الرحلة</button>
            <button type="button" role="tab" data-lm-tab="profile">الملف</button>
            <button type="button" role="tab" data-lm-tab="chat">المحادثة</button>
          </div>
          <div class="lm-drawer-body" id="lmTabBody"></div>
        </aside>

        <!-- Center Stage Main -->
        <main class="lm-stage-main" id="lmStage">
          <div class="lm-stage-header">
            <div class="lm-stage-badges">
              <span class="lm-live"><i></i> محاكاة حية</span>
              <span class="lm-clock" id="lmClock">09:00</span>
              <span class="lm-chip" id="lmOccupancy">إشغال 0</span>
              <span class="lm-chip" id="lmSceneCount">0 ظاهر</span>
              <span class="lm-chip" id="lmSpeedLabel">1×</span>
            </div>
            <div class="lm-active-chips" id="lmActiveFilterChips"></div>
          </div>
          <div class="lm-scene-context" id="lmSceneContext"></div>
          <div class="lm-progress"><i id="lmProgress"></i></div>

          <div class="lm-canvas-container" id="lmCanvases">
            <div class="lm-canvas-wrap lm-canvas-main">
              <canvas id="lmCanvas" tabindex="0" aria-label="مشهد السوق الحي. انقر واسحب للتنقل."></canvas>
            </div>
            <div class="lm-canvas-wrap lm-canvas-compare hidden" id="lmCompareWrap">
              <span class="lm-canvas-tag">قبل التعديل</span>
              <canvas id="lmCompareCanvas" aria-label="مشهد السوق قبل التعديل"></canvas>
            </div>
            <span class="lm-canvas-tag lm-canvas-tag-after hidden" id="lmAfterTag">بعد التعديل</span>

            <div class="lm-stage-empty hidden" id="lmStageEmpty">
              <span class="lm-loader"></span>
              <b id="lmEmptyTitle">نجهّز السوق الحي…</b>
              <small id="lmEmptyDesc">نقرأ قرارات المحاكاة ونبني المشهد المعماري والمسارات.</small>
            </div>

            <!-- Floating Docked Controls (Section 6) -->
            <div class="lm-floating-controls">
              <button type="button" class="lm-btn lm-btn-lime" data-lm-play id="lmPlayBtn">إيقاف مؤقت</button>
              <button type="button" class="lm-btn lm-btn-ghost" data-lm-restart title="إعادة من البداية">إعادة</button>
              <div class="lm-speeds" role="group" aria-label="سرعة المحاكاة">
                <button type="button" data-lm-speed="1" class="active">1×</button>
                <button type="button" data-lm-speed="2">2×</button>
                <button type="button" data-lm-speed="4">4×</button>
              </div>
              <span class="lm-ctrl-sep"></span>
              <button type="button" class="lm-btn lm-btn-ghost" data-lm-reset-cam title="إعادة ضبط الكاميرا">إعادة ضبط الكاميرا</button>
              <button type="button" class="lm-btn lm-btn-ghost" data-lm-overview title="نظرة عامة">نظرة عامة</button>
              <button type="button" class="lm-btn lm-icon-btn" data-lm-zoom="in" title="تكبير">+</button>
              <button type="button" class="lm-btn lm-icon-btn" data-lm-zoom="out" title="تصغير">−</button>
              <span class="lm-ctrl-sep"></span>
              <button type="button" class="lm-btn lm-btn-soft" data-lm-mode>عرض 2D</button>
              <button type="button" class="lm-btn lm-btn-ghost" data-lm-perf>وضع الأداء</button>
            </div>
          </div>
        </main>

        <!-- Right Collapsible Drawer: Events, Filters & People -->
        <aside class="lm-drawer lm-drawer-right" id="lmRightDrawer">
          <div class="lm-drawer-tabs">
            <button type="button" class="lm-d-tab active" data-lm-right-tab="feed">الأحداث (<span id="lmFeedCount">0</span>)</button>
            <button type="button" class="lm-d-tab" data-lm-right-tab="filters">المرشحات</button>
            <button type="button" class="lm-d-tab" data-lm-right-tab="people">الشخصيات (<span id="lmVisibleCount">0</span>)</button>
            <button type="button" class="lm-close-drawer-btn" data-lm-toggle-right title="طي اللوحة">›</button>
          </div>

          <div class="lm-drawer-content" id="lmRightContent">
            <!-- Feed Tab Pane -->
            <div class="lm-right-pane" data-pane="feed">
              <div class="lm-feed-header">
                <span>أحداث اللحظة المباشرة</span>
                <small>اضغط أي حدث لتحديد الشخصية</small>
              </div>
              <div class="lm-feed" id="lmFeed"></div>
            </div>

            <!-- Filters Tab Pane -->
            <div class="lm-right-pane hidden" data-pane="filters">
              <div class="lm-filter-header">
                <span>تصفية شخصيات المشهد</span>
                <button type="button" class="lm-link" data-lm-reset-filters>مسح الكل</button>
              </div>
              <div class="lm-filters-grid" id="lmFilters"></div>
            </div>

            <!-- People Tab Pane -->
            <div class="lm-right-pane hidden" data-pane="people">
              <input class="lm-search" id="lmPeopleSearch" placeholder="بحث بالاسم، الشريحة، الولاية…" aria-label="بحث في الشخصيات">
              <div class="lm-person-list" id="lmPersonList"></div>
            </div>
          </div>
        </aside>
      </div>

      <!-- Secondary Sub-Panels -->
      <div class="lm-sub-panels">
        <section class="lm-panel lm-snapshot-panel">
          <div class="lm-panel-head">
            <div><span class="lm-kicker">LIVE SNAPSHOT</span><h2>لقطة اللحظة الحالية</h2></div>
            <small id="lmSnapshotTime">—</small>
          </div>
          <div class="lm-live-cards" id="lmLiveCards"></div>
        </section>

        <section class="lm-panel">
          <div class="lm-panel-head">
            <div><span class="lm-kicker">DETERMINISTIC METRICS</span><h2>المؤشرات السلوكية والمالية</h2></div>
            <small>محسوبة وموثقة رياضياً من محرك المحاكاة</small>
          </div>
          <div class="lm-metric-cards" id="lmMetricCards"></div>
          <p class="lm-note">المؤشرات المالية والسلوكية محسوبة مباشرة في محرك <bdi>Fintwin</bdi>. المشهد يعرضها فقط ولا يعيد توليدها.</p>
        </section>

        <section class="lm-panel lm-compare-panel hidden" id="lmComparePanel"></section>

        <section class="lm-panel lm-scenario" id="lmScenarioPanel">
          <div class="lm-panel-head">
            <div><span class="lm-kicker">SCENARIO LAB</span><h2>جرّب متغيراً جديداً وشاهد أثره المالي</h2></div>
            <span class="lm-estimate">نتائج تقديرية</span>
          </div>
          <div class="lm-preset-row" id="lmPresets"></div>
          <div class="lm-scenario-row">
            <textarea id="lmScenarioText" rows="2" placeholder="اكتب تغييراً مثل: زيد السعر 10% أو أضف موقف سيارات وخفّض الانتظار…"></textarea>
            <button type="button" class="lm-btn lm-btn-lime" data-lm-run-scenario>شغّل سيناريو جديد</button>
          </div>
          <div class="lm-scenario-response hidden" id="lmScenarioResponse"></div>
        </section>

        <section class="lm-panel lm-runs-panel hidden" id="lmRunsPanel">
          <div class="lm-panel-head"><h2>التشغيلات المحفوظة</h2><small id="lmRunsCount">0</small></div>
          <div class="lm-run-list" id="lmRuns"></div>
        </section>
      </div>

      <footer class="lm-foot">
        <span id="lmDisclaimer">نتائج السوق الحي محاكاة تقديرية، وليست ضماناً تجارياً.</span>
        <span><bdi>Fintwin</bdi> · Decision support</span>
      </footer>
    </div>`;

  function renderShell() {
    S.root.innerHTML = SHELL;
    S.mounted = true;
    S.root.onclick = handleClick;
    S.root.onchange = handleChange;
    S.root.oninput = handleInput;
    S.root.onsubmit = handleSubmit;
    S.root.onkeydown = handleKeydown;
  }

  /* ----------------------------------------------------------------------- */
  /* Data / HUD Rendering & Metric Tooltips                                  */
  /* ----------------------------------------------------------------------- */
  function renderMeta() {
    const data = S.data;
    const activity=data.environment?.visual_activity||data.environment?.activity;
    const context={
      ecommerce:['رحلة شراء رقمية','من الإعلان إلى صفحة المنتج، السلة، الدفع والتوصيل. النقاط المتحركة تمثل قرارات زبائن افتراضيين، وليست أشخاصاً داخل محل.'],
      cafe:['تجربة المقهى','راقب الدخول والانتظار والجلوس والشراء. اضغط على شخصية لفهم سبب قرارها.'],
      restaurant:['تجربة المطعم','راقب وصول الزبائن والطابور والطلب والتوصيل أو المغادرة.'],
      retail:['زيارة متجر محلي','راقب الدخول، استكشاف المنتجات، غرف القياس والدفع.'],
      service:['رحلة طلب خدمة','من اكتشاف الخدمة إلى الحجز والتنفيذ والمتابعة.'],
      fitness:['تجربة النادي الرياضي','من اكتشاف البرنامج والحصة التجريبية إلى التدريب والاشتراك. المجسم توضيحي لرحلة القرار، وليس مخططاً فعلياً للنادي.'],
      other:['خريطة قرار عامة','هذا النشاط خارج القوالب الجاهزة. المشهد يعرض مراحل قرار عامة وليس مجسماً حرفياً لمكان مشروعك.'],
    }[activity]||['رحلة الزبون','تتبع نقاط القرار واضغط على أي شخصية لقراءة أسبابها.'];
    $('#lmSceneContext').innerHTML=`<b>${esc(context[0])}</b><span>${esc(context[1])}</span>`;
    const project = data.project || {};
    $('#lmProjectName').textContent = project.name || 'مشروع';
    $('#lmActivity').textContent = data.environment?.label || project.activity_type || 'نشاط';
    $('#lmScenarioName').textContent = data.run?.scenario_name || 'Baseline';
    $('[data-lm-demo-badge]').classList.toggle('hidden', !S.demo);
    $('[data-lm-demo-badge]').textContent = S.demo ? 'حالة عرض غير محفوظة' : '';
    $('#lmDisclaimer').textContent = data.disclaimer || 'نتائج السوق الحي محاكاة تقديرية، وليست ضماناً تجارياً.';
    renderRuns();
  }

  function renderRuns() {
    const panel = $('#lmRunsPanel');
    const runs = S.data?.runs || [];
    panel.classList.toggle('hidden', runs.length <= 1);
    $('#lmRunsCount').textContent = String(runs.length);
    $('#lmRuns').innerHTML = runs.map((run) => `
      <button type="button" class="lm-run ${String(run.id) === String(S.activeRunId) ? 'active' : ''}" data-lm-run="${esc(run.id)}">
        <b>${esc(run.scenario_name || 'Baseline')}</b>
        <small>${esc(new Date(run.created_at).toLocaleString('fr-DZ'))}</small>
      </button>`).join('');
  }

  function renderFilters() {
    const vocabulary = S.data?.filters || {};
    $('#lmFilters').innerHTML = FILTER_SPEC.map(([key, label]) => {
      let values = vocabulary[key] || [];
      if (key === 'decision') values = ['accepted', 'abandoned'];
      return `<label class="lm-field"><span>${esc(label)}</span><select data-lm-filter="${key}">
        <option value="">الكل</option>
        ${values.map((v) => `<option value="${esc(v)}" ${S.filters[key] === v ? 'selected' : ''}>${esc(key === 'decision' ? decisionLabel(v) : v)}</option>`).join('')}
      </select></label>`;
    }).join('');
    renderActiveFilterChips();
  }

  function renderActiveFilterChips() {
    const chipsContainer = $('#lmActiveFilterChips');
    if (!chipsContainer) return;
    const active = Object.entries(S.filters).filter(([, val]) => Boolean(val));
    if (!active.length) {
      chipsContainer.innerHTML = '';
      return;
    }
    chipsContainer.innerHTML = active.map(([key, val]) => {
      const spec = FILTER_SPEC.find(([k]) => k === key);
      const label = spec ? spec[1] : key;
      const displayVal = key === 'decision' ? decisionLabel(val) : val;
      return `<span class="lm-chip-tag">${esc(label)}: ${esc(displayVal)} <button type="button" data-lm-remove-filter="${esc(key)}">×</button></span>`;
    }).join('') + `<button type="button" class="lm-link" data-lm-reset-filters style="font-size:9px;">مسح</button>`;
  }

  function renderMetrics() {
    const data = S.data;
    const summary = data?.run?.result_summary || {};
    const behavior = data?.metrics?.behavioral || {};
    const financial = data?.metrics?.financial || {};
    const defs = data?.metrics?.definitions || {};
    const subscription = /نادي رياضي|لياقة|اشتراك|fitness|gym/i.test(String(data?.environment?.label || ''));
    const orderLabel = subscription ? 'اشتراكات متوقعة' : 'الطلبات المتوقعة';
    const unitLabel = subscription ? 'الاشتراك' : 'الطلب';
    const unitNoun = subscription ? 'اشتراك' : 'طلب';

    const topCards = [
      ['purchase_intent_pct', 'نية الشراء المقدّرة', pct(summary.purchase_intent_pct), 'من اللوحة الاستطلاعية'],
      ['expected_orders', orderLabel, num(summary.expected_monthly_orders), 'شهرياً'],
      ['average_order_value_dzd', subscription ? 'متوسط قيمة الاشتراك' : 'متوسط قيمة الطلب', dzd(financial.average_order_value_dzd), data.environment?.activity === 'ecommerce' ? 'المنتج والتوصيل' : `قيمة ${unitLabel}`],
      ['expected_revenue_dzd', 'الإيراد المتوقع', dzd(summary.monthly_revenue_dzd), data.environment?.activity === 'ecommerce' ? 'بعد احتساب المرتجعات المتوقعة' : 'شهرياً وفق الفرضيات'],
      ['contribution_margin_dzd', `هامش المساهمة ${subscription ? 'للاشتراك' : 'للطلب'}`, dzd(financial.contribution_margin_dzd), `لكل ${unitNoun}`],
      ['break_even_orders', 'نقطة التعادل', num(summary.break_even_orders), `${unitNoun} شهرياً`],
    ];

    $('#lmMetrics').innerHTML = topCards.map(([key, label, value, note]) => {
      const def = defs[key];
      const tooltip = def ? `${def.title}
• المعنى: ${def.description}
• المعادلة: ${def.formula}
• المصدر: ${def.source} (${def.kind})` : '';
      return `<div class="lm-top-metric" data-tooltip="${esc(tooltip)}">
        <span>${esc(label)}</span>
        <b>${esc(value)}</b>
        <small>${esc(note)}</small>
      </div>`;
    }).join('');

    $('#lmMetricCards').innerHTML = [
      ['entry_rate_pct', data.environment?.activity==='ecommerce'?'نسبة الوصول إلى المتجر الرقمي':'نسبة الدخول للمشروع', pct(behavior.entry_rate_pct), `${num(behavior.visitors)} من ${num(behavior.exposed_personas)} شخصية`],
      ['purchase_conversion_pct', 'التحويل الشرائي', pct(behavior.purchase_conversion_pct), 'قرارات شراء مكتملة'],
      ['abandonment_rate_pct', 'معدل التراجع والمغادرة', pct(behavior.abandonment_rate_pct), 'من إجمالي الزوار'],
      ['average_waiting_minutes', 'متوسط مدة الانتظار', `${num(behavior.average_waiting_minutes)} دقيقة`, 'زمن الخدمة التقديري'],
      ['trust_level_pct', 'مستوى الثقة في المشروع', pct(behavior.trust_level_pct), 'تقييم الطمأنينة والضمان'],
      ['repeat_purchase_intention_pct', 'نية الشراء المتكرر', pct(behavior.repeat_purchase_intention_pct), 'من المشترين'],
      ['expected_revenue_dzd', 'الإيراد المتوقع شهرياً', dzd(financial.expected_revenue_dzd), 'الطلبات × (1 − المرتجعات) × قيمة الطلب'],
      ['direct_cost_dzd', 'التكلفة المباشرة للوحدة', dzd(financial.direct_cost_dzd), 'سلعة + توصيل إن وجد'],
      ['contribution_margin_dzd', 'هامش المساهمة للطلب', dzd(financial.contribution_margin_dzd), 'بعد التكلفة المباشرة'],
      ['liquidity_pressure_dzd', 'ضغط السيولة التشغيلية', dzd(financial.liquidity_pressure_dzd), 'تكاليف ثابتة + مشتريات'],
    ].map(([key, label, value, note]) => {
      const def = defs[key];
      const tooltip = def ? `${def.title}
• ${def.description}
• المعادلة: ${def.formula}` : '';
      return `<div class="lm-metric-card" data-tooltip="${esc(tooltip)}">
        <span>${esc(label)}</span>
        <b>${esc(value)}</b>
        <small>${esc(note)}</small>
      </div>`;
    }).join('');
  }

  function renderLiveCards() {
    if (!S.data) return;
    const ids = visibleIds();
    const live = computeLive(S.data, S.time, ids);
    const capacity = Number(S.data.metrics?.live?.occupancy_capacity) || 0;
    const cards = [
      ['حاضرون الآن', num(live.active), capacity ? `من سعة ${num(capacity)}` : 'داخل المشهد'],
      ['وصلوا للمشهد', num(live.exposed), `من ${num(ids.size)} ظاهرين`],
      ['اشتروا حتى الآن', num(live.buyers), 'قرارات شراء ناجحة'],
      ['غادروا دون شراء', num(live.left), 'فرص غير مكتملة'],
      ['إيراد اللحظة', dzd(live.revenue), 'تراكمي داخل المشهد'],
      ['خسارة الفرص', dzd(live.lost), 'قيمة المبيعات الضائعة'],
    ];
    $('#lmLiveCards').innerHTML = cards.map(([label, value, note]) => `
      <div class="lm-live-card"><span>${esc(label)}</span><b>${esc(value)}</b><small>${esc(note)}</small></div>`).join('');
    $('#lmSnapshotTime').textContent = `${clockAt(S.time, S.duration)} · ${elapsed(S.time)}`;
  }

  function renderPeople() {
    if (!S.data) return;
    const people = visiblePersonas()
      .filter((p) => {
        const query = S.personSearch.trim().toLowerCase();
        if (!query) return true;
        return `${p.name} ${p.wilaya} ${p.segment} ${p.primary_motivation}`.toLowerCase().includes(query);
      })
      .sort((a, b) => Number(b.buys) - Number(a.buys) || a.id - b.id);
    const html = people.map((p) => `
      <button type="button" class="lm-person ${p.buys ? 'accepted' : 'abandoned'} ${String(p.id) === String(S.selectedId) ? 'selected' : ''}" data-lm-persona="${esc(p.id)}">
        <i>${p.buys ? '✓' : '×'}</i>
        <div><b>${esc(p.name)}</b><small>${esc(p.segment || '')} · ${esc(p.wilaya || '')}</small></div>
        <em>${Math.round((Number(p.probability) || 0) * 100)}%</em>
      </button>`).join('');
    const list = $('#lmPersonList');
    if (list) list.innerHTML = html || '<p class="lm-empty-line">لا توجد شخصية مطابقة للمرشحات الحالية.</p>';
    $('#lmVisibleCount').textContent = String(visiblePersonas().length);
  }

  function feedEvents() {
    if (!S.data) return [];
    const people = new Set(visiblePersonas().map((p) => p.id));
    return S.data.events
      .filter((e) => e.representative && people.has(e.personaId) && e.timestamp <= S.time)
      .sort((a, b) => b.timestamp - a.timestamp)
      .slice(0, 45);
  }

  function renderFeed(force = false) {
    if (!S.data) return;
    const key = `${Math.floor(S.time)}:${JSON.stringify(S.filters)}:${S.selectedEventId || ''}`;
    if (!force && key === S.lastFeedKey) return;
    S.lastFeedKey = key;
    const events = feedEvents();
    $('#lmFeedCount').textContent = String(events.length);
    const feed = $('#lmFeed');
    if (!events.length) {
      feed.innerHTML = `<div class="lm-empty-line">الحركة لم تبدأ بعد. شغّل المحاكاة لتبدأ الشخصيات بالتحرك.</div>`;
      return;
    }
    const scroll = feed.scrollTop;
    feed.innerHTML = events.map((e) => {
      const impact = impactText(e);
      const eventPersona = personaById(e.personaId);
      const loc = locationOf(S.data, e.location);
      return `<button type="button" class="lm-event ${String(e.id) === String(S.selectedEventId) ? 'selected' : ''}" data-lm-event="${esc(e.id)}">
        <span class="lm-event-time">${clockAt(e.timestamp, S.duration)}</span>
        <i class="lm-event-dot ${e.category === 'accepted' ? 'lime' : 'coral'}"></i>
        <div class="lm-event-copy">
          <b>${esc(e.personaName || eventPersona?.name || 'شخصية')}</b>
          <span>${esc(e.actionText || e.label)}</span>
          <small>${esc(loc.label)}${impact ? ` · ${esc(impact)}` : ''}</small>
        </div>
      </button>`;
    }).join('');
    feed.scrollTop = scroll;
  }

  function updateHud(force = false) {
    if (!S.data) return;
    const ids = visibleIds();
    const live = computeLive(S.data, S.time, ids);
    const capacity = Number(S.data.metrics?.live?.occupancy_capacity) || 0;
    $('#lmClock').textContent = clockAt(S.time, S.duration);
    $('#lmOccupancy').textContent = capacity ? `إشغال ${num(live.active)} / ${num(capacity)}` : `نشطون ${num(live.active)}`;
    $('#lmSceneCount').textContent = `${num(ids.size)} ظاهر · ${num(S.personasTotal())} إجمالي`;
    $('#lmSpeedLabel').textContent = `${S.speed}×`;
    $('#lmProgress').style.width = `${clamp((S.time / Math.max(1, S.duration)) * 100, 0, 100)}%`;
    renderLiveCards();
    renderFeed(force);
    renderPeople();
    updateJourneyProgress();
  }

  S.personasTotal = () => S.data?.personas?.length || 0;

  function updateJourneyProgress() {
    $$('#lmTabBody .lm-tl-item').forEach((item) => {
      item.classList.toggle('reached', Number(item.dataset.t) <= S.time);
    });
  }

  /* ----------------------------------------------------------------------- */
  /* Inspector: Drawer & Tabs (Decision, Journey, Profile, Chat)             */
  /* ----------------------------------------------------------------------- */
  function setTab(tab) {
    S.tab = tab;
    $$('#lmPersonaDrawer .lm-tabs [data-lm-tab]').forEach((b) => {
      const active = b.dataset.lmTab === tab;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
    });
    renderInspector();
  }

  function setRightTab(tab) {
    S.rightTab = tab;
    $$('.lm-drawer-tabs .lm-d-tab').forEach((b) => {
      b.classList.toggle('active', b.dataset.lmRightTab === tab);
    });
    $$('#lmRightContent .lm-right-pane').forEach((pane) => {
      pane.classList.toggle('hidden', pane.dataset.pane !== tab);
    });
  }

  function toggleRightDrawer(force) {
    const drawer = $('#lmRightDrawer');
    if (!drawer) return;
    S.rightDrawerOpen = force !== undefined ? Boolean(force) : !S.rightDrawerOpen;
    drawer.classList.toggle('collapsed', !S.rightDrawerOpen);
    $('#lmToggleRightBtn')?.classList.toggle('active', S.rightDrawerOpen);
    setTimeout(() => {
      S.renderer?.resize?.();
      S.compareRenderer?.resize?.();
    }, 260);
  }

  function closePersonaDrawer() {
    S.selectedId = null;
    S.selectedEventId = null;
    $('#lmPersonaDrawer')?.classList.add('hidden');
    S.renderer?.setSelected?.(null);
    S.compareRenderer?.setSelected?.(null);
    renderPeople();
    renderFeed(true);
    setTimeout(() => {
      S.renderer?.resize?.();
      S.compareRenderer?.resize?.();
    }, 260);
  }

  function selectPersona(id, eventId = null) {
    const persona = personaById(id);
    if (!persona) return;
    const changed = String(S.selectedId) !== String(id);
    S.selectedId = persona.id;
    if (changed) S.chat = [];
    if (eventId) {
      const e = eventById(eventId);
      if (e) {
        S.selectedEventId = e.id;
        S.time = Math.min(S.duration, Math.max(0, Number(e.timestamp) || 0));
        S.playing = false;
      }
    } else {
      S.selectedEventId = null;
    }

    // Open the left drawer smoothly
    const drawer = $('#lmPersonaDrawer');
    if (drawer) drawer.classList.remove('hidden');

    $$('#lmPersonaDrawer .lm-tabs [data-lm-tab]').forEach((b) => {
      const active = b.dataset.lmTab === S.tab;
      b.classList.toggle('active', active);
    });

    renderInspector();
    renderPeople();
    renderFeed(true);
    updateHud(true);
    S.renderer?.focusPersona?.(persona.id);
    S.compareRenderer?.focusPersona?.(persona.id);
    updatePlayButton();
  }

  function renderInspector() {
    if (!S.data) return;
    const persona = personaById(S.selectedId);
    const drawer = $('#lmPersonaDrawer');
    if (!persona) {
      if (drawer) drawer.classList.add('hidden');
      return;
    }
    if (drawer) drawer.classList.remove('hidden');

    $('#lmAvatar').textContent = (persona.name || 'ش').slice(0, 1);
    $('#lmInsName').textContent = persona.name || `شخصية #${persona.id}`;
    $('#lmInsSegment').textContent = `${persona.segment || 'شخصية'} · ${persona.customer_type || ''} · ${persona.wilaya || ''}`;
    const pill = $('#lmInsDecision');
    pill.classList.remove('hidden');
    pill.textContent = `${decisionLabel(persona.outcome)} (${Math.round((Number(persona.probability) || 0) * 100)}%)`;
    pill.className = `lm-decision-pill ${persona.buys ? 'accepted' : 'abandoned'}`;

    const body = $('#lmTabBody');
    if (S.tab === 'journey') body.innerHTML = journeyTab(persona);
    else if (S.tab === 'profile') body.innerHTML = profileTab(persona);
    else if (S.tab === 'chat') body.innerHTML = chatTab(persona);
    else body.innerHTML = decisionTab(persona);
  }

  /* Decision Tab (Sections 8, 9, 10, 11, 12) */
  function decisionTab(persona) {
    const struct = persona.structured_decision || {};
    const factors = persona.decision_factors || [];
    const platform = persona.platform_analysis || '';
    const quote = persona.persona_quote || '';

    return `
      <div class="lm-decision-view">
        <div class="lm-outcome-card ${persona.buys ? 'accepted' : 'abandoned'}">
          <div class="lm-outcome-title">
            <span>النتيجة: ${esc(struct.outcome || (persona.buys ? 'قرر الشراء.' : 'غادر دون شراء.'))}</span>
            <small>${Math.round((Number(persona.probability) || 0) * 100)}% احتمال</small>
          </div>
          <p style="margin:2px 0 0;font-size:10px;color:#cbe0d6;"><b>الدافع الأبرز:</b> ${esc(struct.main_driver || '—')}</p>
          ${struct.main_friction && struct.main_friction !== 'لا توجد تحفظات جوهرية' ? `<p style="margin:2px 0 0;font-size:10px;color:#efb5ad;"><b>نقطة الاحتكاك:</b> ${esc(struct.main_friction)}</p>` : ''}
        </div>

        <div class="lm-struct-section">
          <strong>السبب الرئيسي</strong>
          <p>${esc(struct.main_reason || persona.decision_reason || '—')}</p>
        </div>

        <div class="lm-struct-section">
          <strong>العوامل المساعدة</strong>
          <p>${esc(struct.supporting_factors || '—')}</p>
        </div>

        <div class="lm-struct-section">
          <strong>نقطة التحفظ</strong>
          <p>${esc(struct.reservation || '—')}</p>
        </div>

        <div class="lm-struct-section">
          <strong>ما الذي قد يغيّر القرار؟</strong>
          <p>${esc(struct.what_would_change || persona.would_change_my_mind || '—')}</p>
        </div>

        <!-- Platform Analysis vs Persona Quote (Section 11) -->
        ${platform ? `
        <div class="lm-analysis-box">
          <span class="lm-badge-platform">تحليل Fintwin</span>
          <p>${esc(platform)}</p>
        </div>` : ''}

        ${quote ? `
        <div class="lm-quote-box">
          <span class="lm-badge-quote">تعليق الشخصية</span>
          <blockquote>«${esc(quote)}»</blockquote>
        </div>` : ''}

        <!-- Decision Factors Bar (Section 12) -->
        <div class="lm-factors-panel">
          <h4>
            <span>دافع القرار ومساهمة العوامل</span>
            <small>المساهمة المرجحة</small>
          </h4>
          <div class="lm-factor-rows">
            ${factors.map((f) => `
              <div class="lm-factor-item ${f.sentiment}">
                <span class="label" title="${esc(f.description || f.label)}">${esc(f.label)}</span>
                <span class="score">${f.sign}${f.impact}</span>
              </div>`).join('')}
          </div>
          <div class="lm-confidence-row">
            <span>مستوى الثقة في التقدير</span>
            <b>${Math.round((Number(struct.confidence || persona.decision_confidence || 0.8)) * 100)}%</b>
          </div>
        </div>
      </div>`;
  }

  function journeyTab(persona) {
    const locations = S.data?.environment?.locations || {};
    const events = persona._events || [];
    if (!events.length) return '<p class="lm-empty-line">لا توجد أحداث محفوظة لهذه الشخصية.</p>';
    return `<div class="lm-timeline">
      ${events.map((e) => {
        const impact = impactText(e);
        const loc = locations[e.location]?.label || e.location;
        return `<button type="button" class="lm-tl-item ${e.timestamp <= S.time ? 'reached' : ''} ${String(e.id) === String(S.selectedEventId) ? 'selected' : ''}" data-lm-timeline="${esc(e.id)}" data-t="${e.timestamp}">
          <i></i>
          <div>
            <b>${esc(e.label)}</b>
            <p>${esc(e.actionText || '')}</p>
            <small>${clockAt(e.timestamp, S.duration)} · ${esc(loc)}${impact ? ` · <em style="color:#64fbd2;">${esc(impact)}</em>` : ''}</small>
          </div>
        </button>`;
      }).join('')}
    </div>`;
  }

  function profileTab(persona) {
    const offer = persona.selected_offer || {};
    const price = persona.price_answers || {};
    const impact = persona.expected_financial_impact || {};
    return `
      <div class="lm-profile-grid">
        <div><small>العمر</small><b>${persona.age} سنة</b></div>
        <div><small>الجنس</small><b>${persona.gender || '—'}</b></div>
        <div><small>الولاية</small><b>${persona.wilaya}</b></div>
        <div><small>الدخل الشهري التقديري</small><b>${dzd(persona.monthly_income_estimate)}</b></div>
        <div><small>شريحة الدخل</small><b>${persona.income_band}</b></div>
        <div><small>القوة الشرائية</small><b>${persona.purchasing_power}</b></div>
        <div><small>طريقة الدفع المفضلة</small><b>${persona.preferred_payment}</b></div>
        <div><small>وسيلة المواصلات</small><b>${persona.transportation}</b></div>
        <div><small>نوع الزبون</small><b>${persona.customer_type}</b></div>
        <div><small>العرض المدروس</small><b>${offer.name ? `${offer.name} (${dzd(offer.price)})` : 'العرض الرئيسي'}</b></div>
      </div>
      <div class="lm-bars" style="margin-top:12px;">
        <h4 style="font-size:10px;margin:0 0 4px;color:#dcece5;">حساسيات الشخصية</h4>
        <div class="lm-mini-bar"><span>السعر</span><i><em style="width:${clamp(persona.price_sensitivity, 0, 100)}%"></em></i><b>${Math.round(persona.price_sensitivity || 0)}%</b></div>
        <div class="lm-mini-bar"><span>الثقة</span><i><em style="width:${clamp(persona.trust_sensitivity, 0, 100)}%"></em></i><b>${Math.round(persona.trust_sensitivity || 0)}%</b></div>
        <div class="lm-mini-bar"><span>السهولة</span><i><em style="width:${clamp(persona.convenience_need, 0, 100)}%"></em></i><b>${Math.round(persona.convenience_need || 0)}%</b></div>
        <div class="lm-mini-bar"><span>التجربة</span><i><em style="width:${clamp(persona.experience_need, 0, 100)}%"></em></i><b>${Math.round(persona.experience_need || 0)}%</b></div>
      </div>
      <div class="lm-profile-grid compact" style="margin-top:12px;">
        <div><small>إيراد محقق</small><b>${dzd(impact.revenue_dzd)}</b></div>
        <div><small>هامش محقق</small><b>${dzd(impact.margin_dzd)}</b></div>
        <div><small>إيراد ضائع</small><b>${dzd(impact.lost_revenue_dzd)}</b></div>
        <div><small>هامش ضائع</small><b>${dzd(impact.lost_margin_dzd)}</b></div>
      </div>`;
  }

  function chatTab(persona) {
    const presets = persona.buys
      ? ['علاش قبلت الشراء؟', 'كيفاش تشوف السعر؟', 'واش رايك في المكان؟', 'واش يخليك ترجع؟']
      : ['علاش ما شريتش؟', 'واش يبدّل رأيك؟', 'كيفاش تشوف السعر؟', 'واش رايك في الانتظار والموقف؟'];
    const log = S.chat.length
      ? S.chat.map((m) => `<div class="lm-chat-msg ${m.role}"><span>${m.role === 'user' ? 'أنت' : esc(persona.name)}</span><p>${esc(m.text)}</p></div>`).join('')
      : `<div class="lm-chat-intro"><b>محادثة مؤسّسة على القرار المحسوب</b><p>الأجوبة مبنية مباشرة على ملف الشخصية وقرارها المحفوظ، دون توليد أرقام عشوائية.</p></div>`;
    return `
      <div class="lm-chat-log" id="lmChatLog">${log}${S.chatBusy ? '<div class="lm-chat-msg persona"><span>…</span><p>نقرأ الملف والقرار…</p></div>' : ''}</div>
      <div class="lm-chat-presets">${presets.map((q) => `<button type="button" class="lm-chip-btn" data-lm-chat="${esc(q)}">${esc(q)}</button>`).join('')}</div>
      <form class="lm-chat-form" data-lm-chat-form>
        <input name="question" autocomplete="off" minlength="2" maxlength="800" placeholder="اسأل الشخصية عن تفاصيل قرارها…" aria-label="سؤال للشخصية">
        <button type="submit" class="lm-btn lm-btn-lime" ${S.chatBusy ? 'disabled' : ''}>إرسال</button>
      </form>`;
  }

  async function askPersona(question) {
    const persona = personaById(S.selectedId);
    if (!persona || !question.trim() || S.chatBusy) return;
    const token = S.openToken;
    S.chatBusy = true;
    S.chat.push({ role: 'user', text: question.trim() });
    renderInspector();
    try {
      const demo = Boolean(S.demoId);
      const url = demo
        ? `/api/demo/${encodeURIComponent(S.demoId)}/live-market/chat`
        : `/api/projects/${encodeURIComponent(S.projectId)}/live-market/chat`;
      const payload = demo
        ? { persona_id: persona.id, question: question.trim(), ...(S.scenarioMessage ? { scenario_message: S.scenarioMessage } : {}) }
        : { run_id: S.activeRunId, persona_id: persona.id, question: question.trim() };
      const response = await lmApi(url, { method: 'POST', body: JSON.stringify(payload) });
      if (token !== S.openToken || !S.mounted) return;
      S.chat.push({ role: 'persona', text: response.answer || 'لا توجد إجابة محفوظة.' });
    } catch (error) {
      if (token !== S.openToken || !S.mounted) return;
      S.chat.push({ role: 'persona', text: `تعذر الاتصال: ${error.message}` });
    } finally {
      if (token !== S.openToken) return;
      S.chatBusy = false;
      renderInspector();
      const log = $('#lmChatLog');
      if (log) log.scrollTop = log.scrollHeight;
    }
  }

  /* ----------------------------------------------------------------------- */
  /* Comparison                                                              */
  /* ----------------------------------------------------------------------- */
  function renderComparisonPanel() {
    const panel = $('#lmComparePanel');
    if (!S.comparison || !S.comparisonOpen) {
      panel.classList.add('hidden');
      return;
    }
    panel.classList.remove('hidden');
    const comp = S.comparison;
    panel.innerHTML = `
      <div class="lm-panel-head">
        <div><span class="lm-kicker">BEFORE / AFTER</span><h2>مقارنة قبل/بعد</h2></div>
        <div class="lm-compare-actions">
          <button type="button" class="lm-btn ${S.split ? 'lm-btn-lime' : 'lm-btn-soft'}" data-lm-split>${S.split ? 'إيقاف الانقسام' : 'عرض منقسم'}</button>
          <button type="button" class="lm-btn lm-btn-ghost" data-lm-close-compare>إخفاء</button>
        </div>
      </div>
      <div class="lm-change-chips">${(comp.changes || []).map((c) => `<span>${esc(c)}</span>`).join('')}</div>
      <div class="lm-compare-metrics">
        <div class="lm-compare-head-row"><span>المؤشر</span><b>قبل</b><b>بعد</b><em>الفرق</em></div>
        ${Object.entries(comp.metrics?.financial || {}).map(([key, v]) => `
          <div class="lm-compare-row">
            <span>${esc(key)}</span>
            <b>${esc(num(v.baseline))}</b>
            <b>${esc(num(v.scenario))}</b>
            <em class="${v.delta > 0 ? 'up' : v.delta < 0 ? 'down' : ''}">${v.delta > 0 ? '+' : ''}${esc(num(v.delta))}</em>
          </div>`).join('')}
      </div>`;
  }

  function toggleComparison(force) {
    if (!S.comparison) {
      notify('شغّل سيناريو أولاً لتتوفر مقارنة قبل/بعد.', true);
      return;
    }
    S.comparisonOpen = force === undefined ? !S.comparisonOpen : Boolean(force);
    renderComparisonPanel();
    if (S.comparisonOpen) $('#lmComparePanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function toggleSplit() {
    if (!S.comparison || !S.baseline) {
      notify('المقارنة تحتاج سيناريو محسوباً أولاً.', true);
      return;
    }
    S.split = !S.split;
    await syncSplitRenderer();
    renderComparisonPanel();
  }

  async function syncSplitRenderer() {
    const stage = $('#lmStage');
    const wrap = $('#lmCompareWrap');
    const afterTag = $('#lmAfterTag');
    stage?.classList.toggle('split', S.split);
    wrap?.classList.toggle('hidden', !S.split);
    afterTag?.classList.toggle('hidden', !S.split);
    if (!S.split) {
      destroyCompareRenderer();
      return;
    }
    if (!S.baseline) return;
    const canvas = replaceCanvas('lmCompareCanvas', { ariaLabel: 'مشهد السوق قبل التغيير' });
    destroyCompareRenderer();
    try {
      await loadThree();
      S.compareRenderer = createThreeRenderer(canvas, S.baseline, {
        lowPerf: S.lowPerf,
        onPick: (id) => selectPersona(id),
      });
    } catch (e) {
      S.compareRenderer = createCanvasRenderer(canvas, S.baseline, {
        lowPerf: S.lowPerf,
        onPick: (id) => selectPersona(id),
      });
    }
    S.compareRenderer.resize();
    S.compareRenderer.setVisible([...visibleIds(S.baseline)]);
    S.compareRenderer.setSelected(S.selectedId);
  }

  /* ----------------------------------------------------------------------- */
  /* Scenario Runner                                                         */
  /* ----------------------------------------------------------------------- */
  function scenarioPresets() {
    const activity = S.data?.environment?.activity;
    const value = S.data?.run?.config || {};
    const presets = [];
    if (activity === 'cafe' || activity === 'restaurant') {
      if (!value.parking) presets.push('أضف موقف سيارات');
      presets.push(`خفّض وقت الانتظار إلى ${activity === 'restaurant' ? 10 : 6} دقائق`);
      if (!value.wifi && activity === 'cafe') presets.push('أضف Wi-Fi');
    }
    if (activity === 'retail') {
      if (!value.fitting_rooms) presets.push('أضف غرف القياس');
      if (!value.clear_prices) presets.push('وضّح الأسعار');
      if (!value.parking) presets.push('أضف موقف سيارات');
    }
    if (activity === 'ecommerce') {
      if (!value.free_delivery) presets.push('التوصيل مجاني');
      presets.push('أضف الدفع بالبطاقة');
      presets.push('قوّي الثقة بإثباتات واضحة');
    }
    presets.push('زيد السعر 10% وقارن الأثر');
    return [...new Set(presets)].slice(0, 5);
  }

  function renderScenarioPanel() {
    $('#lmPresets').innerHTML = scenarioPresets().map((p) => `<button type="button" class="lm-chip-btn" data-lm-preset="${esc(p)}">${esc(p)}</button>`).join('');
  }

  async function runScenario(message) {
    const text = String(message || $('#lmScenarioText')?.value || '').trim();
    if (!text) {
      notify('اكتب التغيير المطلوب أولاً.', true);
      return;
    }
    const token = S.openToken;
    const btn = $('[data-lm-run-scenario]');
    if (btn) { btn.disabled = true; btn.textContent = 'نعيد تشغيل المحاكاة…'; }
    try {
      const demo = Boolean(S.demoId);
      const url = demo
        ? `/api/demo/${encodeURIComponent(S.demoId)}/live-market/scenario`
        : `/api/projects/${encodeURIComponent(S.projectId)}/live-market/scenario`;
      const response = await lmApi(url, {
        method: 'POST',
        body: JSON.stringify({ run_id: S.activeRunId, message: text }),
      });
      if (token !== S.openToken || !S.mounted) return;
      S.baseline = S.data;
      S.comparison = response.before_after || null;
      S.comparisonOpen = false;
      S.data = prepareDataset(response.live_market);
      S.activeRunId = response.run_id || S.data.run?.id;
      S.scenarioMessage = demo ? text : null;
      S.duration = S.data._duration;
      S.time = 0;
      S.playing = !S.reduceMotion;
      S.selectedId = null;
      S.selectedEventId = null;
      S.chat = [];
      S.filters = emptyFilters();
      renderMeta();
      renderFilters();
      renderMetrics();
      renderPeople();
      renderScenarioPanel();
      renderInspector();
      updateControls();
      await initRenderer();
      if (S.split) await syncSplitRenderer();
      updateHud(true);
      $('#lmScenarioText').value = '';
      notify('تم تشغيل السيناريو بنجاح.');
    } catch (err) {
      if (token !== S.openToken) return;
      notify(err.message, true);
    } finally {
      if (btn && btn.isConnected) { btn.disabled = false; btn.textContent = 'شغّل سيناريو جديد'; }
    }
  }

  /* ----------------------------------------------------------------------- */
  /* Three.js 3D Engine: Low-poly Café, Humanoids, Smart Pins (Sections 2-5) */
  /* ----------------------------------------------------------------------- */
  let threePromise = null;
  function loadThree() {
    if (window.THREE) return Promise.resolve(window.THREE);
    if (!threePromise) {
      threePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/static/vendor/three.min.js';
        script.async = true;
        script.onload = () => window.THREE ? resolve(window.THREE) : reject(new Error('Three.js غير متاح.'));
        script.onerror = () => reject(new Error('تعذر تحميل Three.js.'));
        document.head.appendChild(script);
      });
    }
    return threePromise;
  }

  function replaceCanvas(id, { ariaLabel } = {}) {
    const old = document.getElementById(id);
    const canvas = document.createElement('canvas');
    canvas.id = id;
    if (ariaLabel) canvas.setAttribute('aria-label', ariaLabel);
    if (old) {
      for (const attr of old.attributes) {
        if (!['id', 'aria-label'].includes(attr.name)) canvas.setAttribute(attr.name, attr.value);
      }
      old.replaceWith(canvas);
    }
    return canvas;
  }

  function destroyRenderer() {
    try { S.renderer?.destroy?.(); } catch (e) { console.warn(e); }
    S.renderer = null;
  }

  function destroyCompareRenderer() {
    try { S.compareRenderer?.destroy?.(); } catch (e) { console.warn(e); }
    S.compareRenderer = null;
  }

  function createThreeRenderer(canvas, data, options = {}) {
    const THREE = window.THREE;
    if (!THREE) throw new Error('Three.js غير محمّل.');
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: !options.lowPerf,
      alpha: false,
      powerPreference: options.lowPerf ? 'low-power' : 'high-performance',
    });
    renderer.setClearColor(0xf1f7f1, 1);
    if (!options.lowPerf) {
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    renderer.setPixelRatio(options.lowPerf ? 1 : Math.min(2, Math.max(1.5, window.devicePixelRatio || 1)));

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0xf1f7f1, 38, 90);

    const environment = data.environment;
    const physical = environment.kind === 'physical';
    const fitnessScene = environment.visual_activity === 'fitness';
    const cameraCenterX = fitnessScene ? 0 : (physical ? 3.6 : 1.5);

    // Camera setup (Section 4): Framed close to the cafe and activity
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 140);
    const cameraState = {
      azimuth: fitnessScene ? -0.42 : (physical ? -0.58 : 0),
      elevation: physical ? 0.72 : 1.15,
      target: new THREE.Vector3(cameraCenterX, 0.6, 0.0),
      targetGoal: new THREE.Vector3(cameraCenterX, 0.6, 0.0),
      zoom: 1,
      goalZoom: 1,
      defaultAzimuth: fitnessScene ? -0.42 : (physical ? -0.58 : 0),
      defaultElevation: physical ? 0.72 : 1.15,
      defaultTarget: new THREE.Vector3(cameraCenterX, 0.6, 0.0),
    };

    const abort = new AbortController();
    const personas = [];
    const locationPins = [];
    let width = 1;
    let height = 1;
    let selectedId = null;
    let visible = new Set((data.personas || []).filter((p) => p.representative).map((p) => p.id));
    let elapsedTime = 0;

    // Lighting: Atmospheric FinTech ambiance
    const ambient = new THREE.AmbientLight(0xffffff, options.lowPerf ? 1.65 : 1.35);
    scene.add(ambient);

    const sun = new THREE.DirectionalLight(0xffffff, options.lowPerf ? 1.0 : 1.6);
    sun.position.set(-6, 14, 10);
    if (!options.lowPerf) {
      sun.castShadow = true;
      sun.shadow.mapSize.set(1024, 1024);
      sun.shadow.camera.near = 1;
      sun.shadow.camera.far = 45;
      sun.shadow.camera.left = -16;
      sun.shadow.camera.right = 16;
      sun.shadow.camera.top = 14;
      sun.shadow.camera.bottom = -14;
    }
    scene.add(sun);

    const rim = new THREE.DirectionalLight(0x64fbd2, 0.45);
    rim.position.set(8, 6, -10);
    scene.add(rim);

    // Foundation Base Ground
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(54, 42),
      new THREE.MeshStandardMaterial({ color: 0xe4efe5, roughness: 0.98, metalness: 0.0 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.04;
    ground.receiveShadow = !options.lowPerf;
    scene.add(ground);

    // -------------------------------------------------------------------------
    // CANVAS SPRITE & BILLBOARD HELPERS
    // -------------------------------------------------------------------------
    function roundRect(ctx, x, y, w, h, r) {
      if (typeof ctx.roundRect === 'function') {
        ctx.beginPath();
        ctx.roundRect(x, y, w, h, r);
        ctx.closePath();
        return;
      }
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + w, y, x + w, y + h, r);
      ctx.arcTo(x + w, y + h, x, y + h, r);
      ctx.arcTo(x, y + h, x, y, r);
      ctx.arcTo(x, y, x + w, y, r);
      ctx.closePath();
    }

    function makeSignSprite(THREE, text, color = '#64fbd2', scale = 2.8) {
      const canvas = document.createElement('canvas');
      canvas.width = 512;
      canvas.height = 128;
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, 512, 128);
      ctx.fillStyle = 'rgba(10, 20, 16, 0.92)';
      ctx.strokeStyle = 'rgba(100, 251, 210, 0.65)';
      ctx.lineWidth = 2.5;
      roundRect(ctx, 6, 8, 500, 112, 16);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = color;
      ctx.font = '800 38px Alexandria, Segoe UI, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, 256, 64, 480);

      const texture = new THREE.CanvasTexture(canvas);
      texture.minFilter = THREE.LinearFilter;
      const mat = new THREE.SpriteMaterial({ map: texture, transparent: true });
      const sprite = new THREE.Sprite(mat);
      sprite.scale.set(scale, scale * 0.25, 1);
      return sprite;
    }

    function makeLabelSprite(THREE, text) {
      const c = document.createElement('canvas');
      c.width = 440;
      c.height = 100;
      const ctx = c.getContext('2d');
      ctx.clearRect(0, 0, 440, 100);
      ctx.fillStyle = 'rgba(7, 16, 12, 0.92)';
      ctx.strokeStyle = 'rgba(100, 251, 210, 0.5)';
      ctx.lineWidth = 2;
      roundRect(ctx, 6, 8, 428, 84, 16);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = '#e8faf2';
      ctx.font = '700 34px Alexandria, Segoe UI, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, 220, 50, 400);

      const texture = new THREE.CanvasTexture(c);
      texture.minFilter = THREE.LinearFilter;
      const mat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false });
      const sprite = new THREE.Sprite(mat);
      sprite.scale.set(2.4, 0.55, 1);
      return sprite;
    }

    // -------------------------------------------------------------------------
    // BUILD ARCHITECTURAL ENVIRONMENT ACCORDING TO BUSINESS TYPE
    // -------------------------------------------------------------------------
    const act = environment.visual_activity || environment.activity || 'cafe';
    const projTitle = data.project?.name || 'Fintwin Project';

    if (act === 'cafe') {
      buildCafeEnvironment(THREE, scene, environment, projTitle, options);
    } else if (act === 'restaurant') {
      buildRestaurantEnvironment(THREE, scene, environment, projTitle, options);
    } else if (act === 'retail') {
      buildRetailEnvironment(THREE, scene, environment, projTitle, options);
    } else if (act === 'ecommerce') {
      buildEcommerceJourneyEnvironment(THREE, scene, environment, projTitle, options);
    } else if (act === 'service') {
      buildServiceEnvironment(THREE, scene, environment, projTitle, options);
    } else if (act === 'fitness') {
      buildFitnessEnvironment(THREE, scene, environment, projTitle, options);
    } else {
      buildUniversalJourneyEnvironment(THREE, scene, environment, projTitle, options);
    }

    // BUILD SMART LOCATION PINS & BILLBOARDS (Section 5)
    buildLocationPins(THREE, scene, environment, locationPins, options);

    // BUILD HUMANOID CHARACTERS (Section 3 - Critical: populates the 3D scene with representative people)
    if (act === 'ecommerce' || act === 'other') buildDigitalAvatars(THREE, scene, data, personas);
    else buildHumanoidCharacters(THREE, scene, data, personas, options);

    // -------------------------------------------------------------------------
    // 1. CAFE ENVIRONMENT
    // -------------------------------------------------------------------------
    function buildCafeEnvironment(THREE, scene, env, projectName, opts) {
      const matRoad = new THREE.MeshStandardMaterial({ color: 0x3b4941, roughness: 0.95 });
      const matCurb = new THREE.MeshStandardMaterial({ color: 0x24342c, roughness: 0.8 });
      const matSidewalk = new THREE.MeshStandardMaterial({ color: 0x718475, roughness: 0.9 });
      const matStripe = new THREE.MeshBasicMaterial({ color: 0x769485 });
      const matZebra = new THREE.MeshBasicMaterial({ color: 0xe6f5ed });
      const matFloor = new THREE.MeshStandardMaterial({ color: 0xb9c9b7, roughness: 0.65, metalness: 0.02 });
      const matWall = new THREE.MeshStandardMaterial({ color: 0xd9e9dc, roughness: 0.85 });
      const matWood = new THREE.MeshStandardMaterial({ color: 0x4a3424, roughness: 0.65 });
      const matCounterBase = new THREE.MeshStandardMaterial({ color: 0x1c2e25, roughness: 0.7 });
      const matCounterTop = new THREE.MeshStandardMaterial({ color: 0xe6f3ec, roughness: 0.25, metalness: 0.1 });
      const matGlass = new THREE.MeshStandardMaterial({ color: 0x64fbd2, roughness: 0.1, metalness: 0.2, transparent: true, opacity: 0.32 });
      const matLime = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });
      const matMetal = new THREE.MeshStandardMaterial({ color: 0x24372e, roughness: 0.4, metalness: 0.7 });
      const matChrome = new THREE.MeshStandardMaterial({ color: 0xddebe3, roughness: 0.15, metalness: 0.85 });
      const matWarmGold = new THREE.MeshStandardMaterial({ color: 0xc8a462, roughness: 0.3, metalness: 0.6 });
      const matFoliage = new THREE.MeshStandardMaterial({ color: 0x1d5438, roughness: 0.7 });
      const matPot = new THREE.MeshStandardMaterial({ color: 0xd0dfd7, roughness: 0.5 });

      // Street & Sidewalk (Left side along Z)
      const road = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.04, 22), matRoad);
      road.position.set(-6.0, 0, 0);
      road.receiveShadow = !opts.lowPerf;
      scene.add(road);

      for (let z = -9.0; z <= 9.0; z += 2.4) {
        const line = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.02, 1.2), matStripe);
        line.position.set(-6.0, 0.03, z);
        scene.add(line);
      }

      for (let z = 0.2; z <= 2.0; z += 0.45) {
        const stripe = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.02, 0.24), matZebra);
        stripe.position.set(-6.0, 0.03, z);
        scene.add(stripe);
      }

      const sidewalk = new THREE.Mesh(new THREE.BoxGeometry(3.8, 0.12, 20), matSidewalk);
      sidewalk.position.set(-1.9, 0.06, 0);
      sidewalk.receiveShadow = !opts.lowPerf;
      scene.add(sidewalk);

      const curb = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.14, 20), matCurb);
      curb.position.set(-3.8, 0.07, 0);
      scene.add(curb);

      for (const z of [-2.4, -1.2, 0.0]) {
        const pLine = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.02, 0.06), matStripe);
        pLine.position.set(-4.6, 0.04, z);
        scene.add(pLine);
      }

      createCar(THREE, scene, -4.6, 0.04, -1.8, 0x16382a);
      createCar(THREE, scene, -4.6, 0.04, -0.6, 0x2b3d46);
      createOutdoorTerrace(THREE, scene, -1.8, 0.12, 2.4, matWood, matMetal, matLime, matFoliage, matPot);

      // Building Structure
      const floor = new THREE.Mesh(new THREE.BoxGeometry(10.6, 0.14, 7.8), matFloor);
      floor.position.set(5.3, 0.07, -0.35);
      floor.receiveShadow = !opts.lowPerf;
      scene.add(floor);

      const backWall = new THREE.Mesh(new THREE.BoxGeometry(10.6, 3.2, 0.22), matWall);
      backWall.position.set(5.3, 1.6, -4.2);
      backWall.castShadow = !opts.lowPerf;
      scene.add(backWall);

      for (let x = 0.4; x <= 10.2; x += 0.65) {
        const batten = new THREE.Mesh(new THREE.BoxGeometry(0.04, 3.1, 0.04), matWood);
        batten.position.set(x, 1.6, -4.08);
        scene.add(batten);
      }

      const rightWall = new THREE.Mesh(new THREE.BoxGeometry(0.22, 3.2, 7.8), matWall);
      rightWall.position.set(10.5, 1.6, -0.35);
      rightWall.castShadow = !opts.lowPerf;
      scene.add(rightWall);

      const win1 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 2.6, 3.6), matGlass);
      win1.position.set(0.0, 1.35, -2.1);
      scene.add(win1);

      const pillar1 = new THREE.Mesh(new THREE.BoxGeometry(0.26, 3.2, 0.26), matWall);
      pillar1.position.set(0.0, 1.6, -4.2);
      scene.add(pillar1);

      const doorPortal = new THREE.Mesh(new THREE.BoxGeometry(0.18, 2.8, 1.8), matWall);
      doorPortal.position.set(0.0, 1.4, 1.3);
      scene.add(doorPortal);

      const glassDoor = new THREE.Mesh(new THREE.BoxGeometry(0.04, 2.4, 1.6), matGlass);
      glassDoor.position.set(0.0, 1.25, 1.3);
      scene.add(glassDoor);

      const win2 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 2.6, 1.2), matGlass);
      win2.position.set(0.0, 1.35, 2.9);
      scene.add(win2);

      const signBoard = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.65, 3.0), matWall);
      signBoard.position.set(0.0, 2.95, 1.3);
      scene.add(signBoard);

      const signSprite = makeSignSprite(THREE, projectName || 'NOYA WORK CAFÉ', '#64fbd2', 3.2);
      signSprite.position.set(-0.2, 2.95, 1.3);
      scene.add(signSprite);

      // Order Counter & Barista Station
      const counterBase = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.82, 0.85), matCounterBase);
      counterBase.position.set(4.0, 0.47, -2.8);
      counterBase.castShadow = !opts.lowPerf;
      scene.add(counterBase);

      const counterTop = new THREE.Mesh(new THREE.BoxGeometry(4.35, 0.08, 0.95), matCounterTop);
      counterTop.position.set(4.0, 0.92, -2.8);
      scene.add(counterTop);

      const pastryCase = new THREE.Mesh(new THREE.BoxGeometry(0.85, 0.44, 0.55), matGlass);
      pastryCase.position.set(2.5, 1.18, -2.8);
      scene.add(pastryCase);

      const posBase = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.04, 0.24), matMetal);
      posBase.position.set(3.6, 0.98, -2.8);
      scene.add(posBase);
      const posScreen = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.22, 0.04), matLime);
      posScreen.position.set(3.6, 1.12, -2.76);
      posScreen.rotation.x = -0.3;
      scene.add(posScreen);

      const espresso = new THREE.Mesh(new THREE.BoxGeometry(0.68, 0.52, 0.44), matChrome);
      espresso.position.set(4.7, 1.22, -2.8);
      scene.add(espresso);

      for (const px of [5.4, 5.7]) {
        const toGoCup = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.035, 0.12, 10), matCounterTop);
        toGoCup.position.set(px, 1.02, -2.78);
        scene.add(toGoCup);
      }

      for (const sy of [1.6, 2.2]) {
        const shelf = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.04, 0.26), matWood);
        shelf.position.set(4.2, sy, -3.95);
        scene.add(shelf);
      }

      const menuBoard = new THREE.Mesh(new THREE.BoxGeometry(3.0, 1.3, 0.06), matWall);
      menuBoard.position.set(4.0, 2.7, -4.06);
      scene.add(menuBoard);

      const menuSprite = makeSignSprite(THREE, 'قائمة الأسعار والقهوة المختصة', '#64fbd2', 3.0);
      menuSprite.position.set(4.0, 2.7, -3.98);
      scene.add(menuSprite);

      for (const qx of [1.8, 2.7, 3.6]) {
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.8, 8), matWarmGold);
        pole.position.set(qx, 0.46, -1.8);
        scene.add(pole);
      }
      const rope = new THREE.Mesh(new THREE.CylinderGeometry(0.016, 0.016, 1.8, 6), matLime);
      rope.rotation.z = Math.PI / 2;
      rope.position.set(2.7, 0.76, -1.8);
      scene.add(rope);

      // Wi-Fi Work Zone
      const workBar = new THREE.Mesh(new THREE.BoxGeometry(0.75, 0.86, 3.8), matWood);
      workBar.position.set(9.8, 0.5, -0.8);
      scene.add(workBar);

      for (const wz of [-2.0, -0.8, 0.4]) {
        const laptop = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.02, 0.24), matMetal);
        laptop.position.set(9.7, 0.95, wz);
        scene.add(laptop);

        const screen = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.24, 0.32), matLime);
        screen.position.set(9.56, 1.08, wz);
        screen.rotation.z = 0.2;
        scene.add(screen);

        const stoolSeat = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.05, 12), matWood);
        stoolSeat.position.set(8.8, 0.62, wz);
        scene.add(stoolSeat);
      }

      createTableAndChairs(THREE, scene, 4.0, 0.08, 0.8, matWood, matMetal, false);
      createTableAndChairs(THREE, scene, 6.8, 0.08, 0.6, matWood, matMetal, false);
      createTableAndChairs(THREE, scene, 5.4, 0.08, 2.4, matWood, matMetal, false);

      // Seated Regular Customers (Active and visible so the café is never empty)
      createSeatedCustomer(THREE, scene, 8.8, 0.08, -0.8, 0x2e6188, 0xf2d6bd); // At Wi-Fi laptop bar
      createSeatedCustomer(THREE, scene, 4.0, 0.08, 0.3, 0xd4a359, 0xd8b28f);  // At dining table
      createSeatedCustomer(THREE, scene, 6.8, 0.08, 1.2, 0x64fbd2, 0xad7a54);  // At central table

      createPlant(THREE, scene, 0.5, 0.08, -3.7, matFoliage, matPot);
      createPlant(THREE, scene, 0.5, 0.08, 3.2, matFoliage, matPot);

      // Boutique Staff at Cashier wrap
      const boutiqueStaff = new THREE.Group();
      boutiqueStaff.position.set(3.8, 0.08, -2.8);
      boutiqueStaff.scale.set(1.4, 1.4, 1.4);
      const bsTorso = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.44, 0.18), new THREE.MeshStandardMaterial({ color: 0x162c22 }));
      bsTorso.position.y = 0.68;
      boutiqueStaff.add(bsTorso);
      const bsHead = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), new THREE.MeshStandardMaterial({ color: 0xf2d6bd }));
      bsHead.position.y = 1.02;
      boutiqueStaff.add(bsHead);
      scene.add(boutiqueStaff);

      // Customer browsing racks
      const rackShopper = new THREE.Group();
      rackShopper.position.set(3.2, 0.08, -3.2);
      rackShopper.scale.set(1.4, 1.4, 1.4);
      const rsTorso = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.44, 0.18), new THREE.MeshStandardMaterial({ color: 0xd4a359 }));
      rsTorso.position.y = 0.68;
      rackShopper.add(rsTorso);
      const rsHead = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), new THREE.MeshStandardMaterial({ color: 0xd8b28f }));
      rsHead.position.y = 1.02;
      rackShopper.add(rsHead);
      scene.add(rackShopper);
      createPlant(THREE, scene, 10.0, 0.08, -3.7, matFoliage, matPot);

      const counterLight = new THREE.PointLight(0xffeed0, 2.2, 12);
      counterLight.position.set(4.0, 3.0, -2.5);
      scene.add(counterLight);

      const diningLight = new THREE.PointLight(0xfff5e4, 1.4, 11);
      diningLight.position.set(5.5, 3.0, 1.0);
      scene.add(diningLight);

      const wifiLight = new THREE.PointLight(0x64fbd2, 0.9, 8);
      wifiLight.position.set(9.4, 2.4, -0.8);
      scene.add(wifiLight);
    }

    // -------------------------------------------------------------------------
    // 2. RESTAURANT / FAST FOOD ENVIRONMENT
    // -------------------------------------------------------------------------
    function buildRestaurantEnvironment(THREE, scene, env, projectName, opts) {
      buildCafeEnvironment(THREE, scene, env, projectName || 'DAR BOX KITCHEN', opts);
      // Seated diner in restaurant
      createSeatedCustomer(THREE, scene, 5.4, 0.08, 1.8, 0xdf6050, 0xf2d6bd);

      // Add Restaurant fast-food specifics (Heat lamps, soda fountain, meal boxes)
      const matStainless = new THREE.MeshStandardMaterial({ color: 0xd0dcd5, metalness: 0.85, roughness: 0.2 });
      const matOrange = new THREE.MeshBasicMaterial({ color: 0xf39c12 });

      // Heat lamps over pass
      for (const lx of [3.2, 4.4, 5.2]) {
        const lamp = new THREE.Mesh(new THREE.ConeGeometry(0.14, 0.22, 10), matStainless);
        lamp.position.set(lx, 1.8, -2.8);
        scene.add(lamp);
        const bulb = new THREE.Mesh(new THREE.SphereGeometry(0.04, 8, 8), matOrange);
        bulb.position.set(lx, 1.68, -2.8);
        scene.add(bulb);
      }

      // Meal Boxes on counter
      for (const bx of [3.3, 5.2]) {
        const mealBox = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.14, 0.22), matOrange);
        mealBox.position.set(bx, 1.02, -2.78);
        scene.add(mealBox);
      }
    }

    // -------------------------------------------------------------------------
    // 3. RETAIL / CLOTHING BOUTIQUE ENVIRONMENT
    // -------------------------------------------------------------------------
    function buildRetailEnvironment(THREE, scene, env, projectName, opts) {
      const matRoad = new THREE.MeshStandardMaterial({ color: 0x6c7971, roughness: 0.95 });
      const matCurb = new THREE.MeshStandardMaterial({ color: 0xb8c9bc, roughness: 0.8 });
      const matSidewalk = new THREE.MeshStandardMaterial({ color: 0xd8e5da, roughness: 0.9 });
      const matStripe = new THREE.MeshBasicMaterial({ color: 0x769485 });
      const matZebra = new THREE.MeshBasicMaterial({ color: 0xe6f5ed });
      const matFloor = new THREE.MeshStandardMaterial({ color: 0xe8eee8, roughness: 0.72, metalness: 0.02 });
      const matWall = new THREE.MeshStandardMaterial({ color: 0xd9e7db, roughness: 0.85 });
      const matWood = new THREE.MeshStandardMaterial({ color: 0x4a3424, roughness: 0.65 });
      const matGold = new THREE.MeshStandardMaterial({ color: 0xd4af37, roughness: 0.3, metalness: 0.8 });
      const matGlass = new THREE.MeshStandardMaterial({ color: 0x64fbd2, roughness: 0.1, metalness: 0.2, transparent: true, opacity: 0.32 });
      const matLime = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });
      const matFabricCurtain = new THREE.MeshStandardMaterial({ color: 0x17362a, roughness: 0.9 });
      const matMirror = new THREE.MeshStandardMaterial({ color: 0xe0f7ee, roughness: 0.05, metalness: 0.95 });
      const matFoliage = new THREE.MeshStandardMaterial({ color: 0x1d5438, roughness: 0.7 });
      const matPot = new THREE.MeshStandardMaterial({ color: 0xd0dfd7, roughness: 0.5 });

      // Street & Sidewalk
      const road = new THREE.Mesh(new THREE.BoxGeometry(4.4, 0.04, 22), matRoad);
      road.position.set(-6.0, 0, 0);
      scene.add(road);

      const sidewalk = new THREE.Mesh(new THREE.BoxGeometry(3.8, 0.12, 20), matSidewalk);
      sidewalk.position.set(-1.9, 0.06, 0);
      scene.add(sidewalk);

      createCar(THREE, scene, -4.6, 0.04, -1.8, 0x16382a);
      createCar(THREE, scene, -4.6, 0.04, -0.6, 0x2b3d46);

      // Building Walls & Floor
      const floor = new THREE.Mesh(new THREE.BoxGeometry(10.6, 0.14, 7.8), matFloor);
      floor.position.set(5.3, 0.07, -0.35);
      scene.add(floor);

      const backWall = new THREE.Mesh(new THREE.BoxGeometry(10.6, 3.2, 0.22), matWall);
      backWall.position.set(5.3, 1.6, -4.2);
      scene.add(backWall);

      const rightWall = new THREE.Mesh(new THREE.BoxGeometry(0.22, 3.2, 7.8), matWall);
      rightWall.position.set(10.5, 1.6, -0.35);
      scene.add(rightWall);

      // Window with mannequins
      const win1 = new THREE.Mesh(new THREE.BoxGeometry(0.04, 2.6, 3.6), matGlass);
      win1.position.set(0.0, 1.35, -2.1);
      scene.add(win1);

      // 2 Storefront Mannequins in window
      for (const mz of [-2.6, -1.5]) {
        const manBase = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.04, 12), matGold);
        manBase.position.set(0.4, 0.1, mz);
        scene.add(manBase);
        const manBody = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.65, 0.18), matWood);
        manBody.position.set(0.4, 0.8, mz);
        scene.add(manBody);
        const manHead = new THREE.Mesh(new THREE.SphereGeometry(0.1, 10, 8), matGold);
        manHead.position.set(0.4, 1.25, mz);
        scene.add(manHead);
      }

      // Entrance portal & sign
      const doorPortal = new THREE.Mesh(new THREE.BoxGeometry(0.18, 2.8, 1.8), matWall);
      doorPortal.position.set(0.0, 1.4, 1.3);
      scene.add(doorPortal);

      const signSprite = makeSignSprite(THREE, projectName || 'ATELIER YASMINE', '#64fbd2', 3.2);
      signSprite.position.set(-0.2, 2.95, 1.3);
      scene.add(signSprite);

      // Clothing Racks along back wall (z = -3.8)
      for (const rx of [2.0, 5.0]) {
        const rackBar = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 2.2, 8), matGold);
        rackBar.rotation.z = Math.PI / 2;
        rackBar.position.set(rx + 1.1, 1.5, -3.8);
        scene.add(rackBar);
        for (let gx = rx + 0.2; gx <= rx + 2.0; gx += 0.24) {
          const garment = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.65, 0.28), matFabricCurtain);
          garment.position.set(gx, 1.15, -3.8);
          scene.add(garment);
        }
      }

      // Central Display Tables (x = 3.6, z = 0.6)
      const dispTable = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.72, 1.2), matWood);
      dispTable.position.set(3.6, 0.44, 0.6);
      scene.add(dispTable);
      for (const tx of [2.8, 3.6, 4.4]) {
        const folded = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.08, 0.32), matGold);
        folded.position.set(tx, 0.84, 0.6);
        scene.add(folded);
      }

      // Fitting Rooms along right wall (x = 9.8, z = -0.8)
      for (const fz of [-2.0, -0.6]) {
        const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.2, 2.4, 1.1), matWall);
        cabin.position.set(9.6, 1.25, fz);
        scene.add(cabin);
        const curtain = new THREE.Mesh(new THREE.BoxGeometry(0.04, 2.1, 0.95), matFabricCurtain);
        curtain.position.set(8.95, 1.15, fz);
        scene.add(curtain);
        const mirror = new THREE.Mesh(new THREE.BoxGeometry(0.02, 1.6, 0.55), matMirror);
        mirror.position.set(9.0, 1.2, fz + 0.5);
        scene.add(mirror);
      }

      // Boutique Cashier Wrap Counter (x = 3.8, z = -2.2)
      const cashCounter = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.88, 0.75), matWood);
      cashCounter.position.set(3.8, 0.5, -2.2);
      scene.add(cashCounter);

      const pos = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.22, 0.22), matGold);
      pos.position.set(3.8, 1.05, -2.2);
      scene.add(pos);

      // Boutique shopping bags
      for (const bx of [4.6, 4.9]) {
        const bag = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.28, 0.12), matLime);
        bag.position.set(bx, 1.05, -2.2);
        scene.add(bag);
      }

      createPlant(THREE, scene, 0.5, 0.08, -3.7, matFoliage, matPot);
      createPlant(THREE, scene, 0.5, 0.08, 3.2, matFoliage, matPot);

      const boutiqueLight = new THREE.PointLight(0xffeed8, 2.0, 12);
      boutiqueLight.position.set(4.0, 3.0, 0.0);
      scene.add(boutiqueLight);
    }

    function buildUniversalJourneyEnvironment(THREE, scene, env, projectName, opts) {
      const platformMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.86 });
      const cardMaterial = new THREE.MeshStandardMaterial({ color: 0xd8efe1, roughness: 0.7 });
      const darkMaterial = new THREE.MeshStandardMaterial({ color: 0x164535, roughness: 0.55 });
      const accentMaterial = new THREE.MeshBasicMaterial({ color: 0x20b785 });
      const floor = new THREE.Mesh(new THREE.BoxGeometry(16.5, 0.15, 5.4), platformMaterial);
      floor.position.set(0, 0.02, 0);
      floor.receiveShadow = !opts.lowPerf;
      scene.add(floor);
      const title = makeSignSprite(THREE, `${projectName} · خريطة القرار`, '#64fbd2', 5.7);
      title.position.set(0, 2.7, -2.6);
      scene.add(title);
      const route = env.route || [];
      for (let i = 0; i < route.length; i++) {
        const loc = env.locations?.[route[i]];
        if (!loc) continue;
        const base = new THREE.Mesh(new THREE.BoxGeometry(1.65, 0.16, 1.4), cardMaterial);
        base.position.set(loc.x, 0.15, loc.z);
        base.castShadow = !opts.lowPerf;
        scene.add(base);
        const border = new THREE.Mesh(new THREE.BoxGeometry(1.75, 0.05, 1.5), accentMaterial);
        border.position.set(loc.x, 0.06, loc.z);
        scene.add(border);
        const screen = new THREE.Mesh(new THREE.BoxGeometry(0.78, 0.76, 0.07), darkMaterial);
        screen.position.set(loc.x, 0.7, loc.z);
        scene.add(screen);
        const display = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.5, 0.08), cardMaterial);
        display.position.set(loc.x, 0.73, loc.z + 0.04);
        scene.add(display);
        const marker = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.09, 0.09), accentMaterial);
        marker.position.set(loc.x, 0.74, loc.z + 0.1);
        scene.add(marker);
        const label = makeSignSprite(THREE, `${String(i + 1).padStart(2, '0')}  ${loc.label}`, '#64fbd2', 1.72);
        label.position.set(loc.x, 1.55, loc.z - 0.28);
        scene.add(label);
        if (i < route.length - 1) {
          const next = env.locations?.[route[i + 1]];
          if (!next) continue;
          const connector = new THREE.Mesh(new THREE.BoxGeometry(Math.max(0.2, next.x - loc.x - 1.6), 0.025, 0.04), accentMaterial);
          connector.position.set((loc.x + next.x) / 2, 0.18, (loc.z + next.z) / 2);
          scene.add(connector);
        }
      }
    }

    function buildFitnessEnvironment(THREE, scene, env, projectName, opts) {
      const floorMat = new THREE.MeshStandardMaterial({color:0xf3f6f2,roughness:0.92});
      const wallMat = new THREE.MeshStandardMaterial({color:0xd5e4db,roughness:0.9});
      const darkMat = new THREE.MeshStandardMaterial({color:0x214537,metalness:0.15,roughness:0.55});
      const mintMat = new THREE.MeshStandardMaterial({color:0x58dbb4,roughness:0.66});
      const rubberMat = new THREE.MeshStandardMaterial({color:0x607a6b,roughness:0.95});
      const addBox=(w,h,d,x,y,z,mat)=>{const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),mat);mesh.position.set(x,y,z);mesh.castShadow=!opts.lowPerf;mesh.receiveShadow=!opts.lowPerf;scene.add(mesh);return mesh};
      const addBar=(radius,length,x,y,z,mat,axis='z')=>{const mesh=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,length,10),mat);mesh.rotation[axis==='x'?'z':'x']=Math.PI/2;mesh.position.set(x,y,z);mesh.castShadow=!opts.lowPerf;scene.add(mesh);return mesh};
      addBox(20,.18,8.8,0,0,0,floorMat);
      addBox(20,2.8,.16,0,1.4,-4.3,wallMat);
      addBox(20,.08,.2,0,.17,0,mintMat);
      const title=makeSignSprite(THREE,projectName,'#154c3b',6.4);title.position.set(0,3.45,-4.1);scene.add(title);
      // Reception, exercise machines and training mats frame a clear central journey.
      addBox(2.4,.85,.75,-6.6,.51,-2.5,darkMat);
      addBox(2.15,.06,.82,-6.6,.97,-2.5,mintMat);
      for(const x of [-3.8,-1.7]){
        addBox(1.35,.12,2.2,x,.2,-2.5,rubberMat);
        addBox(1.1,.13,.55,x,.32,-1.7,darkMat);
        addBox(.12,1.0,.12,x-.55,.75,-3.3,darkMat);
        addBox(.12,1.0,.12,x+.55,.75,-3.3,darkMat);
        addBox(1.15,.08,.14,x,1.22,-3.3,mintMat);
      }
      for(const x of [1.7,3.6,5.5]){
        addBox(1.25,.04,2.05,x,.13,-2.35,new THREE.MeshStandardMaterial({color:x===3.6?0x9ddfca:0xb5d4c4,roughness:0.94}));
        const ball=new THREE.Mesh(new THREE.SphereGeometry(.21,12,8),mintMat);ball.position.set(x,.31,-2.5);scene.add(ball);
      }
      addBox(4.4,.45,.55,2.4,.42,2.55,darkMat);
      for(const x of [.6,1.5,2.5,3.5,4.2]){
        addBar(.17,.55,x,.78,2.55,rubberMat);
        addBar(.08,.6,x,.78,2.55,mintMat,'x');
      }
      addBox(2.15,.42,.75,6.6,.36,2.4,wallMat);
      const light=new THREE.PointLight(0xffffff,18,22);light.position.set(0,5,1);scene.add(light);
    }

    // -------------------------------------------------------------------------
    // 4. E-COMMERCE / DIGITAL FULFILMENT HUB
    // -------------------------------------------------------------------------
    function buildEcommerceJourneyEnvironment(THREE, scene, env, projectName, opts) {
      // Online businesses have a digital customer journey, never a pretend walk-in shop.
      const base = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.88 });
      const edge = new THREE.MeshStandardMaterial({ color: 0x0f755c, roughness: 0.54 });
      const mint = new THREE.MeshStandardMaterial({ color: 0x64dcb3, roughness: 0.5 });
      const navy = new THREE.MeshStandardMaterial({ color: 0x12362b, roughness: 0.5 });
      const screen = new THREE.MeshBasicMaterial({ color: 0xe3fff0 });
      const card = new THREE.MeshStandardMaterial({ color: 0xd5e9d9, roughness: 0.75 });
      const lineMat = new THREE.MeshBasicMaterial({ color: 0x49b68d });
      const platform = new THREE.Mesh(new THREE.BoxGeometry(18.8, 0.16, 7.2), base);
      platform.position.set(1.2, 0.04, 0);platform.receiveShadow = !opts.lowPerf;scene.add(platform);
      const title = makeSignSprite(THREE, `${projectName} · رحلة الشراء الرقمية`, '#64fbd2', 6.1);
      title.position.set(1.2, 2.95, -3.1);scene.add(title);
      const stages = [
        ['discovery','01','اكتشاف'],['product_page','02','صفحة المنتج'],
        ['comparison','03','مقارنة'],['cart','04','سلة'],
        ['payment','05','دفع'],['confirmation','06','تأكيد'],
        ['delivery','07','توصيل'],['reception','08','استلام'],
      ];
      const points = stages.map(([key])=>env.locations?.[key]).filter(Boolean);
      for(let j=0;j<points.length-1;j++){
        const a=points[j],b=points[j+1];
        const start=new THREE.Vector3(a.x,0.18,a.z),end=new THREE.Vector3(b.x,0.18,b.z);
        const direction=new THREE.Vector3().subVectors(end,start);const length=direction.length();
        const connector=new THREE.Mesh(new THREE.CylinderGeometry(0.025,0.025,length,8),lineMat);
        connector.position.copy(start).addScaledVector(direction,0.5);
        connector.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize());scene.add(connector);
      }
      stages.forEach(([key,number,label],index)=>{
        const pos=env.locations?.[key];if(!pos)return;
        const tile=new THREE.Mesh(new THREE.BoxGeometry(1.38,0.2,1.12),index===4?mint:card);
        tile.position.set(pos.x,0.19,pos.z);tile.castShadow=!opts.lowPerf;tile.receiveShadow=!opts.lowPerf;scene.add(tile);
        const border=new THREE.Mesh(new THREE.BoxGeometry(1.46,0.06,1.2),edge);
        border.position.set(pos.x,0.09,pos.z);scene.add(border);
        const numberTag=makeSignSprite(THREE,`${number}  ${label}`,'#64fbd2',1.65);
        numberTag.position.set(pos.x,1.68,pos.z-0.22);scene.add(numberTag);
        const icon=new THREE.Group();icon.position.set(pos.x,0.32,pos.z);scene.add(icon);
        if(key==='product_page'||key==='comparison'){
          const phone=new THREE.Mesh(new THREE.BoxGeometry(.52,.93,.07),navy);phone.position.y=.55;icon.add(phone);
          const display=new THREE.Mesh(new THREE.BoxGeometry(.43,.74,.075),screen);display.position.set(0,.57,.042);icon.add(display);
          const pic=new THREE.Mesh(new THREE.BoxGeometry(.31,.24,.08),mint);pic.position.set(0,.73,.09);icon.add(pic);
          for(const y of [.48,.39]){const textLine=new THREE.Mesh(new THREE.BoxGeometry(.28,.025,.08),edge);textLine.position.set(0,y,.09);icon.add(textLine)}
        }else if(key==='cart'||key==='payment'||key==='confirmation'){
          const plate=new THREE.Mesh(new THREE.BoxGeometry(.72,.5,.12),navy);plate.position.y=.48;icon.add(plate);
          const face=new THREE.Mesh(new THREE.BoxGeometry(.59,.36,.13),screen);face.position.set(0,.48,.01);icon.add(face);
          const accent=new THREE.Mesh(new THREE.BoxGeometry(.36,.07,.14),mint);accent.position.set(0,.44,.09);icon.add(accent);
        }else if(key==='delivery'||key==='reception'){
          const parcel=new THREE.Mesh(new THREE.BoxGeometry(.52,.45,.45),new THREE.MeshStandardMaterial({color:0xd1a873,roughness:.9}));parcel.position.y=.46;icon.add(parcel);
          const tape=new THREE.Mesh(new THREE.BoxGeometry(.09,.47,.46),mint);tape.position.y=.46;icon.add(tape);
        }else{
          const signal=new THREE.Mesh(new THREE.SphereGeometry(.29,14,10),mint);signal.position.y=.6;icon.add(signal);
          const halo=new THREE.Mesh(new THREE.TorusGeometry(.4,.025,7,30),edge);halo.rotation.x=Math.PI/2;halo.position.y=.21;icon.add(halo);
        }
      });
    }

    function buildEcommerceEnvironment(THREE, scene, env, projectName, opts) {
      const matFloor = new THREE.MeshStandardMaterial({ color: 0x8fae9a, roughness: 0.72, metalness: 0.04 });
      const matWall = new THREE.MeshStandardMaterial({ color: 0x365b47, roughness: 0.9 });
      const matSteel = new THREE.MeshStandardMaterial({ color: 0x243e33, roughness: 0.3, metalness: 0.8 });
      const matCardboard = new THREE.MeshStandardMaterial({ color: 0x9e794b, roughness: 0.85 });
      const matDesk = new THREE.MeshStandardMaterial({ color: 0x1f2e27, roughness: 0.5 });
      const matScreen = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });
      const matVan = new THREE.MeshStandardMaterial({ color: 0x16382a, roughness: 0.4 });
      const matLime = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });

      // Fulfilment Studio Floor
      const floor = new THREE.Mesh(new THREE.BoxGeometry(18.0, 0.14, 10.0), matFloor);
      floor.position.set(1.5, 0.07, 0.0);
      scene.add(floor);

      const backWall = new THREE.Mesh(new THREE.BoxGeometry(18.0, 3.2, 0.22), matWall);
      backWall.position.set(1.5, 1.6, -4.8);
      scene.add(backWall);

      // Studio Billboard on back wall
      const ecomBanner = makeSignSprite(THREE, projectName || 'NORTHLINE STREETWEAR · STORE ONLINE', '#64fbd2', 4.2);
      ecomBanner.position.set(1.5, 2.7, -4.68);
      scene.add(ecomBanner);

      // Left Zone: Digital Funnel & Marketing Station (x = -4.0, z = 0.0)
      const devDesk = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.78, 1.1), matDesk);
      devDesk.position.set(-4.0, 0.45, 0.2);
      scene.add(devDesk);

      // Dual Curved Monitors
      for (const mx of [-4.5, -3.5]) {
        const mon = new THREE.Mesh(new THREE.BoxGeometry(0.68, 0.44, 0.04), matScreen);
        mon.position.set(mx, 1.15, 0.1);
        mon.rotation.y = mx < -4 ? 0.2 : -0.2;
        scene.add(mon);
      }

      // Center Zone: Inventory Warehouse Shelving Racks (x = 0.5, z = -3.2)
      for (const rx of [-1.5, 1.5, 4.5]) {
        const rack = new THREE.Mesh(new THREE.BoxGeometry(1.8, 2.6, 0.7), matSteel);
        rack.position.set(rx, 1.35, -3.2);
        scene.add(rack);
        // Boxes on shelves
        for (const [bx, by] of [[rx - 0.4, 0.8], [rx + 0.4, 0.8], [rx, 1.5], [rx - 0.3, 2.1], [rx + 0.3, 2.1]]) {
          const cBox = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.32, 0.42), matCardboard);
          cBox.position.set(bx, by, -3.2);
          scene.add(cBox);
        }
      }

      // Packaging Station Workbench (x = 4.8, z = -1.8)
      const packBench = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.84, 1.0), matDesk);
      packBench.position.set(4.8, 0.48, -1.8);
      scene.add(packBench);

      // Parcel boxes & tape gun
      for (const px of [4.0, 4.8, 5.5]) {
        const pBox = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.28, 0.36), matCardboard);
        pBox.position.set(px, 1.04, -1.8);
        scene.add(pBox);
      }

      // Right Zone: Delivery Dispatch Loading Bay (x = 7.5, z = 0.5)
      const dispatchBay = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.08, 5.0), matSteel);
      dispatchBay.position.set(7.5, 0.1, 0.5);
      scene.add(dispatchBay);

      // Delivery Courier Cargo Vehicle
      createCar(THREE, scene, 7.5, 0.1, 1.2, 0x16382a);

      // Packing specialist at workbench
      const packer = new THREE.Group();
      packer.position.set(4.8, 0.08, -2.6);
      packer.scale.set(1.4, 1.4, 1.4);
      const pTorso = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.44, 0.18), new THREE.MeshStandardMaterial({ color: 0x64fbd2 }));
      pTorso.position.y = 0.68;
      packer.add(pTorso);
      const pHead = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), new THREE.MeshStandardMaterial({ color: 0xf2d6bd }));
      pHead.position.y = 1.02;
      packer.add(pHead);
      scene.add(packer);

      // Desk operator
      createSeatedCustomer(THREE, scene, -4.0, 0.08, 1.0, 0x2e6188, 0xd8b28f);

      const studioLight = new THREE.PointLight(0x64fbd2, 1.6, 16);
      studioLight.position.set(2.0, 3.2, 0.0);
      scene.add(studioLight);
    }

    // -------------------------------------------------------------------------
    // 5. SERVICES / FREELANCE / CONSULTING STUDIO
    // -------------------------------------------------------------------------
    function buildServiceEnvironment(THREE, scene, env, projectName, opts) {
      const matFloor = new THREE.MeshStandardMaterial({ color: 0xb7c9b8, roughness: 0.65, metalness: 0.02 });
      const matWall = new THREE.MeshStandardMaterial({ color: 0xdceadd, roughness: 0.85 });
      const matWood = new THREE.MeshStandardMaterial({ color: 0x4a3424, roughness: 0.65 });
      const matDesk = new THREE.MeshStandardMaterial({ color: 0x1f2e27, roughness: 0.5 });
      const matLime = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });
      const matScreen = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });
      const matArmchair = new THREE.MeshStandardMaterial({ color: 0x17362a, roughness: 0.8 });
      const matGlass = new THREE.MeshStandardMaterial({ color: 0x64fbd2, roughness: 0.1, metalness: 0.2, transparent: true, opacity: 0.3 });
      const matFoliage = new THREE.MeshStandardMaterial({ color: 0x1d5438, roughness: 0.7 });
      const matPot = new THREE.MeshStandardMaterial({ color: 0xd0dfd7, roughness: 0.5 });

      // Studio Floor & Walls
      const floor = new THREE.Mesh(new THREE.BoxGeometry(14.0, 0.14, 8.5), matFloor);
      floor.position.set(3.5, 0.07, -0.2);
      scene.add(floor);

      const backWall = new THREE.Mesh(new THREE.BoxGeometry(14.0, 3.2, 0.22), matWall);
      backWall.position.set(3.5, 1.6, -4.4);
      scene.add(backWall);

      const serviceBanner = makeSignSprite(THREE, projectName || 'FIXLI HOME SERVICES · STUDIO', '#64fbd2', 3.6);
      serviceBanner.position.set(3.5, 2.8, -4.28);
      scene.add(serviceBanner);

      // Reception Desk (x = 0.0, z = 0.8)
      const recDesk = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.82, 0.75), matDesk);
      recDesk.position.set(0.0, 0.46, 0.8);
      scene.add(recDesk);
      const recScreen = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.24, 0.04), matLime);
      recScreen.position.set(0.0, 1.05, 0.8);
      scene.add(recScreen);

      // Client Waiting Lounge (x = 2.4, z = 1.4)
      for (const [ax, az] of [[2.0, 1.8], [3.2, 1.8]]) {
        const chair = new THREE.Mesh(new THREE.BoxGeometry(0.65, 0.65, 0.65), matArmchair);
        chair.position.set(ax, 0.38, az);
        scene.add(chair);
      }
      const coffeeTable = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.35, 0.6), matGlass);
      coffeeTable.position.set(2.6, 0.2, 1.0);
      scene.add(coffeeTable);

      // Diagnostic & Service Workbench (x = 5.4, z = -2.2)
      const workBench = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.84, 0.9), matWood);
      workBench.position.set(5.4, 0.48, -2.2);
      scene.add(workBench);
      for (const bx of [4.6, 5.4, 6.2]) {
        const toolBox = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.24, 0.24), matDesk);
        toolBox.position.set(bx, 1.0, -2.2);
        scene.add(toolBox);
      }

      // Strategy & Conference Table (x = 6.8, z = 1.0)
      createTableAndChairs(THREE, scene, 6.8, 0.08, 1.0, matWood, matDesk, false);

      createPlant(THREE, scene, -2.5, 0.08, 2.5, matFoliage, matPot);
      createPlant(THREE, scene, 9.5, 0.08, -3.8, matFoliage, matPot);

      // Receptionist at desk
      createSeatedCustomer(THREE, scene, 0.0, 0.08, 0.2, 0x64fbd2, 0xf2d6bd);
      // Client waiting in armchair lounge
      createSeatedCustomer(THREE, scene, 2.0, 0.08, 1.4, 0xd4a359, 0xad7a54);

      const serviceLight = new THREE.PointLight(0xfff3e0, 1.8, 14);
      serviceLight.position.set(4.0, 3.0, 0.0);
      scene.add(serviceLight);
    }

    // -------------------------------------------------------------------------
    // SHARED ARCHITECTURAL HELPERS
    // -------------------------------------------------------------------------
    function createSeatedCustomer(THREE, scene, x, y, z, shirtColor, skinColor) {
      const charGroup = new THREE.Group();
      charGroup.position.set(x, y + 0.38, z);
      charGroup.scale.set(1.4, 1.4, 1.4);

      const torso = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.44, 0.18), new THREE.MeshStandardMaterial({ color: shirtColor, roughness: 0.5 }));
      torso.position.y = 0.24;
      charGroup.add(torso);

      const collar = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.08, 0.19), new THREE.MeshBasicMaterial({ color: 0xffffff }));
      collar.position.y = 0.42;
      charGroup.add(collar);

      const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), new THREE.MeshStandardMaterial({ color: skinColor, roughness: 0.65 }));
      head.position.y = 0.56;
      charGroup.add(head);

      const hair = new THREE.Mesh(new THREE.SphereGeometry(0.125, 8, 8, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x1b130e, roughness: 0.8 }));
      hair.position.y = 0.59;
      charGroup.add(hair);

      const legMat = new THREE.MeshStandardMaterial({ color: 0x1a2620, roughness: 0.7 });
      for (const lx of [-0.09, 0.09]) {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.42, 0.11), legMat);
        leg.position.set(lx, 0.0, 0.18);
        leg.rotation.x = -Math.PI / 2.2;
        charGroup.add(leg);
      }

      const armMat = new THREE.MeshStandardMaterial({ color: shirtColor, roughness: 0.5 });
      for (const ax of [-0.2, 0.2]) {
        const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.36, 0.09), armMat);
        arm.position.set(ax, 0.16, 0.14);
        arm.rotation.x = 0.4;
        charGroup.add(arm);
      }

      // Small glowing indicator badge
      const badge = new THREE.Mesh(new THREE.OctahedronGeometry(0.08, 0), new THREE.MeshBasicMaterial({ color: 0x64fbd2 }));
      badge.position.y = 0.82;
      charGroup.add(badge);

      scene.add(charGroup);
    }

    function createOutdoorTerrace(THREE, scene, x, y, z, matTop, matBase, matAccent, matFoliage, matPot) {
      createTableAndChairs(THREE, scene, x, y, z, matTop, matBase, true);
      createPlant(THREE, scene, x - 0.9, y, z + 0.6, matFoliage, matPot);
    }

    function createPlant(THREE, scene, x, y, z, matFoliage, matPot) {
      const group = new THREE.Group();
      group.position.set(x, y, z);
      const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.16, 0.44, 12), matPot);
      pot.position.y = 0.22;
      group.add(pot);
      for (const [ly, s] of [[0.46, 0.28], [0.68, 0.24], [0.88, 0.18]]) {
        const foliage = new THREE.Mesh(new THREE.DodecahedronGeometry(s, 1), matFoliage);
        foliage.position.y = ly;
        group.add(foliage);
      }
      scene.add(group);
    }

    function createCar(THREE, scene, x, y, z, colorHex) {
      const carGroup = new THREE.Group();
      carGroup.position.set(x, y, z);

      const body = new THREE.Mesh(
        new THREE.BoxGeometry(1.4, 0.42, 2.2),
        new THREE.MeshStandardMaterial({ color: colorHex, roughness: 0.35, metalness: 0.2 }),
      );
      body.position.y = 0.28;
      carGroup.add(body);

      const cabin = new THREE.Mesh(
        new THREE.BoxGeometry(1.18, 0.38, 1.25),
        new THREE.MeshStandardMaterial({ color: 0x111e19, roughness: 0.2, metalness: 0.3 }),
      );
      cabin.position.set(0, 0.62, -0.1);
      carGroup.add(cabin);

      const headMat = new THREE.MeshBasicMaterial({ color: 0xfffee0 });
      const tailMat = new THREE.MeshBasicMaterial({ color: 0xdf4030 });
      for (const hx of [-0.46, 0.46]) {
        const hl = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.08, 0.04), headMat);
        hl.position.set(hx, 0.32, -1.1);
        carGroup.add(hl);
        const tl = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.08, 0.04), tailMat);
        tl.position.set(hx, 0.32, 1.1);
        carGroup.add(tl);
      }

      const wheelMat = new THREE.MeshStandardMaterial({ color: 0x080c0a });
      const wheelGeo = new THREE.CylinderGeometry(0.18, 0.18, 0.14, 12);
      for (const [wx, wz] of [[-0.72, -0.7], [0.72, -0.7], [-0.72, 0.7], [0.72, 0.7]]) {
        const wheel = new THREE.Mesh(wheelGeo, wheelMat);
        wheel.rotation.z = Math.PI / 2;
        wheel.position.set(wx, 0.18, wz);
        carGroup.add(wheel);
      }
      scene.add(carGroup);
    }

    function createTableAndChairs(THREE, scene, x, y, z, matTop, matBase, isOutdoor = false) {
      const group = new THREE.Group();
      group.position.set(x, y, z);

      const top = new THREE.Mesh(new THREE.CylinderGeometry(0.48, 0.48, 0.05, 16), matTop);
      top.position.y = 0.68;
      group.add(top);

      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.66, 8), matBase);
      leg.position.y = 0.35;
      group.add(leg);

      const basePlate = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.02, 12), matBase);
      basePlate.position.y = 0.02;
      group.add(basePlate);

      const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.03, 0.06, 8), new THREE.MeshBasicMaterial({ color: 0xf2fff8 }));
      cup.position.set(0.08, 0.74, -0.06);
      group.add(cup);

      for (const [cx, cz, rot] of [[0, -0.58, 0], [0, 0.58, Math.PI]]) {
        const chair = new THREE.Group();
        chair.position.set(cx, 0, cz);
        chair.rotation.y = rot;

        const seat = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.04, 0.32), matTop);
        seat.position.y = 0.42;
        chair.add(seat);

        const back = new THREE.Mesh(new THREE.BoxGeometry(0.32, 0.36, 0.04), matTop);
        back.position.set(0, 0.62, -0.14);
        chair.add(back);

        for (const [lx, lz] of [[-0.12, -0.12], [0.12, -0.12], [-0.12, 0.12], [0.12, 0.12]]) {
          const chairLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.42, 6), matBase);
          chairLeg.position.set(lx, 0.21, lz);
          chair.add(chairLeg);
        }
        group.add(chair);
      }

      if (isOutdoor) {
        const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 2.2, 8), matBase);
        pole.position.set(0, 1.1, 0);
        group.add(pole);

        const canopy = new THREE.Mesh(new THREE.ConeGeometry(0.95, 0.38, 12), new THREE.MeshStandardMaterial({ color: 0x1f4738, roughness: 0.8 }));
        canopy.position.set(0, 2.1, 0);
        group.add(canopy);
      }

      scene.add(group);
    }

    // -------------------------------------------------------------------------
    // SMART BILLBOARD PIN & LABEL SYSTEM (Section 5)
    // -------------------------------------------------------------------------
    function buildLocationPins(THREE, scene, env, pinList, opts) {
      const pinMat = new THREE.MeshStandardMaterial({ color: 0x162c23, roughness: 0.5, metalness: 0.2 });
      const dotLime = new THREE.MeshBasicMaterial({ color: 0x64fbd2 });

      for (const key of env.route || []) {
        const loc = env.locations[key];
        if (!loc) continue;

        const group = new THREE.Group();
        group.position.set(loc.x, 0.02, loc.z);

        const base = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.38, 0.04, 16), pinMat);
        group.add(base);

        const innerDot = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.05, 12), dotLime);
        innerDot.position.y = 0.01;
        group.add(innerDot);

        const labelSprite = makeLabelSprite(THREE, loc.label);
        labelSprite.position.set(0, 1.45, 0);
        labelSprite.visible = false;
        group.add(labelSprite);

        scene.add(group);
        pinList.push({ key, loc, group, labelSprite, isHovered: false });
      }
    }


    function buildDigitalAvatars(THREE, scene, dataset, personaList) {
      for (const p of dataset.personas.filter((item) => item.representative)) {
        const group = new THREE.Group();
        const charRoot = new THREE.Group();
        group.add(charRoot);
        const accepted = p.buys;
        const color = accepted ? 0x08735b : 0xc75e50;
        const disc = new THREE.Mesh(new THREE.CylinderGeometry(.24,.24,.13,24),new THREE.MeshStandardMaterial({color:0xffffff,roughness:.45}));
        disc.position.y=.23;charRoot.add(disc);
        const torso = new THREE.Mesh(new THREE.CylinderGeometry(.12,.17,.25,12),new THREE.MeshStandardMaterial({color,roughness:.58}));
        torso.position.y=.44;charRoot.add(torso);
        const head = new THREE.Mesh(new THREE.SphereGeometry(.11,14,10),new THREE.MeshStandardMaterial({color:0xe2b894,roughness:.65}));
        head.position.y=.67;charRoot.add(head);
        const ring = new THREE.Mesh(new THREE.TorusGeometry(.36,.025,6,30),new THREE.MeshBasicMaterial({color}));
        ring.rotation.x=Math.PI/2;ring.position.y=.08;group.add(ring);
        const selection = new THREE.Mesh(new THREE.RingGeometry(.42,.53,30),new THREE.MeshBasicMaterial({color:0x10271c,side:THREE.DoubleSide}));
        selection.rotation.x=-Math.PI/2;selection.position.y=.09;selection.visible=false;group.add(selection);
        const nameTag=makeLabelSprite(THREE,p.name||`#${p.id}`);
        nameTag.position.set(0,1.27,0);nameTag.scale.set(1.6,.4,1);nameTag.visible=false;group.add(nameTag);
        group.userData.personaId=p.id;
        group.traverse(obj=>{obj.userData.personaId=p.id});
        const pos=positionAt(dataset,p,80);group.position.set(pos.x,0,pos.z);scene.add(group);
        const limb=()=>({rotation:{x:0}});
        personaList.push({persona:p,group,charRoot,torso,head,leftLeg:limb(),rightLeg:limb(),leftArm:limb(),rightArm:limb(),ring,selection,nameTag,headDiamond:null,phase:hashUnit(p.id)*Math.PI*2});
      }
    }

    function buildHumanoidCharacters(THREE, scene, dataset, personaList, opts) {
      // High-contrast, stylish FinTech attire palette (Mint, Ivory, Camel, Navy, Coral, Emerald)
      const clothingPalette = [
        0x64fbd2, 0xf0f6f3, 0xd4a359, 0x2e6188, 0xdf6050,
        0x3d8b68, 0xe8b86d, 0x395368, 0x228b75, 0x4a7c59,
      ];
      const skinPalette = [0xf2d6bd, 0xd8b28f, 0xad7a54, 0xe8c4a2];

      // Add Barista / Store Staff behind the counter
      if (dataset.environment?.activity === 'cafe' || dataset.environment?.activity === 'restaurant') {
        const staff = new THREE.Group();
        staff.position.set(4.2, 0.08, -3.4);

        const sRoot = new THREE.Group();
        sRoot.scale.set(1.42, 1.42, 1.42);

        // Torso in barista dark apron
        const sTorso = new THREE.Mesh(
          new THREE.BoxGeometry(0.3, 0.44, 0.18),
          new THREE.MeshStandardMaterial({ color: 0x162c22, roughness: 0.6 }),
        );
        sTorso.position.y = 0.68;
        sRoot.add(sTorso);

        // White collar shirt
        const sCollar = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.12, 0.19), new THREE.MeshBasicMaterial({ color: 0xffffff }));
        sCollar.position.y = 0.86;
        sRoot.add(sCollar);

        // Head
        const sHead = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), new THREE.MeshStandardMaterial({ color: 0xf2d6bd, roughness: 0.6 }));
        sHead.position.y = 1.02;
        sRoot.add(sHead);

        // Hair
        const sHair = new THREE.Mesh(new THREE.SphereGeometry(0.125, 8, 8, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.MeshStandardMaterial({ color: 0x1a120c, roughness: 0.8 }));
        sHair.position.y = 1.05;
        sRoot.add(sHair);

        // Staff badge
        const sBadge = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.04, 0.02), new THREE.MeshBasicMaterial({ color: 0x64fbd2 }));
        sBadge.position.set(0.08, 0.74, 0.1);
        sRoot.add(sBadge);

        // Staff legs
        const sLegMat = new THREE.MeshStandardMaterial({ color: 0x162c22, roughness: 0.7 });
        for (const lx of [-0.09, 0.09]) {
          const leg = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.46, 0.11), sLegMat);
          leg.position.set(lx, 0.25, 0);
          sRoot.add(leg);
        }
        // Staff arms resting on espresso bar
        const sArmMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.5 });
        for (const ax of [-0.21, 0.21]) {
          const arm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.38, 0.09), sArmMat);
          arm.position.set(ax, 0.66, 0.05);
          arm.rotation.x = 0.35;
          sRoot.add(arm);
        }

        staff.add(sRoot);
        scene.add(staff);
      }

      for (const p of dataset.personas.filter((item) => item.representative)) {
        const group = new THREE.Group();
        const hash = hashUnit(p.id);
        const heightScale = 1.38 + (hash * 0.22); // Proper scale relative to 3D architectural furniture
        const clothColor = clothingPalette[Math.abs(p.id * 7) % clothingPalette.length];
        const skinColor = skinPalette[Math.abs(p.id * 3) % skinPalette.length];

        const charRoot = new THREE.Group();
        charRoot.scale.set(heightScale, heightScale, heightScale);

        // 1. Torso with stylish jacket / top
        const torsoMat = new THREE.MeshStandardMaterial({ color: clothColor, roughness: 0.5 });
        const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.155, 0.47, 12), torsoMat);
        torso.position.y = 0.68;
        torso.castShadow = !opts.lowPerf;
        charRoot.add(torso);

        // Inner shirt collar
        const collarMat = new THREE.MeshBasicMaterial({ color: 0xf4faf6 });
        const collar = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.1, 0.19), collarMat);
        collar.position.y = 0.85;
        charRoot.add(collar);

        // 2. Head with skin & hair
        const skinMat = new THREE.MeshStandardMaterial({ color: skinColor, roughness: 0.65 });
        const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 8), skinMat);
        head.position.y = 1.02;
        head.castShadow = !opts.lowPerf;
        charRoot.add(head);

        const hairColor = p.id % 2 === 0 ? 0x1b130e : (p.id % 3 === 0 ? 0x3d2719 : 0x241a14);
        const hairMat = new THREE.MeshStandardMaterial({ color: hairColor, roughness: 0.75 });
        const hair = new THREE.Mesh(new THREE.SphereGeometry(0.125, 8, 8, 0, Math.PI * 2, 0, Math.PI / 2), hairMat);
        hair.position.y = 1.05;
        charRoot.add(hair);

        // 3. Articulated Legs & Clean White Sneakers
        const pantsColor = p.id % 3 === 0 ? 0x18241f : (p.id % 2 === 0 ? 0x23323c : 0x2e241c);
        const legMat = new THREE.MeshStandardMaterial({ color: pantsColor, roughness: 0.7 });
        const leftLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.066, 0.072, 0.46, 10), legMat);
        leftLeg.position.set(-0.09, 0.25, 0);
        charRoot.add(leftLeg);

        const rightLeg = new THREE.Mesh(new THREE.CylinderGeometry(0.066, 0.072, 0.46, 10), legMat);
        rightLeg.position.set(0.09, 0.25, 0);
        charRoot.add(rightLeg);

        // White sneakers for distinct footstep visibility
        const shoeMat = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4 });
        const shoeL = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.08, 0.17), shoeMat);
        shoeL.position.set(-0.09, 0.04, 0.03);
        charRoot.add(shoeL);

        const shoeR = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.08, 0.17), shoeMat);
        shoeR.position.set(0.09, 0.04, 0.03);
        charRoot.add(shoeR);

        // 4. Articulated Arms
        const armMat = new THREE.MeshStandardMaterial({ color: clothColor, roughness: 0.5 });
        const leftArm = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.38, 10), armMat);
        leftArm.position.set(-0.21, 0.66, 0);
        charRoot.add(leftArm);

        const rightArm = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.38, 10), armMat);
        rightArm.position.set(0.21, 0.66, 0);
        charRoot.add(rightArm);

        // 5. Overhead Floating Status Diamond
        const diamondColor = p.buys ? 0x64fbd2 : 0xdf5849;
        const diamondMat = new THREE.MeshBasicMaterial({ color: diamondColor });
        const headDiamond = new THREE.Mesh(new THREE.OctahedronGeometry(0.09, 0), diamondMat);
        headDiamond.position.y = 1.34;
        charRoot.add(headDiamond);

        group.add(charRoot);

        // Status Indicator Ring on Floor
        const ringColor = p.buys ? 0x64fbd2 : 0xdf5849;
        const ring = new THREE.Mesh(
          new THREE.TorusGeometry(0.36, 0.024, 6, 24),
          new THREE.MeshBasicMaterial({ color: ringColor, transparent: true, opacity: 0.88 }),
        );
        ring.rotation.x = Math.PI / 2;
        ring.position.y = 0.05;
        group.add(ring);

        // Selection Crown Highlight
        const selection = new THREE.Mesh(
          new THREE.RingGeometry(0.42, 0.54, 24),
          new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95, side: THREE.DoubleSide }),
        );
        selection.rotation.x = -Math.PI / 2;
        selection.position.y = 0.06;
        selection.visible = false;
        group.add(selection);

        // Floating Name Tag (Appears only on selection or hover)
        const nameTag = makeLabelSprite(THREE, p.name || `#${p.id}`);
        nameTag.position.set(0, 1.85, 0);
        nameTag.scale.set(1.9, 0.44, 1);
        nameTag.visible = false;
        group.add(nameTag);

        group.userData.personaId = p.id;
        for (const c of group.children) c.userData.personaId = p.id;

        const pos = positionAt(dataset, p, 80);
        group.position.set(pos.x, 0, pos.z);
        scene.add(group);

        personaList.push({
          persona: p, group, charRoot, torso, head, leftLeg, rightLeg, leftArm, rightArm,
          headDiamond, ring, selection, nameTag, phase: hash * Math.PI * 2,
        });
      }
    }


    function updateCamera() {
      cameraState.target.lerp(cameraState.targetGoal, 0.08);
      cameraState.zoom += (cameraState.goalZoom - cameraState.zoom) * 0.1;

      const cos = Math.cos(cameraState.elevation);
      const radius = 24; // Closer framing for immediate clarity
      camera.position.set(
        cameraState.target.x + Math.sin(cameraState.azimuth) * cos * radius,
        cameraState.target.y + Math.sin(cameraState.elevation) * radius,
        cameraState.target.z + Math.cos(cameraState.azimuth) * cos * radius,
      );
      camera.lookAt(cameraState.target);
      camera.zoom = cameraState.zoom;
      camera.updateProjectionMatrix();
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(280, rect.width || canvas.parentElement?.clientWidth || 600);
      height = Math.max(280, rect.height || canvas.parentElement?.clientHeight || 480);
      renderer.setSize(width, height, false);
      const aspect = width / height;
      const baseView = physical ? 11.2 : 11.0;
      const sceneWidth = physical ? 18.5 : 20.5;
      const view = Math.max(baseView, sceneWidth / Math.max(aspect, 0.7));
      camera.left = (-view * aspect) / 2;
      camera.right = (view * aspect) / 2;
      camera.top = view / 2;
      camera.bottom = -view / 2;
      updateCamera();
    }

    function setSelected(id) {
      selectedId = id;
      for (const item of personas) {
        const isSel = String(item.persona.id) === String(id);
        item.selection.visible = isSel;
        item.nameTag.visible = isSel;
      }
    }

    function setVisible(ids) {
      visible = ids instanceof Set ? ids : new Set(ids || []);
      for (const item of personas) item.group.visible = visible.has(item.persona.id);
    }

    function focusPersona(id) {
      const item = personas.find((e) => String(e.persona.id) === String(id));
      if (!item) return;
      cameraState.targetGoal.set(item.group.position.x, 0.6, item.group.position.z);
      cameraState.goalZoom = 1.45;
    }

    function resetCamera() {
      cameraState.azimuth = cameraState.defaultAzimuth;
      cameraState.elevation = cameraState.defaultElevation;
      cameraState.targetGoal.copy(cameraState.defaultTarget);
      cameraState.goalZoom = 1;
    }

    function overviewCamera() {
      cameraState.azimuth = cameraState.defaultAzimuth;
      cameraState.elevation = cameraState.defaultElevation;
      cameraState.targetGoal.copy(cameraState.defaultTarget);
      cameraState.goalZoom = 0.88;
    }

    function zoomBy(factor) {
      cameraState.goalZoom = clamp(cameraState.goalZoom * factor, 0.7, 2.6);
    }

    function rotateBy(deltaX, deltaY) {
      cameraState.azimuth -= deltaX * 0.005;
      cameraState.elevation = clamp(cameraState.elevation + deltaY * 0.004, 0.42, 1.38); // Clamped above floor
    }

    // Pointer events
    let dragging = false;
    let moved = false;
    let startPos = { x: 0, y: 0 };
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    canvas.addEventListener('pointerdown', (e) => {
      dragging = true;
      moved = false;
      startPos = { x: e.clientX, y: e.clientY };
      canvas.setPointerCapture?.(e.pointerId);
    }, { signal: abort.signal });

    canvas.addEventListener('pointermove', (e) => {
      if (!dragging) {
        // Hover detection for smart pins & characters
        const rect = canvas.getBoundingClientRect();
        pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        raycaster.setFromCamera(pointer, camera);

        // Check pins hover
        for (const pin of locationPins) {
          const hits = raycaster.intersectObject(pin.group, true);
          pin.labelSprite.visible = hits.length > 0;
        }
        return;
      }
      const dx = e.clientX - startPos.x;
      const dy = e.clientY - startPos.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
      rotateBy(e.movementX || dx, e.movementY || dy);
      startPos = { x: e.clientX, y: e.clientY };
    }, { signal: abort.signal });

    canvas.addEventListener('pointerup', (e) => {
      dragging = false;
      if (moved) return;
      const rect = canvas.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hits = raycaster.intersectObjects(
        personas.filter((item) => item.group.visible).map((item) => item.group),
        true,
      );
      if (hits.length) {
        let obj = hits[0].object;
        while (obj && obj.userData.personaId === undefined) obj = obj.parent;
        if (obj?.userData.personaId !== undefined) options.onPick?.(obj.userData.personaId);
      }
    }, { signal: abort.signal });

    canvas.addEventListener('pointerleave', () => { dragging = false; }, { signal: abort.signal });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      zoomBy(e.deltaY > 0 ? 0.92 : 1.1);
    }, { passive: false, signal: abort.signal });

    // Keyboard navigation
    canvas.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { cameraState.azimuth += 0.12; e.preventDefault(); }
      if (e.key === 'ArrowRight') { cameraState.azimuth -= 0.12; e.preventDefault(); }
      if (e.key === 'ArrowUp') { cameraState.elevation = clamp(cameraState.elevation + 0.08, 0.42, 1.38); e.preventDefault(); }
      if (e.key === 'ArrowDown') { cameraState.elevation = clamp(cameraState.elevation - 0.08, 0.42, 1.38); e.preventDefault(); }
      if (e.key === '+' || e.key === '=') { zoomBy(1.12); e.preventDefault(); }
      if (e.key === '-') { zoomBy(0.9); e.preventDefault(); }
    }, { signal: abort.signal });

    // Main animation loop
    function render(time, dt) {
      const delta = clamp(Number(dt) || 0, 0, 0.06);
      elapsedTime += delta;

      for (const item of personas) {
        if (!visible.has(item.persona.id)) {
          item.group.visible = false;
          continue;
        }

        const events = item.persona._events || [];
        const firstT = events.length ? events[0].timestamp : 0;
        const lastT = events.length ? events[events.length - 1].timestamp : 300;

        // Seamless entry and departure culling
        if (events.length && (time < firstT - 8.0 || time > lastT + 12.0)) {
          item.group.visible = false;
          continue;
        }

        item.group.visible = true;
        const target = positionAt(data, item.persona, time);

        // Smooth position lerp
        item.group.position.x += (target.x - item.group.position.x) * 0.18;
        item.group.position.z += (target.z - item.group.position.z) * 0.18;
        item.group.position.y = 0.08;

        // Facing direction rotation while walking
        const dx = target.x - item.group.position.x;
        const dz = target.z - item.group.position.z;
        if (target.isMoving && (Math.abs(dx) > 0.02 || Math.abs(dz) > 0.02)) {
          item.charRoot.rotation.y = Math.atan2(dx, dz);
        } else if (target.isSitting) {
          item.charRoot.rotation.y = target.event?.location === 'wifi' ? Math.PI / 2 : 0;
        }

        // Head diamond gentle pulse
        if (item.headDiamond) {
          item.headDiamond.rotation.y = elapsedTime * 2.5;
          item.headDiamond.position.y = 1.34 + Math.sin(elapsedTime * 4.0 + item.phase) * 0.03;
        }

        // Realistic walking bobbing and true sitting hip height
        if (target.isSitting) {
          item.charRoot.position.y = -0.14; // Correct hip height seated on chair
          item.leftLeg.rotation.x = -Math.PI / 2.1;
          item.rightLeg.rotation.x = -Math.PI / 2.1;
          item.leftArm.rotation.x = 0.35;
          item.rightArm.rotation.x = 0.35;
        } else if (target.isMoving) {
          const stride = Math.sin(elapsedTime * 9.5 + item.phase);
          item.charRoot.position.y = 0.04 + Math.abs(stride) * 0.04; // Walking bobbing
          item.leftLeg.rotation.x = stride * 0.52;
          item.rightLeg.rotation.x = -stride * 0.52;
          item.leftArm.rotation.x = -stride * 0.42;
          item.rightArm.rotation.x = stride * 0.42;
        } else {
          // Idle sway / waiting
          item.charRoot.position.y = Math.sin(elapsedTime * 2.2 + item.phase) * 0.015;
          item.leftLeg.rotation.x = 0;
          item.rightLeg.rotation.x = 0;
          item.leftArm.rotation.x = 0;
          item.rightArm.rotation.x = 0;
        }

        if (item.nameTag.visible) {
          item.selection.scale.setScalar(1 + Math.sin(elapsedTime * 3.5) * 0.08);
        }
      }


      updateCamera();
      renderer.render(scene, camera);
    }

    function destroy() {
      abort.abort();
      scene.traverse((o) => {
        if (o.geometry) o.geometry.dispose?.();
        const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
        for (const m of mats) {
          if (m.map) m.map.dispose?.();
          m.dispose?.();
        }
      });
      renderer.dispose();
    }

    resize();
    return {
      render, resize, setSelected, setVisible, focusPersona, resetCamera,
      overviewCamera, zoomBy, destroy, mode: '3d',
    };
  }

  /* ----------------------------------------------------------------------- */
  /* Canvas 2.5D Fallback Renderer (Section 19)                              */
  /* ----------------------------------------------------------------------- */
  function createCanvasRenderer(canvas, data, options = {}) {
    const ctx = canvas.getContext('2d');
    const env = data.environment;
    let width = 1;
    let height = 1;
    let dpr = 1;
    let zoomLevel = 1;
    let selectedId = null;
    let focusId = null;
    let visible = new Set();
    const abort = new AbortController();

    function resize() {
      const rect = canvas.getBoundingClientRect();
      width = Math.max(280, rect.width || canvas.parentElement?.clientWidth || 600);
      height = Math.max(280, rect.height || canvas.parentElement?.clientHeight || 480);
      dpr = Math.min(window.devicePixelRatio || 1, options.lowPerf ? 1.2 : 2);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function project(x, z) {
      const scale = Math.min(width / 20, height / 12) * zoomLevel;
      return {
        x: width / 2 + (x - z * 1.1) * scale,
        y: height * 0.44 + (x + z) * scale * 0.46,
      };
    }

    function render(time) {
      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = '#f6f9f6';
      ctx.fillRect(0, 0, width, height);

      // Draw an activity-specific 2.5D foundation when WebGL is unavailable.
      draw2DEnvironment();
      draw2DLocations(time);
      draw2DPersonas(time);
      ctx.restore();
    }

    function draw2DEnvironment() {
      if (env.activity === 'ecommerce' || (env.activity === 'other' && env.visual_activity !== 'fitness')) {
        const gradient = ctx.createLinearGradient(0, 0, width, height);
        gradient.addColorStop(0, '#f8fbf8');
        gradient.addColorStop(1, '#e4f3ec');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, width, height);
        ctx.strokeStyle = '#b8d8c9';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 8]);
        for (const key of env.route || []) {
          const loc = env.locations[key];
          if (!loc) continue;
          const point = project(loc.x, loc.z);
          if (key === env.route[0]) ctx.beginPath();
          if (key === env.route[0]) ctx.moveTo(point.x, point.y);
          else ctx.lineTo(point.x, point.y);
        }
        ctx.stroke();
        ctx.setLineDash([]);
        return;
      }
      // Road and floor for places customers can physically visit.
      const r1 = project(-12, -4);
      const r2 = project(12, -4);
      ctx.fillStyle = '#e3e9e3';
      ctx.beginPath();
      ctx.moveTo(r1.x, r1.y);
      ctx.lineTo(r2.x, r2.y);
      ctx.lineTo(r2.x, r2.y + 40);
      ctx.lineTo(r1.x, r1.y + 40);
      ctx.closePath();
      ctx.fill();

      // Venue floor slab
      const f1 = project(-3, -0.5);
      const f2 = project(10, -0.5);
      const f3 = project(10, 6.5);
      const f4 = project(-3, 6.5);
      ctx.fillStyle = '#e9f3ed';
      ctx.strokeStyle = '#9bbfab';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(f1.x, f1.y);
      ctx.lineTo(f2.x, f2.y);
      ctx.lineTo(f3.x, f3.y);
      ctx.lineTo(f4.x, f4.y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }

    function draw2DLocations(time) {
      for (const key of env.route || []) {
        const loc = env.locations[key];
        if (!loc) continue;
        const pt = project(loc.x, loc.z);
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 7, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#0e795d';
        ctx.lineWidth = 1.2;
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#17372c';
        ctx.font = '700 9px Alexandria, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(loc.label, pt.x, pt.y - 12);
      }
    }

    const personHits = [];
    function draw2DPersonas(time) {
      personHits.length = 0;
      for (const p of data.personas) {
        if (!p.representative || !visible.has(p.id)) continue;
        const pos = positionAt(data, p, time);
        const pt = project(pos.x, pos.z);
        const isSel = String(p.id) === String(selectedId);
        const color = p.buys ? '#0ca87f' : '#d66b59';

        ctx.beginPath();
        ctx.arc(pt.x, pt.y, isSel ? 9 : 6, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = isSel ? 2 : 1;
        ctx.stroke();

        if (isSel || String(p.id) === String(focusId)) {
          ctx.fillStyle = '#17372c';
          ctx.font = '800 10px Alexandria, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(p.name || `#${p.id}`, pt.x, pt.y - 14);
        }
        personHits.push({ id: p.id, x: pt.x, y: pt.y, r: 12 });
      }
    }

    canvas.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      for (const hit of personHits) {
        if (Math.hypot(hit.x - x, hit.y - y) <= hit.r) {
          options.onPick?.(hit.id);
          break;
        }
      }
    }, { signal: abort.signal });

    resize();
    return {
      render, resize,
      setSelected: (id) => { selectedId = id; },
      setVisible: (ids) => { visible = ids instanceof Set ? ids : new Set(ids || []); },
      focusPersona: (id) => { focusId = id; },
      resetCamera: () => { zoomLevel = 1; focusId = null; },
      overviewCamera: () => { zoomLevel = 0.85; focusId = null; },
      zoomBy: (f) => { zoomLevel = clamp(zoomLevel * f, 0.7, 2.2); },
      destroy: () => abort.abort(),
      mode: '2d',
    };
  }

  /* ----------------------------------------------------------------------- */
  /* Events / UI Handlers                                                    */
  /* ----------------------------------------------------------------------- */
  function handleClick(e) {
    const t = e.target;
    if (t.closest('[data-lm-close]')) { close(); window.dispatchEvent(new CustomEvent('fintwin:live-close')); return; }
    if (t.closest('[data-lm-play]')) { togglePlay(); return; }
    if (t.closest('[data-lm-restart]')) { restart(); return; }
    const sp = t.closest('[data-lm-speed]');
    if (sp) { S.speed = Number(sp.dataset.lmSpeed) || 1; updateControls(); return; }
    if (t.closest('[data-lm-reset-cam]')) { S.renderer?.resetCamera?.(); S.compareRenderer?.resetCamera?.(); return; }
    if (t.closest('[data-lm-overview]')) { S.renderer?.overviewCamera?.(); S.compareRenderer?.overviewCamera?.(); return; }
    const zm = t.closest('[data-lm-zoom]');
    if (zm) {
      const f = zm.dataset.lmZoom === 'in' ? 1.2 : 0.83;
      S.renderer?.zoomBy?.(f);
      S.compareRenderer?.zoomBy?.(f);
      return;
    }
    if (t.closest('[data-lm-mode]')) { toggleMode(); return; }
    if (t.closest('[data-lm-perf]')) { togglePerformance(); return; }
    if (t.closest('[data-lm-toggle-right]')) { toggleRightDrawer(); return; }
    if (t.closest('[data-lm-close-persona]')) { closePersonaDrawer(); return; }
    if (t.closest('[data-lm-reset-filters]')) {
      S.filters = emptyFilters();
      renderFilters();
      afterFilterChange();
      return;
    }
    const rmFilter = t.closest('[data-lm-remove-filter]');
    if (rmFilter) {
      S.filters[rmFilter.dataset.lmRemoveFilter] = '';
      renderFilters();
      afterFilterChange();
      return;
    }
    if (t.closest('[data-lm-open-compare]')) { toggleComparison(true); return; }
    if (t.closest('[data-lm-close-compare]')) { toggleComparison(false); return; }
    if (t.closest('[data-lm-split]')) { toggleSplit(); return; }
    if (t.closest('[data-lm-run-scenario]')) { runScenario(); return; }
    const preset = t.closest('[data-lm-preset]');
    if (preset) {
      $('#lmScenarioText').value = preset.dataset.lmPreset;
      runScenario(preset.dataset.lmPreset);
      return;
    }
    const tab = t.closest('#lmPersonaDrawer [data-lm-tab]');
    if (tab) { setTab(tab.dataset.lmTab); return; }
    const rTab = t.closest('[data-lm-right-tab]');
    if (rTab) { setRightTab(rTab.dataset.lmRightTab); return; }
    const person = t.closest('[data-lm-persona]');
    if (person) { selectPersona(person.dataset.lmPersona); return; }
    const feedE = t.closest('[data-lm-event]');
    if (feedE) { const item = eventById(feedE.dataset.lmEvent); if (item) selectPersona(item.personaId, item.id); return; }
    const tlE = t.closest('[data-lm-timeline]');
    if (tlE) { const item = eventById(tlE.dataset.lmTimeline); if (item) selectPersona(item.personaId, item.id); return; }
    const chatQ = t.closest('[data-lm-chat]');
    if (chatQ) { askPersona(chatQ.dataset.lmChat); return; }
    const run = t.closest('[data-lm-run]');
    if (run) { openRun(run.dataset.lmRun); return; }
    if (t.closest('[data-lm-run-select]')) {
      $('#lmRunsPanel')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }
  }

  function handleChange(e) {
    const f = e.target.closest('[data-lm-filter]');
    if (f) {
      S.filters[f.dataset.lmFilter] = f.value;
      afterFilterChange();
    }
  }

  function handleInput(e) {
    if (e.target.id === 'lmPeopleSearch') {
      S.personSearch = e.target.value;
      renderPeople();
    }
  }

  function handleSubmit(e) {
    const form = e.target.closest('[data-lm-chat-form]');
    if (!form) return;
    e.preventDefault();
    const input = form.elements.question;
    if (input) askPersona(input.value);
  }

  function handleKeydown(e) {
    if (e.key === 'Escape' && S.selectedId) {
      closePersonaDrawer();
    }
  }

  function afterFilterChange() {
    renderActiveFilterChips();
    const ids = [...visibleIds()];
    S.renderer?.setVisible(ids);
    S.compareRenderer?.setVisible([...visibleIds(S.baseline)]);
    renderPeople();
    renderFeed(true);
    updateHud(true);
    const empty = $('#lmStageEmpty');
    empty.classList.toggle('hidden', ids.length > 0 || S.loading);
    if (!ids.length && !S.loading) {
      $('#lmEmptyTitle').textContent = 'لا توجد شخصيات مطابقة للمرشحات';
      $('#lmEmptyDesc').textContent = 'جرّب مسح بعض المرشحات لعرض شخصيات أخرى.';
    }
  }

  function togglePlay() {
    if (!S.data) return;
    if (!S.playing && S.time >= S.duration) S.time = 0;
    S.playing = !S.playing;
    updatePlayButton();
  }

  function restart() {
    S.time = 0;
    S.playing = !S.reduceMotion;
    S.lastFeedKey = '';
    updatePlayButton();
    updateHud(true);
    S.renderer?.render(0, 0);
  }

  function updatePlayButton() {
    const btn = $('#lmPlayBtn');
    if (btn) btn.textContent = S.playing ? 'إيقاف مؤقت' : 'تشغيل';
  }

  function updateControls() {
    updatePlayButton();
    $$('[data-lm-speed]').forEach((b) => b.classList.toggle('active', Number(b.dataset.lmSpeed) === S.speed));
    $('#lmSpeedLabel').textContent = `${S.speed}×`;
  }

  function toggleMode() {
    S.mode = S.mode === '3d' ? '2d' : '3d';
    initRenderer().then(() => {
      S.renderer?.render(S.time, 0);
      if (S.split) S.compareRenderer?.render(S.time, 0);
    });
  }

  function togglePerformance() {
    S.lowPerf = !S.lowPerf;
    initRenderer().then(() => {
      S.renderer?.render(S.time, 0);
      if (S.split) S.compareRenderer?.render(S.time, 0);
    });
  }

  /* ----------------------------------------------------------------------- */
  /* Lifecycle, Open & Animation Loop                                        */
  /* ----------------------------------------------------------------------- */
  async function fetchLive() {
    if (S.demoId) {
      return lmApi(`/api/demo/${encodeURIComponent(S.demoId)}/live-market`);
    }
    const q = S.runId ? `?run_id=${encodeURIComponent(S.runId)}` : '';
    return lmApi(`/api/projects/${encodeURIComponent(S.projectId)}/live-market${q}`);
  }

  async function initRenderer() {
    destroyRenderer();
    destroyCompareRenderer();
    if (!S.data || !S.mounted) return;
    const token = S.openToken;
    const canvas = replaceCanvas('lmCanvas', { ariaLabel: 'مشهد السوق الحي' });
    if (S.mode === '3d') {
      try {
        await loadThree();
      } catch (e) {
        S.mode = '2d';
      }
    }
    if (token !== S.openToken || !S.mounted) return;
    const opts = {
      lowPerf: S.lowPerf,
      onPick: (id) => selectPersona(id),
    };
    if (S.mode === '3d' && window.THREE) {
      S.renderer = createThreeRenderer(canvas, S.data, opts);
    } else {
      S.mode = '2d';
      S.renderer = createCanvasRenderer(canvas, S.data, opts);
    }
    S.renderer.resize();
    S.renderer.setVisible([...visibleIds()]);
    S.renderer.setSelected(S.selectedId);
    $('[data-lm-mode]').textContent = S.mode === '3d' ? 'عرض 2D' : 'عرض 3D';
    if (S.split) await syncSplitRenderer();
    requestAnimationFrame(() => S.renderer?.resize());
  }

  async function open(options = {}) {
    cancelAnimationFrame(S.raf);
    S.raf = 0;
    destroyRenderer();
    destroyCompareRenderer();
    const token = ++S.openToken;
    S.projectId = options.projectId || null;
    S.demoId = options.demoId || null;
    S.runId = options.runId || null;
    S.demo = Boolean(options.demoId);
    S.filters = emptyFilters();
    S.selectedId = null;
    S.selectedEventId = null;
    S.chat = [];
    S.chatBusy = false;
    S.comparison = null;
    S.baseline = null;
    S.comparisonOpen = false;
    S.split = false;
    S.scenarioMessage = null;
    S.tab = 'decision';
    S.rightTab = 'feed';
    S.rightDrawerOpen = false;
    S.personSearch = '';
    S.reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false;
    S.mode = '3d';
    S.lowPerf = false;
    if (!S.root) S.root = document.getElementById('liveMarketRoot');
    if (!S.root) return;

    renderShell();
    toggleRightDrawer(false);
    $('#lmStageEmpty').classList.remove('hidden');
    $('#lmEmptyTitle').textContent = 'نجهّز السوق الحي…';
    $('#lmEmptyDesc').textContent = 'نقرأ قرارات المحاكاة ونبني المشهد المعماري والمسارات.';

    try {
      const data = await fetchLive();
      if (token !== S.openToken || !S.mounted) return;
      prepareDataset(data);
      S.data = data;
      S.activeRunId = data.run?.id || null;
      S.duration = data._duration;
      S.time = Math.min(85, S.duration * 0.42);
      S.playing = !S.reduceMotion;
      renderMeta();
      renderFilters();
      renderMetrics();
      renderPeople();
      renderFeed(true);
      renderScenarioPanel();
      updateControls();
      updateHud(true);
      await initRenderer();
      if (token !== S.openToken || !S.mounted) return;
      $('#lmStageEmpty').classList.add('hidden');
      startLoop();
      updateHud(true);
    } catch (err) {
      if (token !== S.openToken) return;
      $('#lmStageEmpty').classList.remove('hidden');
      $('#lmEmptyTitle').textContent = 'تعذر تحميل السوق الحي';
      $('#lmEmptyDesc').textContent = err.message;
    }
  }

  function openRun(runId) {
    if (!runId || runId === S.activeRunId || S.demoId) return;
    if (window.history?.pushState) {
      window.history.pushState({}, '', `/projects/${encodeURIComponent(S.projectId)}/live-market?run=${encodeURIComponent(runId)}`);
    }
    open({ projectId: S.projectId, runId });
  }

  function startLoop() {
    cancelAnimationFrame(S.raf);
    S.lastTick = performance.now();
    S.lastHud = 0;
    const tick = (now) => {
      if (!S.mounted) return;
      const dt = clamp((now - S.lastTick) / 1000, 0, 0.08);
      S.lastTick = now;
      if (S.playing && S.data) {
        S.time += dt * S.speed;
        if (S.time >= S.duration) {
          S.time = S.duration;
          S.playing = false;
          updatePlayButton();
        }
      }
      if (S.renderer) S.renderer.render(S.time, dt);
      if (S.split && S.compareRenderer) S.compareRenderer.render(S.time, dt);
      if (now - S.lastHud > 320) {
        S.lastHud = now;
        updateHud();
      }
      S.raf = requestAnimationFrame(tick);
    };
    S.raf = requestAnimationFrame(tick);
  }

  function close() {
    S.openToken += 1;
    cancelAnimationFrame(S.raf);
    S.raf = 0;
    destroyRenderer();
    destroyCompareRenderer();
    S.mounted = false;
    S.data = null;
    if (S.root) S.root.innerHTML = '';
  }

  document.addEventListener('visibilitychange', () => {
    if (!S.mounted) return;
    if (document.hidden) {
      if (S.playing) { S.resumeAfterHidden = true; S.playing = false; updatePlayButton(); }
    } else if (S.resumeAfterHidden) {
      S.resumeAfterHidden = false;
      S.playing = true;
      S.lastTick = performance.now();
      updatePlayButton();
    }
  });

  let resizeTimer = 0;
  window.addEventListener('resize', () => {
    if (!S.mounted) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      S.renderer?.resize();
      S.compareRenderer?.resize();
      updateHud(true);
    }, 140);
  });

  window.LiveMarket = { open, close, focus: selectPersona, __state: S };
})();
