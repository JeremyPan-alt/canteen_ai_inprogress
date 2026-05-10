package com.canteen.intake.model;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.annotation.JsonFormat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class IntakeRecord {
    private String id = UUID.randomUUID().toString();

    @JsonAlias("job_id")
    private String jobId;

    @JsonAlias("batch_id")
    private String batchId;

    @JsonAlias("trigger_type")
    private String triggerType;

    @JsonAlias("recorded_by")
    private String recordedBy;

    private String supplier;
    private List<String> vegetables = new ArrayList<>();
    private Double weight;

    @JsonAlias("captured_at")
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    private Instant capturedAt = Instant.now();

    private Map<String, Object> rawJson = new LinkedHashMap<>();

    @JsonAnySetter
    public void putRawValue(String key, Object value) {
        rawJson.put(key, value);
        if ("metadata".equals(key) && value instanceof Map<?, ?> metadata) {
            Object supplierValue = metadata.get("supplier");
            if (supplierValue != null) {
                supplier = String.valueOf(supplierValue);
            }
        }
    }

    @JsonAnyGetter
    public Map<String, Object> rawValues() {
        return rawJson;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getJobId() {
        return jobId;
    }

    public void setJobId(String jobId) {
        this.jobId = jobId;
    }

    public String getBatchId() {
        return batchId;
    }

    public void setBatchId(String batchId) {
        this.batchId = batchId;
    }

    public String getTriggerType() {
        return triggerType;
    }

    public void setTriggerType(String triggerType) {
        this.triggerType = triggerType;
    }

    public String getRecordedBy() {
        return recordedBy;
    }

    public void setRecordedBy(String recordedBy) {
        this.recordedBy = recordedBy;
    }

    public String getSupplier() {
        return supplier;
    }

    public void setSupplier(String supplier) {
        this.supplier = supplier;
    }

    public List<String> getVegetables() {
        return vegetables;
    }

    public void setVegetables(List<String> vegetables) {
        this.vegetables = vegetables == null ? new ArrayList<>() : vegetables;
    }

    public Double getWeight() {
        return weight;
    }

    public void setWeight(Double weight) {
        this.weight = weight;
    }

    public Instant getCapturedAt() {
        return capturedAt;
    }

    public void setCapturedAt(Object capturedAt) {
        if (capturedAt instanceof Number number) {
            this.capturedAt = Instant.ofEpochMilli((long) (number.doubleValue() * 1000));
        } else if (capturedAt instanceof String text && !text.isBlank()) {
            this.capturedAt = Instant.parse(text);
        }
    }

    public Map<String, Object> getRawJson() {
        return rawJson;
    }

    public void setRawJson(Map<String, Object> rawJson) {
        this.rawJson = rawJson == null ? new LinkedHashMap<>() : rawJson;
    }
}
