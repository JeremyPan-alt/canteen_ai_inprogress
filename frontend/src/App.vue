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
          <el-button @click="reloadStreams">重连视频流</el-button>
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
          <el-table-column label="操作" width="160">
            <template #default="scope">
              <el-button text type="primary" @click="openEditDialog(scope.row)">修改</el-button>
              <el-button text type="danger" @click="removeRecord(scope.row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="editVisible" title="修改进货记录" width="560px">
        <el-form :model="editForm" label-width="110px">
          <el-form-item label="批次号">
            <el-input v-model="editForm.batchId" />
          </el-form-item>
          <el-form-item label="触发方式">
            <el-select v-model="editForm.triggerType" style="width: 100%">
              <el-option label="拍照识别" value="manual" />
              <el-option label="入侵触发" value="intrusion" />
            </el-select>
          </el-form-item>
          <el-form-item label="菜品种类">
            <el-input v-model="editVegetablesText" placeholder="多个菜品用逗号分隔，例如 tomato,potato" />
          </el-form-item>
          <el-form-item label="重量(kg)">
            <el-input-number v-model="editForm.weight" :min="0" :precision="3" style="width: 100%" />
          </el-form-item>
          <el-form-item label="记录人">
            <el-input v-model="editForm.recordedBy" />
          </el-form-item>
          <el-form-item label="供应商/备注">
            <el-input v-model="editForm.supplier" />
          </el-form-item>
          <el-form-item label="时间">
            <el-date-picker v-model="editCapturedAt" type="datetime" style="width: 100%" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" @click="saveEditedRecord">保存</el-button>
        </template>
      </el-dialog>
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
  updateRecord,
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
const editVisible = ref(false);
const editForm = ref<IntakeRecord>({
  id: '',
  batchId: '',
  triggerType: 'manual',
  vegetables: [],
  capturedAt: '',
});
const editVegetablesText = ref('');
const editCapturedAt = ref<Date | null>(null);

const flaskApiPrefix = import.meta.env.VITE_FLASK_API_PREFIX || '/flask-api';
const streamVersion = ref(Date.now());
const entranceStream = computed(() => `${flaskApiPrefix}/cameras/entrance/stream?v=${streamVersion.value}`);
const scaleStream = computed(() => `${flaskApiPrefix}/cameras/scale/stream?v=${streamVersion.value}`);

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
  try {
    const response = await getCameraStatus();
    cameraStatus.value = response.data?.cameras || {};
  } catch (error) {
    console.warn('加载摄像头状态失败', error);
  }
}

async function loadCaptureStatus() {
  try {
    const response = await getCaptureStatus();
    pendingJobs.value = response.data?.pending_jobs || 0;
    lastResult.value = response.data?.last_result || null;
  } catch (error) {
    console.warn('加载识别状态失败', error);
  }
}

async function loadRecords() {
  try {
    const response = await getRecords();
    records.value = response.data?.data || [];
  } catch (error) {
    console.warn('加载进货记录失败，请确认 SpringBoot 后端已启动', error);
  }
}

async function loadModels() {
  try {
    const response = await getModelOptions();
    modelWeights.value = response.data?.weights || [];
    selectedWeight.value = modelWeights.value[0] || '';
  } catch (error) {
    console.warn('加载模型列表失败', error);
  }
}

async function removeRecord(id?: string) {
  if (!id) return;
  await deleteRecord(id);
  ElMessage.success('记录已删除');
  await loadRecords();
}

function openEditDialog(row: IntakeRecord) {
  editForm.value = {
    ...row,
    vegetables: [...(row.vegetables || [])],
  };
  editVegetablesText.value = (row.vegetables || []).join(',');
  editCapturedAt.value = row.capturedAt ? new Date(row.capturedAt) : new Date();
  editVisible.value = true;
}

async function saveEditedRecord() {
  if (!editForm.value.id) return;
  const updated: IntakeRecord = {
    ...editForm.value,
    vegetables: editVegetablesText.value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    capturedAt: (editCapturedAt.value || new Date()).toISOString(),
  };
  await updateRecord(editForm.value.id, updated);
  ElMessage.success('记录已更新');
  editVisible.value = false;
  await loadRecords();
}

async function refreshAll() {
  await Promise.allSettled([loadCameraStatus(), loadCaptureStatus(), loadRecords()]);
}

function reloadStreams() {
  streamVersion.value = Date.now();
}

onMounted(async () => {
  await Promise.allSettled([loadModels(), refreshAll()]);
  window.setInterval(loadCaptureStatus, 3000);
});
</script>
