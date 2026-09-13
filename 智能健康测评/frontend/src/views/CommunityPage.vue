<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  commentSocialPost,
  createSocialPost,
  followSocialUser,
  getModerationQueue,
  getPostComments,
  getSocialFeed,
  likeSocialPost,
  reviewSocialPost,
  uploadSocialImages,
} from '../api'

const currentUser = JSON.parse(localStorage.getItem('healthybot_user') || '{"id":"user","name":"林晓晴"}')
const role = localStorage.getItem('healthybot_role') || 'user'
const isAdmin = role === 'admin'
const posts = ref([])
const loading = ref(true)
const error = ref('')
const notice = ref('')   // 审核成功等正向提示，用绿色条展示（避免塞进红色错误框）
const showComposer = ref(false)
const draft = ref({ content: '', tags: '#今日打卡' })
const liked = ref(new Set())
const following = ref(new Set())
const feedScope = ref('all')
const activeTopic = ref('推荐')
// 图片：待上传文件 + 本地预览
const pickFiles = ref([])
const previewImgs = ref([])
const publishing = ref(false)
const uploading = ref(false)

// —— 管理端：待审队列 ——
const queue = ref([])
const queueLoading = ref(false)
const queueTab = ref('pending_review')

const fallback = [
  { id: 'demo-1', user_id: 'susu', user_name: '苏苏的轻食日记', time: '12分钟前', title: '今天的午餐，给身体一点轻盈', content: '藜麦沙拉、烤南瓜和一份无糖酸奶。规律吃饭之后，下午的能量稳定了很多。', tags: ['#轻食记录', '#今日打卡'], likes: 28, comments: 6, images: ['https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&w=800&q=85'] },
  { id: 'demo-2', user_id: 'zhe', user_name: '阿哲在跑步', time: '1小时前', title: '下班后 5 公里，风很舒服', content: '不追配速，只想把今天的情绪跑出去。你们今天运动了吗？', tags: ['#运动打卡'], likes: 41, comments: 9, images: ['https://images.unsplash.com/photo-1552674605-db6ffd4facb5?auto=format&fit=crop&w=800&q=85'] },
]
function normalize(post) {
  return {
    ...post,
    title: post.title || (post.content || '').slice(0, 24),
    time: post.time || '刚刚',
    images: post.images || [],
    commentsList: [], commentsOpen: false, commentsLoading: false, commentText: '',
  }
}
const topicKeywords = {
  饮食: ['饮食', '便当', '早餐', '午餐', '晚餐', '轻食', '食谱', '热量'],
  运动: ['运动', '跑步', '健身', '步数', '训练'],
  睡眠: ['睡眠', '深睡', '入睡', '失眠', '作息'],
  减脂: ['减脂', '减重', '轻食', '热量'],
}
const visiblePosts = computed(() => {
  if (feedScope.value === 'following' || activeTopic.value === '推荐') return posts.value
  const keywords = topicKeywords[activeTopic.value] || []
  return posts.value.filter((post) => {
    const text = `${post.content || ''} ${(post.tags || []).join(' ')}`.toLowerCase()
    return keywords.some((keyword) => text.includes(keyword))
  })
})

async function loadFeed() {
  loading.value = true
  try {
    const resp = await getSocialFeed(currentUser.id, 20, feedScope.value)
    posts.value = (resp.data || []).map(normalize)
    if (!posts.value.length && !isAdmin && feedScope.value === 'all') posts.value = fallback.map(normalize)
  } catch {
    if (!isAdmin) { posts.value = fallback.map(normalize); error.value = '暂时无法加载最新动态，已显示示例内容' }
  } finally { loading.value = false }
}
async function toggleLike(post, index) {
  if (String(post.id).startsWith('demo-')) { liked.value.has(index) ? liked.value.delete(index) : liked.value.add(index); return }
  try { const resp = await likeSocialPost(post.id, currentUser.id); post.likes = resp.data.likes; post.liked = resp.data.liked } catch (e) { error.value = e.message }
}
async function toggleFollow(post) {
  if (String(post.user_id).startsWith('demo-') || post.user_id === currentUser.id) return
  try {
    const resp = await followSocialUser(post.user_id, currentUser.id)
    post.following = resp.data.following
    resp.data.following ? following.value.add(post.user_id) : following.value.delete(post.user_id)
    if (feedScope.value === 'following') await loadFeed()
  } catch (e) { error.value = e.message }
}

function selectFeed(scopeOrTopic) {
  error.value = ''
  if (scopeOrTopic === '关注') {
    feedScope.value = 'following'
    activeTopic.value = '关注'
    loadFeed()
    return
  }
  feedScope.value = 'all'
  activeTopic.value = scopeOrTopic
  if (!posts.value.length) loadFeed()
}

