package com.canteen.intake.controller;

import com.canteen.intake.model.ApiResponse;
import com.canteen.intake.model.IntakeRecord;
import com.canteen.intake.repository.IntakeRecordRepository;
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
@RequestMapping("/api/intake-records")
public class IntakeRecordController {
    private final IntakeRecordRepository repository;

    public IntakeRecordController(IntakeRecordRepository repository) {
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

    @GetMapping("/{id}")
    public ApiResponse<IntakeRecord> get(@PathVariable String id) {
        return repository.findById(id)
                .map(ApiResponse::ok)
                .orElseGet(() -> ApiResponse.error("record not found"));
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
