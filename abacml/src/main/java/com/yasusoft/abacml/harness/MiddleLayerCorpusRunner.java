package com.yasusoft.abacml.harness;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.wso2.balana.finder.impl.FileBasedPolicyFinderModule;

import com.yasusoft.abacml.ABACML;

/**
 * Runner for the Middle Layer adapter, two modes:
 *
 * Correctness (Step 4/5A):
 *   MiddleLayerCorpusRunner <policyDir> <scenariosTsv> <outputJsonl> <corpusCommit> <adapterCommit>
 *
 * Benchmark (Step 5B):
 *   MiddleLayerCorpusRunner benchmark <policyDir> <scenariosTsv> <manifestConf> <rawOutputTsv> <summaryOutputJson>
 *
 * The policy directory system property is set before ABACML.Evaluate_ABAC_Decision
 * ever calls initBalana(), so this runner's own policy set (not the production
 * abacmlpolicy.xml) is what gets loaded -- Balana caches its configuration on
 * first use per JVM, so this must happen before the first evaluation.
 */
public class MiddleLayerCorpusRunner {

    public static void main(String[] args) throws Exception {
        if (args.length == 7 && "benchmark".equals(args[0])) {
            runBenchmark(args[1], args[2], args[3], args[4], args[5], args[6]);
            return;
        }
        if (args.length != 5) {
            System.err.println("usage: MiddleLayerCorpusRunner <policyDir> <scenariosTsv> <outputJsonl> <corpusCommit> <adapterCommit>");
            System.err.println("   or: MiddleLayerCorpusRunner benchmark <policyDir> <scenariosTsv> <manifestConf> <concurrency> <rawOutputTsv> <summaryOutputJson>");
            System.exit(2);
        }
        runCorrectness(args[0], args[1], args[2], args[3], args[4]);
    }

    private static final class WorkerResult {
        final List<Long> latencies = new ArrayList<Long>();
        final List<String> rawLines = new ArrayList<String>();
    }

    private static void runCorrectness(String policyDir, String scenariosTsv, String outputJsonl,
                                        String corpusCommit, String adapterCommit) throws IOException {
        System.setProperty(FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY, policyDir);

        String hostname = getHostname();
        List<String[]> rows = readTsv(scenariosTsv);
        Map<String, Integer> col = indexHeader(rows.get(0));

        int total = 0;
        int correct = 0;
        String runId = "run-" + System.currentTimeMillis();

        // Warm-up call: not counted toward correctness, but its wall time is
        // policy_load_ns -- Balana parses/loads the policy set lazily on
        // first use and caches it for the rest of this JVM's lifetime, so
        // this isolates that one-time cost from the per-scenario evaluation
        // timings below, which are all "hot" (policy already resident).
        long loadStart = System.nanoTime();
        evaluateRow(rows.get(1), col);
        long policyLoadNs = System.nanoTime() - loadStart;

        PrintWriter out = new PrintWriter(new FileWriter(outputJsonl));
        try {
            for (int r = 1; r < rows.size(); r++) {
                String[] row = rows.get(r);
                total++;
                String id = get(row, col, "id");
                String expected = get(row, col, "expected");

                String actual;
                String error = null;
                long evalStart = System.nanoTime();
                try {
                    actual = evaluateRow(row, col);
                } catch (Exception e) {
                    actual = null;
                    error = e.toString();
                }
                long evalNs = System.nanoTime() - evalStart;

                boolean isCorrect = actual != null && actual.equals(expected);
                if (isCorrect) {
                    correct++;
                }

                out.println(toJsonLine(runId, hostname, corpusCommit, adapterCommit, id, expected, actual, isCorrect, error,
                        policyLoadNs, evalNs));
            }
        } finally {
            out.close();
        }

        System.out.println("Middle Layer correctness: " + correct + "/" + total + " scenarios correct");
        System.exit(correct == total ? 0 : 1);
    }

