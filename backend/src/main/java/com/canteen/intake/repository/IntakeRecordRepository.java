package com.canteen.intake.repository;

import com.canteen.intake.model.IntakeRecord;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Repository
public class IntakeRecordRepository {
    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;
    private final RowMapper<IntakeRecord> rowMapper = this::mapRow;

    public IntakeRecordRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    @PostConstruct
    public void initializeSchema() {
        jdbcTemplate.execute("""
                CREATE TABLE IF NOT EXISTS intake_records (
                  id VARCHAR(64) PRIMARY KEY,
                  job_id VARCHAR(64),
                  batch_id VARCHAR(64) NOT NULL,
                  trigger_type VARCHAR(32),
                  recorded_by VARCHAR(128),
                  supplier VARCHAR(255),
                  vegetables JSON,
                  weight DECIMAL(10, 3),
                  captured_at TIMESTAMP,
                  raw_json JSON,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
                """);
    }

    public IntakeRecord save(IntakeRecord record) {
        if (record.getId() == null || record.getId().isBlank()) {
            record.setId(UUID.randomUUID().toString());
        }
        jdbcTemplate.update("""
                        INSERT INTO intake_records
                          (id, job_id, batch_id, trigger_type, recorded_by, supplier, vegetables, weight, captured_at, raw_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON DUPLICATE KEY UPDATE
                          job_id = VALUES(job_id),
                          batch_id = VALUES(batch_id),
                          trigger_type = VALUES(trigger_type),
                          recorded_by = VALUES(recorded_by),
                          supplier = VALUES(supplier),
                          vegetables = VALUES(vegetables),
                          weight = VALUES(weight),
                          captured_at = VALUES(captured_at),
                          raw_json = VALUES(raw_json)
                        """,
                record.getId(),
                record.getJobId(),
                record.getBatchId(),
                record.getTriggerType(),
                record.getRecordedBy(),
                record.getSupplier(),
                toJson(record.getVegetables()),
                record.getWeight(),
                Timestamp.from(record.getCapturedAt()),
                toJson(record.getRawJson()));
        return record;
    }

    public Optional<IntakeRecord> update(String id, IntakeRecord record) {
        if (findById(id).isEmpty()) {
            return Optional.empty();
        }
        record.setId(id);
        return Optional.of(save(record));
    }

    public List<IntakeRecord> findAll() {
        return jdbcTemplate.query(
                "SELECT * FROM intake_records ORDER BY captured_at DESC, updated_at DESC",
                rowMapper
        );
    }

    public Optional<IntakeRecord> findById(String id) {
        List<IntakeRecord> records = jdbcTemplate.query(
                "SELECT * FROM intake_records WHERE id = ?",
                rowMapper,
                id
        );
        return records.stream().findFirst();
    }

    public boolean deleteById(String id) {
        return jdbcTemplate.update("DELETE FROM intake_records WHERE id = ?", id) > 0;
    }

    private IntakeRecord mapRow(ResultSet rs, int rowNum) throws SQLException {
        IntakeRecord record = new IntakeRecord();
        record.setId(rs.getString("id"));
        record.setJobId(rs.getString("job_id"));
        record.setBatchId(rs.getString("batch_id"));
        record.setTriggerType(rs.getString("trigger_type"));
        record.setRecordedBy(rs.getString("recorded_by"));
        record.setSupplier(rs.getString("supplier"));
        record.setVegetables(fromJson(rs.getString("vegetables"), new TypeReference<List<String>>() {
        }, new ArrayList<>()));
        }));
        double weight = rs.getDouble("weight");
        record.setWeight(rs.wasNull() ? null : weight);
        Timestamp capturedAt = rs.getTimestamp("captured_at");
        record.setCapturedAt(capturedAt == null ? Instant.now() : capturedAt.toInstant());
        record.setRawJson(fromJson(rs.getString("raw_json"), new TypeReference<Map<String, Object>>() {
        }, new LinkedHashMap<>()));
        return record;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("failed to serialize intake record json", e);
        }
    }

    private <T> T fromJson(String json, TypeReference<T> typeReference, T defaultValue) {
        try {
            if (json == null || json.isBlank()) {
                return defaultValue;
            }
            return objectMapper.readValue(json, typeReference);
        } catch (Exception e) {
            throw new IllegalArgumentException("failed to parse intake record json", e);
        }
    }
}
