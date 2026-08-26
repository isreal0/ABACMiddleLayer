package com.yasusoft.abacml.harness;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.wso2.balana.finder.impl.FileBasedPolicyFinderModule;

import com.yasusoft.abacml.ABACML;

/**
 * Correctness-only runner for the Middle Layer adapter (Step 4/5A). Reads a
 * TSV generated from corpus/canonical/scenarios.json by
 * benchmark/scripts/generate-corpus.py, evaluates each scenario through
 * ABACML.Evaluate_ABAC_Decision against the reference policy, and writes one
 * normalized JSON line per scenario matching benchmark/schemas/result.schema.json.
 *
 * Usage: MiddleLayerCorpusRunner <policyDir> <scenariosTsv> <outputJsonl> <corpusCommit> <adapterCommit>
 *
 * The policy directory system property is set before ABACML.Evaluate_ABAC_Decision
 * ever calls initBalana(), so this runner's own policy set (not the production
 * abacmlpolicy.xml) is what gets loaded -- Balana caches its configuration on
 * first use per JVM, so this must happen before the first evaluation.
 */
public class MiddleLayerCorpusRunner {

    public static void main(String[] args) throws IOException {
        if (args.length != 5) {
            System.err.println("usage: MiddleLayerCorpusRunner <policyDir> <scenariosTsv> <outputJsonl> <corpusCommit> <adapterCommit>");
            System.exit(2);
        }
        String policyDir = args[0];
        String scenariosTsv = args[1];
        String outputJsonl = args[2];
        String corpusCommit = args[3];
        String adapterCommit = args[4];

        System.setProperty(FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY, policyDir);

        String hostname;
        try {
            hostname = java.net.InetAddress.getLocalHost().getHostName();
        } catch (Exception e) {
            hostname = "unknown";
        }

        List<String[]> rows = readTsv(scenariosTsv);
        String[] header = rows.get(0);
        Map<String, Integer> col = new HashMap<String, Integer>();
        for (int i = 0; i < header.length; i++) {
            col.put(header[i], Integer.valueOf(i));
        }

        int total = 0;
        int correct = 0;
        String runId = "run-" + System.currentTimeMillis();

        PrintWriter out = new PrintWriter(new FileWriter(outputJsonl));
        try {
            for (int r = 1; r < rows.size(); r++) {
                String[] row = rows.get(r);
                total++;

                String id = get(row, col, "id");
                String subjectId = get(row, col, "subject_id");
                String subjectRole = emptyToNull(get(row, col, "subject_role"));
                String subjectDept = emptyToNull(get(row, col, "subject_department"));
                Integer subjectClearance = parseIntOrNull(get(row, col, "subject_clearance"));
                String resourceId = get(row, col, "resource_id");
                String resourceOwner = emptyToNull(get(row, col, "resource_owner"));
                String resourceDept = emptyToNull(get(row, col, "resource_department"));
                Integer resourceClassification = parseIntOrNull(get(row, col, "resource_classification"));
                String action = get(row, col, "action");
                String envNetwork = emptyToNull(get(row, col, "env_network"));
                Integer envHour = parseIntOrNull(get(row, col, "env_hour"));
                String expected = get(row, col, "expected");

                String actual;
                String error = null;
                try {
                    actual = ABACML.Evaluate_ABAC_Decision(
                            subjectId, subjectRole, subjectDept, subjectClearance,
                            resourceId, resourceOwner, resourceDept, resourceClassification,
                            action, envNetwork, envHour);
                } catch (Exception e) {
                    actual = null;
                    error = e.toString();
                }

                boolean isCorrect = actual != null && actual.equals(expected);
                if (isCorrect) {
                    correct++;
                }

                out.println(toJsonLine(runId, hostname, corpusCommit, adapterCommit, id, expected, actual, isCorrect, error));
            }
        } finally {
            out.close();
        }

        System.out.println("Middle Layer correctness: " + correct + "/" + total + " scenarios correct");
        System.exit(correct == total ? 0 : 1);
    }

    private static String get(String[] row, Map<String, Integer> col, String name) {
        Integer idx = col.get(name);
        if (idx == null || idx >= row.length) {
            return "";
        }
        return row[idx];
    }

    private static String emptyToNull(String s) {
        return (s == null || s.isEmpty()) ? null : s;
    }

    private static Integer parseIntOrNull(String s) {
        if (s == null || s.isEmpty()) {
            return null;
        }
        return Integer.valueOf(s);
    }

    private static List<String[]> readTsv(String path) throws IOException {
        List<String[]> rows = new ArrayList<String[]>();
        BufferedReader br = new BufferedReader(new FileReader(path));
        try {
            String line;
            while ((line = br.readLine()) != null) {
                if (line.length() == 0) {
                    continue;
                }
                rows.add(line.split("\t", -1));
            }
        } finally {
            br.close();
        }
        return rows;
    }

    private static String jsonString(String s) {
        if (s == null) {
            return "null";
        }
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static String toJsonLine(String runId, String hostname, String corpusCommit, String adapterCommit,
                                      String scenarioId, String expected, String actual, boolean correct, String error) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"run_id\":").append(jsonString(runId)).append(",");
        sb.append("\"engine\":\"middle-layer\",");
        sb.append("\"engine_version\":\"balana-1.1.12\",");
        sb.append("\"hostname\":").append(jsonString(hostname)).append(",");
        sb.append("\"corpus_commit\":").append(jsonString(corpusCommit)).append(",");
        sb.append("\"adapter_commit\":").append(jsonString(adapterCommit)).append(",");
        sb.append("\"scenario_id\":").append(jsonString(scenarioId)).append(",");
        sb.append("\"expected\":").append(jsonString(expected)).append(",");
        sb.append("\"actual\":").append(jsonString(actual)).append(",");
        sb.append("\"supported\":true,");
        sb.append("\"correct\":").append(correct).append(",");
        sb.append("\"policy_load_ns\":null,");
        sb.append("\"translation_ns\":null,");
        sb.append("\"evaluation_ns\":null,");
        sb.append("\"total_ns\":null,");
        sb.append("\"error\":").append(jsonString(error)).append(",");
        sb.append("\"notes\":null");
        sb.append("}");
        return sb.toString();
    }
}