    private static void runBenchmark(String policyDir, String scenariosTsv, String manifestConf,
                                      String concurrencyStr, String rawOutputTsv, String summaryOutputJson) throws Exception {
        System.setProperty(FileBasedPolicyFinderModule.POLICY_DIR_PROPERTY, policyDir);
        final int concurrency = Integer.parseInt(concurrencyStr);

        Map<String, String> manifest = readManifest(manifestConf);
        final int warmup = Integer.parseInt(manifest.get("warmup_iterations"));
        final int measured = Integer.parseInt(manifest.get("measured_iterations"));
        final int repetitions = Integer.parseInt(manifest.get("repetitions"));

        List<String[]> rows = readTsv(scenariosTsv);
        final Map<String, Integer> col = indexHeader(rows.get(0));
        final List<String[]> scenarioRows = rows.subList(1, rows.size());
        final int n = scenarioRows.size();

        // Single-threaded warm-up, priming Balana's cached policy before any
        // worker thread touches it -- avoids the first concurrent worker
        // paying (and skewing) the one-time load cost.
        for (int i = 0; i < warmup; i++) {
            try {
                evaluateRow(scenarioRows.get(i % n), col);
            } catch (Exception e) {
                // ignored during warm-up
            }
        }

        ExecutorService pool = Executors.newFixedThreadPool(concurrency);
        List<Long> allLatencies = new ArrayList<Long>();
        List<String> allRawLines = new ArrayList<String>();
        double totalWallSeconds = 0;

        try {
            for (int rep = 0; rep < repetitions; rep++) {
                List<Callable<WorkerResult>> tasks = new ArrayList<Callable<WorkerResult>>();
                for (int w = 0; w < concurrency; w++) {
                    final int workerId = w;
                    tasks.add(new Callable<WorkerResult>() {
                        public WorkerResult call() {
                            WorkerResult r = new WorkerResult();
                            for (int i = 0; i < measured; i++) {
                                String[] row = scenarioRows.get(i % n);
                                long start = System.nanoTime();
                                try {
                                    evaluateRow(row, col);
                                } catch (Exception e) {
                                    // still record latency of the failed call
                                }
                                long latencyNs = System.nanoTime() - start;
                                r.latencies.add(Long.valueOf(latencyNs));
                                r.rawLines.add(workerId + "\t" + i + "\t" + get(row, col, "id") + "\t" + latencyNs);
                            }
                            return r;
                        }
                    });
                }
                long repStart = System.nanoTime();
                List<Future<WorkerResult>> futures = pool.invokeAll(tasks);
                totalWallSeconds += (System.nanoTime() - repStart) / 1e9;
                for (Future<WorkerResult> f : futures) {
                    WorkerResult r = f.get();
                    allLatencies.addAll(r.latencies);
                    allRawLines.addAll(r.rawLines);
                }
            }
        } finally {
            pool.shutdown();
        }

        PrintWriter rawOut = new PrintWriter(new FileWriter(rawOutputTsv));
        try {
            rawOut.println("worker\titeration\tscenario_id\tlatency_ns");
            for (String line : allRawLines) {
                rawOut.println(line);
            }
        } finally {
            rawOut.close();
        }

        double aggregateThroughput = allLatencies.size() / totalWallSeconds;
        writeSummary(summaryOutputJson, "middle-layer", allLatencies, warmup, measured, repetitions, concurrency, aggregateThroughput);
        System.out.println("Middle Layer benchmark (concurrency=" + concurrency + "): " + allLatencies.size()
                + " measured calls, aggregate throughput " + aggregateThroughput + "/s, summary written to " + summaryOutputJson);
    }

    private static String evaluateRow(String[] row, Map<String, Integer> col) {
        return ABACML.Evaluate_ABAC_Decision(
                get(row, col, "subject_id"), emptyToNull(get(row, col, "subject_role")),
                emptyToNull(get(row, col, "subject_department")), parseIntOrNull(get(row, col, "subject_clearance")),
                get(row, col, "resource_id"), emptyToNull(get(row, col, "resource_owner")),
                emptyToNull(get(row, col, "resource_department")), parseIntOrNull(get(row, col, "resource_classification")),
                get(row, col, "action"), emptyToNull(get(row, col, "env_network")), parseIntOrNull(get(row, col, "env_hour")));
    }

    private static String getHostname() {
        try {
            return java.net.InetAddress.getLocalHost().getHostName();
        } catch (Exception e) {
            return "unknown";
        }
    }