// —— 发帖：选图 → 上传 → 发布 ——
function onPickImages(event) {
  const picked = Array.from(event.target.files || [])
  picked.forEach((f) => {
    if (!f.type.startsWith('image/')) { error.value = '只能选择图片文件'; return }
    if (f.size > 5 * 1024 * 1024) { error.value = `${f.name} 超过 5MB`; return }
    if (pickFiles.value.length >= 9) { error.value = '最多上传 9 张图片'; return }
    pickFiles.value.push(f)
    previewImgs.value.push(URL.createObjectURL(f))
  })
  event.target.value = ''
}
function removeImage(i) {
  URL.revokeObjectURL(previewImgs.value[i])
  pickFiles.value.splice(i, 1)
  previewImgs.value.splice(i, 1)
}
async function publish() {
  const text = draft.value.content.trim()
  if (!text) return
  if (publishing.value) return
  publishing.value = true
  error.value = ''
  let images = []
  try {
    if (pickFiles.value.length) {
      uploading.value = true
      const resp = await uploadSocialImages(pickFiles.value, currentUser.id)
      images = resp.data?.urls || []
    }
  } catch (e) {
    error.value = e.message || '图片上传失败'
    uploading.value = false
    publishing.value = false
    return
  }
  uploading.value = false
  try {
    const resp = await createSocialPost({
      user_id: currentUser.id, user_name: currentUser.name,
      content: text, tags: draft.value.tags.split(/[,，\s]+/).filter(Boolean), images,
    })
    if (resp.data?.status === 'pending_review') error.value = '内容已进入人工审核，通过后自动展示'
    else posts.value.unshift(normalize(resp.data))
    draft.value = { content: '', tags: '#今日打卡' }
    previewImgs.value.forEach((u) => URL.revokeObjectURL(u))
    previewImgs.value = []
    pickFiles.value = []
    showComposer.value = false
  } catch (e) {
    error.value = e.message || '发布失败'
  } finally { publishing.value = false }
}

// —— 评论：展开加载 / 发表 ——
async function toggleComments(post) {
  post.commentsOpen = !post.commentsOpen
  if (!post.commentsOpen || post.commentsList.length) return
  if (String(post.id).startsWith('demo-')) {
    post.commentsList = [{ id: 'd1', user_name: '小圆', content: '看起来好好吃！下次试试同款' }]
    return
  }
  post.commentsLoading = true
  try {
    const resp = await getPostComments(post.id)
    post.commentsList = resp.data || []
  } catch (e) {
    error.value = e.message || '评论加载失败'
  } finally { post.commentsLoading = false }
}
async function submitComment(post) {
  const text = (post.commentText || '').trim()
  if (!text || String(post.id).startsWith('demo-')) { post.commentText = ''; return }
  try {
    await commentSocialPost(post.id, { user_id: currentUser.id, user_name: currentUser.name, content: text })
    post.comments = (post.comments || 0) + 1
    post.commentsList = [...(post.commentsList || []), { id: 'x' + Date.now(), user_name: currentUser.name, content: text }]
    post.commentText = ''
  } catch (e) { error.value = e.message || '评论失败' }
}

// —— 管理端审核 ——
async function loadQueue() {
  queueLoading.value = true
  try {
    const resp = await getModerationQueue(queueTab.value)
    queue.value = resp.data || []
  } catch (e) { error.value = e.message || '审核队列加载失败' } finally { queueLoading.value = false }
}
async function reviewPost(post, action) {
  notice.value = ''
  try {
    const resp = await reviewSocialPost(post.id, action, 'admin')
    queue.value = queue.value.filter((p) => p.id !== post.id)
    error.value = ''
    notice.value = resp.message || (action === 'approve' ? '已通过并对外展示' : '已驳回')
  } catch (e) { error.value = e.message }
}
function switchQueue(tab) { queueTab.value = tab; error.value = ''; notice.value = ''; loadQueue() }
onMounted(() => { loadFeed(); if (isAdmin) loadQueue() })
</script>

