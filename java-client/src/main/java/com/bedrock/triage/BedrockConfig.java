package com.bedrock.triage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient;

@Configuration
public class BedrockConfig {

    @Value("${aws.profile:default}")
    private String awsProfile;

    @Bean
    public BedrockRuntimeClient bedrockRuntimeClient() {
        ProfileCredentialsProvider credentialsProvider = ProfileCredentialsProvider.builder()
                .profileName(awsProfile)
                .build();
        credentialsProvider.resolveCredentials();

        return BedrockRuntimeClient.builder()
                .region(Region.US_EAST_1)
                .credentialsProvider(credentialsProvider)
                .build();
    }

    @Bean
    public String bedrockModelId(@Value("${bedrock.model-id:amazon.nova-micro-v1:0}") String modelId) {
        return modelId;
    }
}