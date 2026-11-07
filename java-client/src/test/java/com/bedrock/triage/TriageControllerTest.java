package com.bedrock.triage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class TriageControllerTest {

    private MockMvc mockMvc;
    private BedrockClient bedrockClient;

    @BeforeEach
    void setUp() {
        bedrockClient = mock(BedrockClient.class);
        TriageController controller = new TriageController(bedrockClient);
        mockMvc = MockMvcBuilders.standaloneSetup(controller).build();
    }

    @Test
    void classifyReturnsCategory() throws Exception {
        when(bedrockClient.classify(anyString())).thenReturn(
                new TriageResponse("missing_counterparty", 0.95, "No counterparty identified in the exception text"));

        String request = """
            {
              "exception": "Settlement failed due to missing counterparty information in the trade ticket."
            }
            """;

        mockMvc.perform(post("/triage/classify")
                .contentType(MediaType.APPLICATION_JSON)
                .content(request))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.category").value("missing_counterparty"))
                .andExpect(jsonPath("$.confidence").value(0.95))
                .andExpect(jsonPath("$.reason").exists());
    }

    @Test
    void classifyHandlesDifferentCategories() throws Exception {
        when(bedrockClient.classify(anyString())).thenReturn(
                new TriageResponse("valuation_mismatch", 0.88, "Price discrepancy detected"));

        String request = """
            {
              "exception": "The trade price $45.50 doesn't match the settlement price $45.75 from the exchange."
            }
            """;

        mockMvc.perform(post("/triage/classify")
                .contentType(MediaType.APPLICATION_JSON)
                .content(request))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.category").value("valuation_mismatch"));
    }
}
