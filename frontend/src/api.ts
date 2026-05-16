import axios from 'axios';

export interface IntakeRecord {
  id?: string;
  jobId?: string;
  batchId: string;
  triggerType: string;
  recordedBy?: string;
  supplier?: string;
  vegetables: string[];
  weight?: number;
  capturedAt: string;
  storageDate?: string;
  rawJson?: unknown;
}

export interface CapturePayload {
  recorded_by: string;
  supplier?: string;
  remark?: string;
  metadata?: Record<string, unknown>;
}

const spring = axios.create({
  baseURL: '/api',
  timeout: 15000,
});

const flask = axios.create({
  baseURL: '/flask-api',
  timeout: 15000,
});

export function triggerManualCapture(payload: CapturePayload) {
  return flask.post('/capture/manual', payload);
}

export function triggerIntrusionCapture(payload: CapturePayload) {
  return flask.post('/capture/intrusion', payload);
}

export function getCameraStatus() {
  return flask.get('/cameras/status');
}

export function getCaptureStatus() {
  return flask.get('/capture/status');
}

export function getModelOptions() {
  return flask.get('/models');
}

export function getMysqlRecords(date?: string) {
  return spring.get('/intake-records', {
    params: date ? { date } : undefined,
  });
}

export function getLocalSessionRecords() {
  return spring.get('/local-intake-records/session');
}

export function createLocalRecord(record: IntakeRecord) {
  return spring.post('/local-intake-records', record);
}

export function uploadLocalRecordsToMysql() {
  return spring.post('/local-intake-records/upload-to-mysql');
}

export function getRecords() {
  return getMysqlRecords();
}

export function deleteRecord(id: string) {
  return spring.delete(`/intake-records/${id}`);
}

export function updateRecord(id: string, record: IntakeRecord) {
  return spring.put(`/intake-records/${id}`, record);
}
