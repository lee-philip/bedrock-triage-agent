package com.bedrock.triage;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseRequest;
import software.amazon.awssdk.services.bedrockruntime.model.ConverseResponse;
import software.amazon.awssdk.services.bedrockruntime.model.ContentBlock;
import software.amazon.awssdk.services.bedrockruntime.model.SystemContentBlock;
import software.amazon.awssdk.services.bedrockruntime.model.Message;

import java.util.List;

@Component
public class BedrockTriageService implements BedrockClient {

    private final BedrockRuntimeClient client;
    private final String modelId;
    private final ObjectMapper objectMapper;

    private static final String SYSTEM_PROMPT = """
            You are a trade settlement exception classifier. Given an exception description,
            classify it into one of these categories and return JSON:

            Categories: missing_counterparty, valuation_mismatch, failed_settlement_instruction,
            corporate_action_adjustment, missing_security_master_data, fx_rate_discrepancy,
            failed_position_update, missing_contract_data, failed_payment_instruction,
            failed_tax_calculation, missing_isin, missing_settlement_location,
            failed_position_confirmation, failed_reconciliation, missing_trade_capture_data

            Return exactly this JSON format:
            {"category":"<category>","confidence":<0-1>,"reason":"<brief reason>"}
            """;

    public BedrockTriageService(BedrockRuntimeClient client, String modelId) {
        this.client = client;
        this.modelId = modelId;
        this.objectMapper = new ObjectMapper();
    }

    @Override
    public TriageResponse classify(String exceptionText) {
        SystemContentBlock systemBlock = SystemContentBlock.builder()
                .text(SYSTEM_PROMPT)
                .build();

        Message userMessage = Message.builder()
                .role("user")
                .content(ContentBlock.builder().text(exceptionText).build())
                .build();

        ConverseRequest request = ConverseRequest.builder()
                .modelId(modelId)
                .system(systemBlock)
                .messages(userMessage)
                .inferenceConfig(cfg -> cfg.temperature(0.1f))
                .build();

        ConverseResponse response = client.converse(request);

        String modelOutput = response.output().message().content().get(0).text();
        return parseResponse(modelOutput);
    }

    private TriageResponse parseResponse(String modelOutput) {
        try {
            JsonNode json = objectMapper.readTree(modelOutput);
            return new TriageResponse(
                    json.get("category").asText(),
                    json.get("confidence").asDouble(),
                    json.get("reason").asText()
            );
        } catch (Exception e) {
            throw new RuntimeException("Failed to parse model response: " + modelOutput, e);
        }
    }
}
