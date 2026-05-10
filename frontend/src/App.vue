<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div>
        <h1>食堂食材进货自动录入系统</h1>
        <p>Canteen Ingredient Intake Automation</p>
      </div>
      <el-tag type="success" size="large">双摄像头 / YOLO / OCR</el-tag>
    </el-header>

    <el-main>
      <el-card class="control-card" shadow="hover">
        <div class="toolbar">
          <el-input v-model="operator" placeholder="记录人" style="width: 180px" />
          <el-input v-model="supplier" placeholder="供应商/批次备注" style="width: 220px" />
          <el-select v-model="selectedWeight" placeholder="YOLO模型" style="width: 220px">
            <el-option v-for="item in modelWeights" :key="item" :label="item" :value="item" />
          </el-select>
          <el-slider v-model="confidence" :format-tooltip="formatConfidence" style="width: 260px" />
          <el-button type="primary" :loading="capturing" @click="manualCapture">拍照识别</el-button>
          <el-button type="warning" :loading="capturing" @click="intrusionCapture">模拟入侵触发</el-button>
          <el-button @click="refreshAll">刷新状态</el-button>
        </div>
      </el-card>

      <div class="camera-grid">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>进货区摄像头</span>
              <el-tag :type="cameraTag('entrance')">{{ cameraText('entrance') }}</el-tag>
            </div>
          </template>
          <img class="camera-frame" :src="entranceStream" alt="进货区实时画面" />
        </el-card>

        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>秤面长焦摄像头</span>
              <el-tag :type="cameraTag('scale')">{{ cameraText('scale') }}</el-tag>
            </div>
          </template>
          <img class="camera-frame" :src="scaleStream" alt="秤面实时画面" />
        </el-card>
      </div>

      <el-card class="result-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>最近一次识别结果</span>
            <el-tag>{{ pendingJobs }} 个任务处理中</el-tag>
          </div>
        </template>
        <el-empty v-if="!lastResult" description="暂无识别结果" />
        <el-descriptions v-else :column="3" border>
          <el-descriptions-item label="批次号">{{ lastResult.batch_id }}</el-descriptions-item>
          <el-descriptions-item label="触发方式">{{ triggerLabel(lastResult.trigger_type) }}</el-descriptions-item>
          <el-descriptions-item label="记录人">{{ lastResult.recorded_by || '-' }}</el-descriptions-item>
          <el-descriptions-item label="菜品种类">
            <el-tag v-for="item in lastResult.vegetables" :key="item" class="tag">{{ item }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="OCR重量">{{ lastResult.weight ?? '-' }} kg</el-descriptions-item>
          <el-descriptions-item label="采集时间">{{ formatTime(lastResult.captured_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="records-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>进货记录</span>
            <el-button size="small" @click="loadRecords">刷新记录</el-button>
          </div>
        </template>
        <el-table :data="records" style="width: 100%">
          <el-table-column prop="batchId" label="批次号" min-width="180" />
          <el-table-column prop="triggerType" label="触发方式" width="120">
            <template #default="scope">{{ triggerLabel(scope.row.triggerType) }}</template>
          </el-table-column>
          <el-table-column prop="vegetables" label="菜品种类" min-width="160">
            <template #default="scope">
              <el-tag v-for="item in scope.row.vegetables" :key="item" class="tag">{{ item }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="weight" label="重量(kg)" width="120" />
          <el-table-column prop="recordedBy" label="记录人" width="130" />
          <el-table-column prop="supplier" label="供应商/备注" min-width="150" />
          <el-table-column prop="capturedAt" label="时间" min-width="180" />
          <el-table-column label="操作" width="100">
            <template #default="scope">
              <el-button text type="danger" @click="removeRecord(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';
import {
  deleteRecord,
  getCameraStatus,
  getCaptureStatus,
  getModelOptions,
  getRecords,
  triggerIntrusionCapture,
  triggerManualCapture,
  type IntakeRecord,
} from './api';

interface FlaskCaptureResult {
  batch_id: string;
  trigger_type: string;
  recorded_by?: string;
  captured_at: number;
  vegetables: string[];
  weight?: number;
}

const operator = ref('operator-001');
const supplier = ref('');
const selectedWeight = ref('');
const confidence = ref(45);
const capturing = ref(false);
const modelWeights = ref<string[]>([]);
const cameraStatus = ref<Record<string, { connected: boolean; running: boolean }>>({});
const pendingJobs = ref(0);
const lastResult = ref<FlaskCaptureResult | null>(null);
const records = ref<IntakeRecord[]>([]);

const streamVersion = ref(Date.now());
const entranceStream = computed(() => `/flask-api/cameras/entrance/stream?v=${streamVersion.value}`);
const scaleStream = computed(() => `/flask-api/cameras/scale/stream?v=${streamVersion.value}`);

function formatConfidence(value: number) {
  return (value / 100).toFixed(2);
}

function cameraTag(name: string) {
  const status = cameraStatus.value[name];
  return status?.connected && status?.running ? 'success' : 'danger';
}

function cameraText(name: string) {
  const status = cameraStatus.value[name];
  return status?.connected && status?.running ? '在线' : '离线';
}

function triggerLabel(value: string) {
  return value === 'intrusion' ? '入侵触发' : '拍照识别';
}

function formatTime(value?: number) {
  if (!value) return '-';
  return new Date(value * 1000).toLocaleString();
}

async function manualCapture() {
  await submitCapture('manual');
}

async function intrusionCapture() {
  await submitCapture('intrusion');
}

async function submitCapture(type: 'manual' | 'intrusion') {
  capturing.value = true;
  try {
    const payload = {
      recorded_by: operator.value,
      supplier: supplier.value,
      metadata: {
        yolo_weight: selectedWeight.value,
        confidence: confidence.value / 100,
      },
    };
    if (type === 'manual') {
      await triggerManualCapture(payload);
    } else {
      await triggerIntrusionCapture(payload);
    }
    ElMessage.success('已提交识别任务，等待 YOLO 与 OCR 线程处理');
    setTimeout(refreshAll, 1200);
  } finally {
    capturing.value = false;
  }
}

async function loadCameraStatus() {
  const response = await getCameraStatus();
  cameraStatus.value = response.data?.cameras || {};
}

async function loadCaptureStatus() {
  const response = await getCaptureStatus();
  pendingJobs.value = response.data?.pending_jobs || 0;
  lastResult.value = response.data?.last_result || null;
}

async function loadRecords() {
  const response = await getRecords();
  records.value = response.data?.data || [];
}

async function loadModels() {
  const response = await getModelOptions();
  modelWeights.value = response.data?.weights || [];
  selectedWeight.value = modelWeights.value[0] || '';
}

async function removeRecord(id?: string) {
  if (!id) return;
  await deleteRecord(id);
  ElMessage.success('记录已删除');
  await loadRecords();
}

async function refreshAll() {
  streamVersion.value = Date.now();
  await Promise.all([loadCameraStatus(), loadCaptureStatus(), loadRecords()]);
}

onMounted(async () => {
  await Promise.all([loadModels(), refreshAll()]);
  window.setInterval(loadCaptureStatus, 3000);
});
</script>
