package com.canteen.intake.repository;

import com.canteen.intake.model.IntakeRecord;
import org.springframework.stereotype.Repository;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Repository
public class IntakeRecordRepository {
    private final ConcurrentMap<String, IntakeRecord> records = new ConcurrentHashMap<>();

    public IntakeRecord save(IntakeRecord record) {
        records.put(record.getId(), record);
        return record;
    }

    public List<IntakeRecord> findAll() {
        return records.values().stream()
                .sorted(Comparator.comparing(IntakeRecord::getCapturedAt).reversed())
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
    }

    public Optional<IntakeRecord> findById(String id) {
        return Optional.ofNullable(records.get(id));
    }

    public boolean deleteById(String id) {
        return records.remove(id) != null;
    }
}
