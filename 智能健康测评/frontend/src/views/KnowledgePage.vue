<script setup>
import { ref, onMounted } from 'vue'
import {
  uploadKnowledgeFile,
  listKnowledgeFiles,
  deleteKnowledgeFile,
  searchKnowledge,
  getKnowledgeStats,
} from '../api'

const files = ref([])
const stats = ref(null)
const uploading = ref(false)
const searching = ref(false)
const drag = ref(false)
const searchQuery = ref('')
const searchHits = ref([])
const fileInput = ref(null)

const typeIcons = { text: '📄', doc: '📘', image: '🖼️' }
const statusText = { pending: '排队中', parsing: '解析中', done: '已完成', failed: '失败' }
const statusColor = { pending: 'var(--warning)', parsing: 'var(--warning)', done: 'var(--success)', failed: 'var(--danger)' }

async function loadData() {
  try {
    const [f, s] = await Promise.all([
      listKnowledgeFiles(100, 0),
      getKnowledgeStats().catch(() => null),
    ])
    files.value = f.data || []
    stats.value = s?.data || null
  } catch (e) {
    console.error(e)
  }
}

async function handleFile(file) {
  if (!file) return
  uploading.value = true
  try {
    const resp = await uploadKnowledgeFile(file)
    alert(
      `✅ 入库成功：${resp.data.file_name}\n` +
      `类型：${resp.data.file_type} | 解析文本入库\n` +
      `向量分块：${resp.data.chunk_count}\n${resp.data.parse_message || ''}`
    )
    await loadData()
  } catch (e) {
    alert('❌ 上传失败：' + e.message)
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function onPick(e) {
  handleFile(e.target.files[0])
}
function onDrop(e) {
  drag.value = false
  const f = e.dataTransfer.files?.[0]
  handleFile(f)
}

async function removeFile(id, name) {
  if (!confirm(`确认删除「${name}」及其向量？`)) return
  try {
    await deleteKnowledgeFile(id)
    await loadData()
  } catch (e) {
    alert('删除失败：' + e.message)
  }
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  try {
    const resp = await searchKnowledge(searchQuery.value.trim(), 5)
    searchHits.value = resp.data || []
  } catch (e) {
    alert('检索失败：' + e.message)
  } finally {
    searching.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <div>
    <!-- 统计 -->
    <div class="stat-grid">
      <div class="stat-card">
        <div class="num">{{ stats?.total_files ?? '-' }}</div>
        <div class="label">知识文件</div>
      </div>
      <div class="stat-card">
        <div class="num">{{ stats?.total_chunks ?? '-' }}</div>
        <div class="label">向量分块（Milvus）</div>
      </div>
      <div class="stat-card">
        <div class="num">{{ stats?.by_type?.image ?? 0 }}</div>
        <div class="label">图片（OCR）</div>
      </div>
      <div class="stat-card">
        <div class="num">{{ stats?.by_type?.doc ?? 0 }}</div>
        <div class="label">PDF/Word 文档</div>
      </div>
    </div>

    <!-- 上传区 -->
    <div class="card mt-16">
      <div class="card-title">上传知识文档 / 图片（多模态全解析）</div>
      <div
        class="upload-zone"
        :class="{ drag }"
        @click="fileInput.click()"
        @dragover.prevent="drag = true"
        @dragleave="drag = false"
        @drop.prevent="onDrop"
      >
        <div style="font-size: 34px">📤</div>
        <div>点击或拖拽文件到此处</div>
        <div class="muted mt-8">
          支持：文本(.txt/.md) · PDF(.pdf) · Word(.docx) · 图片(.png/.jpg，自动 OCR 识别文字)
        </div>
        <div class="muted mt-8">
          流程：MinIO 存储原件 → 多模态解析（图片走 DeepSeek-OCR）→ bge-m3 向量化 → Milvus 检索
        </div>
        <input
          ref="fileInput"
          type="file"
          style="display: none"
          accept=".txt,.md,.pdf,.docx,.png,.jpg,.jpeg,.webp"
          @change="onPick"
        />
      </div>
      <div v-if="uploading" class="loading-text">⏳ 上传解析中（图片 OCR 约需 10-30s）…</div>
    </div>

    <!-- 语义检索 -->
    <div class="card mt-16">
      <div class="card-title">知识库语义检索（Milvus 向量）</div>
      <div class="row">
        <input
          v-model="searchQuery"
          style="flex:1;border:1px solid var(--border);border-radius:8px;padding:8px 12px"
          placeholder="输入问题，如：高血压患者的饮食建议？"
          @keyup.enter="doSearch"
        />
        <button class="btn" :disabled="searching" @click="doSearch">检索</button>
      </div>
      <div v-if="searchHits.length" class="mt-16">
        <div v-for="(h, i) in searchHits" :key="i" class="report-rule" style="margin-bottom:8px">
          <div class="row">
            <span class="risk-badge risk-低风险">相关度 {{ (h.distance * 100).toFixed(0) }}%</span>
            <span class="muted">{{ h.source }} #块{{ i + 1 }}</span>
          </div>
          <div style="margin-top:6px">{{ h.content }}</div>
        </div>
      </div>
    </div>

    <!-- 文件列表 -->
    <div class="card mt-16">
      <div class="card-title">已入库文件（{{ files.length }}）</div>
      <table v-if="files.length" class="data">
        <thead>
          <tr>
            <th></th><th>文件名</th><th>类型</th><th>大小</th>
            <th>状态</th><th>分块数</th><th>摘要</th><th>时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in files" :key="f.id">
            <td>{{ typeIcons[f.file_type] || '📦' }}</td>
            <td style="max-width:200px;word-break:break-all">{{ f.file_name }}</td>
            <td>{{ f.file_type }}</td>
            <td>{{ (f.file_size / 1024).toFixed(1) }} KB</td>
            <td><span :style="{ color: statusColor[f.status] }">{{ statusText[f.status] || f.status }}</span></td>
            <td>{{ f.chunk_count }}</td>
            <td style="max-width:300px" class="muted">{{ f.content_summary?.slice(0, 80) }}…</td>
            <td>{{ f.upload_time?.slice(0, 10) }}</td>
            <td><button class="btn danger" style="padding:3px 10px" @click="removeFile(f.id, f.file_name)">删除</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-text">暂无文件，请上传第一个知识文档</div>
    </div>
  </div>
</template>
