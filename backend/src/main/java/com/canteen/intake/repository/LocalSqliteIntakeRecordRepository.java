package com.canteen.intake.repository;

import com.canteen.intake.model.IntakeRecord;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Repository;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@Repository
public class LocalSqliteIntakeRecordRepository {
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final String sqlitePath;
    private final long sessionStartedAt = System.currentTimeMillis();

    public LocalSqliteIntakeRecordRepository(
            @Value("${local.sqlite.path:data/local-intake.db}") String sqlitePath
    ) {
        this.sqlitePath = sqlitePath;
    }

    @PostConstruct
    public void initializeSchema() {
        try {
            Path dbPath = Path.of(sqlitePath);
            Path parent = dbPath.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            try (Connection connection = openConnection(); Statement statement = connection.createStatement()) {
                statement.executeUpdate("""
                        CREATE TABLE IF NOT EXISTS local_intake_records (
                          id TEXT PRIMARY KEY,
                          job_id TEXT,
                          batch_id TEXT NOT NULL,
                          trigger_type TEXT,
                          recorded_by TEXT,
                          supplier TEXT,
                          vegetables TEXT,
                          weight REAL,
                          storage_date TEXT,
                          captured_at TEXT,
                          raw_json TEXT,
                          created_at_millis INTEGER NOT NULL,
                          updated_at_millis INTEGER NOT NULL
                        )
                        """);
            }
        } catch (Exception exc) {
            throw new IllegalStateException("Failed to initialize local SQLite database: " + sqlitePath, exc);
        }
    }

    public IntakeRecord save(IntakeRecord record) {
        if (record.getId() == null || record.getId().isBlank()) {
            record.setId(UUID.randomUUID().toString());
        }
        if (record.getStorageDate() == null || record.getStorageDate().isBlank()) {
            record.setStorageDate(LocalDate.now().toString());
        }
        long now = System.currentTimeMillis();
        try (Connection connection = openConnection();
             PreparedStatement statement = connection.prepareStatement("""
                     INSERT INTO local_intake_records
                       (id, job_id, batch_id, trigger_type, recorded_by, supplier, vegetables, weight,
                        storage_date, captured_at, raw_json, created_at_millis, updated_at_millis)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT(id) DO UPDATE SET
                       job_id = excluded.job_id,
                       batch_id = excluded.batch_id,
                       trigger_type = excluded.trigger_type,
                       recorded_by = excluded.recorded_by,
                       supplier = excluded.supplier,
                       vegetables = excluded.vegetables,
                       weight = excluded.weight,
                       storage_date = excluded.storage_date,
                       captured_at = excluded.captured_at,
                       raw_json = excluded.raw_json,
                       updated_at_millis = excluded.updated_at_millis
                     """)) {
            bindRecord(statement, record, now);
            statement.executeUpdate();
            return record;
        } catch (SQLException exc) {
            throw new IllegalStateException("Failed to save local SQLite intake record", exc);
        }
    }

    public Optional<IntakeRecord> update(String id, IntakeRecord record) {
        if (findById(id).isEmpty()) {
            return Optional.empty();
        }
        record.setId(id);
        return Optional.of(save(record));
    }

    public List<IntakeRecord> findSessionRecords() {
        return query("SELECT * FROM local_intake_records WHERE created_at_millis >= ? ORDER BY created_at_millis DESC", sessionStartedAt);
    }

    public List<IntakeRecord> findAll() {
        return query("SELECT * FROM local_intake_records ORDER BY created_at_millis DESC");
    }

    public Optional<IntakeRecord> findById(String id) {
        List<IntakeRecord> records = query("SELECT * FROM local_intake_records WHERE id = ?", id);
        return records.stream().findFirst();
    }