<template>
  <div class="page-heading">
    <div>
      <span class="overline">{{ isAdmin ? 'COMMUNITY · MODERATION' : 'COMMUNITY · HEALTHY TOGETHER' }}</span>
      <h1>{{ isAdmin ? '内容审核台' : '健康广场' }}</h1>
      <p v-if="!isAdmin">看见真实的坚持，也分享你的每一个小进步。</p>
      <p v-else>红线词机审拦截的内容在这里复核：通过后对外展示，驳回则不进入 feed。</p>
    </div>
    <button v-if="!isAdmin" class="btn primary-btn" @click="showComposer = !showComposer">＋ 发布动态</button>
  </div>
  <div v-if="error" class="alert">{{ error }}</div>
  <div v-if="notice" class="success-banner">{{ notice }}</div>

  <!-- 管理端：审核队列 -->
  <template v-if="isAdmin">
    <div class="composer-card" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <button class="btn ghost" :class="{active: queueTab === 'pending_review'}" @click="switchQueue('pending_review')">待审核</button>
      <button class="btn ghost" :class="{active: queueTab === 'rejected'}" @click="switchQueue('rejected')">已驳回</button>
      <button class="btn ghost" @click="loadQueue">刷新</button>
      <span class="muted" style="margin-left:auto">红线词：禁药 / 夸大功效 / 医疗广告，命中即转人工复核</span>
    </div>
    <div v-if="queueLoading" class="loading-text">加载审核队列…</div>
    <div v-else-if="!queue.length" class="empty-text" style="padding:28px 0;text-align:center">
      {{ queueTab === 'pending_review' ? '当前没有待审核内容 🎉' : '没有已驳回的内容' }}
    </div>
    <article v-for="post in queue" :key="post.id" class="post-card">
      <div class="post-head">
        <div class="post-avatar">{{ (post.user_name || '健').slice(0, 1) }}</div>
        <div><strong>{{ post.user_name }}</strong><span>{{ post.created_at || '刚刚' }}</span></div>
        <span class="mod-status">{{ post.status === 'pending_review' ? '⚠ 待复核' : '✕ 已驳回' }}</span>
      </div>
      <p>{{ post.content }}</p>
      <div class="post-tags"><span v-for="tag in post.tags" :key="tag">{{ tag }}</span></div>
      <div v-if="post.images?.length" class="post-images">
        <img v-for="(img, i) in post.images" :key="i" :src="img" alt="附件" />
      </div>
      <div class="post-actions">
        <button class="btn success small" @click="reviewPost(post, 'approve')">✓ 通过并发布</button>
        <button class="btn danger small" @click="reviewPost(post, 'reject')">✕ 驳回</button>
      </div>
    </article>
  </template>

  <!-- 用户端：发布 + 信息流 -->
  <template v-else>
    <div v-if="showComposer" class="composer-card">
      <textarea v-model="draft.content" rows="3" placeholder="分享今天的饮食、运动或睡眠…" />
      <input v-model="draft.tags" placeholder="#话题标签" />
      <div v-if="previewImgs.length" class="composer-imgs">
        <div v-for="(p, i) in previewImgs" :key="i" class="thumb-wrap">
          <img :src="p" alt="待发布图片" />
          <button type="button" class="thumb-x" @click="removeImage(i)">×</button>
        </div>
      </div>
      <div class="composer-actions">
        <label class="btn ghost">📷 添加图片（≤9张）<input type="file" accept="image/*" multiple hidden @change="onPickImages" /></label>
        <div style="margin-left:auto;display:flex;gap:8px">
          <button class="btn ghost" @click="showComposer = false">取消</button>
          <button class="btn primary-btn" :disabled="publishing" @click="publish">{{ uploading ? '图片机审中…' : publishing ? '发布中…' : '发布' }}</button>
        </div>
      </div>
    </div>
    <div class="community-layout">
      <section>
        <div class="topic-row"><button v-for="topic in ['推荐', '关注', '饮食', '运动', '睡眠', '减脂']" :key="topic" class="topic" :class="{active: activeTopic === topic}" @click="selectFeed(topic)">{{ topic }}</button></div>
        <div v-if="loading" class="loading-text">正在加载社区动态…</div>
        <div v-else-if="!visiblePosts.length" class="empty-text">{{ activeTopic === '关注' ? '还没有关注的动态，先去发现页关注健康伙伴吧。' : '暂无符合该分类的动态。' }}</div>
        <article v-for="(post, index) in visiblePosts" :key="post.id" class="post-card photo-host">
          <div
            v-if="!post.images?.length"
            class="post-photo photo-hidden-in-dark"
            :class="'ph-card-' + (index % 4 + 1)"
            aria-hidden="true"
          ></div>
          <div class="post-head">
            <div class="post-avatar">{{ (post.user_name || '健').slice(0, 1) }}</div>
            <div><strong>{{ post.user_name }}</strong><span>{{ post.time || '刚刚' }}</span></div>
            <button v-if="!String(post.user_id).startsWith('demo-') && post.user_id !== currentUser.id" class="follow-btn" @click="toggleFollow(post)">{{ post.following || following.has(post.user_id) ? '已关注' : '关注' }}</button>
            <button class="more-btn">•••</button>
          </div>
          <h3>{{ post.title }}</h3>
          <p>{{ post.content }}</p>
          <div class="post-tags"><span v-for="tag in post.tags" :key="tag">{{ tag }}</span></div>
          <div v-if="post.images?.length" class="post-images-grid" :class="{ single: post.images.length === 1 }">
            <img v-for="(img, i) in post.images" :key="i" :src="img" alt="健康生活记录" />
          </div>
          <div class="post-actions">
            <button :class="{liked: post.liked || liked.has(index)}" @click="toggleLike(post, index)">♡ {{ (post.likes || 0) + (liked.has(index) && !post.liked ? 1 : 0) }}</button>
            <button :class="{active: post.commentsOpen}" @click="toggleComments(post)">◌ {{ post.comments || 0 }}{{ post.commentsOpen ? ' ▲' : '' }}</button>
            <button>↗ 分享</button>
          </div>
          <div v-if="post.commentsOpen" class="comment-panel">
            <div v-if="post.commentsLoading" class="muted">加载评论…</div>
            <template v-else>
              <div v-if="!post.commentsList?.length" class="muted" style="padding:6px 2px">还没有评论，来抢沙发～</div>
              <div v-for="c in post.commentsList" :key="c.id" class="comment-item">
                <strong>{{ c.user_name }}</strong><span>{{ c.content }}</span>
              </div>
            </template>
            <div class="comment-input">
              <input v-model="post.commentText" placeholder="友善评论…" @keydown.enter="submitComment(post)" />
              <button class="btn small primary-btn" @click="submitComment(post)">发送</button>
            </div>
          </div>
        </article>
      </section>
      <aside>
        <div class="community-side-card accent photo-host"><div class="photo-bg ph-hero-1 mask-deep" aria-hidden="true"></div><span class="overline">THIS WEEK</span><strong>一起完成 7 天<br>健康打卡</strong><span>已有 2,184 人加入</span><button>加入挑战 →</button></div>
        <div class="community-side-card photo-host"><span class="photo-corner ph-card-2" aria-hidden="true"></span><h3>热门话题</h3><div class="hot-topic"><span># 早餐怎么吃</span><b>1.2k</b></div><div class="hot-topic"><span># 睡眠改善计划</span><b>836</b></div><div class="hot-topic"><span># 低卡晚餐</span><b>642</b></div></div>
      </aside>
    </div>
  </template>
