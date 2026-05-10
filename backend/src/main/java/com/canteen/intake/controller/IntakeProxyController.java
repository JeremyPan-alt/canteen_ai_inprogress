package com.canteen.intake.controller;

import com.canteen.intake.model.ApiResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import java.util.Map;

@RestController
@RequestMapping("/api/intake")
public class IntakeProxyController {
    private final RestClient restClient;
    private final String flaskBaseUrl;

    public IntakeProxyController(
            RestClient restClient,
            @Value("${flask.base-url:http://localhost:5000}") String flaskBaseUrl
    ) {
        this.restClient = restClient;
        this.flaskBaseUrl = flaskBaseUrl;
    }

    @PostMapping("/capture/manual")
    public ApiResponse<String> manualCapture(@RequestBody Map<String, Object> payload) {
        return ApiResponse.ok(postToFlask("/api/capture/manual", payload));
    }

    @PostMapping("/capture/intrusion")
    public ApiResponse<String> intrusionCapture(@RequestBody Map<String, Object> payload) {
        return ApiResponse.ok(postToFlask("/api/capture/intrusion", payload));
    }

    @GetMapping("/cameras/status")
    public Map<String, Object> cameraStatus() {
        return restClient.get()
                .uri(flaskBaseUrl + "/api/cameras/status")
                .retrieve()
                .body(new ParameterizedTypeReference<>() {
                });
    }

    private String postToFlask(String path, Map<String, Object> payload) {
        return restClient.post()
                .uri(flaskBaseUrl + path)
                .contentType(MediaType.APPLICATION_JSON)
                .body(payload)
                .retrieve()
                .body(String.class);
    }
}