    public boolean deleteById(String id) {
        try (Connection connection = openConnection();
             PreparedStatement statement = connection.prepareStatement("DELETE FROM local_intake_records WHERE id = ?")) {
            statement.setString(1, id);
            return statement.executeUpdate() > 0;
        } catch (SQLException exc) {
            throw new IllegalStateException("Failed to delete local SQLite intake record", exc);
        }
    }

    public int deleteByIds(List<String> ids) {
        if (ids == null || ids.isEmpty()) {
            return 0;
        }
        try (Connection connection = openConnection();
             PreparedStatement statement = connection.prepareStatement("DELETE FROM local_intake_records WHERE id = ?")) {
            for (String id : ids) {
                statement.setString(1, id);
                statement.addBatch();
            }
            int deleted = 0;
            for (int count : statement.executeBatch()) {
                if (count > 0) {
                    deleted += count;
                }
            }
            return deleted;
        } catch (SQLException exc) {
            throw new IllegalStateException("Failed to delete uploaded local SQLite intake records", exc);
        }
    }

    private Connection openConnection() throws SQLException {
        return DriverManager.getConnection("jdbc:sqlite:" + sqlitePath);
    }

    private void bindRecord(PreparedStatement statement, IntakeRecord record, long now) throws SQLException {
        statement.setString(1, record.getId());
        statement.setString(2, record.getJobId());
        statement.setString(3, record.getBatchId());
        statement.setString(4, record.getTriggerType());
        statement.setString(5, record.getRecordedBy());
        statement.setString(6, record.getSupplier());
        statement.setString(7, toJson(record.getVegetables()));
        if (record.getWeight() == null) {
            statement.setObject(8, null);
        } else {
            statement.setDouble(8, record.getWeight());
        }
        statement.setString(9, record.getStorageDate());
        statement.setString(10, record.getCapturedAt() == null ? Instant.now().toString() : record.getCapturedAt().toString());
        statement.setString(11, toJson(record.getRawJson()));
        statement.setLong(12, now);
        statement.setLong(13, now);
    }

    private List<IntakeRecord> query(String sql, Object... args) {
        try (Connection connection = openConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            for (int index = 0; index < args.length; index++) {
                statement.setObject(index + 1, args[index]);
            }
            try (ResultSet rs = statement.executeQuery()) {
                List<IntakeRecord> records = new ArrayList<>();
                while (rs.next()) {
                    records.add(mapRow(rs));
                }
                return records;
            }
        } catch (SQLException exc) {
            throw new IllegalStateException("Failed to query local SQLite intake records", exc);
        }
    }

    private IntakeRecord mapRow(ResultSet rs) throws SQLException {
        IntakeRecord record = new IntakeRecord();
        record.setId(rs.getString("id"));
        record.setJobId(rs.getString("job_id"));
        record.setBatchId(rs.getString("batch_id"));
        record.setTriggerType(rs.getString("trigger_type"));
        record.setRecordedBy(rs.getString("recorded_by"));
        record.setSupplier(rs.getString("supplier"));
        record.setVegetables(fromJson(rs.getString("vegetables"), new TypeReference<List<String>>() {
        }, new ArrayList<>()));
        Object weight = rs.getObject("weight");
        record.setWeight(weight == null ? null : rs.getDouble("weight"));
        record.setStorageDate(rs.getString("storage_date"));
        String capturedAt = rs.getString("captured_at");
        record.setCapturedAt(capturedAt == null || capturedAt.isBlank() ? Instant.now() : Instant.parse(capturedAt));
        record.setRawJson(fromJson(rs.getString("raw_json"), new TypeReference<Map<String, Object>>() {
        }, new LinkedHashMap<>()));
        return record;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("failed to serialize local intake record json", e);
        }
    }

    private <T> T fromJson(String json, TypeReference<T> typeReference, T defaultValue) {
        try {
            if (json == null || json.isBlank()) {
                return defaultValue;
            }
            return objectMapper.readValue(json, typeReference);
        } catch (Exception e) {
            throw new IllegalArgumentException("failed to parse local intake record json", e);
        }
    }
}