</template>

<style scoped>
/* 帖子配图（浅色模式显示，深色模式由 .photo-hidden-in-dark 隐藏） */
.post-photo {
  height: 148px; margin: 2px 0 14px; border-radius: 12px;
  background-size: cover; background-position: center;
}

.mod-status { margin-left: auto; font-size: 12px; color: #b45309; }
.post-images { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 6px; margin: 8px 0; }
.post-images img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 8px; }
.btn.small { padding: 4px 10px; font-size: 12px; }
.btn.danger { background: #fee2e2; color: #b91c1c; }
.btn.success { background: #d1fae5; color: #065f46; }
.btn.ghost.active { outline: 1px solid var(--primary, #4de3ff); color: var(--primary, #4de3ff); }

/* 发帖图片选择 */
.composer-imgs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.thumb-wrap { position: relative; width: 72px; height: 72px; }
.thumb-wrap img { width: 100%; height: 100%; object-fit: cover; border-radius: 8px; border: 1px solid var(--border, #dbe3ee); }
.thumb-x { position: absolute; top: -7px; right: -7px; width: 20px; height: 20px; border-radius: 50%; border: none; background: #ef4444; color: #fff; font-size: 13px; line-height: 1; cursor: pointer; }
.composer-actions { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.composer-actions label.btn { cursor: pointer; margin-bottom: 0; }
.composer-actions label.btn input { display: none; }

/* 帖子多图 */
.post-images-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px; margin: 10px 0; }
.post-images-grid.single { grid-template-columns: 1fr; }
.post-images-grid img { width: 100%; aspect-ratio: 16/10; object-fit: cover; border-radius: 10px; }
.post-images-grid.single img { aspect-ratio: 16/9; }

/* 评论面板 */
.comment-panel { border-top: 1px dashed var(--border, #dbe3ee); padding: 8px 2px 2px; }
.comment-item { display: flex; gap: 8px; font-size: 13px; padding: 3px 0; }
.comment-item strong { color: #0e7490; white-space: nowrap; }
.comment-item span { word-break: break-word; }
.comment-input { display: flex; gap: 8px; margin-top: 6px; }
.comment-input input { flex: 1; border: 1px solid var(--border, #dbe3ee); border-radius: 8px; padding: 6px 10px; font-size: 13px; }
</style>
