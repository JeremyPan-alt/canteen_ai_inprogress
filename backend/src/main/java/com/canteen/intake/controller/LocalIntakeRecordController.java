package com.canteen.intake.controller;

import com.canteen.intake.model.ApiResponse;
import com.canteen.intake.model.IntakeRecord;
import com.canteen.intake.repository.LocalSqliteIntakeRecordRepository;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/local-intake-records")
public class LocalIntakeRecordController {
    private final LocalSqliteIntakeRecordRepository repository;

    public LocalIntakeRecordController(LocalSqliteIntakeRecordRepository repository) {
        this.repository = repository;
    }

    @PostMapping
    public ApiResponse<IntakeRecord> save(@RequestBody IntakeRecord record) {
        return ApiResponse.ok(repository.save(record));
    }

    @GetMapping
    public ApiResponse<List<IntakeRecord>> list() {
        return ApiResponse.ok(repository.findAll());
    }

    @GetMapping("/session")
    public ApiResponse<List<IntakeRecord>> sessionRecords() {
        return ApiResponse.ok(repository.findSessionRecords());
    }

    @PutMapping("/{id}")
    public ApiResponse<IntakeRecord> update(@PathVariable String id, @RequestBody IntakeRecord record) {
        return repository.update(id, record)
                .map(ApiResponse::ok)
                .orElseGet(() -> ApiResponse.error("record not found"));
    }

    @DeleteMapping("/{id}")
    public ApiResponse<Boolean> delete(@PathVariable String id) {
        return ApiResponse.ok(repository.deleteById(id));
    }
}