    private static Map<String, Integer> indexHeader(String[] header) {
        Map<String, Integer> col = new HashMap<String, Integer>();
        for (int i = 0; i < header.length; i++) {
            col.put(header[i], Integer.valueOf(i));
        }
        return col;
    }

    private static Map<String, String> readManifest(String path) throws IOException {
        Map<String, String> m = new HashMap<String, String>();
        BufferedReader br = new BufferedReader(new FileReader(path));
        try {
            String line;
            while ((line = br.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) {
                    continue;
                }
                int eq = line.indexOf('=');
                if (eq < 0) {
                    continue;
                }
                m.put(line.substring(0, eq).trim(), line.substring(eq + 1).trim());
            }
        } finally {
            br.close();
        }
        return m;
    }

    private static long readPeakRssKb() {
        try {
            BufferedReader br = new BufferedReader(new FileReader("/proc/self/status"));
            try {
                String line;
                while ((line = br.readLine()) != null) {
                    if (line.startsWith("VmHWM:")) {
                        String[] parts = line.trim().split("\\s+");
                        return Long.parseLong(parts[1]);
                    }
                }
            } finally {
                br.close();
            }
        } catch (Exception e) {
            // not on Linux, or /proc unavailable
        }
        return -1;
    }

    private static void writeSummary(String path, String engine, List<Long> latenciesNs,
                                      int warmup, int measured, int repetitions,
                                      int concurrency, double aggregateThroughputPerSec) throws IOException {
        List<Long> sorted = new ArrayList<Long>(latenciesNs);
        Collections.sort(sorted);
        int n = sorted.size();

        double sum = 0;
        for (Long v : sorted) {
            sum += v.doubleValue();
        }
        double mean = sum / n;
        double variance = 0;
        for (Long v : sorted) {
            double d = v.doubleValue() - mean;
            variance += d * d;
        }
        double stddev = Math.sqrt(variance / n);

        long min = sorted.get(0).longValue();
        long max = sorted.get(n - 1).longValue();
        long median = percentile(sorted, 0.50);
        long p95 = percentile(sorted, 0.95);
        long p99 = percentile(sorted, 0.99);
        long peakRssKb = readPeakRssKb();

        PrintWriter out = new PrintWriter(new FileWriter(path));
        try {
            out.println("{");
            out.println("  \"engine\": \"" + engine + "\",");
            out.println("  \"concurrency\": " + concurrency + ",");
            out.println("  \"warmup_iterations\": " + warmup + ",");
            out.println("  \"measured_iterations_per_worker\": " + measured + ",");
            out.println("  \"repetitions\": " + repetitions + ",");
            out.println("  \"sample_count\": " + n + ",");
            out.println("  \"latency_ns\": {");
            out.println("    \"min\": " + min + ",");
            out.println("    \"median\": " + median + ",");
            out.println("    \"mean\": " + Math.round(mean) + ",");
            out.println("    \"p95\": " + p95 + ",");
            out.println("    \"p99\": " + p99 + ",");
            out.println("    \"max\": " + max + ",");
            out.println("    \"stddev\": " + Math.round(stddev));
            out.println("  },");
            out.println("  \"aggregate_throughput_per_sec\": " + aggregateThroughputPerSec + ",");
            out.println("  \"peak_rss_kb\": " + peakRssKb);
            out.println("}");
        } finally {
            out.close();
        }
    }

    private static long percentile(List<Long> sorted, double p) {
        int idx = (int) Math.ceil(p * sorted.size()) - 1;
        if (idx < 0) idx = 0;
        if (idx >= sorted.size()) idx = sorted.size() - 1;
        return sorted.get(idx).longValue();
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
                                      String scenarioId, String expected, String actual, boolean correct, String error,
                                      long policyLoadNs, long evalNs) {
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
        sb.append("\"policy_load_ns\":").append(policyLoadNs).append(",");
        sb.append("\"translation_ns\":null,");
        sb.append("\"evaluation_ns\":").append(evalNs).append(",");
        sb.append("\"total_ns\":").append(evalNs).append(",");
        sb.append("\"error\":").append(jsonString(error)).append(",");
        sb.append("\"notes\":null");
        sb.append("}");
        return sb.toString();
    }
}
