package com.bedrock.triage;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/triage")
public class TriageController {

    private final BedrockClient bedrockClient;

    public TriageController(BedrockClient bedrockClient) {
        this.bedrockClient = bedrockClient;
    }

    @PostMapping("/classify")
    public TriageResponse classify(@RequestBody TriageRequest request) {
        return bedrockClient.classify(request.exception());
    }
}
