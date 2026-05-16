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
          <el-select v-model="selectedWeight" placeholder="目标检测模型" style="width: 220px">
            <el-option v-for="item in modelWeights" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="selectedOcrBackend" placeholder="OCR模型" style="width: 180px">
            <el-option v-for="item in ocrBackends" :key="item" :label="item" :value="item" />
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

      <div class="record-grid">
        <el-card class="records-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>本机 SQLite 待上传条目</span>
              <div class="header-actions">
                <el-button size="small" @click="loadLocalSessionRecords">刷新</el-button>
                <el-button size="small" type="primary" :disabled="localSessionRecords.length === 0" @click="uploadLocalData">
                  数据入库
                </el-button>
              </div>
            </div>
          </template>
          <div class="scroll-panel">
            <el-empty v-if="localSessionRecords.length === 0" :description="localEmptyText" />
            <el-table v-else :data="localSessionRecords" style="width: 100%">
              <el-table-column prop="batchId" label="批次号" min-width="160" />
              <el-table-column prop="vegetables" label="菜品" min-width="150">
                <template #default="scope">
                  <el-tag v-for="item in scope.row.vegetables" :key="item" class="tag">{{ item }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="weight" label="重量(kg)" width="100" />
              <el-table-column prop="storageDate" label="入库日期" width="120" />
              <el-table-column prop="recordedBy" label="记录人" width="110" />
            </el-table>
          </div>
        </el-card>

        <el-card class="records-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>MySQL 已有条目</span>
              <div class="header-actions">
                <el-date-picker v-model="mysqlDate" type="date" size="small" style="width: 150px" />
                <el-button size="small" @click="loadMysqlRecords">查询</el-button>
              </div>
            </div>
          </template>
          <div class="scroll-panel">
            <el-table :data="mysqlRecords" style="width: 100%">
              <el-table-column prop="batchId" label="批次号" min-width="160" />
              <el-table-column prop="vegetables" label="菜品" min-width="150">
                <template #default="scope">
                  <el-tag v-for="item in scope.row.vegetables" :key="item" class="tag">{{ item }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="weight" label="重量(kg)" width="100" />
              <el-table-column prop="storageDate" label="入库日期" width="120" />
              <el-table-column prop="supplier" label="供应商" min-width="120" />
            </el-table>
          </div>
        </el-card>
      </div>

      <el-dialog v-model="confirmVisible" title="确认本次检测数据" width="620px">
        <el-form :model="confirmForm" label-width="110px">
          <el-form-item label="批次号">
            <el-input v-model="confirmForm.batchId" />
          </el-form-item>
          <el-form-item label="菜品种类">
            <el-input v-model="confirmVegetablesText" placeholder="多个菜品用逗号分隔" />
          </el-form-item>
          <el-form-item label="秤上重量(kg)">
            <el-input-number v-model="confirmForm.weight" :min="0" :precision="3" style="width: 100%" />
          </el-form-item>
          <el-form-item label="入库日期">
            <el-date-picker v-model="confirmStorageDate" type="date" style="width: 100%" />
          </el-form-item>
          <el-form-item label="记录人">
            <el-input v-model="confirmForm.recordedBy" />
          </el-form-item>
          <el-form-item label="供应商/备注">
            <el-input v-model="confirmForm.supplier" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="confirmVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmLocalInsert">确认录入 SQLite</el-button>
        </template>
      </el-dialog>

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
import { computed, onMounted, ref, watch } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import {
  createLocalRecord,
  deleteRecord,
  getCameraStatus,
  getCaptureStatus,
  getLocalSessionRecords,
  getModelOptions,
  getMysqlRecords,
  triggerIntrusionCapture,
  triggerManualCapture,
  uploadLocalRecordsToMysql,
  updateRecord,
  type IntakeRecord,
} from './api';

interface FlaskCaptureResult {
  job_id: string;
  batch_id: string;
  trigger_type: string;
  recorded_by?: string;
  captured_at: number;
  vegetables: string[];
  weight?: number;
  metadata?: Record<string, unknown>;
  detection?: unknown;
}

const operator = ref('operator-001');
const supplier = ref('');
const selectedWeight = ref('');
const selectedOcrBackend = ref('paddleocr');
const confidence = ref(45);
const capturing = ref(false);
const modelWeights = ref<string[]>([]);
const ocrBackends = ref<string[]>(['paddleocr']);
const cameraStatus = ref<Record<string, { connected: boolean; running: boolean }>>({});
const pendingJobs = ref(0);
const lastResult = ref<FlaskCaptureResult | null>(null);
const localSessionRecords = ref<IntakeRecord[]>([]);
const localEmptyText = ref('本地数据库暂无待上传数据');
const mysqlRecords = ref<IntakeRecord[]>([]);
const mysqlDate = ref<Date>(new Date());
const handledResultJobIds = ref<Set<string>>(new Set());
const confirmVisible = ref(false);
const confirmForm = ref<IntakeRecord>({
  id: '',
  jobId: '',
  batchId: '',
  triggerType: 'manual',
  vegetables: [],
  capturedAt: '',
  storageDate: '',
});
const confirmVegetablesText = ref('');
const confirmStorageDate = ref<Date>(new Date());
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

function formatDateOnly(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
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
        ocr_backend: selectedOcrBackend.value,
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

async function loadLocalSessionRecords() {
  try {
    const response = await getLocalSessionRecords();
    localSessionRecords.value = response.data?.data || [];
  } catch (error) {
    console.warn('加载本机 SQLite 记录失败，请确认 SpringBoot 后端已启动', error);
  }
}

async function loadMysqlRecords() {
  try {
    const response = await getMysqlRecords(formatDateOnly(mysqlDate.value));
    mysqlRecords.value = response.data?.data || [];
  } catch (error) {
    console.warn('加载 MySQL 记录失败，请确认 SpringBoot 后端和 MySQL 已启动', error);
  }
}

async function loadModels() {
  try {
    const response = await getModelOptions();
    modelWeights.value = response.data?.weights || [];
    ocrBackends.value = response.data?.ocr_backends || ['paddleocr'];
    selectedWeight.value = modelWeights.value[0] || '';
    selectedOcrBackend.value = ocrBackends.value[0] || 'paddleocr';
  } catch (error) {
    console.warn('加载模型列表失败', error);
  }
}

async function removeRecord(id?: string) {
  if (!id) return;
  await deleteRecord(id);
  ElMessage.success('记录已删除');
  await loadMysqlRecords();
}

function openConfirmDialog(result: FlaskCaptureResult) {
  confirmForm.value = {
    jobId: result.job_id,
    batchId: result.batch_id,
    triggerType: result.trigger_type,
    recordedBy: result.recorded_by || operator.value,
    supplier: String(result.metadata?.supplier || supplier.value || ''),
    vegetables: [...(result.vegetables || [])],
    weight: result.weight,
    capturedAt: new Date(result.captured_at * 1000).toISOString(),
    storageDate: formatDateOnly(new Date()),
    rawJson: result,
  };
  confirmVegetablesText.value = (result.vegetables || []).join(',');
  confirmStorageDate.value = new Date();
  confirmVisible.value = true;
}

async function confirmLocalInsert() {
  const record: IntakeRecord = {
    ...confirmForm.value,
    vegetables: confirmVegetablesText.value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    storageDate: formatDateOnly(confirmStorageDate.value),
  };
  await createLocalRecord(record);
  ElMessage.success('已确认并录入本机 SQLite');
  localEmptyText.value = '本地数据库暂无待上传数据';
  confirmVisible.value = false;
  await loadLocalSessionRecords();
}

async function uploadLocalData() {
  if (localSessionRecords.value.length === 0) {
    ElMessage.info('本地数据库暂无待上传数据');
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确认将当前区域内 ${localSessionRecords.value.length} 条数据写入 MySQL，并清空本机待上传区吗？`,
      '确认数据入库',
      {
        confirmButtonText: '确认入库',
        cancelButtonText: '取消',
        type: 'warning',
      }
    );
    const response = await uploadLocalRecordsToMysql();
    const uploadedCount = response.data?.data?.uploadedCount ?? 0;
    localSessionRecords.value = [];
    localEmptyText.value = '数据已入库，本地数据库暂无待上传数据';
    ElMessage.success(`数据已入库，共写入 ${uploadedCount} 条`);
    await Promise.allSettled([loadLocalSessionRecords(), loadMysqlRecords()]);
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      console.warn('数据入库失败', error);
      ElMessage.error('数据入库失败，请检查 SpringBoot 和 MySQL 连接');
    }
  }
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
  await loadMysqlRecords();
}

async function refreshAll() {
  await Promise.allSettled([loadCameraStatus(), loadCaptureStatus(), loadLocalSessionRecords(), loadMysqlRecords()]);
}

function reloadStreams() {
  streamVersion.value = Date.now();
}

onMounted(async () => {
  await Promise.allSettled([loadModels(), refreshAll()]);
  window.setInterval(loadCaptureStatus, 3000);
});

watch(lastResult, (result) => {
  if (!result?.job_id || handledResultJobIds.value.has(result.job_id)) return;
  handledResultJobIds.value.add(result.job_id);
  openConfirmDialog(result);
});
</script>
