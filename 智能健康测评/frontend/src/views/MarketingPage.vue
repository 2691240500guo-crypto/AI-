<script setup>
/**
 * 产品官网 Demo v2 —— 营销官网式 + 深空科技感
 * 参考 Aceternity UI / Magic UI 的视觉语言原创实现：
 * 大 Hero 渐变标题 / 网格星空背景 / bento grid / 辉光边框 / 卡片聚光灯
 * 纯前端 mock 数据，不连后端。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

const now = new Date()
const greeting = computed(() => {
  const h = now.getHours()
  if (h < 6) return '深夜好'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

// —— 顶部时钟 ——
const time = ref('')
let timer
function tick() { time.value = new Date().toLocaleTimeString('zh-CN', { hour12: false }) }
onMounted(() => { tick(); timer = setInterval(tick, 1000) })
onUnmounted(() => { if (timer) clearInterval(timer) })

// —— bento grid 功能矩阵 ——
const features = [
  {
    key: 'chat', size: 'lg', icon: '✦', tone: '#4de3ff', tag: 'AI Agent',
    title: 'AI 智能问答', desc: '多轮对话 · 意图识别 · 任务式执行。说出「帮我订一周减脂餐」，AI 直接生成可审核的个性化计划。',
    chips: ['多轮记忆', '意图识别', '一键记饮食'],
  },
  {
    key: 'plan', size: 'sm', icon: '▦', tone: '#a78bfa', tag: 'Personalized',
    title: '个性化饮食计划', desc: 'BMR 计算 + 近 7 天摄入校准，三档菜谱自动选档，营养师可人工调整。',
    chips: ['Mifflin-St Jeor', '三档菜谱'],
  },
  {
    key: 'tongue', size: 'sm', icon: '◉', tone: '#34d399', tag: 'Vision',
    title: '舌体智能观察', desc: '视觉模型检测 + 颜色观察 + 历史趋势色带，健康变化一眼可见。',
    chips: ['图像检测', '趋势对比'],
  },
  {
    key: 'voice', size: 'sm', icon: '♬', tone: '#f472b6', tag: 'Voice',
    title: '语音助手', desc: 'ASR 转写 + TTS 朗读，端到端语音对话，长辈也能零门槛使用。',
    chips: ['语音输入', '语音播报'],
  },
  {
    key: 'social', size: 'sm', icon: '◌', tone: '#fbbf24', tag: 'Safety',
    title: '健康社区 · 双机审', desc: '红线词 + 视觉模型双重审核，违规内容发不出去，社区干净可信。',
    chips: ['文本机审', '图像机审'],
  },
  {
    key: 'review', size: 'lg', icon: '✓', tone: '#60a5fa', tag: 'Human-in-the-loop',
    title: '营养师工作台', desc: 'AI 生成的计划先落库待审；营养师可改可批——不改则沿用 AI 原版，改过则标注「营养师已调整」。AI 效率与专业把关两全。',
    chips: ['计划审核', 'Diff 对比', '会话管理'],
  },
]

// —— 数据 ——
const heroStats = [
  { value: '12,486', label: '累计测评' },
  { value: '5,672', label: '活跃用户' },
  { value: '4', label: '健康 Agent' },
  { value: '24h', label: '连续陪伴' },
]
const trend = [3, 5, 4, 7, 6, 9, 8, 11, 9, 12, 14, 13, 16, 14, 17, 20, 18, 22, 21, 24, 27]
const trendMax = Math.max(...trend)
const riskDist = [
  { label: '无风险', value: 64, color: '#10b981' },
  { label: '低风险', value: 22, color: '#4de3ff' },
  { label: '中风险', value: 9,  color: '#fbbf24' },
  { label: '高风险', value: 5,  color: '#f472b6' },
]
const circumference = 2 * Math.PI * 48
const riskSegs = computed(() => {
  let acc = 0
  return riskDist.map((r) => {
    const dash = (r.value / 100) * circumference
    const seg = { color: r.color, dash, offset: acc }
    acc += dash
    return seg
  })
})

// —— 营养师 diff ——
const diffBefore = { set: '轻食减负档', target: 1348, lunch: '鸡胸藜麦能量沙拉 540 kcal' }
const diffAfter  = { set: '轻食减负档（已调整）', target: 1280, lunch: '鸡胸藜麦沙拉 + 清蒸鱼（去皮） 470 kcal' }
const reviewNote = '已按你的甲状腺情况把晚餐主食减到 80g，午餐蛋白来源调整为白肉海鲜。'

// —— 社区精选 ——
const posts = [
  { id: 'p1', user: '苏苏的轻食日记', avatar: '苏', time: '12 分钟前', content: '藜麦沙拉 + 烤南瓜 + 无糖酸奶，规律吃饭后下午能量稳定了很多。', tags: ['#轻食', '#打卡'], hue: 142 },
  { id: 'p2', user: '阿哲在跑步', avatar: '哲', time: '1 小时前', content: '下班后 5 公里，风很舒服。不追配速，只想把今天的情绪跑出去。', tags: ['#运动打卡'], hue: 200 },
  { id: 'p3', user: '陈医生', avatar: '陈', time: '今天 09:12', content: '更新知识库 · 春季过敏人群饮食建议 · 附详细解读。', tags: ['#知识', '#营养师'], hue: 280 },
]

// —— 团队 ——
const team = [
  { name: '陈医生', role: '资深营养师 · 12 年', tag: '减脂 / 糖尿病饮食', color: '#a78bfa' },
  { name: '苏苏', role: '注册营养师 · 7 年', tag: '女性健康 / 备孕', color: '#f472b6' },
  { name: '林老师', role: '运动营养师 · 9 年', tag: '增肌 / 运动表现', color: '#34d399' },
]

// —— 卡片聚光灯：鼠标跟随 ——
function spotlight(e) {
  const el = e.currentTarget
  const r = el.getBoundingClientRect()
  el.style.setProperty('--mx', (e.clientX - r.left) + 'px')
  el.style.setProperty('--my', (e.clientY - r.top) + 'px')
}
</script>

<template>
  <div class="site">
    <!-- ============ 导航 ============ -->
    <header class="nav">
      <div class="nav-logo"><span class="logo-dot"></span>Healthy<strong>Bot</strong></div>
      <nav class="nav-links">
        <a href="#features">核心能力</a>
        <a href="#insight">数据洞察</a>
        <a href="#review">人工把关</a>
        <a href="#community">健康社区</a>
        <a href="#team">营养师团队</a>
      </nav>
      <div class="nav-right">
        <span class="nav-time">{{ greeting }} · {{ time }}</span>
        <button class="btn-ghost">登录</button>
        <button class="btn-primary-sm">免费体验 →</button>
      </div>
    </header>

    <!-- ============ Hero ============ -->
    <section class="hero">
      <div class="hero-grid-bg" aria-hidden="true"></div>
      <div class="orb orb-1" aria-hidden="true"></div>
      <div class="orb orb-2" aria-hidden="true"></div>
      <div class="orb orb-3" aria-hidden="true"></div>
      <div class="hero-body">
        <div class="hero-badge"><span class="pulse"></span>AI 驱动的智能健康管理平台</div>
        <h1 class="hero-title">
          让健康管理<br />
          <span class="grad-text">变得有温度</span>
        </h1>
        <p class="hero-sub">
          记录每一餐、每一次运动和每一晚睡眠。四个健康 Agent 全天候待命，
          把复杂的健康问题变成今天就能做的小事。
        </p>
        <div class="hero-cta">
          <button class="btn-primary">立即开始 <span>→</span></button>
          <button class="btn-outline">观看演示</button>
        </div>
        <div class="hero-stats">
          <div v-for="s in heroStats" :key="s.label" class="hstat">
            <strong>{{ s.value }}</strong><span>{{ s.label }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ Bento 功能矩阵 ============ -->
    <section id="features" class="features">
      <div class="sec-head">
        <span class="sec-tag">CORE FEATURES</span>
        <h2>一个平台，<span class="grad-text">六种智能</span></h2>
        <p>从对话到计划、从舌象到社区，AI 与专业营养师共同守护。</p>
      </div>
      <div class="bento">
        <article
          v-for="f in features" :key="f.key"
          class="cell" :class="'cell-' + f.size"
          :style="{ '--tone': f.tone }"
          @mousemove="spotlight"
        >
          <div class="spot" aria-hidden="true"></div>
          <div class="cell-head">
            <span class="cell-icon">{{ f.icon }}</span>
            <span class="cell-tag">{{ f.tag }}</span>
          </div>
          <h3>{{ f.title }}</h3>
          <p>{{ f.desc }}</p>
          <div class="cell-chips">
            <span v-for="c in f.chips" :key="c">{{ c }}</span>
          </div>
        </article>
      </div>
    </section>

    <!-- ============ 数据洞察 ============ -->
    <section id="insight" class="insight">
      <div class="sec-head">
        <span class="sec-tag">DATA INSIGHT</span>
        <h2>看得见的<span class="grad-text">健康趋势</span></h2>
        <p>每一次测评、每一餐记录都会沉淀为可回溯的健康曲线。</p>
      </div>
      <div class="insight-grid">
        <div class="panel" @mousemove="spotlight">
          <div class="spot" aria-hidden="true"></div>
          <div class="panel-head">
            <h3>风险分布</h3><span class="panel-sub">NRS2002 · 近 30 天</span>
          </div>
          <div class="ring-wrap">
            <svg viewBox="0 0 120 120" class="ring">
              <circle cx="60" cy="60" r="48" stroke="#1e293b" stroke-width="14" fill="none" />
              <circle v-for="(seg, i) in riskSegs" :key="i" cx="60" cy="60" r="48"
                      :stroke="seg.color" stroke-width="14" fill="none"
                      :stroke-dasharray="`${seg.dash} ${circumference}`"
                      :stroke-dashoffset="-seg.offset"
                      transform="rotate(-90 60 60)" stroke-linecap="butt" />
            </svg>
            <div class="ring-center"><strong>12,486</strong><span>测评总数</span></div>
          </div>
          <ul class="legend">
            <li v-for="r in riskDist" :key="r.label">
              <span class="dot" :style="{ background: r.color }"></span>
              <span>{{ r.label }}</span><strong>{{ r.value }}%</strong>
            </li>
          </ul>
        </div>
        <div class="panel" @mousemove="spotlight">
          <div class="spot" aria-hidden="true"></div>
          <div class="panel-head">
            <h3>记录热度</h3><span class="panel-sub">近 21 天 · 每日打卡</span>
          </div>
          <div class="bars">
            <div v-for="(v, i) in trend" :key="i" class="bar"
                 :style="{ height: (v / trendMax * 100) + '%', background: i === trend.length - 1 ? '#4de3ff' : 'linear-gradient(180deg, #2dd4bf55, #4de3ff22)' }"></div>
          </div>
          <p class="panel-note">连续打卡用户近 21 天增长 <strong class="up">+800%</strong>，健康习惯正在养成。</p>
        </div>
      </div>
    </section>

    <!-- ============ 人工把关 ============ -->
    <section id="review" class="review">
      <div class="sec-head">
        <span class="sec-tag">HUMAN-IN-THE-LOOP</span>
        <h2>AI 高效，<span class="grad-text">营养师把关</span></h2>
        <p>AI 生成的每份计划都先进入审核队列，专业意见随时注入。</p>
      </div>
      <div class="diff-wrap">
        <div class="diff-card before" @mousemove="spotlight">
          <div class="spot" aria-hidden="true"></div>
          <span class="diff-label">AI 生成</span>
          <h4>{{ diffBefore.set }}</h4>
          <ul>
            <li><span>目标热量</span><strong>{{ diffBefore.target }} kcal</strong></li>
            <li><span>午餐</span><strong>{{ diffBefore.lunch }}</strong></li>
          </ul>
        </div>
        <div class="diff-arrow" aria-hidden="true">→<em>审核调整</em></div>
        <div class="diff-card after" @mousemove="spotlight">
          <div class="spot" aria-hidden="true"></div>
          <span class="diff-label ok">营养师已调整</span>
          <h4>{{ diffAfter.set }}</h4>
          <ul>
            <li><span>目标热量</span><strong>{{ diffAfter.target }} kcal <em class="delta">-68</em></strong></li>
            <li><span>午餐</span><strong>{{ diffAfter.lunch }}</strong></li>
          </ul>
          <p class="diff-note">“{{ reviewNote }}”</p>
        </div>
      </div>
    </section>

    <!-- ============ 社区 ============ -->
    <section id="community" class="community">
      <div class="sec-head">
        <span class="sec-tag">COMMUNITY</span>
        <h2>健康广场 · <span class="grad-text">真实的坚持</span></h2>
        <p>AI 与营养师在评论区实时互动，双机审守住内容底线。</p>
      </div>
      <div class="posts">
        <article v-for="p in posts" :key="p.id" class="post" :style="{ '--hue': p.hue }" @mousemove="spotlight">
          <div class="spot" aria-hidden="true"></div>
          <div class="post-head">
            <div class="post-avatar">{{ p.avatar }}</div>
            <div><strong>{{ p.user }}</strong><span>{{ p.time }}</span></div>
          </div>
          <p>{{ p.content }}</p>
          <div class="post-tags"><span v-for="t in p.tags" :key="t">{{ t }}</span></div>
        </article>
      </div>
    </section>

    <!-- ============ 团队 + CTA ============ -->
    <section id="team" class="team">
      <div class="sec-head">
        <span class="sec-tag">EXPERT TEAM</span>
        <h2>背后是<span class="grad-text">真实的专业团队</span></h2>
      </div>
      <div class="team-grid">
        <div v-for="m in team" :key="m.name" class="member" :style="{ '--tone': m.color }" @mousemove="spotlight">
          <div class="spot" aria-hidden="true"></div>
          <div class="member-avatar" :style="{ background: 'linear-gradient(135deg, ' + m.color + ', transparent)' }">{{ m.name[0] }}</div>
          <div><strong>{{ m.name }}</strong><span>{{ m.role }}</span><em>{{ m.tag }}</em></div>
        </div>
      </div>
      <div class="cta">
        <div class="orb orb-4" aria-hidden="true"></div>
        <h2>今天，从<span class="grad-text">记录一餐</span>开始</h2>
        <p>注册即享 4 个健康 Agent 的全天候陪伴。</p>
        <button class="btn-primary">免费体验 HealthyBot <span>→</span></button>
      </div>
    </section>

    <footer class="foot">
      <div><strong>HealthyBot</strong><span>智能健康测评 · 让健康管理变得有温度</span></div>
      <span class="foot-time">{{ time }} · 产品官网 Demo · 纯前端演示数据</span>
    </footer>
  </div>
</template>

<style scoped>
/* ==================== 基础与变量 ==================== */
.site {
  --bg: #0a0e27;
  --bg-soft: #0f1530;
  --card: #111a38;
  --line: rgba(77, 227, 255, .14);
  --text: #e6ecff;
  --muted: #8b96c9;
  --cyan: #4de3ff;
  --purple: #a78bfa;
  --pink: #f472b6;
  --green: #34d399;
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif;
  overflow-x: hidden;
}
.grad-text {
  background: linear-gradient(92deg, var(--cyan) 10%, var(--purple) 55%, var(--pink) 95%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
section { max-width: 1080px; margin: 0 auto; padding: 72px 24px 0; }

/* ==================== 导航 ==================== */
.nav {
  position: sticky; top: 0; z-index: 50;
  display: flex; align-items: center; gap: 28px;
  padding: 14px 28px;
  background: rgba(10, 14, 39, .72);
  backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line);
}
.nav-logo { display: flex; align-items: center; gap: 8px; font-size: 17px; color: var(--text); }
.nav-logo strong { color: var(--cyan); }
.logo-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 12px var(--cyan); }
.nav-links { display: flex; gap: 20px; margin: 0 auto; }
.nav-links a { color: var(--muted); text-decoration: none; font-size: 13.5px; transition: color .15s; }
.nav-links a:hover { color: var(--cyan); }
.nav-right { display: flex; align-items: center; gap: 12px; }
.nav-time { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.btn-ghost {
  padding: 7px 16px; border-radius: 9px; font-size: 13px;
  background: transparent; border: 1px solid var(--line); color: var(--text); cursor: pointer;
}
.btn-primary-sm {
  padding: 7px 16px; border-radius: 9px; font-size: 13px; cursor: pointer; color: #061229; border: none;
  background: linear-gradient(92deg, var(--cyan), #7cc7ff);
  box-shadow: 0 0 18px rgba(77, 227, 255, .35);
  transition: box-shadow .2s, transform .2s;
}
.btn-primary-sm:hover { box-shadow: 0 0 28px rgba(77, 227, 255, .55); transform: translateY(-1px); }

/* ==================== Hero ==================== */
.hero { position: relative; text-align: center; padding-top: 96px; }
.hero-grid-bg {
  position: absolute; inset: -80px 0 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(77, 227, 255, .06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(77, 227, 255, .06) 1px, transparent 1px);
  background-size: 44px 44px;
  -webkit-mask-image: radial-gradient(ellipse 75% 60% at 50% 30%, #000 35%, transparent 75%);
  mask-image: radial-gradient(ellipse 75% 60% at 50% 30%, #000 35%, transparent 75%);
}
.orb { position: absolute; border-radius: 50%; filter: blur(70px); opacity: .5; pointer-events: none; }
.orb-1 { width: 420px; height: 420px; left: 4%; top: -60px; background: radial-gradient(closest-side, #4de3ff, transparent 70%); animation: float 9s ease-in-out infinite; }
.orb-2 { width: 460px; height: 460px; right: 2%; top: 40px; background: radial-gradient(closest-side, #a78bfa, transparent 70%); animation: float 11s ease-in-out -3s infinite; }
.orb-3 { width: 320px; height: 320px; left: 42%; top: 300px; background: radial-gradient(closest-side, #f472b6, transparent 70%); opacity: .3; animation: float 13s ease-in-out -6s infinite; }
.orb-4 { width: 380px; height: 240px; left: 50%; top: -60px; transform: translateX(-50%); background: radial-gradient(closest-side, #4de3ff, transparent 70%); opacity: .35; }
@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-26px); }
}
.hero-body { position: relative; max-width: 720px; margin: 0 auto; }
.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 16px; border-radius: 999px; font-size: 12.5px; color: var(--cyan);
  border: 1px solid rgba(77, 227, 255, .35); background: rgba(77, 227, 255, .07);
}
.pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 0 0 rgba(77, 227, 255, .6); animation: pulse 2s infinite; }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(77, 227, 255, .55); }
  70% { box-shadow: 0 0 0 9px rgba(77, 227, 255, 0); }
  100% { box-shadow: 0 0 0 0 rgba(77, 227, 255, 0); }
}
.hero-title { font-size: 64px; line-height: 1.16; margin: 26px 0 18px; font-weight: 800; letter-spacing: 1px; }
.hero-sub { color: var(--muted); font-size: 16.5px; line-height: 1.8; max-width: 560px; margin: 0 auto 34px; }
.hero-cta { display: flex; gap: 14px; justify-content: center; margin-bottom: 56px; }
.btn-primary {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 13px 30px; border-radius: 12px; font-size: 15px; font-weight: 600; cursor: pointer; border: none; color: #061229;
  background: linear-gradient(92deg, var(--cyan), #7cc7ff);
  box-shadow: 0 0 26px rgba(77, 227, 255, .4);
  transition: box-shadow .2s, transform .2s;
}
.btn-primary:hover { box-shadow: 0 0 44px rgba(77, 227, 255, .6); transform: translateY(-2px); }
.btn-primary span { transition: transform .2s; }
.btn-primary:hover span { transform: translateX(4px); }
.btn-outline {
  padding: 13px 30px; border-radius: 12px; font-size: 15px; cursor: pointer;
  background: rgba(167, 139, 250, .08); border: 1px solid rgba(167, 139, 250, .4); color: var(--purple);
  transition: background .2s, box-shadow .2s;
}
.btn-outline:hover { background: rgba(167, 139, 250, .16); box-shadow: 0 0 24px rgba(167, 139, 250, .3); }
.hero-stats { display: flex; justify-content: center; gap: 52px; padding: 26px 0 8px; border-top: 1px solid var(--line); }
.hstat strong { display: block; font-size: 26px; color: var(--text); font-variant-numeric: tabular-nums; }
.hstat span { font-size: 12px; color: var(--muted); }

/* ==================== 区块标题 ==================== */
.sec-head { text-align: center; margin-bottom: 40px; }
.sec-tag { font-size: 11.5px; letter-spacing: 3px; color: var(--cyan); opacity: .8; }
.sec-head h2 { font-size: 34px; margin: 12px 0 10px; font-weight: 800; }
.sec-head p { color: var(--muted); font-size: 14.5px; }

/* ==================== Bento 网格 ==================== */
.bento { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.cell {
  position: relative; overflow: hidden; cursor: default;
  border: 1px solid var(--line); border-radius: 18px;
  background: linear-gradient(160deg, rgba(77, 227, 255, .05), rgba(17, 26, 56, .9) 45%);
  padding: 22px;
  transition: transform .25s, border-color .25s, box-shadow .25s;
}
.cell:hover { transform: translateY(-4px); border-color: color-mix(in srgb, var(--tone) 55%, transparent); box-shadow: 0 18px 44px -18px color-mix(in srgb, var(--tone) 45%, transparent); }
.cell-lg { grid-column: span 2; }
.cell-sm { grid-column: span 2; }
.spot {
  position: absolute; inset: 0; pointer-events: none; opacity: 0; transition: opacity .3s;
  background: radial-gradient(320px circle at var(--mx, 50%) var(--my, 50%), color-mix(in srgb, var(--tone, #4de3ff) 14%, transparent), transparent 65%);
}
.cell:hover .spot, .panel:hover .spot, .post:hover .spot, .member:hover .spot, .diff-card:hover .spot { opacity: 1; }
.cell-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.cell-icon {
  width: 40px; height: 40px; border-radius: 12px; font-size: 18px;
  display: flex; align-items: center; justify-content: center;
  color: var(--tone); border: 1px solid color-mix(in srgb, var(--tone) 40%, transparent);
  background: color-mix(in srgb, var(--tone) 10%, transparent);
  box-shadow: 0 0 16px color-mix(in srgb, var(--tone) 30%, transparent);
}
.cell-tag { font-size: 10.5px; letter-spacing: 1.5px; color: var(--muted); border: 1px solid var(--line); padding: 3px 9px; border-radius: 999px; }
.cell h3 { font-size: 17px; margin: 0 0 8px; }
.cell p { font-size: 13px; line-height: 1.7; color: var(--muted); margin: 0 0 14px; }
.cell-chips { display: flex; gap: 8px; flex-wrap: wrap; }
.cell-chips span { font-size: 11.5px; color: color-mix(in srgb, var(--tone) 80%, #fff); background: color-mix(in srgb, var(--tone) 10%, transparent); border: 1px solid color-mix(in srgb, var(--tone) 25%, transparent); padding: 3px 10px; border-radius: 999px; }

/* ==================== 数据洞察 ==================== */
.insight-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.panel {
  position: relative; overflow: hidden; cursor: default;
  border: 1px solid var(--line); border-radius: 18px;
  background: var(--bg-soft); padding: 22px;
  transition: border-color .25s, box-shadow .25s;
}
.panel:hover { border-color: rgba(77, 227, 255, .4); box-shadow: 0 18px 44px -18px rgba(77, 227, 255, .35); }
.panel-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 18px; }
.panel-head h3 { font-size: 16px; margin: 0; }
.panel-sub { font-size: 12px; color: var(--muted); }
.ring-wrap { position: relative; width: 190px; margin: 0 auto 16px; }
.ring { width: 100%; display: block; }
.ring-center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.ring-center strong { font-size: 24px; }
.ring-center span { font-size: 11px; color: var(--muted); }
.legend { list-style: none; display: grid; grid-template-columns: 1fr 1fr; gap: 8px 18px; padding: 0; margin: 0; }
.legend li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--muted); }
.legend strong { margin-left: auto; color: var(--text); font-variant-numeric: tabular-nums; }
.dot { width: 9px; height: 9px; border-radius: 50%; }
.bars { display: flex; align-items: flex-end; gap: 6px; height: 170px; margin-bottom: 14px; }
.bar { flex: 1; border-radius: 4px 4px 0 0; min-height: 6px; transition: transform .2s; }
.bar:hover { transform: scaleY(1.04); }
.panel-note { font-size: 13px; color: var(--muted); margin: 0; }
.up { color: var(--green); }

/* ==================== 人工把关 diff ==================== */
.diff-wrap { display: flex; align-items: stretch; gap: 18px; }
.diff-card {
  position: relative; overflow: hidden; cursor: default; flex: 1;
  border-radius: 18px; padding: 24px;
  background: var(--bg-soft); border: 1px solid var(--line);
  transition: border-color .25s, box-shadow .25s;
}
.diff-card.before:hover { border-color: rgba(139, 150, 201, .5); }
.diff-card.after { border-color: rgba(77, 227, 255, .3); }
.diff-card.after:hover { border-color: rgba(77, 227, 255, .6); box-shadow: 0 18px 44px -18px rgba(77, 227, 255, .4); }
.diff-label { font-size: 11px; letter-spacing: 1.5px; color: var(--muted); border: 1px solid var(--line); padding: 3px 10px; border-radius: 999px; }
.diff-label.ok { color: var(--green); border-color: rgba(52, 211, 153, .4); background: rgba(52, 211, 153, .08); }
.diff-card h4 { font-size: 17px; margin: 14px 0 12px; }
.diff-card ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
.diff-card li { display: flex; justify-content: space-between; font-size: 13px; color: var(--muted); border-bottom: 1px dashed rgba(139, 150, 201, .18); padding-bottom: 8px; }
.diff-card li strong { color: var(--text); font-weight: 500; }
.delta { font-style: normal; color: var(--pink); font-size: 11.5px; margin-left: 6px; }
.diff-arrow { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: var(--cyan); font-size: 22px; }
.diff-arrow em { font-style: normal; font-size: 11px; color: var(--muted); }
.diff-note { margin: 12px 0 0; font-size: 12.5px; color: var(--muted); font-style: italic; line-height: 1.6; }

/* ==================== 社区 ==================== */
.posts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.post {
  position: relative; overflow: hidden; cursor: default;
  border: 1px solid var(--line); border-radius: 16px; background: var(--bg-soft); padding: 18px;
  transition: transform .25s, border-color .25s;
}
.post:hover { transform: translateY(-4px); border-color: hsl(var(--hue, 200) 80% 60% / .55); }
.post::before {
  content: ''; position: absolute; inset: 0; opacity: .14; pointer-events: none;
  background: radial-gradient(120% 80% at 0% 0%, hsl(var(--hue, 200) 80% 60%), transparent 60%);
}
.post-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; position: relative; }
.post-avatar {
  width: 34px; height: 34px; border-radius: 50%; font-weight: 700; font-size: 14px; color: #061229;
  background: linear-gradient(135deg, hsl(var(--hue, 200) 80% 65%), hsl(calc(var(--hue, 200) + 45) 90% 62%));
  display: flex; align-items: center; justify-content: center;
}
.post-head strong { font-size: 13px; display: block; }
.post-head span { font-size: 11px; color: var(--muted); }
.post p { position: relative; font-size: 13px; line-height: 1.7; color: #c6cfee; margin: 0 0 12px; }
.post-tags { position: relative; display: flex; gap: 6px; flex-wrap: wrap; }
.post-tags span { font-size: 11px; padding: 2px 9px; border-radius: 999px; background: rgba(139, 150, 201, .12); color: var(--muted); }

/* ==================== 团队 + CTA ==================== */
.team-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 72px; }
.member {
  position: relative; overflow: hidden; cursor: default;
  display: flex; align-items: center; gap: 14px;
  border: 1px solid var(--line); border-radius: 16px; background: var(--bg-soft); padding: 18px;
  transition: transform .25s, border-color .25s;
}
.member:hover { transform: translateY(-3px); border-color: color-mix(in srgb, var(--tone) 55%, transparent); }
.member-avatar {
  width: 46px; height: 46px; border-radius: 13px; font-size: 19px; font-weight: 700; color: #061229;
  display: flex; align-items: center; justify-content: center;
}
.member strong { display: block; font-size: 14.5px; }
.member span { display: block; font-size: 12px; color: var(--muted); }
.member em { font-style: normal; font-size: 11.5px; color: var(--tone); }
.cta {
  position: relative; overflow: hidden; text-align: center;
  border: 1px solid rgba(77, 227, 255, .3); border-radius: 22px;
  background: linear-gradient(180deg, rgba(77, 227, 255, .07), rgba(17, 26, 56, .6));
  padding: 64px 24px 58px; margin-bottom: 72px;
}
.cta h2 { font-size: 34px; margin: 0 0 10px; font-weight: 800; }
.cta p { color: var(--muted); margin: 0 0 28px; font-size: 14.5px; }

/* ==================== Footer ==================== */
.foot {
  max-width: 1080px; margin: 0 auto; padding: 22px 24px 34px;
  display: flex; justify-content: space-between; align-items: center;
  border-top: 1px solid var(--line); color: var(--muted); font-size: 12.5px;
}
.foot strong { display: block; color: var(--cyan); font-size: 14px; }
.foot-time { font-variant-numeric: tabular-nums; }

/* ==================== 响应式 ==================== */
@media (max-width: 900px) {
  .nav-links, .nav-time { display: none; }
  .hero-title { font-size: 42px; }
  .hero-stats { gap: 24px; flex-wrap: wrap; }
  .bento { grid-template-columns: 1fr; }
  .cell-lg, .cell-sm { grid-column: span 1; }
  .insight-grid, .posts, .team-grid { grid-template-columns: 1fr; }
  .diff-wrap { flex-direction: column; }
  .diff-arrow { flex-direction: row; padding: 6px 0; }
}
</style>
