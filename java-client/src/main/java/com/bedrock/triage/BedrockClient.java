package com.bedrock.triage;

import java.util.List;
import java.util.Map;

public interface BedrockClient {
    TriageResponse classify(String exceptionText);
}
