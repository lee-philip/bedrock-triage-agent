package com.bedrock.triage;

public record TriageResponse(String category, double confidence, String reason) {}
